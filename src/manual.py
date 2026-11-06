"""
src/manual.py
-------------
Manual / on-demand resume tailoring and delivery CLI.

Allows tailoring a resume directly for a specific job without running the
full automated scraper loop.

Supports:
  1. Direct keyword injection (e.g., --keywords "PyTorch, CUDA, Triton, TensorRT")
  2. Full JD extraction via Gemini (e.g., --jd "..." or --jd-file path/to/jd.txt)
  3. Combined mode: Provide both JD and extra custom keywords
  4. Track override (--track AI_ENGINEERING or DATA_SCIENCE)
  5. Deterministic Playwright PDF rendering (strict 1-page check)
  6. Discord webhook delivery with rich embed & PDF attachment

Examples:
  # Quick keyword injection for AI Engineering:
  python -m src.manual -c "Anthropic" -t "Research Engineer" -k "PyTorch, Triton, vLLM, CUDA, Ray" --track ai

  # Provide JD text and let Gemini classify & extract:
  python -m src.manual -c "DeepMind" -t "Research Scientist" --jd "We seek experience in JAX, Haiku, reinforcement learning..."

  # Read JD from a text file:
  python -m src.manual -c "Meta" -t "AI Systems Engineer" --jd-file /path/to/jd.txt
"""

from __future__ import annotations

import argparse
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

_BASE_RESUMES: dict[str, Path] = {
    "AI_ENGINEERING": Path("data/base_resumes/base_ai_engineer.md"),
    "DATA_SCIENCE":   Path("data/base_resumes/base_data_science.md"),
}
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

    Parameters
    ----------
    company : str
        Company name.
    title : str
        Role title.
    jd_text : str, optional
        Job description text. If provided and track is not specified, Gemini
        will classify the role and extract keywords.
    keywords : list of str, optional
        Explicit technical keywords to inject.
    track : str, optional
        "AI_ENGINEERING" or "DATA_SCIENCE" (or shorthands "ai", "ds").
    apply_url : str, optional
        Link to the job posting.
    location : str, optional
        Role location for Discord embed.
    deliver_discord : bool, default True
        Whether to send the PDF and embed to Discord.
    output_path : str, optional
        Custom path for rendered PDF. Defaults to data/output/<Company>_<Title>_<Date>.pdf.

    Returns
    -------
    Path
        Path to the rendered PDF.
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

    base_resume_path = _BASE_RESUMES.get(resolved_track)
    if not base_resume_path or not base_resume_path.exists():
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
        "-c", "--company",
        required=True,
        help="Company name (e.g. 'Apple', 'Meta', 'OpenAI')",
    )
    parser.add_argument(
        "-t", "--title",
        required=True,
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

    jd_text = args.jd
    if args.jd_file:
        if not args.jd_file.exists():
            print(f"Error: JD file not found: {args.jd_file}", file=sys.stderr)
            sys.exit(1)
        jd_text = args.jd_file.read_text(encoding="utf-8")

    keyword_list = [k.strip() for k in args.keywords.split(",")] if args.keywords else None

    try:
        pdf_path = tailor_manual(
            company=args.company,
            title=args.title,
            jd_text=jd_text,
            keywords=keyword_list,
            track=args.track,
            apply_url=args.url,
            location=args.location,
            deliver_discord=not args.no_discord,
            output_path=args.output,
        )
        print(f"\n[Success] Tailored resume written to: {pdf_path.resolve()}")
    except Exception as exc:
        logger.error("Tailoring failed: %s", exc, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
