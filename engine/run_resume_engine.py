#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

APP_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_ROOT = APP_ROOT / "engine"
RULES_PATH = EXPERIMENT_ROOT / "rules" / "merged_ccc_rules.json"
PROMPT_TEMPLATE_PATH = EXPERIMENT_ROOT / "rules" / "prompt_template.md"
DEFAULT_RUNS_DIR = EXPERIMENT_ROOT / "runs"
CCC_ROOT = APP_ROOT
SHARED_RENDERER_DIR = EXPERIMENT_ROOT / "renderer"
LAYOUT_AUDIT_SCRIPT = EXPERIMENT_ROOT / "check_resume_layout.py"

sys.path.insert(0, str(SHARED_RENDERER_DIR))
from ccc_cv_generator_tuned import generate_cv  # noqa: E402

DATE_FMT = "%Y-%m"

GENERIC_SOFT_SKILL_CERT_PATTERNS = [
    r"customer service",
    r"communication",
    r"professional development",
    r"leadership fundamentals",
    r"time management",
]
RECOGNISED_CERT_ISSUERS = {
    "google",
    "microsoft",
    "aws",
    "amazon",
    "acams",
    "cfa",
    "pmi",
    "cima",
    "acca",
    "linkedin learning",
    "salesforce",
    "oracle",
    "sap",
    "python institute",
}
SOFT_SKILLS = {
    "team player",
    "communication",
    "results-driven",
    "detail-oriented",
    "motivated",
    "hardworking",
    "problem solving",
    "great communication skills",
    "service-minded",
    "customer-oriented",
    "teamwork approach",
}
BANNED_PHRASES = [
    "responsible for",
    "worked on",
    "assisted with",
    "assisted",
    "helped",
    "participated in",
    "involved in",
    "duties included",
    "was tasked with",
]


def slugify(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", value.strip()).strip("-").lower()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_jobs(csv_path: Path):
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def find_job(rows: list[dict], job_id: str) -> dict:
    for row in rows:
        if (row.get("job_id") or "").strip() == job_id:
            return row
    raise SystemExit(f"job_id not found: {job_id}")


def build_client_paths(client_name: str) -> dict[str, Path]:
    client_dir = APP_ROOT / "data" / "clients" / slugify(client_name)
    pipeline_dir = client_dir
    return {
        "client_dir": client_dir,
        "pipeline_dir": pipeline_dir,
        "profile": client_dir / "master_profile.json",
        "jobs": client_dir / "jobs.csv",
    }


def render_schema() -> dict:
    rules = load_json(RULES_PATH)
    return rules["output_schema"]


def parse_date_token(value: str | None) -> datetime | None:
    if not value:
        return None
    value = str(value).strip()
    if not value:
        return None
    if value.lower() == "present":
        return datetime.now(UTC)
    if re.fullmatch(r"\d{4}-\d{2}", value):
        return datetime.strptime(value, DATE_FMT).replace(tzinfo=UTC)
    if re.fullmatch(r"\d{4}", value):
        return datetime.strptime(f"{value}-01", DATE_FMT).replace(tzinfo=UTC)
    m = re.search(r"([A-Z][a-z]{2})\s+(\d{4})", value)
    if m:
        return datetime.strptime(f"{m.group(2)}-{datetime.strptime(m.group(1), '%b').month:02d}", DATE_FMT).replace(tzinfo=UTC)
    return None


def months_between(start: datetime | None, end: datetime | None) -> int:
    if not start or not end or end < start:
        return 0
    return (end.year - start.year) * 12 + (end.month - start.month) + 1


def format_resume_date_token(value: str | None) -> str:
    if not value:
        return ""
    raw = str(value).strip()
    if not raw:
        return ""
    if raw.lower() == "present":
        return "Present"
    parsed = parse_date_token(raw)
    if parsed:
        return parsed.strftime("%b %Y")
    return raw


def format_resume_date_range(start: str | None, end: str | None) -> str:
    start_fmt = format_resume_date_token(start)
    end_fmt = format_resume_date_token(end)
    if start_fmt and end_fmt:
        return f"{start_fmt} – {end_fmt}"
    return start_fmt or end_fmt


def normalize_existing_date_range(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    parts = [part.strip() for part in re.split(r"\s*[–-]\s*", raw) if part.strip()]
    if len(parts) == 2:
        return format_resume_date_range(parts[0], parts[1])
    return format_resume_date_token(raw)


def profile_roles(profile: dict) -> list[dict]:
    return deepcopy(profile.get("experience", []) or [])


def total_experience_months(profile: dict) -> int:
    total = 0
    for role in profile_roles(profile):
        total += months_between(parse_date_token(role.get("startDate")), parse_date_token(role.get("endDate")))
    return total


def client_level(profile: dict) -> str:
    raw = str((profile.get("core_positioning") or {}).get("level") or "").strip().lower()
    if raw in {"junior", "mid", "senior", "executive"}:
        return raw
    years = total_experience_months(profile) / 12.0
    if years < 3:
        return "junior"
    if years < 8:
        return "mid"
    if years < 15:
        return "senior"
    return "executive"


def page_budget(profile: dict) -> int:
    return 1 if total_experience_months(profile) / 12.0 < 3 else 2


def choose_positioning(profile: dict, level: str) -> str:
    raw = str((profile.get("core_positioning") or {}).get("strategy") or "").strip().lower()
    if "transfer" in raw:
        return "transferable_value"
    mapping = {
        "junior": "growth_potential",
        "mid": "proven_executor",
        "senior": "strategic_leader",
        "executive": "strategic_leader",
    }
    return mapping[level]


def detect_thin_input(profile: dict) -> bool:
    roles = profile_roles(profile)
    role_count = len(roles)
    years = total_experience_months(profile) / 12.0
    has_numbers = any(re.search(r"\d", json.dumps(role, ensure_ascii=False)) for role in roles)
    return (not has_numbers) or years < 2 or role_count < 3


def collect_summary_evidence(profile: dict, max_items: int = 6) -> list[str]:
    evidence: list[str] = []
    for item in profile.get("summary_base", []) or []:
        text = re.sub(r"\s+", " ", str(item)).strip()
        if text:
            evidence.append(text)
    for role in profile_roles(profile):
        for bullet in role.get("highlights", []) or []:
            text = re.sub(r"\s+", " ", re.sub(r"\*\*", "", str(bullet))).strip()
            if not text:
                continue
            if re.search(r"\d|%|\$|€|£", text):
                evidence.append(text)
            elif len(evidence) < max_items:
                evidence.append(text)
            if len(evidence) >= max_items:
                break
        if len(evidence) >= max_items:
            break
    deduped: list[str] = []
    seen = set()
    for item in evidence:
        low = item.lower()
        if low in seen:
            continue
        seen.add(low)
        deduped.append(item)
    return deduped[:max_items]


def build_transferable_bridge(profile: dict, job: dict) -> str:
    client = profile.get("client", {}) or {}
    positioning = profile.get("core_positioning", {}) or {}
    label = str(client.get("label") or "").strip()
    notes = str(positioning.get("notes") or "").strip()
    title = str(job.get("position") or "the target role").strip()
    if notes:
        return f"Bridge the client's proven background into {title} honestly using this positioning guidance: {notes}"
    if label:
        return f"Position the client for {title} using this source label as the factual bridge: {label}"
    return f"Position the client for {title} by translating source evidence into target-role language without inventing direct ownership they did not have."


def extract_job_keywords(job: dict, max_keywords: int = 18) -> list[str]:
    jd = str(job.get("jd_text") or "")
    lines = [line.strip() for line in jd.splitlines() if line.strip()]
    candidates: list[str] = []
    for line in lines:
        if len(line) > 100:
            continue
        if any(ch in line for ch in [":", "(", ")", "/"]):
            line = line.replace("/", " ")
        if 2 <= len(line.split()) <= 5:
            candidates.append(line)
    token_candidates = re.findall(r"\b[A-Za-z][A-Za-z0-9&+\-]{2,}(?:\s+[A-Za-z][A-Za-z0-9&+\-]{2,}){0,2}\b", jd)
    candidates.extend(token_candidates)
    cleaned = []
    seen = set()
    stop = {"what you ll", "role overview", "what you", "we re", "the", "and", "for", "with", "our", "who we re looking"}
    for item in candidates:
        item = re.sub(r"\s+", " ", item).strip(" -•\t").strip()
        if not item:
            continue
        low = item.lower()
        if low in seen or low in stop:
            continue
        if len(low) < 4:
            continue
        if low in {"hybrid", "apply", "saved", "present", "full-time"}:
            continue
        seen.add(low)
        cleaned.append(item)
    preferred = []
    for item in cleaned:
        low = item.lower()
        if any(term in low for term in [
            "excel",
            "report",
            "analysis",
            "system",
            "cloud",
            "successfactors",
            "data",
            "knowledge base",
            "troubleshooting",
            "project",
            "administrator",
            "compliance",
            "quality",
            "case",
            "operations",
            "administration",
            "reporting",
            "office 365",
            "hr",
            "people",
            "culture",
        ]):
            preferred.append(item)
    merged = preferred + [x for x in cleaned if x not in preferred]
    return merged[:max_keywords]


def build_plan(profile: dict, job: dict) -> dict[str, Any]:
    level = client_level(profile)
    budget = page_budget(profile)
    plan = {
        "client_level": level,
        "page_budget": budget,
        "positioning": choose_positioning(profile, level),
        "positioning_notes": (profile.get("core_positioning") or {}).get("notes"),
        "client_label": (profile.get("client") or {}).get("label"),
        "summary_base": profile.get("summary_base", []) or [],
        "summary_evidence_pack": collect_summary_evidence(profile),
        "transferable_bridge": build_transferable_bridge(profile, job),
        "thin_input": detect_thin_input(profile),
        "experience_months": total_experience_months(profile),
        "experience_years_estimate": round(total_experience_months(profile) / 12.0, 1),
        "exact_target_title": job.get("position"),
        "keyword_targets": extract_job_keywords(job),
        "section_order": [
            "name_contact",
            "professional_summary",
            "education",
            "professional_experience",
            "skills",
            "projects",
            "certifications",
        ] if budget == 1 else [
            "name_contact",
            "professional_summary",
            "professional_experience",
            "education",
            "skills",
            "projects",
            "certifications",
        ],
        "skills_row_cap": 3 if budget == 1 else 5,
        "summary_style": {
            "target": "sound like a recruiter-ready positioning statement, not a generic profile summary",
            "prefer_contextual_framing": True,
            "prefer_transferable_bridge_when_adjacent": True,
            "avoid_abstract_compression": True,
            "prefer_role_language_over_meta_language": True
        },
        "bullet_generation_mode": "llm_planner_writer_validated",
        "bullet_style": {
            "llm_plans_role_bullets_before_writing": True,
            "llm_rewrites_bullets_after_resume_draft": True,
            "prefer_contextual_reframing": True,
            "prefer_transferable_target_language_when_adjacent": True,
            "validator_keeps_source_fallback_only_when_needed": True
        },
        "skills_generation_mode": "llm_planner_writer_validated",
        "skills_rules": {
            "llm_plans_categories_before_writing": True,
            "llm_writes_final_skills_after_resume_draft": True,
            "llm_owns_final_categories": True,
            "preserve_llm_order": True,
            "languages_last": True,
            "certifications_row_allowed": True,
            "validator_may_trim_excess_rows": True,
            "validator_may_drop_unsupported_items": False,
            "validator_prefers_audit_over_dropping": True,
            "intent": "Produce a recruiter-facing shortlist, not a profile dump.",
            "prioritisation_order": [
                "exact_jd_match_supported_by_source",
                "near_match_supported_by_source",
                "secondary_supporting_tools_if_space_allows"
            ],
            "prefer_specific_category_labels": True,
            "avoid_generic_category_labels": ["Skills", "Other", "Additional Skills", "Tools"],
            "prefer_stronger_fewer_categories": True,
            "order_items_by_role_relevance": True
        },
        "source_skill_inventory": source_skill_inventory(profile),
        "max_roles": 4 if budget == 1 else 6,
    }
    return plan


def build_prompt(profile: dict, job: dict, plan: dict, mode: str = "full") -> str:
    schema = render_schema()
    if mode == "slim":
        compact_profile = {
            "client": profile.get("client", {}),
            "core_positioning": profile.get("core_positioning", {}),
            "experience": profile.get("experience", []),
            "education": profile.get("education", []),
            "skills": profile.get("skills", {}),
            "languages": profile.get("languages", []),
            "certifications": profile.get("certifications", []),
        }
        return (
            "Return only valid JSON matching this schema. "
            f"Make the strongest truthful CCC resume payload for the target role with PAGE_BUDGET={plan['page_budget']}. "
            f"Client level={plan['client_level']}; positioning={plan['positioning']}. "
            "Use HTML <b> tags for the exact target title in summary sentence 1, the strongest proof point in the summary, and the lead phrase of every bullet. "
            "Do not invent experience, metrics, tools, certifications, or domain expertise. "
            "Use transferable framing honestly if the fit is adjacent. "
            "Make the summary sound like a recruiter-ready positioning statement, not a generic profile summary. "
            "Use the build plan's summary_base, summary_evidence_pack, client_label, and transferable_bridge in context. "
            "If the background is adjacent, actively bridge into the target role in natural language instead of falling back to vague professional-summary wording. "
            "Prefer contextual target-role phrasing over abstract compression and avoid bland lines like strong communication skills or experience applying standards. "
            "No first person. No generic openers. Hard skills only. Use exact JD terminology where natural. "
            "You must choose the final skills section intentionally, including category labels, item selection, and order. "
            "Treat the skills section as a curated recruiter shortlist, not a dump of everything in the source profile. "
            "Prioritise exact JD matches supported by source evidence first, then near-match supported skills, then secondary tools only if space remains. "
            "Prefer concrete multi-word recruiter phrases over over-compressed abstractions, and do not flatten strong source phrasing into weak generic nouns. "
            "Common baseline productivity tools like Excel, Microsoft Office, PowerPoint, Word, Outlook, or Google Workspace may be included when they materially help recruiter fit, even if the source profile does not spell them out line by line. "
            "Prefer fewer stronger categories with specific recruiter-meaningful labels, mirror the hiring manager mental model, group related systems when useful, and order each category from strongest to weakest. "
            "Prefer returning skills category values as ordered arrays when that preserves stronger grouped wording. "
            "Respect the skills_row_cap in the build plan, keep Languages last, and be conservative only with niche unsupported systems or tools. "
            "For under-3-year profiles keep education above experience in the logical content plan, and for 3+ years keep education below experience. "
            "Every bullet must pass the so-what test and avoid banned phrases.\n\n"
            f"Build plan:\n{json.dumps(plan, ensure_ascii=False, separators=(',', ':'))}\n\n"
            f"Schema:\n{json.dumps(schema, ensure_ascii=False, separators=(',', ':'))}\n\n"
            f"Client profile:\n{json.dumps(compact_profile, ensure_ascii=False, separators=(',', ':'))}\n\n"
            f"Target job:\n{json.dumps(job, ensure_ascii=False, separators=(',', ':'))}"
        )

    template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    rules = load_json(RULES_PATH)
    return (
        template
        .replace("{SCHEMA_JSON}", json.dumps(schema, ensure_ascii=False, indent=2))
        .replace("{CLIENT_PROFILE_JSON}", json.dumps(profile, ensure_ascii=False, indent=2))
        .replace("{JOB_JSON}", json.dumps(job, ensure_ascii=False, indent=2))
        .replace("{RULES_JSON}", json.dumps(rules, ensure_ascii=False, indent=2))
        .replace("{BUILD_PLAN_JSON}", json.dumps(plan, ensure_ascii=False, indent=2))
    )


def build_skills_plan_prompt(profile: dict, job: dict, plan: dict) -> str:
    schema = {
        "category_order": ["str"],
        "category_plan": [
            {
                "label": "str",
                "why": "str",
                "items": ["str"],
            }
        ],
        "keep_certifications_in_skills": True,
        "certification_items": ["str"],
        "language_items": ["str"],
        "must_keep_groups": ["str"],
        "avoid": ["str"],
    }
    return (
        "Return ONLY valid JSON. You are designing the final recruiter-facing skills block for a CCC resume. "
        "Plan only the skills section. Do not write summary or experience. "
        "Choose categories and item phrasing that match how hiring managers scan this role. "
        "Prefer exact JD terminology where natural, then near-match recruiter phrasing clearly supported by source evidence. "
        "Prefer concrete multi-word phrases over abstract compressed nouns. "
        "Group tools and systems into stronger recruiter-facing labels when useful, including parenthetical detail such as system names. "
        "You may include Certifications as a skills row when it helps recruiter fit and the source supports it. "
        "Languages must be last. Keep the total row count within skills_row_cap. "
        "Avoid generic categories like Skills or Other. Avoid weak fragments unless they are standard recruiter wording. "
        "Output schema:\n"
        f"{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
        f"Build plan:\n{json.dumps(plan, ensure_ascii=False, indent=2)}\n\n"
        f"Client profile:\n{json.dumps(profile, ensure_ascii=False, indent=2)}\n\n"
        f"Target job:\n{json.dumps(job, ensure_ascii=False, indent=2)}"
    )



def build_skills_writer_prompt(profile: dict, job: dict, plan: dict, current_resume: dict, skills_plan: dict) -> str:
    schema = {
        "skills": {
            "Category": ["Item 1", "Item 2"]
        }
    }
    return (
        "Return ONLY valid JSON. You are writing the final recruiter-facing skills section for a CCC resume. "
        "Write only the skills object. Do not rewrite summary, experience, or education. "
        "Use the skills plan as the governing structure unless a tiny wording adjustment makes the result more recruiter-natural. "
        "Prefer strong multi-word recruiter phrases, preserve grouped system labels, and avoid over-abstracting source evidence. "
        "Mirror the hiring manager mental model: core functional scope first, then compliance/risk or reporting if relevant, then tools/systems, then certifications if strategically useful, with Languages last. "
        "Use exact JD terminology where natural. Common baseline tools like Excel, Microsoft Office, Word, PowerPoint, Outlook, or Google Workspace may be included when role-natural. "
        "Return category values as ordered arrays when that preserves grouped wording best. "
        "Do not add soft skills. Do not invent niche systems unsupported by source evidence. "
        "Output schema:\n"
        f"{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
        f"Build plan:\n{json.dumps(plan, ensure_ascii=False, indent=2)}\n\n"
        f"Skills plan:\n{json.dumps(skills_plan, ensure_ascii=False, indent=2)}\n\n"
        f"Current resume draft:\n{json.dumps(current_resume, ensure_ascii=False, indent=2)}\n\n"
        f"Client profile:\n{json.dumps(profile, ensure_ascii=False, indent=2)}\n\n"
        f"Target job:\n{json.dumps(job, ensure_ascii=False, indent=2)}"
    )



def build_bullet_plan_prompt(profile: dict, job: dict, plan: dict, current_resume: dict) -> str:
    schema = {
        "roles": [
            {
                "title": "str",
                "company": "str",
                "bucket": "current_or_last2|2to5|5to10|10to15|15plus",
                "target_bullet_count": 4,
                "role_positioning": "str",
                "must_preserve_evidence": ["str"],
                "jd_terms_to_weave": ["str"],
                "bullet_objectives": ["str"]
            }
        ]
    }
    return (
        "Return ONLY valid JSON. You are planning the final experience bullets for a CCC resume. "
        "Plan only the bullets. Do not rewrite the full resume yet. "
        "For each role in the current resume draft, decide what each bullet should accomplish so the role reads closer to the target job while staying truthful. "
        "Use the source profile evidence and the JD to shape stronger recruiter-facing bullets. "
        "Prefer contextual, role-relevant reframing over generic task narration. "
        "Do not invent new tools, metrics, systems, or direct domain ownership. "
        "Each role plan should identify the evidence that must stay grounded plus the JD terms that can be woven in naturally. "
        "Respect age-bucket bullet counts from the build plan. "
        "Output schema:\n"
        f"{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
        f"Build plan:\n{json.dumps(plan, ensure_ascii=False, indent=2)}\n\n"
        f"Current resume draft:\n{json.dumps(current_resume, ensure_ascii=False, indent=2)}\n\n"
        f"Client profile:\n{json.dumps(profile, ensure_ascii=False, indent=2)}\n\n"
        f"Target job:\n{json.dumps(job, ensure_ascii=False, indent=2)}"
    )



def build_bullet_writer_prompt(profile: dict, job: dict, plan: dict, current_resume: dict, bullet_plan: dict) -> str:
    schema = {
        "experience": [
            {
                "title": "str",
                "company": "str",
                "bullets": ["<b>Lead phrase</b> action plus significance"]
            }
        ]
    }
    return (
        "Return ONLY valid JSON. You are writing the final experience bullets for a CCC resume. "
        "Rewrite only the bullets for each existing experience role. Do not change titles, companies, dates, education, or summary. "
        "Use the bullet plan as the governing structure unless a tiny wording adjustment improves recruiter readability. "
        "Every bullet must begin with a short HTML bold lead phrase using <b> tags. "
        "Make bullets sound more contextual and recruiter-ready, not like raw source notes. "
        "Use exact JD terminology where natural, but stay honest and grounded in source evidence. "
        "Prefer transferable framing over generic operations filler when the target role is adjacent. "
        "Do not invent unsupported metrics, tools, systems, legislation knowledge, or direct payroll ownership. "
        "Output schema:\n"
        f"{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
        f"Build plan:\n{json.dumps(plan, ensure_ascii=False, indent=2)}\n\n"
        f"Bullet plan:\n{json.dumps(bullet_plan, ensure_ascii=False, indent=2)}\n\n"
        f"Current resume draft:\n{json.dumps(current_resume, ensure_ascii=False, indent=2)}\n\n"
        f"Client profile:\n{json.dumps(profile, ensure_ascii=False, indent=2)}\n\n"
        f"Target job:\n{json.dumps(job, ensure_ascii=False, indent=2)}"
    )



def strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```json\s*", "", text)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def parse_jsonish(text: str) -> dict:
    text = strip_fences(text)
    if not text:
        raise ValueError("empty model text")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]
        return json.loads(candidate)
    raise ValueError("no parseable JSON object found in model text")


def build_ssl_context() -> tuple[ssl.SSLContext, str]:
    try:
        import certifi  # type: ignore

        return ssl.create_default_context(cafile=certifi.where()), "certifi"
    except Exception:
        pass

    try:
        return ssl.create_default_context(), "system"
    except Exception:
        ctx = ssl._create_unverified_context()
        return ctx, "unverified"


def http_post_json(url: str, payload: dict, headers: dict[str, str], request_timeout: int = 240) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method="POST",
    )

    ssl_context, ssl_mode = build_ssl_context()

    try:
        with urllib.request.urlopen(request, timeout=request_timeout, context=ssl_context) as response:
            raw_text = response.read().decode("utf-8")
            outer = json.loads(raw_text)
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {error_body}") from exc
    except urllib.error.URLError as exc:
        if "CERTIFICATE_VERIFY_FAILED" in str(exc):
            insecure_context = ssl._create_unverified_context()
            try:
                with urllib.request.urlopen(request, timeout=request_timeout, context=insecure_context) as response:
                    raw_text = response.read().decode("utf-8")
                    outer = json.loads(raw_text)
                    outer.setdefault("_transport", {})["ssl_mode"] = "unverified-fallback"
            except Exception as insecure_exc:
                raise RuntimeError(f"request failed after SSL fallback: {insecure_exc}") from insecure_exc
        else:
            raise RuntimeError(f"request failed: {exc}") from exc

    outer.setdefault("_transport", {})["ssl_mode"] = outer.get("_transport", {}).get("ssl_mode", ssl_mode)
    return outer


def call_gemini(prompt: str, model: str, api_key: str, request_timeout: int = 240) -> tuple[dict, dict]:
    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{urllib.parse.quote(model, safe='')}:generateContent?key={urllib.parse.quote(api_key, safe='')}"
    )
    payload = {
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
    }
    try:
        outer = http_post_json(
            endpoint,
            payload,
            {"Content-Type": "application/json"},
            request_timeout=request_timeout,
        )
    except Exception as exc:
        raise RuntimeError(f"Gemini {exc}") from exc

    parts = []
    for candidate in outer.get("candidates") or []:
        for part in ((candidate.get("content") or {}).get("parts") or []):
            if part.get("text"):
                parts.append(part["text"])
    text = "\n".join(parts).strip()
    if not text:
        raise RuntimeError(f"Gemini returned no text payload: {json.dumps(outer, ensure_ascii=False)}")
    data = parse_jsonish(text)
    return data, outer


def call_openai(prompt: str, model: str, api_key: str, request_timeout: int = 240) -> tuple[dict, dict]:
    endpoint = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": model,
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
    }
    try:
        outer = http_post_json(
            endpoint,
            payload,
            {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            request_timeout=request_timeout,
        )
    except Exception as exc:
        raise RuntimeError(f"OpenAI {exc}") from exc

    choices = outer.get("choices") or []
    text = (((choices[0] if choices else {}).get("message") or {}).get("content") or "").strip()
    if not text:
        raise RuntimeError(f"OpenAI returned no text payload: {json.dumps(outer, ensure_ascii=False)}")
    data = parse_jsonish(text)
    return data, outer


def run_llm(prompts: dict[str, str], provider: str, model: str, api_key: str, run_dir: Path, max_attempts: int = 4, task_name: str = "resume") -> tuple[dict, dict]:
    attempts_dir = run_dir / "attempts"
    attempts_dir.mkdir(parents=True, exist_ok=True)

    prompt_modes = ["full", "slim"]
    last_error = f"unknown {provider} error"
    attempt_no = 0

    provider_fn = call_openai if provider == "openai" else call_gemini

    for prompt_mode in prompt_modes:
        active_prompt = prompts.get(prompt_mode)
        if not active_prompt:
            last_error = f"missing prompt for mode: {prompt_mode}"
            continue
        for _ in range(max_attempts):
            attempt_no += 1
            attempt_prefix = attempts_dir / f"{task_name}-attempt-{attempt_no:02d}_{provider}_{prompt_mode}"
            (attempt_prefix.with_suffix(".prompt.txt")).write_text(active_prompt + "\n", encoding="utf-8")
            try:
                data, outer = provider_fn(active_prompt, model, api_key)
                (attempt_prefix.with_suffix(".outer.json")).write_text(json.dumps(outer, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                return data, {"attempt": attempt_no, "provider": provider, "model": model, "prompt_mode": prompt_mode}
            except Exception as e:
                last_error = str(e)
                (attempt_prefix.with_suffix(".stderr.txt")).write_text(last_error + "\n", encoding="utf-8")
                time.sleep(2)
                continue

    raise RuntimeError(last_error)


def run_openclaw(prompts: dict[str, str], requested_agent: str, run_dir: Path, max_attempts: int = 6, task_name: str = "resume") -> tuple[dict, dict]:
    attempts_dir = run_dir / "attempts"
    attempts_dir.mkdir(parents=True, exist_ok=True)

    agent_order = []
    for agent in [requested_agent, "main", "samantha"]:
        if agent and agent not in agent_order:
            agent_order.append(agent)
    prompt_modes = ["full", "slim"]

    last_error = "unknown error"
    attempt_no = 0
    for prompt_mode in prompt_modes:
        active_prompt = prompts.get(prompt_mode)
        for agent in agent_order:
            if attempt_no >= max_attempts:
                break
            attempt_no += 1
            if not active_prompt:
                last_error = f"missing prompt for mode: {prompt_mode}"
                continue
            attempt_prefix = attempts_dir / f"{task_name}-attempt-{attempt_no:02d}_{agent}_{prompt_mode}"
            result = subprocess.run(
                [
                    "openclaw", "agent",
                    "--agent", agent,
                    "--local",
                    "--json",
                    "--thinking", "minimal",
                    "--timeout", "240",
                    "--message", active_prompt,
                ],
                text=True,
                capture_output=True,
            )
            (attempt_prefix.with_suffix(".prompt.txt")).write_text(active_prompt + "\n", encoding="utf-8")
            (attempt_prefix.with_suffix(".stdout.txt")).write_text(result.stdout or "", encoding="utf-8")
            (attempt_prefix.with_suffix(".stderr.txt")).write_text(result.stderr or "", encoding="utf-8")

            if result.returncode != 0:
                last_error = result.stderr.strip() or result.stdout.strip() or "openclaw agent failed"
                time.sleep(2)
                continue

            try:
                outer = json.loads((result.stdout or "").strip())
            except json.JSONDecodeError as e:
                last_error = f"outer openclaw JSON parse failed: {e}"
                time.sleep(2)
                continue

            (attempt_prefix.with_suffix(".outer.json")).write_text(json.dumps(outer, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            payloads = outer.get("payloads") or []
            text = (payloads[0] if payloads else {}).get("text", "")
            text = text.strip()
            lower = text.lower()
            if not text or lower in {"forbidden", "bad gateway"} or "502 bad gateway" in lower:
                last_error = f"provider returned non-JSON payload: {text or '<empty>'}"
                time.sleep(2)
                continue

            try:
                data = parse_jsonish(text)
                return data, {"attempt": attempt_no, "agent": agent, "prompt_mode": prompt_mode, "provider": "openclaw"}
            except Exception as e:
                last_error = f"inner model JSON parse failed: {e}"
                time.sleep(2)
                continue

    raise RuntimeError(last_error)


def markdown_bold_to_html(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    return text


def role_age_bucket(role: dict) -> str:
    end = parse_date_token(role.get("endDate"))
    if not end:
        dates = str(role.get("dates") or "")
        if "Present" in dates:
            end = datetime.now(UTC)
        else:
            parsed = re.findall(r"([A-Z][a-z]{2}\s+\d{4}|\d{4}-\d{2}|\d{4})", dates)
            if parsed:
                end = parse_date_token(parsed[-1])
    if not end:
        return "2to5"
    months_ago = months_between(end, datetime.now(UTC))
    years_ago = months_ago / 12.0
    if "Present" in str(role.get("dates") or role.get("endDate") or "") or years_ago <= 2:
        return "current_or_last2"
    if years_ago <= 5:
        return "2to5"
    if years_ago <= 10:
        return "5to10"
    if years_ago <= 15:
        return "10to15"
    return "15plus"


def bullet_limits_for_bucket(bucket: str) -> tuple[int, int]:
    return {
        "current_or_last2": (4, 6),
        "2to5": (3, 4),
        "5to10": (2, 3),
        "10to15": (1, 2),
        "15plus": (0, 0),
    }[bucket]


def role_duration_months(role: dict) -> int:
    return months_between(parse_date_token(role.get("startDate")), parse_date_token(role.get("endDate")))


def source_role_for_match(profile: dict, title: str, company: str) -> dict | None:
    for src in profile_roles(profile):
        if src.get("company", "").strip().lower() == company.strip().lower() and src.get("position", "").strip().lower() == title.strip().lower():
            return src
    return None


def source_bullets_for_role(profile: dict, title: str, company: str) -> list[str]:
    src = source_role_for_match(profile, title, company)
    if not src:
        return []
    return [markdown_bold_to_html(x) for x in (src.get("highlights") or [])]


def merge_rewritten_experience(existing_experience: list[dict], rewritten_payload: dict) -> list[dict]:
    rewritten_roles = rewritten_payload.get("experience") or []
    rewritten_map = {
        (str(role.get("title", "")).strip().lower(), str(role.get("company", "")).strip().lower()): role
        for role in rewritten_roles
    }
    merged: list[dict] = []
    for role in existing_experience:
        key = (str(role.get("title", "")).strip().lower(), str(role.get("company", "")).strip().lower())
        rewritten = rewritten_map.get(key)
        if rewritten and isinstance(rewritten.get("bullets"), list):
            role_out = deepcopy(role)
            role_out["bullets"] = [markdown_bold_to_html(str(b).strip()) for b in rewritten.get("bullets", []) if str(b).strip()]
            merged.append(role_out)
        else:
            merged.append(role)
    return merged


def filter_certifications(certifications: list[str], job: dict, plan: dict) -> tuple[list[str], list[str]]:
    job_text = (job.get("jd_text") or "").lower()
    dropped = []
    kept = []
    for cert in certifications or []:
        cert_low = cert.lower()
        has_year = bool(re.search(r"\b(20\d{2}|19\d{2})\b", cert)) or "expected" in cert_low or "in progress" in cert_low
        issuer_hit = any(issuer in cert_low for issuer in RECOGNISED_CERT_ISSUERS)
        generic_soft = any(re.search(pat, cert_low) for pat in GENERIC_SOFT_SKILL_CERT_PATTERNS)
        core_relevant = any(token in cert_low for token in ["excel", "python", "sql", "power bi", "data", "sap", "successfactors", "accounting", "financial"]) and any(token in job_text for token in ["excel", "python", "sql", "power bi", "sap", "successfactors", "data", "reporting", "financial"])
        if generic_soft:
            dropped.append(f"{cert} — generic soft-skill certification")
            continue
        if plan["page_budget"] == 1 and not core_relevant and not issuer_hit:
            dropped.append(f"{cert} — non-core for one-page target role")
            continue
        if not has_year and not issuer_hit and not core_relevant:
            dropped.append(f"{cert} — missing year and weak role relevance")
            continue
        kept.append(cert)
    return kept, dropped


def normalize_degree_item(edu: dict) -> dict:
    degree = edu.get("degree") or ""
    if not degree:
        study = edu.get("studyType", "")
        area = edu.get("area", "")
        degree = ", ".join([x for x in [study, area] if x])
    school = edu.get("school") or ""
    if not school:
        institution = edu.get("institution", "")
        location = edu.get("location", "")
        school = ", ".join([x for x in [institution, location] if x])
    dates = normalize_existing_date_range(edu.get("dates") or "")
    if not dates:
        start = edu.get("startDate", "")
        end = edu.get("endDate", "")
        dates = format_resume_date_range(start, end)
    return {
        "degree": degree,
        "school": school,
        "dates": dates,
        "note": edu.get("note"),
    }


def ensure_html_bullets(role: dict) -> dict:
    role_out = deepcopy(role)
    role_out["bullets"] = [markdown_bold_to_html(str(b).strip()) for b in role_out.get("bullets", []) if str(b).strip()]
    return role_out


def source_skill_inventory(profile: dict) -> list[str]:
    inventory: list[str] = []
    for category, items in (profile.get("skills") or {}).items():
        inventory.append(str(category))
        if isinstance(items, list):
            inventory.extend(str(x) for x in items)
        else:
            inventory.extend(part.strip() for part in re.split(r",(?=(?:[^()]*\([^()]*\))*[^()]*$)", str(items)) if part.strip())
    for item in profile.get("languages", []) or []:
        if item.get("language"):
            inventory.append(str(item.get("language")))
    for cert in profile.get("certifications", []) or []:
        inventory.append(str(cert))
    return inventory


def skill_supported(skill: str, supported_terms: list[str]) -> bool:
    skill_norm = re.sub(r"[^a-z0-9+&.# ]+", " ", skill.lower())
    skill_norm = re.sub(r"\s+", " ", skill_norm).strip()
    if not skill_norm:
        return False
    skill_tokens = {tok for tok in skill_norm.split() if len(tok) >= 2}
    if not skill_tokens:
        return False
    for raw in supported_terms:
        raw_norm = re.sub(r"[^a-z0-9+&.# ]+", " ", str(raw).lower())
        raw_norm = re.sub(r"\s+", " ", raw_norm).strip()
        if not raw_norm:
            continue
        if skill_norm in raw_norm or raw_norm in skill_norm:
            return True
        raw_tokens = {tok for tok in raw_norm.split() if len(tok) >= 2}
        overlap = skill_tokens & raw_tokens
        if len(overlap) >= min(2, len(skill_tokens)):
            return True
    return False


def split_skill_text(text: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for ch in str(text):
        if ch == "(":
            depth += 1
        elif ch == ")" and depth > 0:
            depth -= 1
        if ch == "," and depth == 0:
            part = "".join(current).strip()
            if part:
                parts.append(part)
            current = []
            continue
        current.append(ch)
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def normalize_skill_items(items: Any) -> list[str]:
    if isinstance(items, list):
        raw_items = items
    else:
        raw_items = split_skill_text(str(items))
    cleaned: list[str] = []
    seen = set()
    for item in raw_items:
        item = str(item).strip().strip(";")
        if not item:
            continue
        low = item.lower()
        if low in seen:
            continue
        seen.add(low)
        cleaned.append(item)
    return cleaned


def validate_and_trim_skills(skills: dict, profile: dict, job: dict, plan: dict) -> tuple[dict, dict]:
    supported_terms = source_skill_inventory(profile)
    validated: dict[str, str] = {}
    dropped_items: list[str] = []
    flagged_items: list[str] = []
    languages_value = None

    for category, items in skills.items():
        category_name = str(category).strip()
        item_list = normalize_skill_items(items)
        kept_items: list[str] = []
        for item in item_list:
            low = item.lower()
            if low in SOFT_SKILLS:
                dropped_items.append(f"{item} — soft skill")
                continue
            if category_name.lower() == "languages":
                kept_items.append(item)
                continue
            if not skill_supported(item, supported_terms):
                flagged_items.append(f"{item} — not explicit in source profile (kept by LLM-first skills mode)")
            kept_items.append(item)
        if not kept_items:
            continue
        if category_name.lower() == "languages":
            languages_value = ", ".join(kept_items)
        else:
            validated[category_name] = ", ".join(kept_items)

    if not languages_value:
        langs = profile.get("languages", []) or []
        if langs:
            languages_value = ", ".join(
                f"{item.get('language', '').strip()} ({item.get('level', '').strip()})".strip()
                for item in langs if item.get("language")
            )

    limit = plan.get("skills_row_cap", 3)
    ordered_items = list(validated.items())
    trimmed_categories: list[str] = []
    max_non_language = limit - (1 if languages_value else 0)
    if max_non_language < 0:
        max_non_language = 0
    if len(ordered_items) > max_non_language:
        trimmed_categories = [name for name, _ in ordered_items[max_non_language:]]
        ordered_items = ordered_items[:max_non_language]

    result = {name: value for name, value in ordered_items}
    if languages_value:
        result["Languages"] = languages_value

    audit = {
        "dropped_skill_items": dropped_items,
        "flagged_skill_items": flagged_items,
        "trimmed_skill_categories": trimmed_categories,
        "llm_skills_preserved_order": True,
    }
    return result, audit


def enforce_page_rules(normalized: dict, profile: dict, job: dict, plan: dict) -> tuple[dict, dict]:
    data = deepcopy(normalized)
    audit: dict[str, Any] = {"bullet_reductions": [], "dropped_certifications": [], "estimated_bullets": [], "dropped_skill_items": [], "flagged_skill_items": [], "trimmed_skill_categories": []}

    max_roles = plan["max_roles"]
    experiences = [ensure_html_bullets(r) for r in data.get("experience", [])]
    experiences = experiences[:max_roles]

    enforced_roles = []
    for role in experiences:
        bucket = role_age_bucket(role)
        min_bullets, max_bullets = bullet_limits_for_bucket(bucket)
        src_bullets = source_bullets_for_role(profile, role.get("title", ""), role.get("company", ""))
        role_bullets = [b for b in role.get("bullets", []) if b]
        # Fill up from source evidence when the model under-shoots the minimum.
        target_fill = min_bullets
        if plan["thin_input"] and bucket == "current_or_last2":
            target_fill = max_bullets
        if len(role_bullets) < target_fill:
            for src_b in src_bullets:
                if src_b not in role_bullets:
                    role_bullets.append(src_b)
                if len(role_bullets) >= target_fill:
                    break
        original_count = len(role_bullets)
        if bucket == "15plus":
            role_bullets = []
        else:
            role_bullets = role_bullets[:max_bullets]
        if len(role_bullets) < min_bullets and src_bullets:
            role_bullets = src_bullets[:max_bullets]
            role_bullets = role_bullets[: max(min_bullets, len(role_bullets))]
        if len(role_bullets) < original_count:
            audit["bullet_reductions"].append({
                "role": f"{role.get('title')} | {role.get('company')}",
                "from": original_count,
                "to": len(role_bullets),
                "bucket": bucket,
            })
        role["bullets"] = role_bullets
        enforced_roles.append(role)
    data["experience"] = enforced_roles

    candidate_certs = data.get("certifications") or profile.get("certifications", []) or []
    kept_certs, dropped_certs = filter_certifications(candidate_certs, job, plan)
    data["certifications"] = kept_certs
    audit["dropped_certifications"] = dropped_certs

    data["skills"], skills_audit = validate_and_trim_skills(data.get("skills", {}), profile, job, plan)
    audit["dropped_skill_items"] = skills_audit.get("dropped_skill_items", [])
    audit["flagged_skill_items"] = skills_audit.get("flagged_skill_items", [])
    audit["trimmed_skill_categories"] = skills_audit.get("trimmed_skill_categories", [])

    # Ensure education format and order semantics.
    data["education"] = [normalize_degree_item(edu) for edu in data.get("education", [])]

    client = profile.get("client", {})
    if not data.get("work_authorization") and client.get("work_authorization"):
        data["work_authorization"] = client.get("work_authorization")

    return data, audit


SUMMARY_MAX_SENTENCES = 4
SUMMARY_MAX_WORDS = 68
SUMMARY_MAX_CHARS = 460


def split_summary_sentences(summary: str) -> list[str]:
    text = re.sub(r"<br\s*/?>", " ", str(summary or ""), flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", text) if p.strip()]
    return parts or [text]


def trim_summary_to_word_limit(text: str, max_words: int) -> str:
    words = str(text or "").split()
    if len(words) <= max_words:
        return str(text or "").strip()
    trimmed = " ".join(words[:max_words]).rstrip(",;:- ")
    if not trimmed.endswith((".", "!", "?")):
        trimmed += "."
    return trimmed


def trim_summary_to_char_limit(text: str, max_chars: int) -> str:
    text = str(text or "").strip()
    if len(text) <= max_chars:
        return text
    trimmed = text[:max_chars].rstrip(",;:- ")
    last_space = trimmed.rfind(" ")
    if last_space > int(max_chars * 0.75):
        trimmed = trimmed[:last_space]
    trimmed = trimmed.rstrip(",;:- ")
    trimmed = re.sub(r"\b(and|or|with|for|across|including|plus)$", "", trimmed, flags=re.I).rstrip(",;:- ")
    if not trimmed.endswith((".", "!", "?")):
        trimmed += "."
    return trimmed


def enforce_summary_limits(summary: str) -> str:
    sentences = split_summary_sentences(summary)
    if not sentences:
        return ""
    summary = " ".join(sentences[:SUMMARY_MAX_SENTENCES]).strip()
    summary = re.sub(r"\s+", " ", summary)
    summary = trim_summary_to_word_limit(summary, SUMMARY_MAX_WORDS)
    summary = trim_summary_to_char_limit(summary, SUMMARY_MAX_CHARS)
    summary = re.sub(r"\s+", " ", summary).strip()
    return summary


def normalize_resume_payload(data: dict, profile: dict) -> dict:
    required = ["name", "city", "phone", "email", "linkedin", "summary", "experience", "education", "skills"]
    missing = [k for k in required if k not in data]
    if missing:
        raise RuntimeError(f"resume JSON missing required keys: {', '.join(missing)}")

    if not isinstance(data["experience"], list) or not data["experience"]:
        raise RuntimeError("experience must be a non-empty list")
    if not isinstance(data["education"], list) or not data["education"]:
        raise RuntimeError("education must be a non-empty list")
    if not isinstance(data["skills"], dict) or not data["skills"]:
        raise RuntimeError("skills must be a non-empty object")

    normalized = dict(data)
    normalized["linkedin"] = str(normalized["linkedin"]).replace("https://", "").replace("http://", "")
    normalized["summary"] = enforce_summary_limits(normalized.get("summary", ""))

    profile_experience = profile.get("experience", []) or []
    normalized_experience = []
    for role in normalized["experience"]:
        role_out = dict(role)
        if not role_out.get("context"):
            for src_role in profile_experience:
                same_company = src_role.get("company", "").strip().lower() == str(role_out.get("company", "")).strip().lower()
                same_title = src_role.get("position", "").strip().lower() == str(role_out.get("title", "")).strip().lower()
                if same_company and same_title and src_role.get("summary"):
                    role_out["context"] = src_role.get("summary")
                    break
        if role_out.get("dates"):
            role_out["dates"] = normalize_existing_date_range(role_out.get("dates"))
        else:
            for src_role in profile_experience:
                same_company = src_role.get("company", "").strip().lower() == str(role_out.get("company", "")).strip().lower()
                same_title = src_role.get("position", "").strip().lower() == str(role_out.get("title", "")).strip().lower()
                if same_company and same_title:
                    role_out["dates"] = format_resume_date_range(src_role.get("startDate"), src_role.get("endDate"))
                    break
        normalized_experience.append(role_out)
    normalized["experience"] = normalized_experience

    normalized["education"] = [normalize_degree_item(edu) for edu in normalized["education"]]

    skills_out = {}
    for category, items in normalized["skills"].items():
        normalized_items = normalize_skill_items(items)
        if normalized_items:
            skills_out[str(category).strip()] = ", ".join(normalized_items)
    normalized["skills"] = skills_out

    client = profile.get("client", {})
    normalized["name"] = normalized.get("name") or client.get("name", "")
    normalized["city"] = normalized.get("city") or ", ".join(filter(None, [client.get("city", ""), client.get("country", "")]))
    normalized["phone"] = normalized.get("phone") or client.get("phone", "")
    normalized["email"] = normalized.get("email") or client.get("email", "")
    normalized["linkedin"] = normalized.get("linkedin") or client.get("linkedin", "").replace("https://", "").replace("http://", "")
    normalized["work_authorization"] = normalized.get("work_authorization") or client.get("work_authorization")
    return normalized


def count_metric_bullets(experience: list[dict]) -> tuple[int, int]:
    total = 0
    metric = 0
    for role in experience:
        for bullet in role.get("bullets", []) or []:
            total += 1
            if re.search(r"\d|%|\$|€|£", bullet):
                metric += 1
    return metric, total


def detect_repeated_verbs(role: dict) -> list[str]:
    verbs = []
    repeats = set()
    for bullet in role.get("bullets", []) or []:
        text = re.sub(r"<[^>]+>", "", bullet).strip("• ")
        m = re.match(r"([A-Za-z][A-Za-z-]+)", text)
        if not m:
            continue
        verb = m.group(1).lower()
        if verb in verbs:
            repeats.add(verb)
        verbs.append(verb)
    return sorted(repeats)


def build_audit_report(resume: dict, profile: dict, job: dict, plan: dict, enforcement_audit: dict, layout_audit: dict | None) -> dict:
    summary = resume.get("summary", "")
    job_title = str(job.get("position") or "")
    jd_keywords = plan.get("keyword_targets", [])
    keyword_hits = [kw for kw in jd_keywords if kw.lower() in json.dumps(resume, ensure_ascii=False).lower()]
    metric_bullets, total_bullets = count_metric_bullets(resume.get("experience", []))
    metric_ratio = round(metric_bullets / total_bullets, 3) if total_bullets else 0.0

    banned_hits = []
    resume_text = json.dumps(resume, ensure_ascii=False).lower()
    for phrase in BANNED_PHRASES:
        if phrase in resume_text:
            banned_hits.append(phrase)

    repeated_verbs = {
        f"{role.get('title')} | {role.get('company')}": detect_repeated_verbs(role)
        for role in resume.get("experience", [])
    }
    repeated_verbs = {k: v for k, v in repeated_verbs.items() if v}

    soft_skill_hits = []
    for category, items in (resume.get("skills", {}) or {}).items():
        item_text = str(items).lower()
        for term in SOFT_SKILLS:
            if term in item_text:
                soft_skill_hits.append({"category": category, "term": term})

    invisible_rejectors = []
    email = str(resume.get("email") or "")
    if any(bad in email.lower() for bad in ["hotmail.", "yahoo.", "outlook."]):
        invisible_rejectors.append("Non-preferred email domain")
    if not resume.get("linkedin"):
        invisible_rejectors.append("LinkedIn URL missing")
    if "references available upon request" in resume_text:
        invisible_rejectors.append("References available upon request present")
    if total_experience_months(profile) / 12.0 < 3 and len(resume.get("education", [])) == 0:
        invisible_rejectors.append("Junior profile missing education")

    bullet_policy = []
    for role in resume.get("experience", []):
        bucket = role_age_bucket(role)
        min_bullets, max_bullets = bullet_limits_for_bucket(bucket)
        bullet_policy.append({
            "role": f"{role.get('title')} | {role.get('company')}",
            "bucket": bucket,
            "count": len(role.get("bullets", []) or []),
            "min": min_bullets,
            "max": max_bullets,
            "within_limits": min_bullets <= len(role.get("bullets", []) or []) <= max_bullets,
        })

    quality_gate = {
        "target_title_in_summary": f"<b>{job_title}</b>" in summary,
        "metric_ratio_ge_40pct": metric_ratio >= 0.4,
        "banned_phrases": not banned_hits,
        "soft_skills_in_skills": not soft_skill_hits,
        "keywords_15_plus": len(keyword_hits) >= 15,
        "page_budget_respected": (layout_audit or {}).get("page_count", 1) <= plan["page_budget"],
        "repeated_verbs_within_role": not repeated_verbs,
    }

    return {
        "plan": plan,
        "keyword_hits": keyword_hits,
        "keyword_hit_count": len(keyword_hits),
        "metric_bullets": metric_bullets,
        "total_bullets": total_bullets,
        "metric_ratio": metric_ratio,
        "banned_phrase_hits": banned_hits,
        "soft_skill_hits": soft_skill_hits,
        "repeated_verbs": repeated_verbs,
        "invisible_rejectors": invisible_rejectors,
        "bullet_policy": bullet_policy,
        "enforcement": enforcement_audit,
        "layout_audit_summary": {
            "status": (layout_audit or {}).get("status"),
            "page_count": (layout_audit or {}).get("page_count"),
            "reasons": (layout_audit or {}).get("reasons"),
        } if layout_audit else None,
        "quality_gate": quality_gate,
    }


def write_va_notes(path: Path, audit: dict, job: dict) -> None:
    lines = [
        "VA NOTES:",
        f"- Page budget enforced: {audit['plan']['page_budget']} page(s)",
        f"- Positioning strategy: {audit['plan']['positioning']}",
        f"- JD keywords integrated ({audit['keyword_hit_count']}): {', '.join(audit['keyword_hits'][:10])}",
        f"- Metric bullets: {audit['metric_bullets']}/{audit['total_bullets']} ({audit['metric_ratio']:.0%})",
    ]
    dropped = audit.get("enforcement", {}).get("dropped_certifications", []) or []
    if dropped:
        lines.append("- Certifications dropped:")
        lines.extend([f"  - {item}" for item in dropped])
    dropped_skills = audit.get("enforcement", {}).get("dropped_skill_items", []) or []
    if dropped_skills:
        lines.append("- Skill items dropped by validator:")
        lines.extend([f"  - {item}" for item in dropped_skills])
    flagged_skills = audit.get("enforcement", {}).get("flagged_skill_items", []) or []
    if flagged_skills:
        lines.append("- Skill items kept via LLM-first judgment (not explicit in source profile):")
        lines.extend([f"  - {item}" for item in flagged_skills])
    trimmed_skill_categories = audit.get("enforcement", {}).get("trimmed_skill_categories", []) or []
    if trimmed_skill_categories:
        lines.append(f"- Skill categories trimmed to row cap: {', '.join(trimmed_skill_categories)}")
    reductions = audit.get("enforcement", {}).get("bullet_reductions", []) or []
    if reductions:
        lines.append("- Bullets reduced:")
        for item in reductions:
            lines.append(f"  - {item['role']}: {item['from']} → {item['to']} ({item['bucket']})")
    if audit.get("invisible_rejectors"):
        lines.append("- Invisible rejectors found:")
        lines.extend([f"  - {item}" for item in audit["invisible_rejectors"]])
    if audit.get("banned_phrase_hits"):
        lines.append(f"- Banned phrase hits: {', '.join(audit['banned_phrase_hits'])}")
    if audit.get("repeated_verbs"):
        lines.append("- Repeated verbs by role:")
        for role, verbs in audit["repeated_verbs"].items():
            lines.append(f"  - {role}: {', '.join(verbs)}")
    lines.append(f"- Cover letter: type 'Cover letter for {job.get('position')}'")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_run_dir(base_dir: Path, job: dict) -> Path:
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    slug = slugify(f"{job.get('Name','company')}-{job.get('position','role')}")[:100]
    run_dir = base_dir / f"{ts}_{slug}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def run_model_task(args, prompts: dict[str, str], run_dir: Path, task_name: str, max_attempts: int = 4) -> tuple[dict, dict]:
    if args.llm_provider == "openai":
        if not args.openai_api_key:
            raise SystemExit("missing OpenAI API key. Provide --openai-api-key or set OPENAI_API_KEY.")
        return run_llm(prompts, "openai", args.openai_model, args.openai_api_key, run_dir, max_attempts=max_attempts, task_name=task_name)
    if args.llm_provider == "gemini":
        if not args.gemini_api_key:
            raise SystemExit("missing Gemini API key. Provide --gemini-api-key or set GEMINI_API_KEY.")
        return run_llm(prompts, "gemini", args.gemini_model, args.gemini_api_key, run_dir, max_attempts=max_attempts, task_name=task_name)
    return run_openclaw(prompts, args.llm_agent, run_dir, max_attempts=max_attempts, task_name=task_name)


def main():
    ap = argparse.ArgumentParser(description="CCC resume engine experiment")
    ap.add_argument("--client-name", default="Beste Keskiner")
    ap.add_argument("--profile-file")
    ap.add_argument("--job-id")
    ap.add_argument("--job-file")
    ap.add_argument("--llm-agent", default="samantha")
    ap.add_argument("--llm-provider", choices=["openai", "gemini", "openclaw"], default="gemini")
    ap.add_argument("--openai-model", default=os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"))
    ap.add_argument("--openai-api-key", default=os.environ.get("OPENAI_API_KEY", ""))
    ap.add_argument("--gemini-model", default=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"))
    ap.add_argument("--gemini-api-key", default=os.environ.get("GEMINI_API_KEY", ""))
    ap.add_argument("--output-dir", default=str(DEFAULT_RUNS_DIR))
    ap.add_argument("--show-work-authorization", action="store_true")
    args = ap.parse_args()

    if not args.job_id and not args.job_file:
        raise SystemExit("provide either --job-id or --job-file")
    if args.job_id and args.job_file:
        raise SystemExit("use only one of --job-id or --job-file")

    client_paths = build_client_paths(args.client_name)
    profile_path = Path(args.profile_file).expanduser().resolve() if args.profile_file else client_paths["profile"]
    if not profile_path.exists():
        raise SystemExit(f"missing profile: {profile_path}")

    profile = load_json(profile_path)

    if args.job_file:
        job_path = Path(args.job_file).expanduser().resolve()
        if not job_path.exists():
            raise SystemExit(f"missing job file: {job_path}")
        job = load_json(job_path)
    else:
        if not client_paths["jobs"].exists():
            raise SystemExit(f"missing jobs file: {client_paths['jobs']}")
        jobs = read_jobs(client_paths["jobs"])
        job = find_job(jobs, args.job_id)

    plan = build_plan(profile, job)

    output_dir = Path(args.output_dir).expanduser().resolve()
    run_dir = make_run_dir(output_dir, job)
    (run_dir / "job_input.json").write_text(json.dumps(job, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    skills_plan_data = None
    skills_plan_meta = None
    skills_plan_error = None
    skills_writer_meta = None
    skills_writer_error = None
    bullet_plan_data = None
    bullet_plan_meta = None
    bullet_plan_error = None
    bullet_writer_meta = None
    bullet_writer_error = None

    try:
        skills_plan_prompt = build_skills_plan_prompt(profile, job, plan)
        (run_dir / "skills_plan.prompt.txt").write_text(skills_plan_prompt + "\n", encoding="utf-8")
        skills_plan_data, skills_plan_meta = run_model_task(
            args,
            {"full": skills_plan_prompt, "slim": skills_plan_prompt},
            run_dir,
            "skills-plan",
            max_attempts=3,
        )
        (run_dir / "skills_plan.json").write_text(json.dumps(skills_plan_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        plan["skills_llm_plan"] = skills_plan_data
        plan["skills_plan_attempt_meta"] = skills_plan_meta
    except Exception as e:
        skills_plan_error = str(e)
        (run_dir / "skills_plan.error.txt").write_text(skills_plan_error + "\n", encoding="utf-8")
        plan["skills_llm_plan_error"] = skills_plan_error

    prompt = build_prompt(profile, job, plan, mode="full")
    slim_prompt = build_prompt(profile, job, plan, mode="slim")
    (run_dir / "build_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (run_dir / "prompt.txt").write_text(prompt + "\n", encoding="utf-8")
    (run_dir / "prompt.slim.txt").write_text(slim_prompt + "\n", encoding="utf-8")

    layout_audit_path = None
    rules_audit_path = None
    va_notes_path = None

    try:
        resume_json, attempt_meta = run_model_task(
            args,
            {"full": prompt, "slim": slim_prompt},
            run_dir,
            "resume",
            max_attempts=4,
        )

        if skills_plan_data:
            try:
                skills_writer_prompt = build_skills_writer_prompt(profile, job, plan, resume_json, skills_plan_data)
                (run_dir / "skills_writer.prompt.txt").write_text(skills_writer_prompt + "\n", encoding="utf-8")
                skills_writer_payload, skills_writer_meta = run_model_task(
                    args,
                    {"full": skills_writer_prompt, "slim": skills_writer_prompt},
                    run_dir,
                    "skills-write",
                    max_attempts=3,
                )
                (run_dir / "skills_writer.json").write_text(json.dumps(skills_writer_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                if isinstance(skills_writer_payload, dict) and isinstance(skills_writer_payload.get("skills"), dict):
                    resume_json["skills"] = skills_writer_payload["skills"]
                if isinstance(skills_writer_payload, dict) and skills_writer_payload.get("certifications"):
                    resume_json["certifications"] = skills_writer_payload.get("certifications")
            except Exception as e:
                skills_writer_error = str(e)
                (run_dir / "skills_writer.error.txt").write_text(skills_writer_error + "\n", encoding="utf-8")

        try:
            bullet_plan_prompt = build_bullet_plan_prompt(profile, job, plan, resume_json)
            (run_dir / "bullet_plan.prompt.txt").write_text(bullet_plan_prompt + "\n", encoding="utf-8")
            bullet_plan_data, bullet_plan_meta = run_model_task(
                args,
                {"full": bullet_plan_prompt, "slim": bullet_plan_prompt},
                run_dir,
                "bullet-plan",
                max_attempts=3,
            )
            (run_dir / "bullet_plan.json").write_text(json.dumps(bullet_plan_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception as e:
            bullet_plan_error = str(e)
            (run_dir / "bullet_plan.error.txt").write_text(bullet_plan_error + "\n", encoding="utf-8")

        if bullet_plan_data:
            try:
                bullet_writer_prompt = build_bullet_writer_prompt(profile, job, plan, resume_json, bullet_plan_data)
                (run_dir / "bullet_writer.prompt.txt").write_text(bullet_writer_prompt + "\n", encoding="utf-8")
                bullet_writer_payload, bullet_writer_meta = run_model_task(
                    args,
                    {"full": bullet_writer_prompt, "slim": bullet_writer_prompt},
                    run_dir,
                    "bullet-write",
                    max_attempts=3,
                )
                (run_dir / "bullet_writer.json").write_text(json.dumps(bullet_writer_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                if isinstance(bullet_writer_payload, dict) and isinstance(bullet_writer_payload.get("experience"), list):
                    resume_json["experience"] = merge_rewritten_experience(resume_json.get("experience", []), bullet_writer_payload)
            except Exception as e:
                bullet_writer_error = str(e)
                (run_dir / "bullet_writer.error.txt").write_text(bullet_writer_error + "\n", encoding="utf-8")

        normalized = normalize_resume_payload(resume_json, profile)
        normalized, enforcement_audit = enforce_page_rules(normalized, profile, job, plan)
        if not args.show_work_authorization:
            normalized.pop("work_authorization", None)
        resume_json_path = run_dir / "resume.json"
        resume_json_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        pdf_path = run_dir / "resume.pdf"
        generate_cv(
            normalized,
            str(pdf_path),
            one_page=(plan["page_budget"] == 1),
            education_first=(plan["page_budget"] == 1),
        )
        layout_audit_path = run_dir / "layout_audit.json"
        layout_audit_data = None
        if LAYOUT_AUDIT_SCRIPT.exists():
            layout_cmd = [
                sys.executable,
                str(LAYOUT_AUDIT_SCRIPT),
                str(pdf_path),
                "--resume-json",
                str(resume_json_path),
                "--output",
                str(layout_audit_path),
                "--page-budget",
                str(plan["page_budget"]),
            ]
            try:
                layout_result = subprocess.run(
                    layout_cmd,
                    check=True,
                    text=True,
                    capture_output=True,
                )
                if layout_result.stdout:
                    (run_dir / "layout_audit.stdout.txt").write_text(layout_result.stdout, encoding="utf-8")
                if layout_result.stderr:
                    (run_dir / "layout_audit.stderr.txt").write_text(layout_result.stderr, encoding="utf-8")
                if layout_audit_path.exists():
                    layout_audit_data = load_json(layout_audit_path)
            except subprocess.CalledProcessError as layout_error:
                error_parts = [
                    f"command: {' '.join(layout_cmd)}",
                    f"exit_code: {layout_error.returncode}",
                ]
                if layout_error.stdout:
                    error_parts.append("stdout:\n" + layout_error.stdout)
                if layout_error.stderr:
                    error_parts.append("stderr:\n" + layout_error.stderr)
                (run_dir / "layout_audit.error.txt").write_text("\n\n".join(error_parts) + "\n", encoding="utf-8")
        rules_audit = build_audit_report(normalized, profile, job, plan, enforcement_audit, layout_audit_data)
        rules_audit_path = run_dir / "rules_audit.json"
        rules_audit_path.write_text(json.dumps(rules_audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        va_notes_path = run_dir / "va_notes.md"
        write_va_notes(va_notes_path, rules_audit, job)
        status = "success"
        error = None
    except Exception as e:
        status = "failed"
        error = str(e)
        attempt_meta = None
        (run_dir / "error.txt").write_text(error + "\n", encoding="utf-8")

    metadata = {
        "client_name": args.client_name,
        "profile_file": str(profile_path),
        "job_id": job.get("job_id"),
        "job_file": str(Path(args.job_file).expanduser().resolve()) if args.job_file else None,
        "company": job.get("Name"),
        "position": job.get("position"),
        "llm_agent": args.llm_agent,
        "llm_provider": args.llm_provider,
        "openai_model": args.openai_model if args.llm_provider == "openai" else None,
        "gemini_model": args.gemini_model if args.llm_provider == "gemini" else None,
        "attempt_meta": attempt_meta,
        "skills_plan_attempt_meta": skills_plan_meta,
        "skills_writer_attempt_meta": skills_writer_meta,
        "bullet_plan_attempt_meta": bullet_plan_meta,
        "bullet_writer_attempt_meta": bullet_writer_meta,
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "status": status,
        "artifacts": {
            "job_input": str(run_dir / "job_input.json"),
            "build_plan": str(run_dir / "build_plan.json"),
            "prompt": str(run_dir / "prompt.txt"),
            "skills_plan_prompt": str(run_dir / "skills_plan.prompt.txt"),
            "skills_plan": str(run_dir / "skills_plan.json") if (run_dir / "skills_plan.json").exists() else None,
            "skills_writer_prompt": str(run_dir / "skills_writer.prompt.txt") if (run_dir / "skills_writer.prompt.txt").exists() else None,
            "skills_writer": str(run_dir / "skills_writer.json") if (run_dir / "skills_writer.json").exists() else None,
            "bullet_plan_prompt": str(run_dir / "bullet_plan.prompt.txt") if (run_dir / "bullet_plan.prompt.txt").exists() else None,
            "bullet_plan": str(run_dir / "bullet_plan.json") if (run_dir / "bullet_plan.json").exists() else None,
            "bullet_writer_prompt": str(run_dir / "bullet_writer.prompt.txt") if (run_dir / "bullet_writer.prompt.txt").exists() else None,
            "bullet_writer": str(run_dir / "bullet_writer.json") if (run_dir / "bullet_writer.json").exists() else None,
            "resume_json": str(run_dir / "resume.json"),
            "resume_pdf": str(run_dir / "resume.pdf"),
            "layout_audit": str(layout_audit_path) if layout_audit_path else None,
            "rules_audit": str(rules_audit_path) if rules_audit_path else None,
            "va_notes": str(va_notes_path) if va_notes_path else None,
        },
        "page_budget": plan["page_budget"],
        "positioning": plan["positioning"],
        "display_work_authorization": args.show_work_authorization,
        "skills_plan_error": skills_plan_error,
        "skills_writer_error": skills_writer_error,
        "bullet_plan_error": bullet_plan_error,
        "bullet_writer_error": bullet_writer_error,
        "error": error,
    }
    (run_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if status != "success":
        raise SystemExit(f"Run failed. See {run_dir / 'error.txt'}")

    print(str(run_dir))


if __name__ == "__main__":
    main()
