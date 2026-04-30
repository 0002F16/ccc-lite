#!/usr/bin/env python3
"""
CCC CV PDF Generator — tuned one-page version
"""

from copy import deepcopy
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

RENDERER_DIR = Path(__file__).resolve().parent
APP_ROOT = RENDERER_DIR.parent.parent
LOCAL_FONTS_DIR = APP_ROOT / "fonts"

BLACK = colors.HexColor("#1A1A1A")
ACCENT = colors.HexColor("#1F3864")
RULE_COLOR = colors.HexColor("#1F3864")
LIGHT_GRAY = colors.HexColor("#555555")

TIGHT_CONSTRAINTS = {
    "max_roles": 4,
    "max_bullets_total": 10,
    "max_bullets_per_role": [5, 3, 2, 2],
    "max_skill_categories": 4,
    "max_certifications": 3,
    "max_projects": 0,
}

BALANCED_CONSTRAINTS = {
    "max_roles": 4,
    "max_bullets_total": 12,
    "max_bullets_per_role": [6, 4, 3, 2],
    "max_skill_categories": 5,
    "max_certifications": 5,
    "max_projects": 0,
}

EXPAND_CONSTRAINTS = {
    "max_roles": 4,
    "max_bullets_total": 14,
    "max_bullets_per_role": [6, 5, 4, 3],
    "max_skill_categories": 5,
    "max_certifications": 5,
    "max_projects": 0,
}

DEFAULT_CONSTRAINTS = TIGHT_CONSTRAINTS


FONT_REGULAR = "Helvetica"
FONT_BOLD = "Helvetica-Bold"


def configure_fonts():
    global FONT_REGULAR, FONT_BOLD

    bundled_unicode = LOCAL_FONTS_DIR / "ArialUnicode.ttf"
    bundled_arial = LOCAL_FONTS_DIR / "Arial.ttf"
    bundled_arial_bold = LOCAL_FONTS_DIR / "Arial-Bold.ttf"

    regular_candidates = [
        str(bundled_unicode),
        str(bundled_arial),
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]
    bold_candidates = [
        str(bundled_arial_bold),
        str(bundled_unicode),
        str(bundled_arial),
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]

    regular_path = next((p for p in regular_candidates if Path(p).exists()), None)
    bold_path = next((p for p in bold_candidates if Path(p).exists()), regular_path)

    if not regular_path or not bold_path:
        return

    try:
        pdfmetrics.registerFont(TTFont("CCCArial", regular_path))
    except Exception:
        pass
    try:
        pdfmetrics.registerFont(TTFont("CCCArialBold", bold_path))
    except Exception:
        pass
    try:
        pdfmetrics.registerFontFamily("CCCArial", normal="CCCArial", bold="CCCArialBold")
    except Exception:
        pass

    registered = set(pdfmetrics.getRegisteredFontNames())
    if "CCCArial" in registered:
        FONT_REGULAR = "CCCArial"
    if "CCCArialBold" in registered:
        FONT_BOLD = "CCCArialBold"


configure_fonts()


def build_styles(compact=True, balanced=False):
    return {
        "name": ParagraphStyle(
            "name", fontName=FONT_BOLD, fontSize=(20 if balanced else 19) if compact else 22,
            leading=(23 if balanced else 22) if compact else 26, alignment=TA_CENTER,
            textColor=ACCENT, spaceAfter=1,
        ),
        "contact": ParagraphStyle(
            "contact", fontName=FONT_REGULAR, fontSize=(8.7 if balanced else 8.5) if compact else 9,
            leading=(11.0 if balanced else 10.5) if compact else 13, alignment=TA_CENTER,
            textColor=LIGHT_GRAY, spaceAfter=4 if compact else 6,
        ),
        "section": ParagraphStyle(
            "section", fontName=FONT_BOLD, fontSize=(9.4 if balanced else 9.2) if compact else 10,
            leading=(12.0 if balanced else 11.5) if compact else 14, textColor=ACCENT,
            spaceBefore=5 if compact else 8, spaceAfter=1,
            textTransform="uppercase",
        ),
        "role_header": ParagraphStyle(
            "role_header", fontName=FONT_REGULAR, fontSize=(9.25 if balanced else 9.1) if compact else 10,
            leading=(11.8 if balanced else 11.3) if compact else 14, textColor=BLACK,
            spaceBefore=3 if compact else 6, spaceAfter=1,
        ),
        "role_context": ParagraphStyle(
            "role_context", fontName=FONT_REGULAR, fontSize=(8.7 if balanced else 8.5) if compact else 9,
            leading=(11.0 if balanced else 10.6) if compact else 12.5, textColor=LIGHT_GRAY,
            spaceBefore=0, spaceAfter=1,
        ),
        "bullet": ParagraphStyle(
            "bullet", fontName=FONT_REGULAR, fontSize=(8.95 if balanced else 8.7) if compact else 9.5,
            leading=(11.8 if balanced else 11.2) if compact else 13.5, leftIndent=10, firstLineIndent=-10,
            textColor=BLACK, spaceAfter=1,
        ),
        "summary": ParagraphStyle(
            "summary", fontName=FONT_REGULAR, fontSize=(9.0 if balanced else 8.8) if compact else 9.5,
            leading=(12.0 if balanced else 11.6) if compact else 14, textColor=BLACK, spaceAfter=2,
        ),
        "skills": ParagraphStyle(
            "skills", fontName=FONT_REGULAR, fontSize=(8.9 if balanced else 8.7) if compact else 9.5,
            leading=(11.8 if balanced else 11.3) if compact else 14, textColor=BLACK, spaceAfter=1,
        ),
        "edu_title": ParagraphStyle(
            "edu_title", fontName=FONT_BOLD, fontSize=(9.0 if balanced else 8.8) if compact else 9.5,
            leading=(11.4 if balanced else 11) if compact else 13, textColor=BLACK, spaceBefore=2, spaceAfter=0,
        ),
        "edu_sub": ParagraphStyle(
            "edu_sub", fontName=FONT_REGULAR, fontSize=(8.9 if balanced else 8.7) if compact else 9.5,
            leading=(11.4 if balanced else 11) if compact else 13, textColor=LIGHT_GRAY, spaceAfter=1,
        ),
    }


def rule(story, compact=True):
    story.append(HRFlowable(width="100%", thickness=0.7, color=RULE_COLOR, spaceAfter=2 if compact else 4))


def section_header(story, styles, title, compact=True):
    story.append(Paragraph(title, styles["section"]))
    rule(story, compact=compact)


def bullet_para(styles, text):
    return Paragraph(f"• {text}", styles["bullet"])


def clamp_list(items, limit):
    return items[: max(0, limit)]


def estimate_underfill_level(cv_data):
    roles = cv_data.get("experience", [])
    bullets_total = sum(len(r.get("bullets", [])) for r in roles)
    summary_len = len(cv_data.get("summary", ""))
    skills_count = len(cv_data.get("skills", {}))
    role_count = len(roles)
    certs_count = len(cv_data.get("certifications", []))
    # Heuristic tiers for sparse one-page resumes.
    if bullets_total <= 9 and summary_len < 430 and (skills_count <= 4 or role_count <= 3):
        return "high"
    if bullets_total <= 11 and (summary_len < 520 or skills_count <= 4 or certs_count == 0):
        return "medium"
    return "none"


def apply_guardrails(cv_data, constraints=None):
    constraints = constraints or DEFAULT_CONSTRAINTS
    data = deepcopy(cv_data)

    data["experience"] = clamp_list(data.get("experience", []), constraints["max_roles"])

    budgets = constraints.get("max_bullets_per_role", [])
    remaining = constraints.get("max_bullets_total", 999)
    trimmed_roles = []
    for i, role in enumerate(data["experience"]):
        per_role = budgets[i] if i < len(budgets) else 2
        allowed = min(per_role, remaining)
        role = deepcopy(role)
        role["bullets"] = clamp_list(role.get("bullets", []), allowed)
        remaining -= len(role["bullets"])
        trimmed_roles.append(role)
    data["experience"] = trimmed_roles

    skills = data.get("skills", {})
    kept = {}
    for i, (k, v) in enumerate(skills.items()):
        if i >= constraints.get("max_skill_categories", 999):
            break
        kept[k] = v
    data["skills"] = kept

    if constraints.get("max_certifications", 0) == 0:
        data.pop("certifications", None)
    else:
        data["certifications"] = clamp_list(data.get("certifications", []), constraints["max_certifications"])

    if constraints.get("max_projects", 0) == 0:
        data.pop("projects", None)
    else:
        data["projects"] = clamp_list(data.get("projects", []), constraints["max_projects"])

    return data


def render_header(story, styles, data):
    story.append(Paragraph(data["name"], styles["name"]))
    contact = " | ".join(filter(None, [data.get("city"), data.get("phone"), data.get("email"), data.get("linkedin")]))
    if data.get("work_authorization"):
        contact = f"{contact}<br/>{data.get('work_authorization')}"
    story.append(Paragraph(contact, styles["contact"]))
    story.append(Spacer(1, 2))


def render_summary(story, styles, data, compact=True):
    section_header(story, styles, "Professional Summary", compact=compact)
    summary = str(data.get("summary", "")).replace("\n", "<br/>")
    story.append(Paragraph(summary, styles["summary"]))
    story.append(Spacer(1, 1))


def render_experience(story, styles, data, compact=True):
    section_header(story, styles, "Professional Experience", compact=compact)
    for role in data["experience"]:
        title_part = f"<b>{role['title']}</b>"
        parts = [title_part] + [role.get(k, "") for k in ("company", "location", "dates") if role.get(k)]
        story.append(Paragraph(" | ".join(parts), styles["role_header"]))
        if role.get("context"):
            story.append(Paragraph(role["context"], styles["role_context"]))
        for b in role.get("bullets", []):
            story.append(bullet_para(styles, b))
        story.append(Spacer(1, 1))


def render_education(story, styles, data, compact=True):
    section_header(story, styles, "Education", compact=compact)
    for edu in data["education"]:
        story.append(Paragraph(edu["degree"], styles["edu_title"]))
        parts = [edu.get("school", "")]
        if edu.get("dates"):
            parts.append(edu["dates"])
        if edu.get("note"):
            parts.append(edu["note"])
        story.append(Paragraph(" | ".join(filter(None, parts)), styles["edu_sub"]))


def render_skills(story, styles, data, compact=True):
    section_header(story, styles, "Skills", compact=compact)
    for category, items in data["skills"].items():
        story.append(Paragraph(f"<b>{category}:</b> {items}", styles["skills"]))
    story.append(Spacer(1, 1))


def render_certifications(story, styles, data, compact=True):
    certs = data.get("certifications", []) or []
    if not certs:
        return
    section_header(story, styles, "Certifications", compact=compact)
    cert_line = "; ".join(str(c) for c in certs if str(c).strip())
    if cert_line:
        story.append(Paragraph(cert_line, styles["skills"]))
        story.append(Spacer(1, 1))


def generate_cv(cv_data: dict, output_path: str = "cv_output.pdf", *, one_page=True, constraints=None, auto_retry_underfill=True, education_first=False):
    mode = "full"
    if not one_page:
        data = deepcopy(cv_data)
        balanced = False
        expanded = False
    else:
        initial_constraints = constraints or DEFAULT_CONSTRAINTS
        data = apply_guardrails(cv_data, initial_constraints)
        balanced = initial_constraints == BALANCED_CONSTRAINTS
        expanded = initial_constraints == EXPAND_CONSTRAINTS
        mode = "tight"
        if auto_retry_underfill:
            underfill = estimate_underfill_level(data)
            if underfill == "high":
                data = apply_guardrails(cv_data, EXPAND_CONSTRAINTS)
                balanced = True
                expanded = True
                mode = "expand-retry"
            elif underfill == "medium":
                data = apply_guardrails(cv_data, BALANCED_CONSTRAINTS)
                balanced = True
                expanded = False
                mode = "balanced-retry"

    compact = one_page
    left_right = 12.5 if expanded else (12 if balanced else 11)
    top_bottom = 11.5 if expanded else (11 if balanced else 10)
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=(left_right if compact else 15) * mm,
        rightMargin=(left_right if compact else 15) * mm,
        topMargin=(top_bottom if compact else 14) * mm,
        bottomMargin=(top_bottom if compact else 14) * mm,
    )
    styles = build_styles(compact=compact, balanced=(balanced or expanded))
    story = []
    render_header(story, styles, data)
    render_summary(story, styles, data, compact=compact)
    if education_first:
        render_education(story, styles, data, compact=compact)
        render_experience(story, styles, data, compact=compact)
    else:
        render_experience(story, styles, data, compact=compact)
        render_education(story, styles, data, compact=compact)
    render_skills(story, styles, data, compact=compact)
    render_certifications(story, styles, data, compact=compact)
    doc.build(story)
    print(f"✅ CV written to: {output_path} [{mode}]")
