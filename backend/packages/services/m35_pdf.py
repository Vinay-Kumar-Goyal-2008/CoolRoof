"""M35+36 Checklist selection and the assistance-summary PDF (fpdf2 + HarfBuzz shaping).

Replaces the spec's WeasyPrint (needs GTK on Windows). Jinja2 is not needed for layout —
text comes from the assessment's pre-formatted en/hi strings so numbers match the UI and
agent. PDF text extracted back with PyMuPDF equals the source text after control
characters (emitted at Devanagari conjuncts) are stripped.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

from fpdf import FPDF

from packages.core.enums import Language
from packages.core.errors import IncompleteError
from packages.core.i18n import format_number
from packages.core.settings import BACKEND_ROOT
from packages.services.policy_store import PolicyStore, PolicyType

__all__ = ["build_pdf", "extract_text", "find_font", "select_checklist", "strip_controls"]

FONT_CANDIDATES = (
    BACKEND_ROOT / "assets" / "fonts" / "NotoSansDevanagari-Regular.ttf",
    Path(r"C:\Windows\Fonts\Nirmala.ttc"),
    Path("/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf"),
)
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def find_font() -> Path:
    for path in FONT_CANDIDATES:
        if path.exists():
            return path
    raise FileNotFoundError(
        "no Devanagari font found; place NotoSansDevanagari-Regular.ttf in backend/assets/fonts"
    )


def find_latin_font() -> Path:
    candidates = (
        BACKEND_ROOT / "assets" / "fonts" / "NotoSans-Regular.ttf",
        Path("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"),
    )
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError("no Latin font; place NotoSans-Regular.ttf in backend/assets/fonts")


def strip_controls(text: str) -> str:
    return _CONTROL.sub("", text)


def select_checklist(store: PolicyStore, state: str, discom: str, on: date) -> dict[str, Any]:
    """State+DISCOM → state → generic. The level used is recorded; generic is 'confirm on portal'."""
    record, level = store.resolve(PolicyType.CHECKLIST, state=state, discom=discom, on=on)
    if record is None:
        raise IncompleteError("no checklist template available")
    return {
        **record.doc,
        "level": level,
        "banner": {
            "en": "Confirm each step on the official portal.",
            "hi": "हर चरण की पुष्टि आधिकारिक पोर्टल पर करें।",
        }
        if level == "national"
        else None,
    }


def _fmt(label: dict[str, str], lang: Language) -> str:
    return label[lang.value]


def _draw_outline(pdf: FPDF, points_m: list[tuple[float, float]], box_mm: float = 45.0) -> None:
    """Vector roof outline scaled into a square box (y up → page y down)."""
    xs, ys = [p[0] for p in points_m], [p[1] for p in points_m]
    span = max(max(xs) - min(xs), max(ys) - min(ys)) or 1.0
    scale = box_mm / span
    x0, y0 = pdf.get_x() + 4, pdf.get_y() + 2
    poly = [((x - min(xs)) * scale + x0, (max(ys) - y) * scale + y0) for x, y in points_m]
    pdf.set_draw_color(11, 92, 173)
    pdf.set_fill_color(214, 229, 245)
    pdf.set_line_width(0.5)
    pdf.polygon(poly, style="DF")
    pdf.set_y(y0 + box_mm * (max(ys) - min(ys)) / span + 4)


def build_pdf(
    assessment: dict[str, Any],
    checklist: dict[str, Any],
    lang: Language,
    engine_version: str,
    consent: dict[str, str] | None = None,
) -> bytes:
    """Render one language of the summary. ``consent`` holds name/address only if given."""
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_font("Body", fname=str(find_latin_font()))  # Latin letters, digits, rupee sign
    pdf.add_font("Deva", fname=str(find_font()))  # Devanagari fallback
    pdf.set_fallback_fonts(["Deva"])
    pdf.add_page()
    pdf.set_text_shaping(True)
    lang_key = lang.value
    strings = {  # static strings
        "title": {"en": "Rooftop solar - assistance summary", "hi": "रूफटॉप सोलर - सहायता सारांश"},
        "head": {
            "en": "Assistance summary - not the official application - apply at pmsuryaghar.gov.in",
            "hi": "सहायता सारांश - आधिकारिक आवेदन नहीं - pmsuryaghar.gov.in पर आवेदन करें",
        },
        "system": {"en": "System and generation", "hi": "सिस्टम और उत्पादन"},
        "outline": {"en": "Roof outline (drawn on the map)", "hi": "छत की रूपरेखा (नक्शे पर बनाई गई)"},
        "subsidy": {"en": "Subsidy", "hi": "सब्सिडी"},
        "payback": {"en": "Payback", "hi": "लागत वापसी"},
        "checklist": {"en": "Checklist", "hi": "चेकलिस्ट"},
        "applicant": {
            "en": "Applicant details (provided with consent)",
            "hi": "आवेदक विवरण (सहमति से दिया गया)",
        },
    }

    def heading(text: str) -> None:
        pdf.set_font("Body", size=13)
        pdf.set_fill_color(235, 240, 245)
        pdf.cell(0, 8, text, fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

    def line(text: str, size: int = 10) -> None:
        pdf.set_font("Body", size=size)
        pdf.multi_cell(0, 5.5, text, new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Body", size=16)
    pdf.cell(0, 10, strings["title"][lang_key], new_x="LMARGIN", new_y="NEXT")
    line(strings["head"][lang_key], 9)
    pdf.ln(3)

    system = assessment.get("system") or {}
    heading(strings["system"][lang_key])
    if system:
        kw = system["kw_recommended"]
        gen = system["generation_year1_kwh"]
        if lang_key == "en":
            line(
                f"Recommended size: {format_number(kw, decimals=0)} kW "
                f"(limited by: {system['limiting_factor']})"
            )
            line(
                f"Year-1 generation: {format_number(gen['low'])} to {format_number(gen['high'])} kWh "
                f"(base {format_number(gen['base'])})"
            )
        else:
            line(f"अनुशंसित क्षमता: {format_number(kw, decimals=0)} किलोवाट")
            line(
                f"पहले वर्ष का उत्पादन: {format_number(gen['low'])} से {format_number(gen['high'])} "
                f"यूनिट (आधार {format_number(gen['base'])})"
            )
        line("Assumptions: " + ", ".join(system["assumptions"]), 8)
    else:
        line(
            "Not available - more information needed."
            if lang_key == "en"
            else "उपलब्ध नहीं - अधिक जानकारी चाहिए।"
        )

    outline = (assessment.get("roof") or {}).get("outline")
    if outline:
        heading(strings["outline"][lang_key])
        _draw_outline(pdf, outline["points_m"])
        line(
            f"{format_number(outline['area_m2'], decimals=0)} m²"
            + (
                (
                    "  -  differs from the area entered"
                    if lang_key == "en"
                    else "  -  दर्ज क्षेत्र से भिन्न"
                )
                if outline.get("outline_changed")
                else ""
            ),
            8,
        )

    sub = assessment.get("subsidy")
    heading(strings["subsidy"][lang_key])
    if sub:
        line(f"{sub['amount'][lang_key]}  ({sub['policy_version']}, {sub['effective_date']})")
        line(f"Source: {sub['source_url']}  |  Record hash: {sub['record_hash']}", 8)
        line(
            "State top-up: unknown. Eligibility unconfirmed - decided on the national portal."
            if lang_key == "en"
            else "राज्य टॉप-अप: अज्ञात। पात्रता अपुष्ट - राष्ट्रीय पोर्टल पर तय होती है।"
        )

    pb = assessment.get("payback") or {}
    heading(strings["payback"][lang_key])
    if pb.get("status") == "ok":
        lo, hi = pb["payback_simple_years"]["high"], pb["payback_simple_years"]["low"]
        line(
            f"{lo} - {hi} years (simple payback range)"
            if lang_key == "en"
            else f"{lo} से {hi} वर्ष (सरल लागत वापसी सीमा)"
        )
        if pb.get("tariff_synthetic"):
            line(
                "WARNING: synthetic test tariff."
                if lang_key == "en"
                else "चेतावनी: कृत्रिम परीक्षण टैरिफ़।",
                8,
            )
    else:
        line(
            f"Not shown: {pb.get('status', 'unavailable')}"
            if lang_key == "en"
            else f"नहीं दिखाया गया: {pb.get('status', 'unavailable')}"
        )

    heading(strings["checklist"][lang_key])
    if checklist.get("banner"):
        line(checklist["banner"][lang_key], 9)
    for i, item in enumerate(checklist["items"], 1):
        line(f"{i}. {item['title_i18n'][lang_key]}", 10)
        line(f"   {item['detail_i18n'][lang_key]}", 8)

    if consent:
        heading(strings["applicant"][lang_key])
        line(f"{consent.get('name', '')}  |  {consent.get('address', '')}")

    pdf.ln(4)
    line(
        f"Generated {date.today().isoformat()} | engine {engine_version} | "
        f"policy {assessment.get('policy_version')} | input {assessment['input_hash'][:12]}",
        7,
    )
    return bytes(pdf.output())


def extract_text(pdf_bytes: bytes) -> str:
    import pymupdf

    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        return "".join(page.get_text() for page in doc)
