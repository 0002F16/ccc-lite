#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

from PIL import Image
from PyPDF2 import PdfReader


def render_thumbnail(pdf_path: Path, size: int = 1600) -> Path:
    out_dir = Path(tempfile.mkdtemp(prefix="ccc-layout-audit-"))
    subprocess.run(
        ["qlmanage", "-t", "-s", str(size), "-o", str(out_dir), str(pdf_path)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    png_path = out_dir / f"{pdf_path.name}.png"
    if not png_path.exists():
        raise FileNotFoundError(f"thumbnail not generated for {pdf_path}")
    return png_path


def image_metrics(png_path: Path, threshold: int = 245) -> dict:
    img = Image.open(png_path).convert("L")
    width, height = img.size
    mask = img.point(lambda p: 255 if p < threshold else 0)
    bbox = mask.getbbox()
    if not bbox:
        return {
            "image_size": {"width": width, "height": height},
            "content_bbox": None,
            "bbox_height_ratio": 0.0,
            "bbox_width_ratio": 0.0,
            "top_gap_ratio": 1.0,
            "bottom_gap_ratio": 1.0,
            "ink_ratio": 0.0,
            "max_internal_vertical_gap_ratio": 1.0,
            "ink_rows": 0,
        }

    left, top, right, bottom = bbox
    px = mask.load()
    total_ink = 0
    ink_rows = []
    for y in range(height):
        row_ink = 0
        for x in range(width):
            if px[x, y]:
                row_ink += 1
        total_ink += row_ink
        if top <= y < bottom:
            ink_rows.append(row_ink)

    gaps = []
    current_gap = 0
    for row_ink in ink_rows:
        if row_ink == 0:
            current_gap += 1
        else:
            if current_gap:
                gaps.append(current_gap)
                current_gap = 0
    if current_gap:
        gaps.append(current_gap)

    return {
        "image_size": {"width": width, "height": height},
        "content_bbox": {"left": left, "top": top, "right": right, "bottom": bottom},
        "bbox_height_ratio": round((bottom - top) / height, 4),
        "bbox_width_ratio": round((right - left) / width, 4),
        "top_gap_ratio": round(top / height, 4),
        "bottom_gap_ratio": round((height - bottom) / height, 4),
        "ink_ratio": round(total_ink / (width * height), 4),
        "max_internal_vertical_gap_ratio": round((max(gaps) if gaps else 0) / height, 4),
        "ink_rows": sum(1 for row_ink in ink_rows if row_ink > 0),
    }


def resume_json_metrics(resume_json_path: Path | None) -> dict | None:
    if not resume_json_path or not resume_json_path.exists():
        return None
    data = json.loads(resume_json_path.read_text(encoding="utf-8"))
    experience = data.get("experience", []) or []
    skills = data.get("skills", {}) or {}
    certs = data.get("certifications", []) or []
    bullets_total = sum(len(role.get("bullets", []) or []) for role in experience)
    return {
        "roles": len(experience),
        "bullets_total": bullets_total,
        "skill_categories": len(skills),
        "certifications": len(certs),
        "summary_chars": len(data.get("summary", "")),
        "education_items": len(data.get("education", []) or []),
    }


def classify_layout(page_count: int, metrics: dict, resume_metrics: dict | None, page_budget: int = 1) -> tuple[str, list[str], list[str]]:
    reasons = []
    suggestions = []

    if page_count > page_budget:
        reasons.append(f"page_count={page_count} (budget={page_budget})")
        suggestions.append("Tighten the content or page-budget constraints before delivery.")
        return "overflow", reasons, suggestions

    if page_budget > 1 and page_count > 1:
        return "balanced", reasons, suggestions

    underfill_score = 0
    dense_score = 0

    if metrics["bbox_height_ratio"] < 0.68:
        underfill_score += 1
        reasons.append(f"bbox_height_ratio={metrics['bbox_height_ratio']} < 0.68")
    if metrics["bottom_gap_ratio"] > 0.28:
        underfill_score += 1
        reasons.append(f"bottom_gap_ratio={metrics['bottom_gap_ratio']} > 0.28")
    if metrics["ink_ratio"] < 0.085:
        underfill_score += 1
        reasons.append(f"ink_ratio={metrics['ink_ratio']} < 0.085")

    if metrics["bbox_height_ratio"] > 0.84:
        dense_score += 1
        reasons.append(f"bbox_height_ratio={metrics['bbox_height_ratio']} > 0.84")
    if metrics["bottom_gap_ratio"] < 0.1:
        dense_score += 1
        reasons.append(f"bottom_gap_ratio={metrics['bottom_gap_ratio']} < 0.10")
    if metrics["ink_ratio"] > 0.135:
        dense_score += 1
        reasons.append(f"ink_ratio={metrics['ink_ratio']} > 0.135")

    if underfill_score >= 2:
        status = "underfilled"
        suggestions.append("Enrich the structured source profile or render more valid content (context line, more grounded bullets, certifications).")
    elif dense_score >= 2:
        status = "dense"
        suggestions.append("Trim bullets/skills or tighten layout before delivery.")
    else:
        status = "balanced"

    if resume_metrics:
        if resume_metrics["roles"] <= 1:
            suggestions.append("Single-role resumes are most likely to underfill; prefer 5–6 grounded bullets, a role context line, and a visible certifications section.")
        if status == "underfilled" and resume_metrics["certifications"] == 0:
            suggestions.append("Missing certifications can make the page feel sparse when experience is thin.")
        if status == "dense" and resume_metrics["bullets_total"] >= 12:
            suggestions.append("Too many bullets may be driving visual density; trim to the strongest evidence.")

    return status, reasons, suggestions


def audit(pdf_path: Path, resume_json_path: Path | None = None, page_budget: int = 1) -> dict:
    page_count = len(PdfReader(str(pdf_path)).pages)
    png_path = render_thumbnail(pdf_path)
    metrics = image_metrics(png_path)
    resume_metrics = resume_json_metrics(resume_json_path)
    status, reasons, suggestions = classify_layout(page_count, metrics, resume_metrics, page_budget=page_budget)
    return {
        "pdf_path": str(pdf_path),
        "resume_json_path": str(resume_json_path) if resume_json_path else None,
        "page_budget": page_budget,
        "page_count": page_count,
        "status": status,
        "metrics": metrics,
        "resume_metrics": resume_metrics,
        "reasons": reasons,
        "suggestions": suggestions,
        "render_preview_png": str(png_path),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Audit CCC resume PDF layout for underfill/overflow risk")
    ap.add_argument("pdf_path")
    ap.add_argument("--resume-json")
    ap.add_argument("--output")
    ap.add_argument("--page-budget", type=int, default=1)
    args = ap.parse_args()

    pdf_path = Path(args.pdf_path).expanduser().resolve()
    resume_json_path = Path(args.resume_json).expanduser().resolve() if args.resume_json else None
    result = audit(pdf_path, resume_json_path, page_budget=args.page_budget)

    if args.output:
        out_path = Path(args.output).expanduser().resolve()
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
