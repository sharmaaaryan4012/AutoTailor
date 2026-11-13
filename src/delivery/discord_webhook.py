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


def _format_contacts_field(contacts: list[dict], max_items: int = 4) -> str:
    """Format hiring manager or referral contact dicts into a Discord embed field value."""
    lines: list[str] = []
    for c in contacts[:max_items]:
        if not isinstance(c, dict):
            continue
        name = (c.get("name") or "").strip()
        if not name:
            continue
        role = (c.get("title") or c.get("info") or "").strip()
        linkedin = (c.get("linkedin_url") or "").strip()
        email = (c.get("email") or "").strip()

        entry = f"• **{name}**"
        if role:
            entry += f" — {role}"
        parts: list[str] = []
        if linkedin:
            parts.append(f"[LinkedIn]({linkedin})")
        if email:
            parts.append(f"`{email}`")
        if parts:
            entry += f" ({' · '.join(parts)})"

        if sum(len(x) + 1 for x in lines) + len(entry) > 1000:
            break
        lines.append(entry)
    return "\n".join(lines)


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
        Optional keys:
            source_label        : str        — Footer tag (default: recruiting-pipeline)
            age_label           : str        — Posting age (e.g. '1h')
            hiring_managers     : list[dict] — Enriched recruiter / HM contacts
            referral_candidates : list[dict] — Enriched referral candidates
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

    company             = job_meta.get("company", "Unknown Company")
    title               = job_meta.get("title", "Unknown Role")
    location            = job_meta.get("location", "Unknown Location")
    apply_url           = job_meta.get("apply_url", "")
    track               = job_meta.get("track", "IRRELEVANT")
    fit_score           = job_meta.get("fit_score", 0)
    reasoning           = job_meta.get("reasoning", "")
    source_label        = job_meta.get("source_label") or "recruiting-pipeline"
    age_label           = (job_meta.get("age_label") or "").strip()
    hiring_managers     = job_meta.get("hiring_managers") or []
    referral_candidates = job_meta.get("referral_candidates") or []

    colour      = _TRACK_COLOURS.get(track, _DEFAULT_COLOUR)
    track_label = _TRACK_LABELS.get(track, track)

    # ── Fit score bar (visual indicator) ─────────────────────────────────────
    filled = round(fit_score / 10)
    score_bar = "█" * filled + "░" * (10 - filled)

    fields = [
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
    ]

    hm_text = _format_contacts_field(hiring_managers, max_items=4)
    if hm_text:
        fields.append({
            "name": "👔 Hiring Managers & Recruiters",
            "value": hm_text,
            "inline": False,
        })

    ref_text = _format_contacts_field(referral_candidates, max_items=3)
    if ref_text:
        fields.append({
            "name": "🤝 Potential Referrals",
            "value": ref_text,
            "inline": False,
        })

    if not hm_text and not ref_text and job_meta.get("contacts_checked"):
        fields.append({
            "name": "📇 Hiring Contacts",
            "value": "Checked — 0 indexed contacts found for this company.",
            "inline": False,
        })

    footer_parts = [source_label]
    if age_label:
        footer_parts.append(f"Posted {age_label} ago")
    footer_parts.append(pdf.name)

    # ── Build Discord embed payload ───────────────────────────────────────────
    embed = {
        "title": f"{company} — {title}",
        "url": apply_url or None,
        "color": colour,
        "fields": fields,
        "footer": {
            "text": " • ".join(footer_parts),
        },
    }

    # Remove None url to avoid Discord API error
    if not embed.get("url"):
        embed.pop("url", None)

    # ── Multipart payload: embed JSON + PDF file ──────────────────────────────
    payload_json = json.dumps({"embeds": [embed]})

    return _post_with_retry(webhook_url, payload_json, pdf)


def _post_with_retry(webhook_url: str, payload_json: str, pdf: Path) -> bool:
    """Send the multipart Discord POST, retrying on transient SSL/network errors or 429/5xx."""
    max_attempts = 4
    for attempt in range(1, max_attempts + 1):
        try:
            with pdf.open("rb") as pdf_file:
                response = requests.post(
                    webhook_url,
                    data={"payload_json": payload_json},
                    files={"file": (pdf.name, pdf_file, "application/pdf")},
                    timeout=30,
                )
        except requests.RequestException as exc:
            logger.warning("Discord webhook request failed (attempt %d/%d): %s", attempt, max_attempts, exc)
            if attempt < max_attempts:
                time.sleep(attempt * 1.5)
                continue
            logger.error("Discord webhook permanently failed after %d attempts.", max_attempts)
            return False

        if response.status_code in (200, 204):
            logger.info("Discord alert delivered for %s", pdf.name)
            return True

        if response.status_code == 429 and attempt < max_attempts:
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

        if response.status_code >= 500 and attempt < max_attempts:
            logger.warning(
                "Discord server error HTTP %d (attempt %d/%d) — retrying...",
                response.status_code, attempt, max_attempts
            )
            time.sleep(attempt * 1.5)
            continue

        # Unexpected client error (e.g. 400/401/404)
        logger.error(
            "Discord webhook returned HTTP %d: %s",
            response.status_code,
            response.text[:300],
        )
        return False

    return False
