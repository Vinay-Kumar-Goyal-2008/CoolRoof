"""Unit tests: alerts hub, advisories, incidents, signals, rules, adapters (NWP, solar), auth, metrics."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from packages.adapters.blobstore import LocalBlobStore
from packages.adapters.docstore import SQLiteDocStore
from packages.adapters.notifier import FileNotifier
from packages.adapters.nwp_source import OpenMeteoNWP
from packages.adapters.tts import AudioResult, LanguageRoutedTTS, SilentWavStub, TTSProvider
from packages.core import metrics
from packages.core.enums import Language, Role
from packages.core.errors import (
    AuthenticationError,
    ConflictError,
    InputValidationError,
    UpstreamError,
)
from packages.core.params import ParamRegistry, load_params
from packages.core.timeutil import set_clock
from packages.services.m18_advisory import AdvisoryService, load_advice
from packages.services.m37_alerts import AlertHub
from packages.services.signals import OfficialWarnings, current_signals
from packages.services.solar_fallback import monthly_kwh_per_kwp, nasa_power_monthly
from packages.services.suryacheck import SolarSource

RULES = Path(__file__).resolve().parents[3] / "rules"
NOW = datetime(2026, 5, 10, 12, 0, tzinfo=UTC)


@pytest.fixture
def params() -> ParamRegistry:
    return load_params()


@pytest.fixture
def stack(tmp_path: Path, params: ParamRegistry) -> tuple[SQLiteDocStore, FileNotifier, AlertHub]:
    docs = SQLiteDocStore(tmp_path / "db.sqlite")
    notifier = FileNotifier(tmp_path / "outbox")
    return docs, notifier, AlertHub(docs, notifier, params)


def _alert(hub: AlertHub, **kw: object) -> dict:  # type: ignore[type-arg]
    base: dict = dict(  # type: ignore[type-arg]
        alert_type="satellite_fire",
        city="c",
        audience="staff",
        severity="low",
        texts={"en": "x", "hi": "y"},
        valid_until=(NOW + timedelta(hours=5)).isoformat(),
        ward_id="W1",
        dedupe_key="k",
        auto_info=True,
    )
    base.update(kw)
    return hub.raise_alert(**base)


# ------------------------------------------------------------------------------- M37
def test_dedupe_is_idempotent_and_one_publish_per_language(stack: tuple) -> None:  # type: ignore[type-arg]
    set_clock(lambda: NOW)
    _, notifier, hub = stack
    a = _alert(hub)
    b = _alert(hub)
    assert a["alert_id"] == b["alert_id"] and a["status"] == "sent"
    msgs = notifier.read_outbox()
    assert len(msgs) == 2 and {m["attributes"]["language"] for m in msgs} == {"en", "hi"}


def test_public_alerts_need_approval_and_cannot_be_auto(stack: tuple) -> None:  # type: ignore[type-arg]
    set_clock(lambda: NOW)
    _, notifier, hub = stack
    with pytest.raises(InputValidationError):
        _alert(hub, audience="public", auto_info=True)
    draft = _alert(hub, audience="public", auto_info=False, dedupe_key="p")
    assert draft["status"] == "draft" and notifier.read_outbox() == []
    with pytest.raises(ConflictError):
        hub.send("c", draft["alert_id"])  # unapproved: never sent
    hub.approve("c", draft["alert_id"], "asha")
    assert hub.send("c", draft["alert_id"])["status"] == "sent"


def test_expired_alerts_are_never_sent_or_shown(stack: tuple) -> None:  # type: ignore[type-arg]
    set_clock(lambda: NOW)
    _, notifier, hub = stack
    a = _alert(hub, audience="staff", auto_info=False, dedupe_key="e")
    hub.approve("c", a["alert_id"], "asha")
    set_clock(lambda: NOW + timedelta(days=1))
    assert hub.send("c", a["alert_id"])["status"] == "expired" and notifier.read_outbox() == []
    assert hub.active("c", include_staff=True) == []


def test_rate_limit_suppresses_but_high_severity_passes(
    stack: tuple, params: ParamRegistry
) -> None:  # type: ignore[type-arg]
    set_clock(lambda: NOW)
    _, _, hub = stack
    limit = int(params.require("P-ALERT-RATE")["per_ward_per_day"])
    states = [_alert(hub, dedupe_key=f"k{i}")["status"] for i in range(limit + 1)]
    assert states[:limit] == ["sent"] * limit and states[-1] == "suppressed"
    assert _alert(hub, dedupe_key="urgent", severity="high")["status"] == "sent"


def test_subscription_filter_matches_ward_and_language(stack: tuple) -> None:  # type: ignore[type-arg]
    set_clock(lambda: NOW)
    _, _, hub = stack
    s = hub.subscribe("c", channel="email", address="a@b.org", ward_ids=["W1"], languages=["hi"])
    doc = {"ward_id": "W1"}
    assert hub.matching_subscriptions("c", doc, "hi") == [s["subscription_id"]]
    assert hub.matching_subscriptions("c", doc, "en") == []
    assert hub.matching_subscriptions("c", {"ward_id": "W2"}, "hi") == []
    with pytest.raises(InputValidationError):
        hub.subscribe("c", channel="sms", address="not-a-number", ward_ids=None, languages=["en"])


# ------------------------------------------------------------------------------- M18+19
class _Failing(TTSProvider):
    name = "failing"

    def synthesize(self, text: str, lang: Language) -> AudioResult:
        raise UpstreamError("down")


def _service(
    tmp_path: Path, stack: tuple, tts: LanguageRoutedTTS | None = None, **kw: object
) -> AdvisoryService:  # type: ignore[type-arg]
    docs, _, hub = stack
    return AdvisoryService(
        docs,
        LocalBlobStore(tmp_path / "blobs"),
        tts or LanguageRoutedTTS(SilentWavStub(), SilentWavStub()),
        hub,
        load_advice(RULES, "v1"),
        **kw,  # type: ignore[arg-type]
    )


def _compose(svc: AdvisoryService, **kw: object) -> tuple[dict, dict]:  # type: ignore[type-arg]
    args: dict = dict(  # type: ignore[type-arg]
        advisory_type="heatwave_relay",
        ward_name={"en": "Ward 1", "hi": "वार्ड 1"},
        valid_until=(NOW + timedelta(days=2)).isoformat(),
        level="orange",
        issued_by="IMD",
    )
    args.update(kw)
    return svc.compose(**args)


def test_composed_text_uses_only_whitelisted_advice_and_grounded_numbers(
    tmp_path: Path, stack: tuple
) -> None:  # type: ignore[type-arg]
    from packages.core.grounding import check_grounding

    set_clock(lambda: NOW)
    svc = _service(tmp_path, stack)
    texts, slots = _compose(svc)
    advice = load_advice(RULES, "v1")["lines"]
    for k in slots["advice_keys"]:
        assert advice[k]["en"] in texts["en"] and advice[k]["hi"] in texts["hi"]
    assert 1 <= len(slots["advice_keys"]) <= 4
    assert check_grounding(
        texts["en"], slots, allowed=[slots["day"], slots["month"], slots["year"]]
    ).grounded


def test_rewriter_is_rejected_when_it_invents_numbers_or_drops_the_label(
    tmp_path: Path, stack: tuple
) -> None:  # type: ignore[type-arg]
    set_clock(lambda: NOW)
    plain, _ = _compose(_service(tmp_path, stack))
    liar = _service(
        tmp_path, stack, rewriter=lambda t, lang: t + " Temperatures will reach 51 degrees."
    )
    assert _compose(liar)[0]["en"] == plain["en"]
    good = _service(
        tmp_path, stack, rewriter=lambda t, lang: t.replace("Heat advisory", "Heat notice")
    )
    assert _compose(good)[0]["en"].startswith("Heat notice")
    unlabeled = _service(
        tmp_path,
        stack,
        rewriter=lambda t, lang: t.replace("forecast signal, not an official warning", "alert"),
    )
    forecast = dict(advisory_type="heatdome_forecast", level=None, issued_by=None, risk="high")
    assert "forecast signal, not an official warning" in _compose(unlabeled, **forecast)[0]["en"]


def test_tts_failure_falls_back_to_text_and_cap_is_enforced(tmp_path: Path, stack: tuple) -> None:  # type: ignore[type-arg]
    set_clock(lambda: NOW)
    svc = _service(
        tmp_path, stack, tts=LanguageRoutedTTS(_Failing(), SilentWavStub()), tts_daily_cap=1
    )
    texts, slots = _compose(svc)
    adv = svc.create(
        city="c",
        ward_id=None,
        advisory_type="heatwave_relay",
        texts=texts,
        slots=slots,
        valid_until=(NOW + timedelta(days=2)).isoformat(),
        created_by="asha",
    )
    svc.approve("c", adv["advisory_id"], "asha", "planner")
    assert svc.audio("c", adv["advisory_id"], "en")["audio"] is None  # provider down → text only
    assert svc.audio("c", adv["advisory_id"], "hi")["audio"]  # Hindi uses its own provider
    from packages.core.errors import ThrottledError

    texts2, slots2 = _compose(svc, level="red")
    other = svc.create(
        city="c",
        ward_id=None,
        advisory_type="heatwave_relay",
        texts=texts2,
        slots=slots2,
        valid_until=(NOW + timedelta(days=2)).isoformat(),
        created_by="asha",
    )
    svc.approve("c", other["advisory_id"], "asha", "planner")
    with pytest.raises(ThrottledError):
        svc.audio("c", other["advisory_id"], "hi")


def test_two_person_rule_and_role_gate(tmp_path: Path, stack: tuple) -> None:  # type: ignore[type-arg]
    from packages.core.errors import ForbiddenError

    set_clock(lambda: NOW)
    svc = _service(tmp_path, stack, two_person_rule=True)
    texts, slots = _compose(svc)
    adv = svc.create(
        city="c",
        ward_id=None,
        advisory_type="heatwave_relay",
        texts=texts,
        slots=slots,
        valid_until=(NOW + timedelta(days=2)).isoformat(),
        created_by="asha",
    )
    with pytest.raises(ForbiddenError):
        svc.approve("c", adv["advisory_id"], "bob", "viewer")
    with pytest.raises(ConflictError):
        svc.approve("c", adv["advisory_id"], "asha", "planner")
    assert svc.approve("c", adv["advisory_id"], "ravi", "planner")["status"] == "approved"


# ------------------------------------------------------------------------------- signals + rules
def test_official_warning_precedence_and_validity(stack: tuple) -> None:  # type: ignore[type-arg]
    set_clock(lambda: NOW)
    docs, _, _ = stack
    ow = OfficialWarnings(docs)
    ow.add(
        "c",
        level="yellow",
        issued_by="IMD",
        valid_from=(NOW - timedelta(hours=1)).isoformat(),
        valid_until=(NOW + timedelta(days=1)).isoformat(),
        text="a",
    )
    ow.add(
        "c",
        level="red",
        issued_by="IMD",
        valid_from=(NOW - timedelta(hours=1)).isoformat(),
        valid_until=(NOW + timedelta(days=1)).isoformat(),
        text="b",
    )
    ow.add(
        "c",
        level="red",
        issued_by="IMD",
        valid_from=(NOW + timedelta(days=5)).isoformat(),
        valid_until=(NOW + timedelta(days=6)).isoformat(),
        text="future",
    )
    active = ow.active("c")
    assert active and active["level"] == "red" and active["text"] == "b"
    assert current_signals(docs, "c", {"risk": "none"}).active  # official warning alone activates
    assert not current_signals(docs, "other", {"risk": "watch"}).active
    assert current_signals(docs, "other", {"risk": "elevated"}).active
    with pytest.raises(InputValidationError):
        ow.add(
            "c",
            level="red",
            issued_by="IMD",
            valid_from=NOW.isoformat(),
            valid_until=NOW.isoformat(),
            text="z",
        )


def test_rules_each_have_evidence_and_new_rules_exist() -> None:
    from packages.services.m17_reco import load_rules

    rules = load_rules(RULES, "v1")
    ids = {r["id"] for r in rules.rules}
    assert {"R-RD-01", "R-FR-01", "R-DG-01"} <= ids
    assert all(r["evidence_ref"] for r in rules.rules)
    assert all(r["text"]["en"] and r["text"]["hi"] for r in rules.rules)


# ------------------------------------------------------------------------------- adapters
def _mock(handler) -> httpx.Client:  # type: ignore[no-untyped-def]
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_open_meteo_builds_payload_and_reports_temperature_only() -> None:
    days = [f"2026-05-{d:02d}" for d in range(11, 14)]

    def handler(req: httpx.Request) -> httpx.Response:
        if "ensemble" in req.url.host:
            return httpx.Response(
                200,
                json={
                    "daily": {
                        "time": days,
                        "temperature_2m_max_member01": [44.0, 45.0, 46.0],
                        "temperature_2m_max_member02": [43.0, 44.0, 45.0],
                    }
                },
            )
        years = [f"{y}-05-{d:02d}" for y in range(1991, 2021) for d in range(1, 31)]
        return httpx.Response(
            200, json={"daily": {"time": years, "temperature_2m_max": [38.0] * len(years)}}
        )

    payload = OpenMeteoNWP(client=_mock(handler)).fetch(18.5, 73.8, 5.0, 3)
    assert payload and len(payload["members"]) == 2 and payload["z500_available"] is False
    assert payload["members"][0]["z500_box_mean_m"] is None
    assert payload["climatology"][0]["tmax_mean_c"] == 38.0


def test_open_meteo_down_returns_none_not_old_data() -> None:
    client = _mock(lambda req: httpx.Response(503))
    assert OpenMeteoNWP(client=client).fetch(18.5, 73.8, 5.0, 3) is None


def test_nasa_power_and_pvlib_fallback_gives_a_plausible_yield() -> None:
    body = {
        "properties": {
            "parameter": {
                "ALLSKY_SFC_SW_DWN": dict(
                    zip(
                        [
                            "JAN",
                            "FEB",
                            "MAR",
                            "APR",
                            "MAY",
                            "JUN",
                            "JUL",
                            "AUG",
                            "SEP",
                            "OCT",
                            "NOV",
                            "DEC",
                        ],
                        [5.3, 6.1, 6.7, 6.9, 6.6, 4.9, 3.9, 4.1, 4.9, 5.2, 5.0, 4.9],
                        strict=True,
                    )
                ),
                "T2M": dict(
                    zip(
                        [
                            "JAN",
                            "FEB",
                            "MAR",
                            "APR",
                            "MAY",
                            "JUN",
                            "JUL",
                            "AUG",
                            "SEP",
                            "OCT",
                            "NOV",
                            "DEC",
                        ],
                        [22, 24, 27, 30, 31, 28, 26, 25, 25, 26, 24, 22],
                        strict=True,
                    )
                ),
            }
        }
    }
    ghi, temp = nasa_power_monthly(18.5, 73.8, _mock(lambda r: httpx.Response(200, json=body)))
    monthly = monthly_kwh_per_kwp(18.5, 73.8, 18.0, 180.0, ghi, temp, -0.004)
    assert len(monthly) == 12 and all(m > 0 for m in monthly)
    assert 1100 < sum(monthly) < 2100  # kWh/kWp/yr, loss-free, plausible for western India
    bad = {
        "properties": {
            "parameter": {
                "ALLSKY_SFC_SW_DWN": dict.fromkeys(body["properties"]["parameter"]["T2M"], -999),
                "T2M": body["properties"]["parameter"]["T2M"],
            }
        }
    }
    with pytest.raises(ValueError):
        nasa_power_monthly(18.5, 73.8, _mock(lambda r: httpx.Response(200, json=bad)))


def test_solar_source_serves_a_stale_cached_value_when_everything_is_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docs = SQLiteDocStore(tmp_path / "s.sqlite")
    src = SolarSource(None, live=True, cache=docs, gamma_pdc=-0.004)
    ok = [100.0] * 12
    monkeypatch.setattr(
        SolarSource,
        "_pvgis",
        staticmethod(
            lambda *a: __import__(
                "packages.services.suryacheck", fromlist=["SolarResource"]
            ).SolarResource({}, ok, "pvgis_v5_2")
        ),
    )
    first = src.fetch(18.5, 73.8, 18, 180)
    assert first and not first.stale

    def boom(*a: object) -> None:
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(SolarSource, "_pvgis", staticmethod(boom))
    monkeypatch.setattr("packages.services.suryacheck.fallback_monthly", boom)
    fresh_instance = SolarSource(
        None, live=True, cache=docs, gamma_pdc=-0.004
    )  # new Lambda instance
    stale = fresh_instance.fetch(18.5, 73.8, 18, 180)
    assert stale and stale.stale and stale.monthly_base == ok
    assert (
        SolarSource(None, live=True, cache=SQLiteDocStore(tmp_path / "e.sqlite")).fetch(
            1.0, 1.0, 1, 1
        )
        is None
    )


# ------------------------------------------------------------------------------- auth + metrics
def _keypair():  # type: ignore[no-untyped-def]
    from cryptography.hazmat.primitives.asymmetric import rsa

    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def test_cognito_tokens_map_groups_to_roles_and_reject_bad_tokens() -> None:
    import jwt

    from packages.api.auth import CognitoVerifier

    key = _keypair()
    issuer, client = "https://cognito-idp.ap-south-1.amazonaws.com/pool", "app-client"
    verifier = CognitoVerifier(issuer, client, key_resolver=lambda tok: key.public_key())

    def token(groups: list[str], **over: object) -> str:
        claims = {
            "iss": issuer,
            "sub": "u1",
            "token_use": "id",
            "aud": client,
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            "cognito:groups": groups,
        }
        claims.update(over)
        return jwt.encode(claims, key, algorithm="RS256")

    assert verifier.verify(token(["admin"])).role is Role.ADMIN
    assert verifier.verify(token(["planner"])).role is Role.PLANNER
    assert verifier.verify(token([])).role is Role.VIEWER
    for bad in (token([], exp=1), token([], iss="https://evil"), token([], aud="other"), "garbage"):
        with pytest.raises(AuthenticationError):
            verifier.verify(bad)


def test_bearer_token_unlocks_planner_routes_in_the_api(tmp_path: Path) -> None:
    import jwt
    from fastapi.testclient import TestClient

    from packages.adapters.registry import build_adapters
    from packages.api.app import create_app
    from packages.api.auth import CognitoVerifier
    from packages.core.settings import AppSettings

    key = _keypair()
    issuer, client_id = "https://issuer.example/pool", "cid"
    settings = AppSettings(
        data_dir=tmp_path, cognito_issuer=issuer, cognito_client_id=client_id, _env_file=None
    )  # type: ignore[call-arg]
    app = create_app(settings, build_adapters(settings))
    app.state.coolroof.verifier = CognitoVerifier(
        issuer, client_id, key_resolver=lambda t: key.public_key()
    )
    tc = TestClient(app)
    tok = jwt.encode(
        {
            "iss": issuer,
            "sub": "u",
            "token_use": "id",
            "aud": client_id,
            "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            "cognito:groups": ["planner"],
        },
        key,
        algorithm="RS256",
    )
    assert tc.get("/alerts", headers={"Authorization": f"Bearer {tok}"}).status_code == 200
    assert (
        tc.get("/admin/official-warnings", headers={"Authorization": f"Bearer {tok}"}).status_code
        == 200
    )
    assert tc.get("/admin/params", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_metrics_emit_embedded_format(capsys: pytest.CaptureFixture[str]) -> None:
    metrics.reset()
    metrics.emit("LatencyMs", 12.5, "Milliseconds", Route="/x")
    line = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert line["_aws"]["CloudWatchMetrics"][0]["Namespace"] == "CoolRoof" and line["Route"] == "/x"
    assert metrics.snapshot()["LatencyMs|Route=/x"]["count"] == 1
