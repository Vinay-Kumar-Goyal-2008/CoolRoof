"""Writes rules/v1/*.json (recommendation rules, evidence, cooling catalogue, briefs, glossary).

Evidence entries other than the PM Surya Ghar policy are marked NV: they are placeholders
that must be curated from peer-reviewed sources / the AIDMI page (spec Appendix B items 8, 9).
Rules with grade-C evidence never enter Tier 1.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

OUT = Path(__file__).resolve().parents[1] / "rules" / "v1"

EVIDENCE: list[dict[str, Any]] = [
    {
        "id": "EV-PMSG-POLICY",
        "title": "PM Surya Ghar CFA structure (state sheet and Pune district portal)",
        "publisher": "JBVNL / Pune district administration",
        "url": "https://pune.gov.in/scheme/pm-surya-gharmuft-bijli-yojna/",
        "claim": "Residential subsidy tiers and cap used by SuryaCheck",
        "grade": "A",
        "context_tags": ["solar", "policy"],
        "reviewed_by": "Build Spec v0.3 fact F1 [V]",
        "reviewed_on": "2026-10-08",
    },
    {
        "id": "EV-COOLROOF-LIT",
        "title": "Cool-roof effectiveness literature (to be curated)",
        "publisher": "to be curated",
        "url": None,
        "claim": "Reflective roofs can lower roof-surface and indoor temperatures; magnitude depends on albedo change and building form",
        "grade": "C",
        "context_tags": ["cool_roof"],
        "reviewed_by": None,
        "reviewed_on": None,
        "status": "NV - curate peer-reviewed sources (Appendix B item 8)",
    },
    {
        "id": "EV-AIDMI-HEAT",
        "title": "AIDMI extreme-heat resource page (to be curated)",
        "publisher": "All India Disaster Mitigation Institute",
        "url": None,
        "claim": "Community cooling points, shade and water access are common heat-action-plan measures",
        "grade": "C",
        "context_tags": ["cooling_point", "green", "economical_cooling"],
        "reviewed_by": None,
        "reviewed_on": None,
        "status": "NV - extract entries (Appendix B item 9)",
    },
    {
        "id": "EV-HEAT-PLAN",
        "title": "Heat action plan guidance (to be curated)",
        "publisher": "to be curated",
        "url": None,
        "claim": "Heat advisories should reach schools and event organisers when heat is forecast",
        "grade": "C",
        "context_tags": ["advisory"],
        "reviewed_by": None,
        "reviewed_on": None,
        "status": "NV",
    },
]


def _rule(
    rid: str,
    intervention: str,
    fields: list[str],
    ev: list[str],
    grade: str,
    caveats: list[str],
    audience: str,
    quantified: bool,
    en: str,
    hi: str,
) -> dict[str, Any]:
    return {
        "id": rid,
        "intervention": intervention,
        "required_fields": fields,
        "evidence_ref": ev,
        "evidence_grade": grade,
        "caveats": caveats,
        "audience": audience,
        "quantified": quantified,
        "text": {"en": en, "hi": hi},
    }


RULES = [
    _rule(
        "R-CR-01",
        "Ward cool-roof programme",
        ["heat.mean_dlst_c", "built_environment.eligible_roof_area_m2"],
        ["EV-COOLROOF-LIT"],
        "C",
        [
            "Cool-roof coefficients and costs are placeholders until a 10-20 roof pilot",
            "LST is the surface temperature at a late-morning satellite pass",
        ],
        "staff",
        True,
        "Consider a cool-roof programme in {ward}: high-priority ward with a large share of eligible roof area.",
        "{ward} में कूल-रूफ कार्यक्रम पर विचार करें: उच्च प्राथमिकता वाला वार्ड जहाँ पात्र छत क्षेत्र अधिक है।",
    ),
    _rule(
        "R-SO-01",
        "Rooftop solar opportunity (SuryaCheck)",
        ["built_environment.eligible_roof_area_m2"],
        ["EV-PMSG-POLICY"],
        "A",
        ["Final eligibility is decided on pmsuryaghar.gov.in"],
        "public",
        True,
        "Households in {ward} can check rooftop solar and the PM Surya Ghar subsidy with SuryaCheck.",
        "{ward} के परिवार सूर्याचेक से रूफटॉप सोलर और पीएम सूर्य घर सब्सिडी जाँच सकते हैं।",
    ),
    _rule(
        "R-CP-01",
        "Public cooling-point siting",
        ["population.exposed_population", "built_environment.eligible_roof_area_m2"],
        ["EV-AIDMI-HEAT"],
        "C",
        ["Candidate public facilities must be identified on the ground"],
        "staff",
        False,
        "Many people are exposed to heat in {ward} with few eligible roofs: consider a public cooling point.",
        "{ward} में बहुत लोग गर्मी के संपर्क में हैं और पात्र छतें कम हैं: सार्वजनिक शीतलन स्थल पर विचार करें।",
    ),
    _rule(
        "R-GR-01",
        "Green cover and shade on open land",
        ["environment.ndvi_mean", "environment.bare_fraction"],
        ["EV-AIDMI-HEAT"],
        "C",
        ["Needs an on-ground land availability check"],
        "staff",
        False,
        "{ward} has low green cover and bare land: consider tree planting and shade.",
        "{ward} में हरियाली कम है और खाली ज़मीन है: पेड़ लगाने और छाया पर विचार करें।",
    ),
    _rule(
        "R-EC-01",
        "Economical cooling options for this locality",
        ["heat.mean_dlst_c"],
        ["EV-AIDMI-HEAT"],
        "C",
        ["Costs are bands only until cited"],
        "staff",
        False,
        "Low-cost cooling options that suit {ward} are listed below.",
        "{ward} के लिए उपयुक्त कम-लागत शीतलन विकल्प नीचे दिए गए हैं।",
    ),
    _rule(
        "R-HD-01",
        "Heat-dome forecast signal relay",
        ["heat.heatdome_risk"],
        ["EV-HEAT-PLAN"],
        "C",
        ["Forecast signal, not an official warning; official IMD warnings take precedence"],
        "staff",
        False,
        "A heat-dome forecast signal (not an official warning) covers {ward}: review readiness.",
        "{ward} के लिए हीट-डोम पूर्वानुमान संकेत (आधिकारिक चेतावनी नहीं) है: तैयारी की समीक्षा करें।",
    ),
    _rule(
        "R-EX-01",
        "Exam and event heat advisory",
        ["heat.heatdome_risk"],
        ["EV-HEAT-PLAN"],
        "C",
        ["Needs school data (not loaded)"],
        "staff",
        False,
        "Schools in {ward} may need heat precautions during the forecast signal.",
        "पूर्वानुमान संकेत के दौरान {ward} के स्कूलों में गर्मी से बचाव ज़रूरी हो सकता है।",
    ),
]

COOLING = [
    {
        "id": "CO-REFLECTIVE-PAINT",
        "name_i18n": {"en": "Reflective roof paint", "hi": "परावर्तक छत पेंट"},
        "type": "passive",
        "suits": {
            "heat_type": ["dense_built_low_green", "chronic_other"],
            "roof_type": ["concrete", "metal"],
            "built_form": ["dense"],
        },
        "cost_band": "low",
        "capex_range_inr": None,
        "evidence_ref": ["EV-COOLROOF-LIT"],
        "caveats": ["Cost needs a cited local schedule"],
    },
    {
        "id": "CO-SHADE-NET",
        "name_i18n": {"en": "Shading nets", "hi": "छाया जाल"},
        "type": "passive",
        "suits": {
            "heat_type": ["dense_built_low_green", "open_bare_or_industrial"],
            "roof_type": ["metal", "concrete"],
            "built_form": ["dense", "industrial"],
        },
        "cost_band": "low",
        "capex_range_inr": None,
        "evidence_ref": ["EV-AIDMI-HEAT"],
        "caveats": [],
    },
    {
        "id": "CO-COMMUNITY-COOLING",
        "name_i18n": {"en": "Community cooling centre", "hi": "सामुदायिक शीतलन केंद्र"},
        "type": "community",
        "suits": {
            "heat_type": ["dense_built_low_green", "chronic_other", "episodic"],
            "roof_type": [],
            "built_form": ["dense"],
        },
        "cost_band": "med",
        "capex_range_inr": None,
        "evidence_ref": ["EV-AIDMI-HEAT"],
        "caveats": ["Needs a suitable public building"],
    },
]

BRIEFS = {
    "dense_built_low_green": {
        "means": "Persistently hot, densely built with little vegetation.",
        "rules": ["R-CR-01", "R-CP-01", "R-EC-01"],
        "check": [
            "Roof materials and available terraces",
            "Nearest public buildings for cooling points",
        ],
        "departments": ["Municipal engineering", "Urban forestry", "Health"],
    },
    "open_bare_or_industrial": {
        "means": "Persistently hot with low built share and low vegetation: bare ground or industrial land.",
        "rules": ["R-GR-01", "R-EC-01"],
        "check": ["Land use and ownership", "Industrial heat sources (not visible to Landsat)"],
        "departments": ["Town planning", "Industries", "Urban forestry"],
    },
    "episodic": {
        "means": "Hot in some scenes but not consistently.",
        "rules": ["R-EC-01"],
        "check": ["Which dates were hot (events, fires, harvest burning)"],
        "departments": ["Disaster management"],
    },
    "chronic_other": {
        "means": "Persistently hot without the dense-built or bare-land pattern.",
        "rules": ["R-CR-01", "R-EC-01"],
        "check": ["Local land cover and surface materials"],
        "departments": ["Municipal engineering"],
    },
    "not_hot": {
        "means": "Not among the hotter wards in this city on this analysis.",
        "rules": [],
        "check": [],
        "departments": [],
    },
    "undetermined": {
        "means": "Not enough valid data to type this ward.",
        "rules": [],
        "check": ["See missing fields"],
        "departments": [],
    },
}

GLOSSARY = {
    "LST": {
        "en": "surface temperature at a late-morning satellite pass",
        "hi": "सुबह के उपग्रह गुज़रने के समय की सतह का तापमान",
    },
    "cool roof": {"en": "cool roof", "hi": "कूल रूफ"},
    "subsidy": {"en": "subsidy", "hi": "सब्सिडी"},
    "payback": {"en": "payback period", "hi": "लागत वापसी अवधि"},
    "DISCOM": {
        "en": "electricity distribution company (DISCOM)",
        "hi": "बिजली वितरण कंपनी (DISCOM)",
    },
    "net metering": {"en": "net metering", "hi": "नेट मीटरिंग"},
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    files: dict[str, Any] = {
        "evidence": EVIDENCE,
        "rules": RULES,
        "cooling_options": COOLING,
        "heat_type_briefs": BRIEFS,
        "glossary": GLOSSARY,
        "advice": {"note": "advisories are deferred (see Agent/SCOPE_DEFERRED.md)"},
    }
    for name, obj in files.items():
        (OUT / f"{name}.json").write_text(
            json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(f"rules written to {OUT}")


if __name__ == "__main__":
    main()
