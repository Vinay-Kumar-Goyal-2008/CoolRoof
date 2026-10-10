"""The demo path through the real API: pick ward → rank → roof → solar → chat (hi) → PDF."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from packages.adapters.landsat_source import FixtureLandsatSource
from packages.adapters.registry import build_adapters
from packages.api.app import create_app
from packages.core.city import load_city
from packages.core.grounding import check_grounding
from packages.core.params import load_params
from packages.core.settings import AppSettings
from packages.pipeline.inputs import CityInputs
from packages.pipeline.m43_heatdome import forecast_heatdome, load_nwp_fixture
from packages.pipeline.runner import HeatPipeline
from packages.services.m35_pdf import extract_text, strip_controls
from packages.services.policy_store import PolicyStore
from packages.services.repository import Repository
from scripts.seed import seed_policies

BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> TestClient:
    settings = AppSettings(data_dir=tmp_path_factory.mktemp("data"), _env_file=None)  # type: ignore[call-arg]
    adapters = build_adapters(settings)
    city = load_city("mini_city")
    inputs = CityInputs(city)
    assert inputs.landsat_items_dir is not None
    run = HeatPipeline(
        city,
        load_params(),
        FixtureLandsatSource(inputs.landsat_items_dir),
        run_date=date(2026, 10, 10),
        run_id="e2e",
    ).run_all()
    forecast = forecast_heatdome(load_nwp_fixture(inputs.nwp_path), run.params).to_dict()
    Repository(adapters.docstore, adapters.blobstore).persist(run, forecast)
    seed_policies(PolicyStore(adapters.docstore), BACKEND / "seed")
    return TestClient(create_app(settings, adapters))


def test_ward_ranking_with_intervals_and_geojson(client: TestClient) -> None:
    data = client.get("/wards", params={"city": "mini_city"}).json()["data"]
    wards = {w["ward_id"]: w for w in data["wards"]}
    assert len(wards) == 12 and len(data["geojson"]["features"]) == 12
    assert wards["W07"]["priority"]["rank"] < wards["W10"]["priority"]["rank"]
    assert wards["W07"]["heat_type"]["type"] in {"dense_built_low_green", "chronic_other"}


def test_roofs_ranked_and_cost_unavailable_without_pcm2(client: TestClient) -> None:
    body = client.get("/wards/W07/buildings", params={"top": 5}).json()["data"]
    assert body["basis"] == "benefit_only" and len(body["roofs"]) == 5
    assert body["roofs"][0]["assessment"]["unavailable"]["cost_inr"] == ["P-CM2"]
    assert client.get("/wards/W09/buildings").status_code == 422  # incomplete footprints
    plan = client.post("/interventions/plan", json={"budget_inr": 1_000_000})
    assert plan.status_code == 422 and plan.json()["error"]["code"] == 422


def test_recommendations_carry_evidence_and_not_evaluated(client: TestClient) -> None:
    data = client.get("/wards/W07/recommendations").json()["data"]
    assert data["recommendations"]
    assert all(r["evidence"] for r in data["recommendations"])
    fired = {r["id"] for r in data["recommendations"]}
    assert (
        "R-HD-01" in fired
    )  # the fixture forecast is elevated/high and is patched into the context
    assert isinstance(data["not_evaluated"], list)
    hindi = client.get("/wards/W07/recommendations", params={"lang": "hi"}).json()["data"]
    assert hindi["recommendations"][0]["text"] != data["recommendations"][0]["text"]


def test_heatdome_signal_is_labelled_forecast_not_warning(client: TestClient) -> None:
    f = client.get("/forecast/heatdome").json()["data"]
    assert f["risk"] in {"elevated", "high"} and f["first_day"] == 4 and f["duration_days"] == 4
    assert "not an official warning" in f["label_en"]


def test_solar_assess_and_policy(client: TestClient) -> None:
    body = {
        "lat": 18.52,
        "lon": 73.86,
        "state": "TEST",
        "discom": "TEST-DISCOM",
        "roof_area_m2": 70,
        "avg_monthly_kwh": 400,
        "gross_cost_inr": 180000,
    }
    res = client.post("/solar/assess", json=body)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["subsidy"]["amount"]["value"] == 78000
    assert res.json()["meta"]["policy_version"] == "subsidy:ALL:ALL:2024-02-29"
    assert client.get("/policy/subsidy").json()["data"]["applications_portal"].endswith(".gov.in")


def test_agent_hindi_solar_flow_is_grounded(client: TestClient) -> None:
    sid = client.post("/sessions").json()["data"]["session_id"]
    h = {"X-Session-ID": sid}
    first = client.post(
        "/agent/chat", headers=h, json={"message": "सोलर सब्सिडी कितनी मिलेगी?", "lang": "hi"}
    ).json()["data"]
    assert first["lang"] == "hi" and "request_user_input" in first["tool_calls"]
    second = client.post(
        "/agent/chat",
        headers=h,
        json={"message": "मेरी छत 70 वर्ग मीटर है और 400 यूनिट बिजली लगती है", "lang": "hi"},
    ).json()["data"]
    assert "₹78,000" in second["reply"] and second["grounded"] and not second["fallback_used"]
    assert second["citations"][0]["source_url"].startswith("https://")


def test_agent_refuses_and_never_submits(client: TestClient) -> None:
    sid = client.post("/sessions").json()["data"]["session_id"]
    h = {"X-Session-ID": sid}
    medical = client.post(
        "/agent/chat", headers=h, json={"message": "which medicine for heat stroke?", "lang": "en"}
    ).json()["data"]
    assert "medical or legal" in medical["reply"]
    submit = client.post(
        "/agent/chat", headers=h, json={"message": "please submit my application", "lang": "en"}
    ).json()["data"]
    assert "pmsuryaghar.gov.in" in submit["reply"] and submit["tool_calls"] == []


def test_agent_invented_numbers_are_caught_by_grounding() -> None:
    outputs = {"solar": {"subsidy": {"amount": {"value": 78000}}}}
    assert not check_grounding("Your subsidy is ₹90,000", outputs).grounded


def test_unknown_session_is_404(client: TestClient) -> None:
    res = client.post("/agent/chat", headers={"X-Session-ID": "nope"}, json={"message": "hi"})
    assert res.status_code == 404


@pytest.mark.parametrize("lang", ["en", "hi"])
def test_pdf_text_matches_source_after_stripping_controls(client: TestClient, lang: str) -> None:
    body = {
        "assessment": {
            "lat": 18.52,
            "lon": 73.86,
            "state": "TEST",
            "discom": "TEST-DISCOM",
            "roof_area_m2": 70,
            "avg_monthly_kwh": 400,
            "on_date": "2026-10-10",
        },
        "lang": lang,
    }
    res = client.post("/documents/application-pdf", json=body)
    assert res.status_code == 200, res.text
    pdf = client.get(res.json()["data"]["url"])
    text = strip_controls(extract_text(pdf.content))
    assert "pmsuryaghar.gov.in" in text and "78,000" in text
    if lang == "hi":
        assert "सहायता सारांश" in text and "रूफटॉप सोलर" in text
