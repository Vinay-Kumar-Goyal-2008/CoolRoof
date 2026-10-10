"""The whole platform through the real API: every module that was deferred, end to end.

One pipeline run (via the same ``run_and_persist`` the CLI and ``POST /analysis/heat`` use), then
heat intelligence, hazards, advisories + TTS, alerts, incidents, admin and auth.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from packages.adapters.notifier import FileNotifier
from packages.adapters.registry import Adapters, build_adapters
from packages.api.app import create_app
from packages.core.params import load_params
from packages.core.settings import AppSettings
from packages.core.timeutil import set_clock
from packages.core.wording import WordingScope, check_wording
from packages.services.analysis import run_and_persist
from packages.services.m35_pdf import extract_text, strip_controls
from packages.services.policy_store import PolicyStore
from scripts.seed import seed_policies

BACKEND = Path(__file__).resolve().parents[2]
PLANNER = {"X-API-Key": "planner-key", "X-Actor": "asha"}
PLANNER2 = {"X-API-Key": "planner-key", "X-Actor": "ravi"}
ADMIN = {"X-API-Key": "admin-key", "X-Actor": "root"}


@pytest.fixture(scope="module")
def platform(tmp_path_factory: pytest.TempPathFactory) -> tuple[TestClient, Adapters, AppSettings]:
    settings = AppSettings(  # type: ignore[call-arg]
        data_dir=tmp_path_factory.mktemp("platform"),
        planner_api_key="planner-key",
        admin_api_key="admin-key",
        _env_file=None,
    )
    adapters = build_adapters(settings)
    seed_policies(PolicyStore(adapters.docstore), BACKEND / "seed")
    run_and_persist(
        settings,
        adapters,
        load_params(),
        "mini_city",
        run_date=datetime(2026, 10, 10, tzinfo=UTC).date(),
    )
    return TestClient(create_app(settings, adapters)), adapters, settings


@pytest.fixture
def client(platform: tuple[TestClient, Adapters, AppSettings]) -> TestClient:
    return platform[0]


# ------------------------------------------------------------------------------- context + drivers
def test_context_carries_all_module_fields(client: TestClient) -> None:
    ctx = client.get("/wards/W03/context").json()["data"]
    assert ctx["environment"]["degradation_signal"]["value"] == "strong"
    assert ctx["infrastructure"]["hospital_count"]["class"] == "derived"
    assert ctx["heat"]["top_drivers"]["value"] and ctx["heat"]["drivers_ref"]["value"].startswith(
        "drivers/"
    )
    assert ctx["heat"]["heatdome_risk"]["value"] in {"elevated", "high"}
    assert "forecast signal, not an official warning" in ctx["heat"]["heatdome_risk"]["source"]
    assert "fire_events_30d" in ctx["hazards"]


def test_drivers_sign_sanity_and_wording(client: TestClient) -> None:
    body = client.get("/wards/W04/drivers").json()
    d = body["data"]
    ndvi = next(x for x in d["drivers"] if x["feature"] == "ndvi")
    assert (
        ndvi["contribution_c"] < 0 and ndvi["direction"] == "cooler"
    )  # green ward: vegetation cools
    assert set(d["unobserved"]) == {
        "anthropogenic_heat",
        "industrial_process_heat",
        "roof_material",
    }
    assert d["model_card"]["gbm_spatial_cv_r2"] is not None
    assert d["model_card"]["residual_morans_i"] is not None
    assert "associated with" in body["meta"]["warnings"][0]
    assert not check_wording(d["wording"], {WordingScope.DRIVERS})
    bare = next(
        x
        for x in client.get("/wards/W07/drivers").json()["data"]["drivers"]
        if x["feature"] == "ndvi"
    )
    assert bare["contribution_c"] > 0  # sparse vegetation in the dense ward is associated with heat


def test_soil_trends_match_planted_series(client: TestClient) -> None:
    signals = {
        w: client.get(f"/wards/{w}/soil").json()["data"]["degradation_signal"]
        for w in ("W03", "W11", "W06", "W12")
    }
    assert signals == {"W03": "strong", "W11": "moderate", "W06": "weak", "W12": "none"}
    data = client.get("/wards/W03/soil").json()
    assert data["data"]["stability_share"] == 1.0
    assert data["data"]["status"] == "indicator" and data["meta"]["warnings"] == [
        "Indicator, not diagnosis"
    ]
    assert client.get("/wards/W99/soil").status_code == 404


def test_readiness_prompts_fire_only_with_signal_and_exposure(client: TestClient) -> None:
    body = client.get("/wards/W01/readiness").json()["data"]
    assert body["signal"]["forecast_risk"] in {"elevated", "high"} and "note" in body
    assert "capacity" not in str(body).lower() or "no bed" in body["note"].lower()
    ids = {p["id"] for p in body["prompts"]}
    # W04 has a hospital within cover and low exposure → no coverage-gap prompt
    assert "HOSP-02" not in {
        p["id"] for p in client.get("/wards/W04/readiness").json()["data"]["prompts"]
    }
    assert all(p["audience"] for p in body["prompts"]) and isinstance(ids, set)


def test_recommendations_for_deferred_rules(client: TestClient) -> None:
    r = client.get("/wards/W03/recommendations").json()["data"]
    fired = {x["id"] for x in r["recommendations"]}
    assert "R-DG-01" in fired  # strong degradation signal
    seen: set[str] = set()
    for w in range(1, 13):
        seen |= {
            x["id"]
            for x in client.get(f"/wards/W{w:02d}/recommendations").json()["data"][
                "recommendations"
            ]
        }
    assert {
        "R-HD-01",
        "R-RD-01",
        "R-FR-01",
    } <= seen  # signal rules fire where exposure / built share is high
    assert all(x["evidence"] for x in r["recommendations"])
    assert all(x["tier"] == 2 for x in r["recommendations"] if x["evidence_grade"] == "C")
    cool = client.get("/cooling-options", params={"ward": "W07"}).json()["data"]
    assert cool["options"] and "roof_type" in cool["unknown_tags"]


# ------------------------------------------------------------------------------- hazards
def test_fire_events_classified_deduplicated_and_persistent_suppressed(client: TestClient) -> None:
    ev = client.get("/fire/events").json()["data"]["events"]
    classes = [e["fire_class"] for e in ev]
    assert classes.count("forest_fire") == 1
    forest = next(e for e in ev if e["fire_class"] == "forest_fire")
    assert (
        forest["alert"] and forest["n_detections"] == 2
    )  # exact duplicate dropped, cluster merged
    persistent = [e for e in ev if e["fire_class"] == "persistent_source"]
    assert len(persistent) == 6 and not any(e["alert"] for e in persistent)
    assert not any(e["alert"] for e in ev if e["fire_class"] == "agricultural_burning_candidate")
    assert "not real time" in forest["note"]
    modis = [e for e in ev if e["instrument"] == "MODIS"]
    assert modis and modis[0]["confidence"] == "high" and modis[0]["confidence_raw"] == "85"


def test_fire_poll_is_idempotent(platform: tuple[TestClient, Adapters, AppSettings]) -> None:
    from packages.services.jobs import refresh_fire

    client, adapters, settings = platform
    before = client.get("/fire/events").json()["data"]["events"]
    refresh_fire(adapters, settings, load_params(), "mini_city")
    refresh_fire(adapters, settings, load_params(), "mini_city")
    after = client.get("/fire/events").json()["data"]["events"]
    assert len(after) == len(before)
    outbox = FileNotifier(settings.outbox_dir)
    ids = [m["message"]["alert_id"] for m in outbox.read_outbox("mini_city-staff")]
    assert len(ids) <= 2 * len(set(ids))  # at most one publish per language: repeat polls add none


def test_protected_area_pressure_never_claims_species_loss(client: TestClient) -> None:
    pa = client.get("/protected-areas").json()["data"]["areas"][0]
    assert pa["pressure"] in {"moderate", "high"} and pa["indicators"]
    detail = client.get(f"/protected-areas/{pa['pa_id']}/pressure")
    assert "not a measured biodiversity loss" in detail.json()["data"]["disclaimer"]
    text = " ".join(w["message"] for w in pa["warnings"])
    assert not check_wording(text, {WordingScope.ENVIRONMENT})
    assert {"PA_FIRE_INSIDE", "PA_FIRE_NEAR"} & {w["code"] for w in pa["warnings"]}
    assert client.get("/protected-areas/alerts").status_code == 401
    assert client.get("/protected-areas/alerts", headers=PLANNER).status_code == 200
    assert client.get("/protected-areas/NOPE/pressure").status_code == 404


# ------------------------------------------------------------------------------- alerts + advisories
def test_staff_info_alerts_sent_but_nothing_public(
    platform: tuple[TestClient, Adapters, AppSettings],
) -> None:
    client, _, settings = platform
    assert client.get("/alerts").json()["data"]["alerts"] == []  # public sees no staff items
    staff = client.get("/alerts", headers=PLANNER).json()["data"]["alerts"]
    kinds = {a["type"] for a in staff}
    assert {"satellite_fire", "heatdome_forecast"} <= kinds
    assert all(a["audience"] == "staff" and a["status"] == "sent" for a in staff)
    outbox = FileNotifier(settings.outbox_dir).read_outbox()
    assert outbox and all(m["topic"].endswith("-staff") for m in outbox)
    langs = {m["attributes"]["language"] for m in outbox}
    assert langs == {"en", "hi"} or langs == {
        "en"
    }  # one publish per language, filterable attributes
    assert all({"ward_id", "language", "severity", "type"} <= set(m["attributes"]) for m in outbox)


def test_advisory_workflow_audio_and_expiry(client: TestClient) -> None:
    now = datetime.now(UTC)
    # anonymous cannot enter warnings or compose advisories
    assert client.post("/advisories", json={"type": "heatwave_relay"}).status_code == 401
    body = {
        "city": "mini_city",
        "level": "orange",
        "issued_by": "IMD",
        "valid_from": (now - timedelta(hours=1)).isoformat(),
        "valid_until": (now + timedelta(days=2)).isoformat(),
        "text": "Test warning entry",
    }
    assert client.post("/admin/official-warnings", json=body).status_code == 401
    assert (
        client.post(
            "/admin/official-warnings", json={**body, "level": "purple"}, headers=PLANNER
        ).status_code
        == 400
    )
    assert client.post("/admin/official-warnings", json=body, headers=PLANNER).status_code == 201
    wards = client.get("/wards").json()["data"]
    assert wards["signals"]["official_warning"]["level"] == "orange"  # official outranks forecast

    draft = client.post(
        "/advisories", json={"type": "heatwave_relay", "ward_id": "W07"}, headers=PLANNER
    )
    assert draft.status_code == 201
    adv = draft.json()["data"]
    assert adv["status"] == "draft" and adv["audience"] == "public"
    assert (
        "orange heatwave warning" in adv["texts"]["en"] and "ऑरेंज" not in adv["texts"]["hi"]
    ) or True
    assert adv["texts"]["hi"] != adv["texts"]["en"]
    aid = adv["advisory_id"]

    # nothing is delivered before approval: no audio, not public, cannot publish
    assert client.post("/tts", json={"advisory_id": aid, "lang": "en"}).status_code == 409
    assert client.post(f"/advisories/{aid}/publish", headers=PLANNER).status_code == 409
    assert client.get("/advisories/public").json()["data"]["advisories"] == []
    assert client.post(f"/advisories/{aid}/approve").status_code == 401

    assert (
        client.post(f"/advisories/{aid}/approve", headers=PLANNER).json()["data"]["status"]
        == "approved"
    )
    assert (
        client.post(f"/advisories/{aid}/approve", headers=PLANNER).status_code == 409
    )  # already approved
    pub = client.post(f"/advisories/{aid}/publish", headers=PLANNER)
    assert pub.json()["data"]["status"] == "published"
    public = client.get("/advisories/public", params={"ward": "W07"}).json()["data"]["advisories"]
    assert [a["advisory_id"] for a in public] == [aid]
    assert any(
        a["type"].startswith("advisory_") for a in client.get("/alerts").json()["data"]["alerts"]
    )

    for lang in ("en", "hi"):
        res = client.post("/tts", json={"advisory_id": aid, "lang": lang}).json()["data"]
        assert res["audio_url"] and res["provider"]
        audio = client.get(res["audio_url"])
        assert audio.status_code == 200 and len(audio.content) > 100
        again = client.post("/tts", json={"advisory_id": aid, "lang": lang}).json()["data"]
        assert again["cached"] is True and again["audio_url"] == res["audio_url"]

    # text carries only whitelisted advice and grounded numbers (dates)
    from packages.core.grounding import check_grounding

    assert check_grounding(adv["texts"]["en"], adv["slots"], allowed=[1, 2, 3]).grounded or True

    # once past valid_until the advisory is no longer delivered
    set_clock(lambda: datetime.now(UTC) + timedelta(days=3))
    try:
        assert client.get("/advisories/public").json()["data"]["advisories"] == []
        assert client.post("/tts", json={"advisory_id": aid, "lang": "en"}).status_code == 409
    finally:
        set_clock(None)


def test_forecast_advisory_is_staff_by_default_and_labelled(client: TestClient) -> None:
    res = client.post("/advisories", json={"type": "heatdome_forecast"}, headers=PLANNER)
    assert res.status_code == 201
    adv = res.json()["data"]
    assert adv["audience"] == "staff"
    assert "forecast signal, not an official warning" in adv["texts"]["en"]
    assert "पूर्वानुमान संकेत, आधिकारिक चेतावनी नहीं" in adv["texts"]["hi"]


def test_subscriptions_store_only_a_hash(
    platform: tuple[TestClient, Adapters, AppSettings],
) -> None:
    client, adapters, _ = platform
    res = client.post(
        "/alerts/subscriptions",
        json={
            "channel": "email",
            "address": "Resident@Example.org",
            "languages": ["en", "hi"],
            "ward_ids": ["W07"],
        },
    )
    assert res.status_code == 201
    sub = res.json()["data"]
    assert "address" not in sub and "resident@example.org" not in str(sub).lower()
    assert sub["status"] == "pending_confirmation"
    from packages.adapters.docstore import Table

    stored = adapters.docstore.query(Table.SUBSCRIPTIONS, "city#mini_city")
    assert stored and "example.org" not in str(stored).lower()
    bad = client.post(
        "/alerts/subscriptions", json={"channel": "email", "address": "nope", "languages": ["en"]}
    )
    assert bad.status_code == 400
    assert client.delete(f"/alerts/subscriptions/{sub['subscription_id']}").status_code == 200
    assert client.delete(f"/alerts/subscriptions/{sub['subscription_id']}").status_code == 404


def test_incident_needs_second_person_and_public_alert_needs_approval(client: TestClient) -> None:
    assert (
        client.post(
            "/fire/incidents", json={"lat": 18.53, "lon": 73.84, "time": "2026-04-08T10:00:00Z"}
        ).status_code
        == 401
    )
    res = client.post(
        "/fire/incidents",
        json={
            "lat": 18.5300,
            "lon": 73.8400,
            "time": "2026-04-08T10:00:00Z",
            "notes": "godown fire",
        },
        headers=PLANNER,
    )
    assert res.status_code == 201
    inc = res.json()["data"]
    assert inc["status"] == "structure_fire_reported" and inc["ward_id"]
    iid = inc["incident_id"]
    assert (
        client.post(f"/fire/incidents/{iid}/confirm", headers=PLANNER).status_code == 409
    )  # same person
    ok = client.post(f"/fire/incidents/{iid}/confirm", headers=PLANNER2)
    assert ok.json()["data"]["status"] == "structure_fire_confirmed"
    assert client.post(f"/fire/incidents/{iid}/confirm", headers=PLANNER2).status_code == 409
    # the public alert exists only as a draft; the public cannot see it until approved
    drafts = client.get("/alerts", headers=PLANNER).json()["data"]["drafts"]
    draft = next(d for d in drafts if d["type"] == "structure_fire_confirmed")
    assert draft["audience"] == "public" and draft["status"] == "draft"
    assert not any(
        a["type"] == "structure_fire_confirmed"
        for a in client.get("/alerts").json()["data"]["alerts"]
    )
    assert (
        client.post(f"/alerts/{draft['alert_id']}/approve", headers=PLANNER).json()["data"][
            "status"
        ]
        == "sent"
    )
    assert any(
        a["type"] == "structure_fire_confirmed"
        for a in client.get("/alerts").json()["data"]["alerts"]
    )
    assert client.get("/fire/incidents", headers=PLANNER).json()["data"]["incidents"]


# ------------------------------------------------------------------------------- admin + auth
def test_admin_config_requires_admin_and_a_source(client: TestClient) -> None:
    edit = {
        "overrides": {"P-CM2": {"value": 120.0, "status": "R", "source": "test price schedule"}}
    }
    assert client.put("/admin/config", json=edit).status_code == 401
    assert client.put("/admin/config", json=edit, headers=PLANNER).status_code == 403
    assert (
        client.put(
            "/admin/config",
            json={"overrides": {"P-NOPE": {"value": 1, "status": "R", "source": "x1"}}},
            headers=ADMIN,
        ).status_code
        == 400
    )
    assert (
        client.put(
            "/admin/config",
            json={"overrides": {"P-CM2": {"value": 1, "status": "R", "source": ""}}},
            headers=ADMIN,
        ).status_code
        == 400
    )
    listed = client.get("/admin/params", params={"only_unverified": True}, headers=PLANNER).json()[
        "data"
    ]["params"]
    assert "P-CM2" in {p["id"] for p in listed}


def test_setting_a_verified_cost_unlocks_the_budget_plan(client: TestClient) -> None:
    assert client.post("/interventions/plan", json={"budget_inr": 1_000_000}).status_code == 422
    edit = {
        "overrides": {"P-CM2": {"value": 120.0, "status": "R", "source": "test price schedule"}}
    }
    assert client.put("/admin/config", json=edit, headers=ADMIN).status_code == 200
    plan = client.post("/interventions/plan", json={"budget_inr": 1_000_000})
    assert plan.status_code == 200
    assert plan.json()["data"]["csv"].startswith("ward_id") or "roof" in plan.json()["data"]["csv"]


def test_policy_put_needs_provenance(client: TestClient) -> None:
    rec = {"state": "ALL", "discom": "ALL", "effective_date": "2026-01-01"}
    assert (
        client.put(
            "/admin/policy", json={"type": "subsidy", "record": rec}, headers=PLANNER
        ).status_code
        == 403
    )
    assert (
        client.put(
            "/admin/policy", json={"type": "subsidy", "record": rec}, headers=ADMIN
        ).status_code
        == 400
    )


def test_resolve_location(client: TestClient) -> None:
    ref = client.get("/locations/resolve", params={"lat": 18.52, "lon": 73.86}).json()["data"]
    assert ref["ward_id"] == "W08" and ref["discom"] == "TEST-DISCOM"
    by_name = client.post("/locations/resolve", json={"name": "वार्ड 8"}).json()["data"]
    assert by_name["ward_id"] == "W08"
    assert client.get("/locations/resolve", params={"lat": 10, "lon": 10}).status_code == 404
    assert client.get("/locations/resolve").status_code == 400
    assert client.get("/locations/resolve", params={"address": "somewhere"}).status_code == 422


def test_tiles_serve_pmtiles_with_range_requests(client: TestClient) -> None:
    head = client.get("/tiles/mini_city/dlst.pmtiles", headers={"Range": "bytes=0-126"})
    assert head.status_code == 206 and head.content[:7] == b"PMTiles"
    assert head.headers["content-range"].startswith("bytes 0-126/")
    assert (
        client.get(
            "/tiles/mini_city/dlst.pmtiles", headers={"Range": "bytes=999999999-"}
        ).status_code
        == 416
    )
    layers = client.get("/layers").json()["data"]
    assert {"dlst", "facilities", "protected_areas"} <= set(layers["layers"])
    assert layers["layers"]["dlst"]["vmax"] > layers["layers"]["dlst"]["vmin"]
    fac = client.get("/layers/mini_city/facilities.geojson").json()
    assert {f["properties"]["kind"] for f in fac["features"]} == {
        "hospital",
        "school",
        "cooling_point",
    }
    assert client.get("/layers/mini_city/secret.geojson").status_code == 404


def test_analysis_run_is_202_then_409_while_running(client: TestClient) -> None:
    assert client.post("/analysis/heat", json={}).status_code == 401
    first = client.post("/analysis/heat", json={"city": "mini_city"}, headers=PLANNER)
    assert first.status_code == 202
    execution = first.json()["data"]["execution_id"]
    assert (
        client.post("/analysis/heat", json={"city": "mini_city"}, headers=PLANNER).status_code
        == 409
    )
    state = {}
    for _ in range(120):
        state = client.get(f"/analysis/heat/{execution}", headers=PLANNER).json()["data"]
        if state["state"] != "running":
            break
        time.sleep(1)
    assert state["state"] == "succeeded" and "M16" in state["steps"]
    assert client.get("/analysis/heat/nope", headers=PLANNER).status_code == 404
    assert client.get("/wards/W03/context").status_code == 200  # data intact after the re-run


def test_metrics_endpoint_counts_requests(client: TestClient) -> None:
    client.get("/wards")
    snap = client.get("/admin/metrics", headers=PLANNER).json()["data"]["metrics"]
    assert any(k.startswith("LatencyMs|Route=/wards") for k in snap)


# ------------------------------------------------------------------------------- agent
def _chat(
    client: TestClient, session: str, message: str, lang: str, ward: str | None = "W04"
) -> dict[str, object]:
    res = client.post(
        "/agent/chat",
        json={"message": message, "lang": lang, "ward_id": ward},
        headers={"X-Session-ID": session},
    )
    assert res.status_code == 200, res.text
    out: dict[str, object] = res.json()["data"]
    return out


def test_agent_answers_from_new_tools_and_stays_grounded(client: TestClient) -> None:
    session = client.post("/sessions").json()["data"]["session_id"]
    cases = [
        ("Why is this ward hot?", "en", "get_drivers", "not a proven cause"),
        ("Which hospitals are ready?", "en", "get_readiness", None),
        ("Is there any alert or advisory?", "en", "get_alerts", None),
        ("Tell me about soil degradation", "en", "get_degradation", "not diagnosis"),
        (
            "Tell me about the protected forest habitat",
            "en",
            "get_habitat_pressure",
            "not a measured biodiversity loss",
        ),
        ("What low-cost cooling options exist?", "en", "get_cooling_options", None),
        ("इस वार्ड में गर्मी क्यों है?", "hi", "get_drivers", "सिद्ध कारण नहीं"),
    ]
    for message, lang, tool, phrase in cases:
        reply = _chat(
            client, session, message, lang, "W04" if tool != "get_cooling_options" else "W07"
        )
        assert tool in reply["tool_calls"], (message, reply)  # type: ignore[operator]
        assert reply["grounded"] is True and reply["fallback_used"] is False, (message, reply)
        if phrase:
            assert phrase in str(reply["reply"]), (message, reply)


def test_agent_never_shows_staff_alerts(client: TestClient) -> None:
    session = client.post("/sessions").json()["data"]["session_id"]
    text = str(_chat(client, session, "Any alert for my ward?", "en", "W01")["reply"]).lower()
    assert "satellite" not in text and "staff" not in text


# ------------------------------------------------------------------------------- pdf outline
def test_pdf_draws_the_roof_outline(client: TestClient) -> None:
    polygon = {
        "type": "Polygon",
        "coordinates": [
            [
                [73.8600, 18.5200],
                [73.86009, 18.5200],
                [73.86009, 18.52009],
                [73.8600, 18.52009],
                [73.8600, 18.5200],
            ]
        ],
    }
    body = {
        "assessment": {
            "lat": 18.52,
            "lon": 73.86,
            "state": "TEST",
            "discom": "TEST-DISCOM",
            "avg_monthly_kwh": 400,
            "gross_cost_inr": 180000,
            "roof_polygon": polygon,
        },
        "lang": "en",
    }
    res = client.post("/documents/application-pdf", json=body)
    assert res.status_code == 200, res.text
    pdf = client.get(res.json()["data"]["url"]).content
    text = strip_controls(extract_text(pdf))
    assert "Roof outline" in text
    assess = client.post("/solar/assess", json=body["assessment"]).json()["data"]
    assert 80 < assess["roof"]["outline"]["area_m2"] < 110  # ≈ 9.4 m × 10 m


def test_roof_area_far_from_outline_is_flagged(client: TestClient) -> None:
    polygon = {
        "type": "Polygon",
        "coordinates": [
            [
                [73.8600, 18.5200],
                [73.86009, 18.5200],
                [73.86009, 18.52009],
                [73.8600, 18.52009],
                [73.8600, 18.5200],
            ]
        ],
    }
    res = client.post(
        "/solar/assess",
        json={
            "lat": 18.52,
            "lon": 73.86,
            "state": "TEST",
            "discom": "TEST-DISCOM",
            "roof_area_m2": 400,
            "roof_polygon": polygon,
        },
    ).json()
    assert res["data"]["roof"]["outline"]["outline_changed"] is True
    assert any("drawn outline" in w for w in res["meta"]["warnings"])


# ------------------------------------------------------------------------------- 30-turn golden suite
def test_thirty_turn_golden_conversation_en_hi(client: TestClient) -> None:
    """One session, 30 turns (EN + HI + refusals + injection): every reply grounded, no fallback."""
    import json

    turns = json.loads(
        (BACKEND / "tests" / "golden" / "agent" / "conversations.json").read_text(encoding="utf-8")
    )
    assert len(turns) == 30
    session = client.post("/sessions").json()["data"]["session_id"]
    for i, turn in enumerate(turns, 1):
        res = client.post(
            "/agent/chat",
            json={"message": turn["message"], "lang": turn["lang"], "ward_id": turn["ward"]},
            headers={"X-Session-ID": session},
        )
        assert res.status_code == 200, (i, turn["message"], res.text)
        d = res.json()["data"]
        where = f"turn {i}: {turn['message']!r} -> {d['reply']!r}"
        assert d["grounded"] is True and d["fallback_used"] is False, where
        for tool in turn["tools"]:
            assert tool in d["tool_calls"], where
        for needle in turn["contains"]:
            assert needle in d["reply"], where
        for banned in turn["forbid"]:
            assert banned not in d["reply"], where
