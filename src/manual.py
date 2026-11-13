"""
src/manual.py
-------------
Manual / on-demand resume tailoring and delivery CLI.

Allows tailoring a resume directly for a specific job without running the
full automated scraper loop.

Supports:
  1. Reading from an input file (e.g. manual_input.txt or --from-file)
  2. Automatic extraction of Company & Title from raw JD text via Gemini
  3. Direct keyword injection (e.g., --keywords "PyTorch, CUDA, Triton, TensorRT")
  4. Full JD extraction via Gemini (e.g., --jd "..." or --jd-file path/to/jd.txt)
  5. Combined mode: Provide both JD and extra custom keywords
  6. Track override (--track AI_ENGINEERING or DATA_SCIENCE)
  7. Deterministic Playwright PDF rendering (strict 1-page check)
  8. Discord webhook delivery with rich embed & PDF attachment

Examples:
  # Simplest: Just paste JD into manual_input.txt and run:
  ./manual.sh

  # Quick keyword injection for AI Engineering:
  python -m src.manual -c "Anthropic" -t "Research Engineer" -k "PyTorch, Triton, vLLM, CUDA, Ray" --track ai

  # Provide JD text and let Gemini classify & extract:
  python -m src.manual -c "DeepMind" -t "Research Scientist" --jd "We seek experience in JAX, Haiku, reinforcement learning..."

  # Read JD from a text file:
  python -m src.manual --from-file manual_input.txt
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Prevent sockets from hanging indefinitely
socket.setdefaulttimeout(45.0)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("manual_tailor")

from src.ai_tailor.patch_applier import apply_patch
from src.renderer.pdf_generator import render_to_pdf
from src.delivery.discord_webhook import send_alert

def get_base_resume_path(track: str) -> Path:
    """
    Resolve base resume path for a track.
    Prefers user's personal base resume (e.g. data/base_resumes/base_ai_engineer.md)
    if present; otherwise falls back to the open-source template
    (e.g. data/base_resumes/template_ai_engineer.md).
    """
    track_key = "ai_engineer" if "AI" in track.upper() else "data_science"
    personal = Path(f"data/base_resumes/base_{track_key}.md")
    if personal.exists():
        return personal
    template = Path(f"data/base_resumes/template_{track_key}.md")
    if template.exists():
        return template
    return personal

_OUTPUT_DIR = Path("data/output")


def _normalize_track(raw_track: str | None) -> str | None:
    if not raw_track:
        return None
    cleaned = raw_track.strip().upper()
    if cleaned in ("AI", "AI_ENGINEERING", "AI_ENG", "SWE_ML", "ML"):
        return "AI_ENGINEERING"
    if cleaned in ("DS", "DATA_SCIENCE", "DATA", "ANALYTICS"):
        return "DATA_SCIENCE"
    return cleaned


def _safe_filename(company: str, title: str) -> str:
    raw = f"{company}_{title}"
    safe = re.sub(r"[^\w\-]", "_", raw)
    safe = re.sub(r"_+", "_", safe).strip("_")
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"{safe[:80]}_{date_str}"


def infer_company_and_title(jd_text: str) -> tuple[str, str]:
    """Use Gemini to quickly infer the company name and job title from raw JD text."""
    try:
        from google import genai
        from google.genai import types
        from pydantic import BaseModel

        class JobMeta(BaseModel):
            company: str
            title: str

        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            return "Company", "Job Role"

        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=20000),
        )
        resp = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=jd_text[:4000],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=JobMeta.model_json_schema(),
                system_instruction=(
                    "Extract the exact company name and job title from the job posting text. "
                    "Return ONLY valid JSON with keys 'company' and 'title'."
                ),
                temperature=0.1,
            ),
        )
        res = json.loads(resp.text)
        comp = res.get("company", "").strip() or "Company"
        title = res.get("title", "").strip() or "Job Role"
        logger.info("Inferred from JD: Company='%s', Title='%s'", comp, title)
        return comp, title
    except Exception as exc:
        logger.warning("Could not infer company/title via Gemini: %s. Using default names.", exc)
        return "Company", "Job Role"


def parse_input_file(path: Path) -> dict:
    """
    Parse an input text file containing either:
      1. A header block (Company:, Role:, Keywords:, Track:, URL:) followed by --- and the JD
      2. Or raw job description text pasted directly from the web.
    """
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path.resolve()}")

    raw_text = path.read_text(encoding="utf-8").strip()
    if not raw_text:
        raise ValueError(
            f"Input file '{path.name}' is empty. Please paste a job description into it."
        )

    data = {
        "company": None,
        "title": None,
        "keywords": [],
        "track": None,
        "url": None,
        "location": "Remote / Flexible",
        "jd_text": "",
    }

    # Split on markdown divider if present
    parts = re.split(r"^---+\s*$", raw_text, maxsplit=1, flags=re.MULTILINE)
    if len(parts) == 2:
        header_text = parts[0]
        body_text = parts[1].strip()
    else:
        # Check if first lines look like headers
        header_lines = []
        body_lines = []
        in_header = True
        for line in raw_text.splitlines():
            clean = line.strip()
            if in_header and (clean.startswith("#") or not clean):
                continue
            if in_header and re.match(r"^(company|role|title|keywords|skills|track|url|link|location)\s*:", clean, re.IGNORECASE):
                header_lines.append(clean)
            else:
                in_header = False
                body_lines.append(line)
        header_text = "\n".join(header_lines)
        body_text = "\n".join(body_lines).strip()
        if not body_text:
            body_text = raw_text

    # Parse headers if present
    for line in header_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(
            r"^(company|role|title|position|keywords|skills|track|url|link|location)\s*:\s*(.*)$",
            line,
            re.IGNORECASE,
        )
        if m:
            key = m.group(1).lower()
            val = m.group(2).strip()
            if not val:
                continue
            if key == "company":
                data["company"] = val
            elif key in ("role", "title", "position"):
                data["title"] = val
            elif key in ("keywords", "skills"):
                data["keywords"] = [k.strip() for k in val.split(",") if k.strip()]
            elif key == "track":
                data["track"] = val
            elif key in ("url", "link"):
                data["url"] = val
            elif key == "location":
                data["location"] = val

    data["jd_text"] = body_text or raw_text

    # If company or title still missing, use Gemini to automatically infer from the JD text
    if not data["company"] or not data["title"]:
        logger.info("Company/Title not specified in headers; analyzing JD text with Gemini...")
        inferred_comp, inferred_title = infer_company_and_title(data["jd_text"])
        data["company"] = data["company"] or inferred_comp
        data["title"] = data["title"] or inferred_title

    return data


def tailor_manual(
    company: str,
    title: str,
    jd_text: str | None = None,
    keywords: list[str] | None = None,
    track: str | None = None,
    apply_url: str | None = None,
    location: str | None = "Remote / Flexible",
    deliver_discord: bool = True,
    output_path: str | None = None,
) -> Path:
    """
    Manually tailor and render a 1-page ATS resume, with optional Discord delivery.
    """
    logger.info("============================================================")
    logger.info("Manual Tailoring: %s — %s", company, title)
    logger.info("============================================================")

    resolved_track = _normalize_track(track)
    injected_keywords: list[str] = [k.strip() for k in (keywords or []) if k and k.strip()]
    fit_score = 100
    reasoning = "Manual on-demand tailoring"

    # If JD is provided, run Gemini for classification / keyword extraction
    if jd_text and jd_text.strip():
        logger.info("Analyzing job description with Gemini...")
        from src.ai_tailor.gemini_client import generate_patch

        patch = generate_patch(jd_text)
        logger.info(
            "Gemini assessment: track=%s, fit_score=%d, extracted_keywords=%s",
            patch.track, patch.fit_score, patch.extracted_keywords,
        )

        if not resolved_track:
            resolved_track = patch.track if patch.track != "IRRELEVANT" else "AI_ENGINEERING"
        fit_score = patch.fit_score

        # Combine explicit keywords with Gemini's extracted keywords (deduped, preserving order)
        seen_lower = {k.lower() for k in injected_keywords}
        for kw in patch.extracted_keywords:
            if kw.lower() not in seen_lower:
                injected_keywords.append(kw)
                seen_lower.add(kw.lower())

        reasoning = f"Gemini Fit {fit_score}/100 · Keywords: {', '.join(injected_keywords)}"

    # Default to AI_ENGINEERING if track still undetermined
    if not resolved_track:
        resolved_track = "AI_ENGINEERING"
        logger.info("Track unspecified; defaulting to AI_ENGINEERING")

    base_resume_path = get_base_resume_path(resolved_track)
    if not base_resume_path.exists():
        raise FileNotFoundError(
            f"Base resume for track '{resolved_track}' not found at {base_resume_path}"
        )

    logger.info("Target resume: %s", base_resume_path)
    logger.info("Keywords to inject: %s", injected_keywords or ["(none)"])

    # 1. Apply deterministic patch
    patched_content = apply_patch(str(base_resume_path), injected_keywords)

    # 2. Render to single-page PDF
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if output_path:
        dest_pdf = Path(output_path)
    else:
        dest_pdf = _OUTPUT_DIR / f"{_safe_filename(company, title)}.pdf"

    logger.info("Rendering PDF to: %s", dest_pdf)
    success = render_to_pdf(patched_content, str(dest_pdf))
    if not success:
        raise RuntimeError(
            f"PDF rendering failed or exceeded 1 page constraint for {dest_pdf.name}!"
        )

    logger.info("✓ PDF successfully generated and validated (strictly 1 page).")

    # 3. Deliver to Discord
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")
    if deliver_discord and webhook_url:
        logger.info("Dispatching to Discord...")
        job_meta = {
            "company":   company,
            "title":     title,
            "location":  location or "Remote",
            "apply_url": apply_url or "",
            "track":     resolved_track,
            "fit_score": fit_score,
            "reasoning": reasoning,
        }
        delivered = send_alert(job_meta, str(dest_pdf), webhook_url)
        if delivered:
            logger.info("✓ Discord notification delivered with PDF attachment!")
        else:
            logger.warning("Discord delivery failed (PDF still preserved locally).")
    elif deliver_discord and not webhook_url:
        logger.warning("DISCORD_WEBHOOK_URL not set — skipped Discord dispatch.")

    return dest_pdf


# ── CLI Interface ─────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AutoTailor Manual: On-demand resume tailoring & delivery"
    )
    parser.add_argument(
        "--from-file",
        nargs="?",
        const="manual_input.txt",
        help="Path to file containing JD and optional headers (default: manual_input.txt)",
    )
    parser.add_argument(
        "-c", "--company",
        help="Company name (e.g. 'Apple', 'Meta', 'OpenAI')",
    )
    parser.add_argument(
        "-t", "--title",
        help="Job role title (e.g. 'AI Engineer', 'Research Scientist')",
    )
    parser.add_argument(
        "-k", "--keywords",
        help="Comma-separated keywords to inject (e.g. 'PyTorch, CUDA, Triton, vLLM')",
    )
    parser.add_argument(
        "--track",
        choices=["ai", "ds", "AI_ENGINEERING", "DATA_SCIENCE"],
        help="Resume track override (ai / ds / AI_ENGINEERING / DATA_SCIENCE)",
    )
    parser.add_argument(
        "--jd",
        help="Raw text of the job description for automated Gemini extraction",
    )
    parser.add_argument(
        "--jd-file",
        type=Path,
        help="Path to a text file containing the job description",
    )
    parser.add_argument(
        "--url",
        help="Direct apply URL for Discord embed",
    )
    parser.add_argument(
        "--location",
        default="Remote / Flexible",
        help="Location string (default: 'Remote / Flexible')",
    )
    parser.add_argument(
        "--no-discord",
        action="store_true",
        help="Generate local PDF only without posting to Discord",
    )
    parser.add_argument(
        "-o", "--output",
        help="Custom output PDF path",
    )
    return parser.parse_args()


def main():
    args = _parse_args()

    # Mode 1: --from-file (or default manual_input.txt if no flags supplied)
    if args.from_file or (not args.company and not args.title and not args.jd and not args.jd_file):
        file_path = Path(args.from_file or "manual_input.txt")
        if not file_path.exists():
            print(
                f"[AutoTailor] Error: Input file '{file_path}' not found.\n"
                f"Please paste the job description into '{file_path}' and run ./manual.sh again.",
                file=sys.stderr,
            )
            sys.exit(1)

        parsed = parse_input_file(file_path)

        # Allow CLI flags to override file headers
        company = args.company or parsed["company"]
        title = args.title or parsed["title"]
        track = args.track or parsed["track"]
        url = args.url or parsed["url"]
        location = args.location if args.location != "Remote / Flexible" else parsed["location"]
        jd_text = parsed["jd_text"]

        # Merge keywords
        cli_kws = [k.strip() for k in args.keywords.split(",")] if args.keywords else []
        combined_kws = list(dict.fromkeys(cli_kws + parsed["keywords"]))

    else:
        # Mode 2: Explicit command line flags
        if not args.company or not args.title:
            print("Error: Either provide --from-file OR both -c/--company and -t/--title", file=sys.stderr)
            sys.exit(1)

        company = args.company
        title = args.title
        track = args.track
        url = args.url
        location = args.location
        combined_kws = [k.strip() for k in args.keywords.split(",")] if args.keywords else None
        jd_text = args.jd
        if args.jd_file:
            if not args.jd_file.exists():
                print(f"Error: JD file not found: {args.jd_file}", file=sys.stderr)
                sys.exit(1)
            jd_text = args.jd_file.read_text(encoding="utf-8")

    try:
        pdf_path = tailor_manual(
            company=company,
            title=title,
            jd_text=jd_text,
            keywords=combined_kws,
            track=track,
            apply_url=url,
            location=location,
            deliver_discord=not args.no_discord,
            output_path=args.output,
        )
        print(f"\n[Success] Tailored resume written to: {pdf_path.resolve()}")
    except Exception as exc:
        logger.error("Tailoring failed: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
