"""M20+21 Readiness prompts for health and utility officers (no beds, stock or demand data).

Prompts are rule-based over the Ward Context and the current signal (official warning or
M43 ≥ elevated). They ask officers to *confirm* readiness; the tool never states capacity.
The electricity *forecast* mode (peak-demand regression) is data-gated and not built.
"""

from __future__ import annotations

from typing import Any

from packages.core.context import WardContext
from packages.core.params import ParamRegistry
from packages.services.m17_reco import city_percentiles
from packages.services.signals import Signals

__all__ = ["readiness"]

HOT_TYPES = {"dense_built_low_green", "open_bare_or_industrial", "chronic_other", "episodic"}

PROMPTS: dict[str, dict[str, Any]] = {
    "HOSP-01": {
        "audience": "health officer",
        "en": "Heat exposure is high in {ward} and a warning or forecast signal is active: confirm facility readiness.",
        "hi": "{ward} में गर्मी का संपर्क अधिक है और चेतावनी या पूर्वानुमान संकेत सक्रिय है: अस्पतालों की तैयारी की पुष्टि करें।",
    },
    "HOSP-02": {
        "audience": "health officer",
        "en": "No hospital lies within the coverage radius of the exposed population in {ward}: coverage gap.",
        "hi": "{ward} में प्रभावित आबादी के कवरेज दायरे में कोई अस्पताल नहीं है: कवरेज में कमी।",
    },
    "EXAM-01": {
        "audience": "exam / event coordinator",
        "en": "Schools in {ward} are in a hot area and a warning or forecast signal is active: plan exam and event timings.",
        "hi": "{ward} के स्कूल गर्म क्षेत्र में हैं और चेतावनी या पूर्वानुमान संकेत सक्रिय है: परीक्षा और आयोजनों का समय तय करें।",
    },
    "COOL-01": {
        "audience": "planner",
        "en": "{ward} has no public cooling point and high exposure: see the cooling-point recommendation (R-CP-01).",
        "hi": "{ward} में कोई सार्वजनिक शीतलन स्थल नहीं है और संपर्क अधिक है: शीतलन स्थल सिफ़ारिश (R-CP-01) देखें।",
    },
    "ELEC-01": {
        "audience": "utility",
        "en": "Review feeder readiness for {ward}; no demand data was used.",
        "hi": "{ward} के फीडर की तैयारी की समीक्षा करें; माँग का कोई डेटा उपयोग नहीं किया गया।",
    },
}


def readiness(
    ward_id: str,
    contexts: list[WardContext],
    heat_type: str | None,
    signals: Signals,
    params: ParamRegistry,
    lang: str = "en",
) -> dict[str, Any]:
    ctx = next(c for c in contexts if c.ward_id == ward_id)
    exposed_pct = city_percentiles(contexts)["exposed"].get(ward_id)
    high_exposure = exposed_pct is not None and exposed_pct >= params.require("P-THETA-RULE")["exp"]
    name = ctx.location.name if lang == "en" else ctx.location.name_hi
    hospitals = ctx.value("infrastructure.hospital_count")
    schools = ctx.value("infrastructure.school_count")
    cooling = ctx.value("infrastructure.cooling_point_count")
    per10k = ctx.value("infrastructure.facilities_per_10k_exposed")
    conditions = {
        "HOSP-01": high_exposure and signals.active,
        "HOSP-02": high_exposure and per10k == 0,
        "EXAM-01": bool(schools) and heat_type in HOT_TYPES and signals.active,
        "COOL-01": cooling == 0 and high_exposure,
        "ELEC-01": high_exposure and signals.active,
    }
    not_evaluated = []
    if not ctx.field("infrastructure.hospital_count").is_available:
        not_evaluated.append({"id": "HOSP-02", "missing_fields": ["infrastructure.*"]})
        conditions["HOSP-02"] = False
    if not signals.active and signals.forecast_risk == "unavailable":
        not_evaluated.append(
            {"id": "signal", "missing_fields": ["heat.heatdome_risk or official warning"]}
        )
    prompts = [
        {
            "id": pid,
            "audience": PROMPTS[pid]["audience"],
            "text": PROMPTS[pid][lang].format(ward=name),
        }
        for pid, fired in conditions.items()
        if fired
    ]
    return {
        "ward_id": ward_id,
        "facilities": {
            "hospital_count": hospitals,
            "school_count": schools,
            "cooling_point_count": cooling,
            "nearest_hospital_m": ctx.value("infrastructure.nearest_hospital_m"),
            "facilities_per_10k_exposed": per10k,
        },
        "high_exposure": high_exposure,
        "signal": signals.to_dict(),
        "prompts": prompts,
        "not_evaluated": not_evaluated,
        "note": "Prompts ask officers to confirm readiness. No bed, stock or demand data is used.",
    }
