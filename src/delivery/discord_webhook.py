"""
src/delivery/discord_webhook.py
--------------------------------
Delivers a tailored resume PDF to a Discord channel via webhook.

Discord message structure:
  - Rich embed with role metadata (company, title, track, fit score, apply URL).
  - PDF attached as a file so it can be downloaded directly from Discord.

Embed colour coding:
  AI_ENGINEERING → Discord blurple  (#5865F2)
  DATA_SCIENCE   → Green            (#57F287)
  Other          → Yellow           (#FEE75C)

Rate-limit handling:
  On HTTP 429, the response body contains a "retry_after" float (seconds).
  We sleep that duration and retry once. Persistent failure is logged and
  returns False — delivery is best-effort and never blocks the pipeline.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# Discord embed colour codes (as integers)
_TRACK_COLOURS: dict[str, int] = {
    "AI_ENGINEERING": 0x5865F2,   # blurple
    "DATA_SCIENCE":   0x57F287,   # green
    "IRRELEVANT":     0xFEE75C,   # yellow (shouldn't be delivered, but safe fallback)
}
_DEFAULT_COLOUR = 0xEB459E   # hot pink — signals something unexpected

_TRACK_LABELS: dict[str, str] = {
    "AI_ENGINEERING": "🤖 AI Engineering",
    "DATA_SCIENCE":   "📊 Data Science",
    "IRRELEVANT":     "⚠️ Irrelevant",
}


def send_alert(
    job_meta: dict,
    pdf_path: str,
    webhook_url: str,
) -> bool:
    """
    Post a Discord message with a rich embed and an attached PDF.

    Parameters
    ----------
    job_meta : dict
        Must contain keys:
            company   : str   — Company name
            title     : str   — Job title
            location  : str   — Location string
            apply_url : str   — Direct application URL
            track     : str   — "AI_ENGINEERING" | "DATA_SCIENCE" | "IRRELEVANT"
            fit_score : int   — 0–100 Gemini fit score
            reasoning : str   — Short reasoning string from Gemini
    pdf_path : str
        Path to the tailored resume PDF file to attach.
    webhook_url : str
        Discord webhook URL (from DISCORD_WEBHOOK_URL env var).

    Returns
    -------
    bool
        True if the message was delivered (HTTP 200/204), False otherwise.
    """
    pdf = Path(pdf_path)
    if not pdf.exists():
        logger.error("PDF not found at %s — skipping Discord delivery", pdf_path)
        return False

    company   = job_meta.get("company", "Unknown Company")
    title     = job_meta.get("title", "Unknown Role")
    location  = job_meta.get("location", "Unknown Location")
    apply_url = job_meta.get("apply_url", "")
    track     = job_meta.get("track", "IRRELEVANT")
    fit_score = job_meta.get("fit_score", 0)
    reasoning = job_meta.get("reasoning", "")

    colour      = _TRACK_COLOURS.get(track, _DEFAULT_COLOUR)
    track_label = _TRACK_LABELS.get(track, track)

    # ── Fit score bar (visual indicator) ─────────────────────────────────────
    filled = round(fit_score / 10)
    score_bar = "█" * filled + "░" * (10 - filled)

    # ── Build Discord embed payload ───────────────────────────────────────────
    embed = {
        "title": f"{company} — {title}",
        "url": apply_url or None,
        "color": colour,
        "fields": [
            {
                "name": "🏷️ Track",
                "value": track_label,
                "inline": True,
            },
            {
                "name": "📍 Location",
                "value": location or "Not specified",
                "inline": True,
            },
            {
                "name": "🎯 Fit Score",
                "value": f"`{score_bar}` {fit_score}/100",
                "inline": False,
            },
            {
                "name": "💬 Reasoning",
                "value": reasoning[:1020] if reasoning else "—",  # Discord field limit: 1024
                "inline": False,
            },
        ],
        "footer": {
            "text": f"recruiting-pipeline • {pdf.name}",
        },
    }

    # Remove None url to avoid Discord API error
    if not embed.get("url"):
        embed.pop("url", None)

    # ── Multipart payload: embed JSON + PDF file ──────────────────────────────
    payload_json = json.dumps({"embeds": [embed]})

    return _post_with_retry(webhook_url, payload_json, pdf)


def _post_with_retry(webhook_url: str, payload_json: str, pdf: Path) -> bool:
    """Send the multipart Discord POST, retrying once on a 429 rate-limit."""
    for attempt in range(1, 3):
        try:
            with pdf.open("rb") as pdf_file:
                response = requests.post(
                    webhook_url,
                    data={"payload_json": payload_json},
                    files={"file": (pdf.name, pdf_file, "application/pdf")},
                    timeout=30,
                )
        except requests.RequestException as exc:
            logger.error("Discord webhook request failed (attempt %d): %s", attempt, exc)
            return False

        if response.status_code in (200, 204):
            logger.info("Discord alert delivered for %s", pdf.name)
            return True

        if response.status_code == 429 and attempt == 1:
            # Rate limited — read retry_after and wait
            try:
                retry_after = response.json().get("retry_after", 2.0)
            except Exception:
                retry_after = 2.0
            logger.warning(
                "Discord rate-limited (429) — waiting %.1fs before retry", retry_after
            )
            time.sleep(float(retry_after) + 0.25)   # small buffer
            continue

        # Unexpected error
        logger.error(
            "Discord webhook returned HTTP %d: %s",
            response.status_code,
            response.text[:300],
        )
        return False

    return False
