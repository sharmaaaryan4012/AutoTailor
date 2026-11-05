"""
src/main.py
-----------
Core execution loop for the automated job-watching and resume-tailoring pipeline.

Phase order per listing:
  1. Scrape       — SimplifyNewGradAdapter fetches README listings
  2. Dedup        — StateManager.is_new() skips already-seen fingerprints
  3. Flag check   — Skip listings flagged 🛂/🇺🇸 in the Simplify legend
  4. Page extract — extract_page_text() fetches the full JD via Playwright
  5. Eligibility  — evaluate_eligibility() hard-gates on regex patterns
  6. AI tailor    — gemini_client.generate_patch() classifies + patches
  7. Patch apply  — patch_applier.apply_patch() rewrites bullet text
  8. PDF render   — pdf_generator.render_to_pdf() (1-page validated)
  9. File export  — copy to RESUME_EXPORT_DIR if set
 10. Discord      — discord_webhook.send_alert() delivers embed + PDF
 11. Persist      — StateManager.mark_seen() + save()

Run:
    python -m src.main
    python -m src.main --dry-run   (skip Gemini + PDF + Discord; just log what would run)
    python -m src.main --limit 5   (process at most 5 listings)
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Global default socket timeout to prevent indefinite network hangs during sleep/network transitions
socket.setdefaulttimeout(45.0)

# ── Logging setup (must happen before any module imports that log at import-time)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("data/pipeline.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")

# ── Internal imports (after logging is configured) ─────────────────────────────
from src.scraper.adapters import SimplifyNewGradAdapter, extract_page_text
from src.scraper.state_manager import StateManager
from src.filtering.eligibility import evaluate_eligibility, explain_eligibility
from src.ai_tailor.gemini_client import generate_patch, ResumePatch
from src.ai_tailor.patch_applier import apply_patch
from src.renderer.pdf_generator import render_to_pdf
from src.delivery.discord_webhook import send_alert

# ── Config from environment ────────────────────────────────────────────────────
_DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
_RESUME_EXPORT_DIR   = os.getenv("RESUME_EXPORT_DIR", "")   # optional local sync dir
_MIN_FIT_SCORE       = int(os.getenv("MIN_FIT_SCORE", "55"))  # skip delivery below this

# ── Base resume paths (track → file) ──────────────────────────────────────────
_BASE_RESUMES: dict[str, Path] = {
    "AI_ENGINEERING": Path("data/base_resumes/base_ai_engineer.md"),
    "DATA_SCIENCE":   Path("data/base_resumes/base_data_science.md"),
}

# Output directory for rendered PDFs
_OUTPUT_DIR = Path("data/output")


def _safe_filename(company: str, title: str) -> str:
    """Produce a filesystem-safe filename stem from company and title."""
    raw = f"{company}_{title}"
    safe = re.sub(r"[^\w\-]", "_", raw)
    safe = re.sub(r"_+", "_", safe).strip("_")
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"{safe[:80]}_{date_str}"


def _export_pdf(pdf_path: Path, track: str) -> None:
    """Copy a rendered PDF to the optional RESUME_EXPORT_DIR, organised by track."""
    if not _RESUME_EXPORT_DIR:
        return
    export_root = Path(_RESUME_EXPORT_DIR)
    track_dir = export_root / track.lower()
    try:
        track_dir.mkdir(parents=True, exist_ok=True)
        dest = track_dir / pdf_path.name
        shutil.copy2(pdf_path, dest)
        logger.info("Exported PDF to %s", dest)
    except OSError as exc:
        logger.warning("Could not export PDF to %s: %s", _RESUME_EXPORT_DIR, exc)


def run_pipeline(dry_run: bool = False, limit: int = 50) -> None:
    """
    Execute one full pipeline run.

    Parameters
    ----------
    dry_run : bool
        If True, skip Gemini API calls, PDF rendering, and Discord delivery.
        Useful for verifying scraping + eligibility without spending quota.
    limit : int
        Maximum number of listings to process in this run.
    """
    logger.info("=" * 60)
    logger.info("Pipeline starting  [dry_run=%s, limit=%d]", dry_run, limit)
    logger.info("=" * 60)

    # ── Phase 0: Initialise state ──────────────────────────────────────────────
    state = StateManager()
    state.prune_old_fingerprints()
    logger.info("State loaded: %d seen fingerprints", state.seen_count)

    # ── Phase 1: Scrape ────────────────────────────────────────────────────────
    # Fetch a wider candidate pool from the README so `limit` applies to
    # genuinely unexamined listings rather than already-seen entries.
    fetch_pool_size = max(limit * 5, 50)
    adapter = SimplifyNewGradAdapter(max_listings=fetch_pool_size, max_age_days=14)
    raw_listings = adapter.fetch()
    logger.info("Scraped %d raw listings from Simplify", len(raw_listings))

    # ── Run counters ───────────────────────────────────────────────────────────
    stats = {
        "scraped":      len(raw_listings),
        "skipped_seen": 0,
        "skipped_flag": 0,
        "hard_rejected": 0,
        "irrelevant":   0,
        "low_score":    0,
        "pdf_overflow": 0,
        "delivered":    0,
        "errors":       0,
    }

    processed = 0

    for listing in raw_listings:
        if processed >= limit:
            break

        company   = listing.company
        title     = listing.title
        apply_url = listing.apply_url
        location  = listing.location

        logger.info("─" * 50)
        logger.info("Processing: %s @ %s  [%s]", title, company, listing.age_label)

        # ── Phase 2: Dedup ─────────────────────────────────────────────────────
        if not state.is_new(apply_url, title, company):
            logger.info("  → SKIP (already seen)")
            stats["skipped_seen"] += 1
            continue

        # ── Phase 3: Listing-level emoji flag check ────────────────────────────
        if listing.hard_reject_hint:
            logger.info("  → HARD_REJECT (listing flag: %s)", listing.flags)
            state.mark_rejected(apply_url, title, company, "FLAG", str(listing.flags))
            stats["skipped_flag"] += 1
            processed += 1
            continue

        try:
            _process_listing(
                company=company,
                title=title,
                location=location,
                apply_url=apply_url,
                state=state,
                stats=stats,
                dry_run=dry_run,
            )
        except KeyboardInterrupt:
            logger.warning("Interrupted — saving state before exit")
            state.update_last_run()
            state.save()
            raise
        except Exception as exc:
            logger.exception("Unhandled error processing %s @ %s: %s", title, company, exc)
            stats["errors"] += 1
            # Still mark as seen so we don't retry a broken listing forever
            state.mark_seen(apply_url, title, company)

        processed += 1

    # ── Persist state ──────────────────────────────────────────────────────────
    state.update_last_run()
    state.save()

    # ── Summary ────────────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("Run complete")
    logger.info("  Scraped       : %d", stats["scraped"])
    logger.info("  Seen/skipped  : %d", stats["skipped_seen"])
    logger.info("  Flag rejected : %d", stats["skipped_flag"])
    logger.info("  Hard rejected : %d", stats["hard_rejected"])
    logger.info("  Irrelevant    : %d", stats["irrelevant"])
    logger.info("  Low score     : %d", stats["low_score"])
    logger.info("  PDF overflow  : %d", stats["pdf_overflow"])
    logger.info("  Delivered     : %d", stats["delivered"])
    logger.info("  Errors        : %d", stats["errors"])
    logger.info("=" * 60)


def _process_listing(
    *,
    company: str,
    title: str,
    location: str,
    apply_url: str,
    state: StateManager,
    stats: dict,
    dry_run: bool,
) -> None:
    """
    Process a single new listing through Phases 4–11.
    All state mutations (mark_seen / mark_rejected) happen here.
    Does NOT call state.save() — caller does that after the full loop.
    """

    # ── Phase 4: Extract full page text ───────────────────────────────────────
    # Seed the text with the title + company in case the JD page can't be loaded.
    page_text = f"{title} at {company}\n\n"
    if not dry_run:
        extracted = extract_page_text(apply_url)
        if extracted:
            page_text += extracted
        else:
            logger.warning("  Could not extract page text — proceeding on title+company only")
    else:
        logger.info("  [DRY RUN] Skipping page text extraction")
        page_text += f"Location: {location}"

    # ── Phase 5: Regex eligibility gate ───────────────────────────────────────
    result = explain_eligibility(page_text)
    status = result["status"]

    if status == "HARD_REJECT":
        logger.info(
            "  → HARD_REJECT [%s] pattern=%r",
            result["label"], result["matched_pattern"]
        )
        state.mark_rejected(
            apply_url, title, company,
            reason="HARD_REJECT",
            matched_pattern=result["matched_pattern"],
        )
        stats["hard_rejected"] += 1
        return

    logger.info("  → Eligibility: %s [%s]", status, result["label"])

    # ── Phase 6: Gemini classification + patch generation ─────────────────────
    if dry_run:
        logger.info("  [DRY RUN] Skipping Gemini call")
        state.mark_seen(apply_url, title, company)
        return

    try:
        patch: ResumePatch = generate_patch(page_text)
    except Exception as exc:
        logger.error("  Gemini failed: %s — marking seen and skipping", exc)
        state.mark_seen(apply_url, title, company)
        stats["errors"] += 1
        return

    logger.info(
        "  Gemini: track=%s fit=%d keywords=%s",
        patch.track, patch.fit_score, patch.extracted_keywords
    )

    if patch.track == "IRRELEVANT":
        logger.info("  → IRRELEVANT (Gemini classification)")
        state.mark_rejected(apply_url, title, company, reason="IRRELEVANT")
        stats["irrelevant"] += 1
        return

    if patch.fit_score < _MIN_FIT_SCORE:
        logger.info("  → LOW_SCORE (%d < %d threshold)", patch.fit_score, _MIN_FIT_SCORE)
        state.mark_rejected(
            apply_url, title, company,
            reason="LOW_SCORE",
            matched_pattern=f"fit_score={patch.fit_score}",
        )
        stats["low_score"] += 1
        return

    # ── Phase 7: Select base resume + apply patch ──────────────────────────────
    base_md_path = _BASE_RESUMES.get(patch.track)
    if base_md_path is None or not base_md_path.exists():
        logger.error("  Base resume not found for track %s — skipping", patch.track)
        state.mark_seen(apply_url, title, company)
        stats["errors"] += 1
        return

    try:
        patched_md = apply_patch(str(base_md_path), patch.extracted_keywords)
    except Exception as exc:
        logger.error("  patch_applier failed: %s", exc)
        state.mark_seen(apply_url, title, company)
        stats["errors"] += 1
        return

    # ── Phase 8: Render PDF ────────────────────────────────────────────────────
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    filename = _safe_filename(company, title)
    pdf_path = _OUTPUT_DIR / f"{filename}.pdf"

    success = render_to_pdf(patched_md, str(pdf_path))
    if not success:
        logger.warning("  → PDF_OVERFLOW or render error — not delivering")
        state.mark_rejected(
            apply_url, title, company,
            reason="PDF_OVERFLOW",
            matched_pattern=str(pdf_path.name),
        )
        stats["pdf_overflow"] += 1
        return

    logger.info("  PDF: %s", pdf_path.name)

    # ── Phase 9: Export to sync dir ───────────────────────────────────────────
    _export_pdf(pdf_path, patch.track)

    # ── Phase 10: Discord delivery ─────────────────────────────────────────────
    if _DISCORD_WEBHOOK_URL:
        kws_str = ", ".join(patch.extracted_keywords) if patch.extracted_keywords else "None"
        job_meta = {
            "company":   company,
            "title":     title,
            "location":  location,
            "apply_url": apply_url,
            "track":     patch.track,
            "fit_score": patch.fit_score,
            "reasoning": f"Injected keywords: {kws_str}",
        }
        delivered = send_alert(job_meta, str(pdf_path), _DISCORD_WEBHOOK_URL)
        if delivered:
            stats["delivered"] += 1
        else:
            logger.warning("  Discord delivery failed (PDF still saved locally)")
    else:
        logger.info("  DISCORD_WEBHOOK_URL not set — skipping delivery")

    # ── Phase 11: Mark as seen ─────────────────────────────────────────────────
    state.mark_seen(apply_url, title, company)

    # Polite inter-listing delay (avoid hammering apply-link servers)
    time.sleep(2.0)


# ── CLI entry point ────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Automated job-watcher and resume-tailoring pipeline"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scrape and check eligibility without calling Gemini, rendering PDFs, or posting to Discord.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        metavar="N",
        help="Maximum number of listings to process per run (default: 50).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    # Ensure data directory exists for the log file
    Path("data").mkdir(exist_ok=True)
    run_pipeline(dry_run=args.dry_run, limit=args.limit)
