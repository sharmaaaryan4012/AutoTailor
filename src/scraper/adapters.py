"""
src/scraper/adapters.py
-----------------------
Job listing scrapers.

Adapters
--------
SimplifyNewGradAdapter
    Fetches the SimplifyJobs/New-Grad-Positions GitHub README via raw HTTP
    (no browser needed — it's a public CDN URL) and parses the HTML tables
    embedded in the Markdown. Returns listings from the AI/DS and SWE sections.

    Table structure (5 <td> per row):
      0: Company  (<strong><a href="simplify.jobs/c/...">Name</a></strong>)
             or   ↳  (continuation row — inherits previous company)
      1: Role title (plain text, may contain emoji flags)
      2: Location   (<details> or plain text)
      3: Application links (first <a href> is the direct apply URL)
      4: Age        ("2d", "5d", etc.)

    Legend flags in the README (stripped from role titles before use):
      🛂  Does NOT offer sponsorship   → hard-reject signal
      🇺🇸  Requires U.S. Citizenship   → hard-reject signal
      🔒  Closed application           → skip
      🔥  FAANG+ company
      🎓  Advanced degree required

extract_page_text(url)
    Playwright headless fallback that opens any URL and returns
    document.body.innerText for the eligibility and Gemini modules.
"""

from __future__ import annotations

import logging
import random
import re
import time
from dataclasses import dataclass, field
from typing import Iterator

import requests

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

_SIMPLIFY_RAW_URL = (
    "https://raw.githubusercontent.com/SimplifyJobs/"
    "New-Grad-Positions/dev/README.md"
)

# Section headings to scrape — keys are substrings to locate each <table>
_TARGET_SECTIONS = [
    "Data Science, AI & Machine Learning New Grad Roles",
    "Software Engineering New Grad Roles",   # broad net; Gemini classifies
]

# Emoji flags that are hard-reject signals at the listing level
_HARD_REJECT_EMOJI = {
    "🛂",   # no sponsorship
    "🇺🇸",  # US citizenship required
}

# Listings with this emoji are closed — skip unconditionally
_CLOSED_EMOJI = "🔒"

# Emoji to strip from role titles before storing/displaying
_STRIP_EMOJI = re.compile(
    r"[\U0001F300-\U0001FFFF\U00002702-\U000027B0\U0000231A-\U0000231B"
    r"\U00002614-\U00002615\U00002702\U00002705\U00002728\U0000274C"
    r"\U0000274E\U0000FE0F]",
    re.UNICODE,
)


@dataclass
class JobListing:
    company: str
    title: str
    location: str
    apply_url: str
    age_label: str          # "2d", "5d", "30d+"
    flags: list[str] = field(default_factory=list)   # emoji flags found
    hard_reject_hint: bool = False   # True if a flag signals ineligibility


# ── HTML parsing helpers ───────────────────────────────────────────────────────

def _strip_html_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def _extract_text(cell_html: str) -> str:
    """Extract visible text from a <td> cell, collapsing whitespace."""
    text = _strip_html_tags(cell_html)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_first_href(cell_html: str) -> str | None:
    """Return the first href value found in a table cell."""
    m = re.search(r'href="([^"]+)"', cell_html)
    return m.group(1) if m else None


def _extract_location(cell_html: str) -> str:
    """
    Location cells are either plain text or a <details> block.
    Unwrap the <details> and join multiple locations with ' / '.
    """
    # Remove <details>, <summary>, </details>, </summary> tags
    text = re.sub(r"</?(?:details|summary)[^>]*>", " ", cell_html)
    # Replace <br>, </br>, <br/> with separator
    text = re.sub(r"</?br\s*/?>", " / ", text, flags=re.IGNORECASE)
    text = _strip_html_tags(text)
    text = re.sub(r"\s+", " ", text).strip()
    # Trim "4 locations: " prefix that comes from <summary>
    text = re.sub(r"^\d+\s+locations?\s*[:/]?\s*", "", text).strip()
    return text


# ── Simplify README adapter ────────────────────────────────────────────────────

class SimplifyNewGradAdapter:
    """
    Fetches and parses the SimplifyJobs/New-Grad-Positions README.

    This uses raw HTTP (requests library) — no browser needed since the README
    is a plain-text CDN response. Playwright is only used for the follow-up
    extract_page_text() call on individual apply links.
    """

    def __init__(
        self,
        sections: list[str] = _TARGET_SECTIONS,
        max_listings: int = 50,
        max_age_days: int = 7,
    ) -> None:
        self.sections = sections
        self.max_listings = max_listings
        self.max_age_days = max_age_days

    def fetch(self) -> list[JobListing]:
        """
        Download the README and return parsed listings from target sections.
        Closed listings (🔒) are skipped. Hard-reject flag is set but not
        filtered here — eligibility.py makes the final call.
        """
        logger.info("Fetching Simplify README from %s", _SIMPLIFY_RAW_URL)
        try:
            resp = requests.get(_SIMPLIFY_RAW_URL, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Failed to download Simplify README: %s", exc)
            return []

        content = resp.text
        listings: list[JobListing] = []

        for section_heading in self.sections:
            section_start = content.find(section_heading)
            if section_start == -1:
                logger.warning("Section not found in README: %r", section_heading)
                continue

            # Advance to the next <table> after this heading
            table_start = content.find("<table", section_start)
            if table_start == -1:
                continue
            table_end = content.find("</table>", table_start)
            if table_end == -1:
                continue

            table_html = content[table_start : table_end + 8]
            section_listings = list(self._parse_table(table_html))
            logger.info(
                "Section %r: %d raw rows parsed", section_heading, len(section_listings)
            )
            listings.extend(section_listings)

            if len(listings) >= self.max_listings:
                break

        return listings[: self.max_listings]

    def _parse_table(self, table_html: str) -> Iterator[JobListing]:
        """
        Parse one <table> block into JobListing objects.

        Handles:
        - Continuation rows (company cell is "↳") — inherit previous company name.
        - <details> location cells.
        - Emoji flag detection.
        - Closed listing filtering (🔒).
        - Age filtering (skip if older than max_age_days).
        """
        # Extract all <tr> blocks
        row_pattern = re.compile(r"<tr>(.*?)</tr>", re.DOTALL | re.IGNORECASE)
        td_pattern = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL | re.IGNORECASE)

        current_company: str = ""
        current_company_url: str = ""
        is_header = True  # skip the first <tr> (header row)

        for row_match in row_pattern.finditer(table_html):
            row_html = row_match.group(1)
            cells = td_pattern.findall(row_html)

            if is_header or len(cells) < 4:
                is_header = False
                continue

            # ── Cell 0: Company ───────────────────────────────────────────────
            company_cell = cells[0]
            company_text = _extract_text(company_cell)

            if company_text.startswith("↳"):
                # Continuation row — use last seen company
                company = current_company
            else:
                # Strip emoji prefix (🔥 FAANG marker) from company name
                company = _STRIP_EMOJI.sub("", company_text).strip()
                company_href = _extract_first_href(company_cell) or ""
                current_company = company
                current_company_url = company_href

            # ── Cell 1: Role title ────────────────────────────────────────────
            raw_title = _extract_text(cells[1])

            # Detect and record emoji flags before stripping
            flags: list[str] = []
            hard_reject_hint = False
            for emoji in _HARD_REJECT_EMOJI:
                if emoji in raw_title:
                    flags.append(emoji)
                    hard_reject_hint = True

            # Skip closed listings immediately
            if _CLOSED_EMOJI in raw_title:
                logger.debug("Skipping closed listing: %s @ %s", raw_title, company)
                continue

            title = _STRIP_EMOJI.sub("", raw_title).strip()

            # ── Cell 2: Location ──────────────────────────────────────────────
            location = _extract_location(cells[2])

            # ── Cell 3: Apply link ────────────────────────────────────────────
            apply_url = _extract_first_href(cells[3]) or ""
            if not apply_url:
                logger.debug("No apply URL found for %s @ %s — skipping", title, company)
                continue

            # ── Cell 4: Age ────────────────────────────────────────────────────
            age_label = _extract_text(cells[4]) if len(cells) > 4 else ""
            if self._is_too_old(age_label):
                logger.debug("Skipping stale listing (%s): %s @ %s", age_label, title, company)
                continue

            yield JobListing(
                company=company,
                title=title,
                location=location,
                apply_url=apply_url,
                age_label=age_label,
                flags=flags,
                hard_reject_hint=hard_reject_hint,
            )

    def _is_too_old(self, age_label: str) -> bool:
        """
        Return True if the age label indicates the listing is older than
        max_age_days. The README uses labels like "2d", "5d", "30d+".
        """
        if not age_label:
            return False
        m = re.match(r"(\d+)d", age_label)
        if not m:
            return False
        days = int(m.group(1))
        return days > self.max_age_days


# ── Generic Playwright fallback ────────────────────────────────────────────────

def extract_page_text(url: str, timeout_ms: int = 20_000) -> str:
    """
    Open a URL with a headless Playwright browser and return
    document.body.innerText (the full visible text, no HTML).

    Used to extract the full job description text from individual apply links
    so eligibility.py and gemini_client can process the content.

    Parameters
    ----------
    url : str
        The job application or JD page URL.
    timeout_ms : int
        Navigation timeout in milliseconds (default: 20s).

    Returns
    -------
    str
        Extracted body text, or an empty string on failure.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        logger.error("Playwright not installed — cannot extract page text from %s", url)
        return ""

    logger.info("Extracting page text from %s", url)

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()

            # Randomised polite delay before navigation (anti-bot courtesy)
            time.sleep(random.uniform(1.5, 3.5))

            try:
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                # Give JS a moment to settle
                page.wait_for_timeout(1500)
            except PWTimeout:
                logger.warning("Navigation timed out for %s — returning partial text", url)

            text: str = page.evaluate("document.body.innerText") or ""
            browser.close()

        logger.debug("Extracted %d chars from %s", len(text), url)
        return text

    except Exception as exc:
        logger.error("extract_page_text failed for %s: %s", url, exc)
        return ""
