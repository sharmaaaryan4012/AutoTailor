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

import html as html_lib
import itertools
import json
import logging
import os
import random
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests
import yaml

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
    source: str = "simplify"
    details_url: str = ""            # Optional JSON API endpoint (e.g., SmartRecruiters)
    prefetched_text: str = ""        # Optional pre-fetched JD body


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


# ── Shared age, URL, and text helpers ──────────────────────────────────────────

_JOB_SEARCH_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "job_search.yaml"

_INTERN_TITLE_RE = re.compile(r"\b(?:interns?|internships?|co-?ops?)\b", re.IGNORECASE)

_SR_SENIOR_OR_NONTECH_RE = re.compile(
    r"\b(?:senior|sr\.?|staff|principal|lead|manager|director|vp|chief|"
    r"architect|fellow|distinguished|advisor|analyst|consultant|supervisor|"
    r"coordinator|specialist|recruiter|sales|operator|mechanic|nursing|nurse|"
    r"therapist|technician|clinical|elisa|agronomic|molecular|toxicology|"
    r"pharmacology|polymer|nucleic|iii|iv|v)\b|\b\d+\+\s*years?\b",
    re.IGNORECASE,
)

_SR_RELEVANT_TITLE_RE = re.compile(
    r"\b(?:machine learning|artificial intelligence|ai|data scien\w*|"
    r"research scientist|applied scientist|ml|mlops|llm|deep learning|"
    r"nlp|computer vision|research engineer)\b|"
    r"(?:software engineer|software developer).*?\b(?:new grad|graduate|entry|junior|university|i|1)\b",
    re.IGNORECASE,
)


def _parse_age_days(age_label: str) -> float | None:
    """Convert shorthand age labels ('26m', '18h', '3d', '1w', '2mo') to days."""
    if not age_label:
        return None
    clean = age_label.strip().lower()
    m = re.match(r"(\d+)\s*(mo|w|d|hrs?|h|mins?|m)\b", clean)
    if not m:
        return None
    val = int(m.group(1))
    unit = m.group(2)
    if unit == "mo":
        return float(val * 30)
    if unit == "w":
        return float(val * 7)
    if unit == "d":
        return float(val)
    if unit.startswith("h"):
        return val / 24.0
    if unit.startswith("m"):
        return val / 1440.0
    return None


def _normalize_url_for_dedup(url: str) -> str:
    """Normalize a URL for cross-source deduplication (strips UTM/ref params)."""
    if not url:
        return ""
    raw = html_lib.unescape(url.strip())
    try:
        parsed = urlparse(raw)
        clean_qs = [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if not k.lower().startswith("utm_") and k.lower() not in {"ref", "s"}
        ]
        normalized = urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path.rstrip("/"),
            "",
            urlencode(clean_qs),
            "",
        ))
        return normalized
    except Exception:
        return raw.lower().rstrip("/")


def resolve_apply_url(url: str, timeout: int = 10) -> str:
    """
    Resolve shortener/redirector links (e.g., zapply.jobs/l/d/..., go.vansh.nyc/...)
    to the destination ATS URL when possible.
    Never replaces a redirector URL with a generic index fallback (e.g. zapply.jobs/jobs).
    """
    if not url:
        return url
    parsed_src = urlparse(url)
    host = parsed_src.netloc.lower()
    if not any(h in host for h in ("zapply.jobs", "go.vansh.nyc")):
        return url

    try:
        resp = requests.get(
            url,
            allow_redirects=True,
            timeout=timeout,
            stream=True,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        final_url = resp.url or url
        resp.close()
        parsed_dest = urlparse(final_url)
        if (
            final_url
            and parsed_dest.netloc.lower() != host
            and not parsed_dest.path.rstrip("/") in {"", "/jobs"}
        ):
            logger.debug("Resolved redirect %s -> %s", url, final_url)
            return final_url
    except requests.RequestException as exc:
        logger.debug("Could not resolve redirect for %s: %s", url, exc)

    # Smart fallback for zapply.jobs/l/d/sr-<Company>-<PostingId> slugs
    m_sr = re.search(r"/l/d/sr-([A-Za-z0-9_]+)-(\d+)", parsed_src.path)
    if m_sr:
        comp_id, posting_id = m_sr.group(1), m_sr.group(2)
        sr_url = f"https://jobs.smartrecruiters.com/{comp_id}/{posting_id}"
        logger.debug("Derived SmartRecruiters URL from slug %s -> %s", url, sr_url)
        return sr_url

    return url


def fetch_smartrecruiters_text(details_url: str, timeout: int = 15) -> str:
    """
    Fetch clean full job description text directly from SmartRecruiters' official
    Public Posting API endpoint (`actions.details`) without launching Playwright.
    """
    if not details_url:
        return ""
    try:
        resp = requests.get(details_url, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("SmartRecruiters detail fetch failed (%s): %s", details_url, exc)
        return ""

    parts: list[str] = []
    comp_name = (data.get("company") or {}).get("name")
    title = data.get("name")
    loc = (data.get("location") or {}).get("fullLocation")
    if title or comp_name:
        parts.append(f"{title or ''} at {comp_name or ''}".strip())
    if loc:
        parts.append(f"Location: {loc}")

    exp = (data.get("experienceLevel") or {}).get("label")
    if exp:
        parts.append(f"Experience Level: {exp}")

    sections = ((data.get("jobAd") or {}).get("sections") or {})
    for key in ("jobDescription", "qualifications", "additionalInformation", "companyDescription"):
        sec = sections.get(key)
        if not isinstance(sec, dict):
            continue
        sec_title = sec.get("title", "")
        sec_html = sec.get("text", "")
        if sec_html:
            clean_txt = html_lib.unescape(re.sub(r"<[^>]+>", "\n", sec_html))
            clean_txt = re.sub(r"\n{3,}", "\n\n", clean_txt).strip()
            if clean_txt:
                parts.append(f"\n## {sec_title}\n{clean_txt}" if sec_title else clean_txt)

    return "\n".join(parts).strip()


# ── SpeedyApply AI New Grad Adapter ────────────────────────────────────────────

_SPEEDYAPPLY_USA_URL = (
    "https://raw.githubusercontent.com/speedyapply/"
    "2027-AI-College-Jobs/main/NEW_GRAD_USA.md"
)


class SpeedyApplyNewGradAdapter:
    """
    Fetches and parses the speedyapply/2027-AI-College-Jobs NEW_GRAD_USA.md table.
    """

    def __init__(self, max_listings: int = 50, max_age_days: int = 14) -> None:
        self.max_listings = max_listings
        self.max_age_days = max_age_days

    def fetch(self) -> list[JobListing]:
        logger.info("Fetching SpeedyApply AI New Grad feed from %s", _SPEEDYAPPLY_USA_URL)
        try:
            resp = requests.get(_SPEEDYAPPLY_USA_URL, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Failed to download SpeedyApply USA AI feed: %s", exc)
            return []

        listings: list[JobListing] = []
        current_company = ""

        for raw_line in resp.text.splitlines():
            line = raw_line.strip()
            if not line.startswith("|") or "|---" in line or line.lower().startswith("| company"):
                continue

            cols = [c.strip() for c in line.strip("|").split("|")]
            if len(cols) < 6:
                continue

            company_raw = html_lib.unescape(_extract_text(cols[0]))
            company_raw = re.sub(r"\*+", "", company_raw).strip()
            if company_raw.startswith("↳"):
                company = current_company
            else:
                company = _STRIP_EMOJI.sub("", company_raw).strip()
                current_company = company

            raw_title = html_lib.unescape(_extract_text(cols[1]))
            if _CLOSED_EMOJI in raw_title:
                continue

            flags = [e for e in _HARD_REJECT_EMOJI if e in raw_title]
            hard_reject_hint = bool(flags)
            title = _STRIP_EMOJI.sub("", raw_title).strip()

            location = html_lib.unescape(_extract_location(cols[2]))
            apply_url = _extract_first_href(cols[4])
            if not apply_url:
                m_md = re.search(r"\]\((https?://[^)\s]+)\)", cols[4])
                apply_url = m_md.group(1) if m_md else ""
            if not apply_url:
                continue
            apply_url = html_lib.unescape(apply_url)

            age_label = html_lib.unescape(_extract_text(cols[5]))
            age_days = _parse_age_days(age_label)
            if age_days is not None and age_days > self.max_age_days:
                continue

            if not company or not title:
                continue

            listings.append(
                JobListing(
                    company=company,
                    title=title,
                    location=location,
                    apply_url=apply_url,
                    age_label=age_label,
                    flags=flags,
                    hard_reject_hint=hard_reject_hint,
                    source="speedyapply_ai",
                )
            )
            if len(listings) >= self.max_listings:
                break

        logger.info("SpeedyApply AI: %d fresh listings parsed", len(listings))
        return listings


# ── Zapply Data Science & ML Adapter ───────────────────────────────────────────

_ZAPPLY_DS_URL = (
    "https://raw.githubusercontent.com/zapplyjobs/"
    "New-Grad-Data-Science-Jobs-2027/main/README.md"
)


class ZapplyNewGradAdapter:
    """
    Fetches Data Scientist and Machine Learning sections from
    zapplyjobs/New-Grad-Data-Science-Jobs-2027 (updated every 10 minutes).
    Excludes non-DS/ML sections (Data Analyst, Data Engineer, Business Intelligence)
    and optionally skips internship/co-op postings.
    """

    def __init__(
        self,
        sections: tuple[str, ...] = ("Data Scientist", "Machine Learning"),
        max_listings: int = 50,
        max_age_days: int = 14,
        exclude_internships: bool = True,
    ) -> None:
        self.sections = sections
        self.max_listings = max_listings
        self.max_age_days = max_age_days
        self.exclude_internships = exclude_internships

    def fetch(self) -> list[JobListing]:
        logger.info("Fetching Zapply DS/ML feed from %s", _ZAPPLY_DS_URL)
        try:
            resp = requests.get(_ZAPPLY_DS_URL, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Failed to download Zapply DS/ML feed: %s", exc)
            return []

        content = resp.text
        listings: list[JobListing] = []

        # Iterate over <details>...</details> blocks and parse only target sections
        for block in re.finditer(r"<details>(.*?)</details>", content, re.DOTALL | re.IGNORECASE):
            block_text = block.group(1)
            sum_match = re.search(r"<summary>(.*?)</summary>", block_text, re.DOTALL | re.IGNORECASE)
            if not sum_match:
                continue
            section_name = _extract_text(sum_match.group(1))
            if not any(target.lower() in section_name.lower() for target in self.sections):
                continue

            for raw_line in block_text.splitlines():
                line = raw_line.strip()
                if not line.startswith("|") or "|---" in line or line.lower().startswith("| company"):
                    continue

                cols = [c.strip() for c in line.strip("|").split("|")]
                if len(cols) < 6:
                    continue

                company = html_lib.unescape(re.sub(r"\*+", "", _extract_text(cols[0]))).strip()
                company = _STRIP_EMOJI.sub("", company).strip()

                raw_title = html_lib.unescape(_extract_text(cols[1]))
                if _CLOSED_EMOJI in raw_title:
                    continue

                title = _STRIP_EMOJI.sub("", raw_title).strip()
                if self.exclude_internships and _INTERN_TITLE_RE.search(title):
                    continue
                if re.search(
                    r"\b(?:senior|sr\.?|staff|principal|manager|director|vice president|vp)\b",
                    title,
                    re.IGNORECASE,
                ):
                    continue

                location = html_lib.unescape(_extract_location(cols[2]))
                age_label = html_lib.unescape(_extract_text(cols[3]))
                age_days = _parse_age_days(age_label)
                if age_days is not None and age_days > self.max_age_days:
                    continue

                visa_cell = cols[4]
                flags = [e for e in _HARD_REJECT_EMOJI if e in raw_title or e in visa_cell]
                hard_reject_hint = bool(flags) or (
                    "no sponsorship" in visa_cell.lower() or "citizen" in visa_cell.lower()
                )

                apply_url = _extract_first_href(cols[5])
                if not apply_url:
                    m_md = re.search(r"\]\((https?://[^)\s]+)\)", cols[5])
                    apply_url = m_md.group(1) if m_md else ""
                if not apply_url or not company or not title:
                    continue
                apply_url = html_lib.unescape(apply_url)
                details_url = ""
                m_sr = re.search(r"/l/d/sr-([A-Za-z0-9_]+)-(\d+)", apply_url)
                if m_sr:
                    details_url = f"https://api.smartrecruiters.com/v1/companies/{m_sr.group(1)}/postings/{m_sr.group(2)}"

                listings.append(
                    JobListing(
                        company=company,
                        title=title,
                        location=location,
                        apply_url=apply_url,
                        age_label=age_label,
                        flags=flags,
                        hard_reject_hint=hard_reject_hint,
                        source="zapply_ds",
                        details_url=details_url,
                    )
                )
                if len(listings) >= self.max_listings:
                    break

            if len(listings) >= self.max_listings:
                break

        logger.info("Zapply DS/ML: %d fresh listings parsed", len(listings))
        return listings


# ── SmartRecruiters Public Search Adapter ──────────────────────────────────────

_SMARTRECRUITERS_SEARCH_URL = "https://jobs.smartrecruiters.com/sr-jobs/search"


class SmartRecruitersAdapter:
    """
    Queries SmartRecruiters' public job board index (`jobs.smartrecruiters.com/sr-jobs/search`)
    for fresh US AI/ML, Data Science, and New Grad SWE postings, filtering strictly by recency,
    seniority, and technical relevance.
    """

    def __init__(
        self,
        queries: list[str] | None = None,
        countries: tuple[str, ...] = ("us",),
        max_listings: int = 30,
        max_age_days: int = 14,
        exclude_internships: bool = True,
    ) -> None:
        self.queries = queries or [
            '"Machine Learning"',
            '"AI Engineer"',
            '"Data Scientist"',
            '"Research Scientist"',
            '"New Grad"',
            '"Graduate" Data',
        ]
        self.countries = {c.lower() for c in countries}
        self.max_listings = max_listings
        self.max_age_days = max_age_days
        self.exclude_internships = exclude_internships

    def fetch(self) -> list[JobListing]:
        logger.info("Querying SmartRecruiters across %d queries", len(self.queries))
        now = datetime.now(timezone.utc)
        collected: dict[str, tuple[float, JobListing]] = {}

        for kw in self.queries:
            try:
                resp = requests.get(
                    _SMARTRECRUITERS_SEARCH_URL,
                    params={"keyword": kw, "limit": 100},
                    timeout=15,
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                resp.raise_for_status()
                payload = resp.json()
            except Exception as exc:
                logger.warning("SmartRecruiters query %r failed: %s", kw, exc)
                continue

            for item in payload.get("content", []):
                jid = str(item.get("id") or "")
                apply_url = (item.get("applyUrl") or "").strip()
                if not apply_url:
                    continue

                loc = item.get("location") or {}
                country = (loc.get("country") or "").lower()
                if self.countries and country not in self.countries:
                    continue

                rel_str = item.get("releasedDate") or ""
                if not rel_str:
                    continue
                try:
                    dt = datetime.fromisoformat(rel_str.replace("Z", "+00:00"))
                    age_days = (now - dt).total_seconds() / 86400.0
                except ValueError:
                    continue
                if age_days > self.max_age_days:
                    continue

                exp_id = ((item.get("experienceLevel") or {}).get("id") or "").lower()
                if exp_id in {"mid_senior_level", "executive", "director"}:
                    continue
                if self.exclude_internships and exp_id == "internship":
                    continue

                title = (item.get("name") or "").strip()
                company = ((item.get("company") or {}).get("name") or "").strip()
                if not title or not company:
                    continue

                if self.exclude_internships and _INTERN_TITLE_RE.search(title):
                    continue
                title_for_seniority = re.sub(
                    r"\bmember of technical staff\b",
                    "",
                    title,
                    flags=re.IGNORECASE,
                )
                if _SR_SENIOR_OR_NONTECH_RE.search(title_for_seniority):
                    continue
                if not _SR_RELEVANT_TITLE_RE.search(title):
                    continue

                dedup_key = jid or apply_url
                if dedup_key in collected:
                    continue

                if age_days < 1.0:
                    hrs = max(1, int(age_days * 24))
                    age_label = f"{hrs}h"
                else:
                    age_label = f"{int(age_days)}d"

                location_str = (
                    item.get("shortLocation")
                    or ", ".join(p for p in (loc.get("city"), loc.get("region"), country.upper()) if p)
                    or "United States"
                )
                details_url = ((item.get("actions") or {}).get("details") or "").strip()

                collected[dedup_key] = (
                    age_days,
                    JobListing(
                        company=company,
                        title=title,
                        location=location_str,
                        apply_url=apply_url,
                        age_label=age_label,
                        source="smartrecruiters",
                        details_url=details_url,
                    ),
                )

        # Sort newest first and cap at max_listings
        ordered = [
            listing
            for _, listing in sorted(collected.values(), key=lambda pair: pair[0])
        ]
        logger.info("SmartRecruiters: %d fresh filtered listings matched", len(ordered))
        return ordered[: self.max_listings]


# ── Multi-Source Orchestrator ──────────────────────────────────────────────────

def _load_sources_config(config_path: Path = _JOB_SEARCH_CONFIG_PATH) -> dict:
    try:
        if config_path.exists():
            cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            return cfg.get("sources") or {}
    except Exception as exc:
        logger.warning("Failed to read sources config from %s: %s", config_path, exc)
    return {}


def fetch_all_sources(
    max_listings_per_source: int = 60,
    config_path: Path = _JOB_SEARCH_CONFIG_PATH,
) -> list[JobListing]:
    """
    Fetch listings from all enabled sources in config/job_search.yaml, interleave
    them in round-robin order so every source gets fair coverage within run limits,
    and deduplicate across sources by normalized URL and (company, title).
    """
    src_cfg = _load_sources_config(config_path)

    simplify_cfg = src_cfg.get("simplify", {"enabled": True, "max_age_days": 14})
    sa_cfg = src_cfg.get("speedyapply_ai", {"enabled": True, "max_age_days": 14})
    zapply_cfg = src_cfg.get("zapply_ds", {"enabled": True, "max_age_days": 14, "exclude_internships": True})
    sr_cfg = src_cfg.get("smartrecruiters", {"enabled": True, "max_age_days": 14, "exclude_internships": True})
    buckets: list[list[JobListing]] = []

    if simplify_cfg.get("enabled", True):
        buckets.append(
            SimplifyNewGradAdapter(
                max_listings=max_listings_per_source,
                max_age_days=int(simplify_cfg.get("max_age_days", 14)),
            ).fetch()
        )

    if sa_cfg.get("enabled", True):
        buckets.append(
            SpeedyApplyNewGradAdapter(
                max_listings=max_listings_per_source,
                max_age_days=int(sa_cfg.get("max_age_days", 14)),
            ).fetch()
        )

    if zapply_cfg.get("enabled", True):
        buckets.append(
            ZapplyNewGradAdapter(
                max_listings=max_listings_per_source,
                max_age_days=int(zapply_cfg.get("max_age_days", 14)),
                exclude_internships=bool(zapply_cfg.get("exclude_internships", True)),
            ).fetch()
        )

    if sr_cfg.get("enabled", True):
        buckets.append(
            SmartRecruitersAdapter(
                queries=sr_cfg.get("queries"),
                countries=tuple(sr_cfg.get("countries") or ("us",)),
                max_listings=min(max_listings_per_source, 40),
                max_age_days=int(sr_cfg.get("max_age_days", 14)),
                exclude_internships=bool(sr_cfg.get("exclude_internships", True)),
            ).fetch()
        )

    # Interleave across sources so --limit N draws balanced candidates from every feed
    merged: list[JobListing] = []
    seen_urls: set[str] = set()
    seen_roles: set[tuple[str, str]] = set()

    for group in itertools.zip_longest(*buckets):
        for item in group:
            if item is None:
                continue
            url_key = _normalize_url_for_dedup(item.apply_url)
            role_key = (
                re.sub(r"[^a-z0-9]", "", item.company.lower()),
                re.sub(r"[^a-z0-9]+", " ", item.title.lower()).strip(),
            )
            if url_key in seen_urls or role_key in seen_roles:
                continue
            seen_urls.add(url_key)
            seen_roles.add(role_key)
            merged.append(item)

    logger.info(
        "Multi-source aggregate: %d unique listings across %d active feeds",
        len(merged),
        len(buckets),
    )
    return merged


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
