"""
src/filtering/eligibility.py
-----------------------------
Regex-based hard-reject / pass / review filter for visa, title, and clearance eligibility gating.

Evaluation order (short-circuit logic):
  0. TITLE CHECK         — Ineligible if role targets PhD, is sub-level (Skill Level 0 / IT support),
                            senior/executive, or non-technical/business.
  1. ABSOLUTE CLEARANCE  — HARD_REJECT immediately if security clearance or US citizenship is required.
                            (Cannot be bypassed by F-1/OPT fast-pass under any circumstances).
  2. FAST_PASS           — PASS if explicit F-1 / OPT / CPT or visa sponsorship is stated.
  3. CONDITIONAL REJECT  — HARD_REJECT if no sponsorship, mandatory PhD in body, or 3+ years required.
  4. SOFT_PASS           — PASS if new grad / entry-level / target graduation year / degree mentioned.
  5. REVIEW              — Ambiguous; Gemini makes the final classification call.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

_JOB_SEARCH_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "job_search.yaml"
_DEFAULT_EXCLUDED_COMPANIES: tuple[str, ...] = ("tiktok",)


def _load_excluded_companies() -> list[str]:
    """
    Load excluded company names from config/job_search.yaml, always preserving
    the built-in defaults (e.g., 'tiktok') even if config is absent/incomplete.
    """
    merged: list[str] = list(_DEFAULT_EXCLUDED_COMPANIES)
    try:
        if _JOB_SEARCH_CONFIG_PATH.exists():
            cfg = yaml.safe_load(_JOB_SEARCH_CONFIG_PATH.read_text(encoding="utf-8")) or {}
            raw = cfg.get("excluded_companies") or []
            if isinstance(raw, list):
                for item in raw:
                    val = str(item).strip().lower()
                    if val and val not in merged:
                        merged.append(val)
    except Exception as exc:
        logger.warning("Failed to load excluded_companies from %s: %s", _JOB_SEARCH_CONFIG_PATH, exc)
    return merged


EXCLUDED_COMPANIES: list[str] = _load_excluded_companies()


def is_company_excluded(company: str = "", apply_url: str = "") -> str | None:
    """
    Return the matched excluded company key if the listing belongs to a
    blacklisted company (checking both company name and application URL host/path),
    else None.
    """
    comp_lower = (company or "").lower()
    comp_norm = re.sub(r"[^a-z0-9]", "", comp_lower)
    comp_tokens = re.sub(r"[^a-z0-9]+", " ", comp_lower).strip()
    url_norm = re.sub(r"lifeattiktok", "tiktok", (apply_url or "").lower())

    for excluded in EXCLUDED_COMPANIES:
        ex_norm = re.sub(r"[^a-z0-9]", "", excluded.lower())
        if not ex_norm:
            continue
        if len(ex_norm) >= 5:
            if ex_norm in comp_norm:
                return excluded
        else:
            if comp_norm == ex_norm or re.search(rf"\b{re.escape(ex_norm)}\b", comp_tokens):
                return excluded
        if url_norm and re.search(rf"(?:^|[/.:\-]){re.escape(ex_norm)}(?:$|[/.:\-])", url_norm):
            return excluded
    return None


# ---------------------------------------------------------------------------
# Pattern sets — all compiled once at import time, case-insensitive
# ---------------------------------------------------------------------------

# Step 0: Job Title Ineligibility Filters
_PHD_TITLE_RE = re.compile(
    r"\b(?:ph\.?d\.?|doctorate|doctoral|post[\s\-]?doc)\b",
    re.IGNORECASE,
)

_SUBLEVEL_OR_LOW_SKILL_RE = re.compile(
    r"\b(?:(?:skill\s*)?level\s*0\b|\b0\s*or\s*1\b|\bswe\s*0\b|\bengineer\s*0\b)\b|"
    r"\b(?:help\s*desk|desktop\s*support|it\s+support|tech(?:nical)?\s+support|data\s+entry|data\s+collector)\b",
    re.IGNORECASE,
)

_SENIOR_TITLE_RE = re.compile(
    r"\b(?:senior|sr\.?|staff|principal|lead|manager|director|vp|chief|architect|fellow)\b",
    re.IGNORECASE,
)

_NON_TECH_TITLE_RE = re.compile(
    r"\b(?:advisor|rotational|development\s+program|early\s+career\s+program|"
    r"consult\w*|business\s+intelligence|bi\b|marketing|sales|"
    r"operations|clerk|admin|recruiter|talent|human\s+resources|hr\b)\b|"
    r"\b(?!quantitative\b|quant\b)\w+\s+analyst\b",
    re.IGNORECASE,
)

_INTERN_TITLE_RE = re.compile(
    r"\b(?:interns?|internships?|co-?ops?)\b",
    re.IGNORECASE,
)


def check_title_ineligibility(title: str = "", job_text: str = "") -> dict | None:
    """
    Check if the job title matches any blacklisted or ineligible role patterns:
      1. PhD / Doctoral roles (candidate has BS/MS, no PhD)
      2. Sub-entry / Skill Level 0 / IT support / data entry roles
      3. Senior / leadership roles (excluding Member of Technical Staff)
      4. Non-technical / business / analyst roles
    """
    target = title.strip()
    if not target and job_text:
        first_line = job_text.strip().splitlines()[0]
        if " at " in first_line:
            target = first_line.split(" at ")[0].strip()
        else:
            target = first_line.strip()

    if not target:
        return None

    # 1. PhD / Doctoral roles
    m_phd = _PHD_TITLE_RE.search(target)
    if m_phd:
        return {
            "status": "HARD_REJECT",
            "matched_pattern": m_phd.group(0),
            "label": "phd_only_role",
            "reason": f"Role targets PhD/Doctoral candidates ({m_phd.group(0)!r})",
        }

    # 2. Sub-entry / Level 0 / IT Support
    m_sub = _SUBLEVEL_OR_LOW_SKILL_RE.search(target)
    if m_sub:
        return {
            "status": "HARD_REJECT",
            "matched_pattern": m_sub.group(0),
            "label": "sublevel_or_low_skill_role",
            "reason": f"Sub-entry/Skill Level 0 or IT support role ({m_sub.group(0)!r})",
        }

    # 3. Seniority (allow "member of technical staff")
    target_clean = re.sub(r"\bmember of technical staff\b", "mts", target, flags=re.IGNORECASE)
    m_senior = _SENIOR_TITLE_RE.search(target_clean)
    if m_senior:
        return {
            "status": "HARD_REJECT",
            "matched_pattern": m_senior.group(0),
            "label": "seniority",
            "reason": f"Senior or executive role ({m_senior.group(0)!r})",
        }

    # 4. Non-technical / Business
    m_nontech = _NON_TECH_TITLE_RE.search(target)
    if m_nontech:
        return {
            "status": "INELIGIBLE",
            "matched_pattern": m_nontech.group(0),
            "label": "non_technical_role",
            "reason": f"Non-technical or business role ({m_nontech.group(0)!r})",
        }

    return None


# Step 1: Absolute Hard-Reject Gate (Clearance & Citizenship)
# CRITICAL: These MUST evaluate unconditionally. Fast-pass (F-1 / OPT) CANNOT override
# classified security clearance or US citizenship requirements.
_ABSOLUTE_HARD_REJECT_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"security clearance", re.I), "clearance", "Security clearance required"),
    (re.compile(r"(secret|top secret|ts/sci|ts\\|sci) clearance", re.I), "clearance", "Classified clearance required"),
    (re.compile(r"\bpolygraph\b", re.I), "clearance", "Polygraph required"),
    (re.compile(r"\bdod clearance\b", re.I), "clearance", "DoD clearance required"),
    (re.compile(r"\bpublic trust\b", re.I), "clearance", "Public trust clearance required"),
    (re.compile(r"u\.s\.?\s*citizen", re.I), "us_citizenship", "US Citizenship required"),
    (re.compile(r"united states citizen", re.I), "us_citizenship", "United States Citizenship required"),
    (re.compile(r"only\s+(?:us|u\.s\.)\s+citizens?", re.I), "us_citizenship", "Only US citizens eligible"),
    (re.compile(r"must\s+be\s+(?:a\s+)?(?:us|u\.s\.)\s+citizen", re.I), "us_citizenship", "Must be a US citizen"),
    (re.compile(r"due to federal contract requirements", re.I), "us_citizenship", "Federal contract citizenship/clearance mandated"),
    (re.compile(r"green card (required|holders? only)", re.I), "green_card_only", "Green Card holders only"),
    (re.compile(r"must have (permanent|unrestricted) work auth", re.I), "green_card_only", "Unrestricted/Permanent work auth required"),
]

# Step 2: Fast-pass signals — explicit visa sponsorship / F-1 / OPT support language
_FAST_PASS_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bf-?1\b",
        r"\bf1-opt\b",
        # Explicit word-boundary excluding opt-in, opt-out, option, adoption
        r"\bopt\b(?!\s*[-/]?\s*(?:in|out|ion))\b",
        r"\bcpt\b",
        r"(?<!no )(?<!not )(?<!cannot )visa sponsorship (is )?(available|offered|provided)",
        r"we (do |will )?sponsor",
        r"sponsorship (is )?provided",
    ]
]

_NEGATED_CONTEXT_RE = re.compile(
    r"(?:not\s+considering|will\s+not\s+sponsor|do(?:es)?\s+not\s+(?:offer|provide|sponsor|support)|"
    r"cannot\s+(?:provide|offer|sponsor|consider)|unable\s+to\s+sponsor|no\s+(?:visa|immigration)\s+sponsorship|"
    r"not\s+limited\s+to|without\s+(?:visa\s+|immigration\s+)?sponsorship)",
    re.IGNORECASE,
)


def _find_positive_fast_pass(job_text: str) -> re.Pattern | None:
    """
    Return the first _FAST_PASS_PATTERNS regex whose match is NOT inside a
    negative sponsorship disclaimer (e.g., 'not considering ... F1-OPT, F1-CPT').
    """
    for pattern in _FAST_PASS_PATTERNS:
        for m in pattern.finditer(job_text):
            ctx = job_text[max(0, m.start() - 280) : m.start()]
            if "\n\n" in ctx:
                ctx = ctx.rsplit("\n\n", 1)[-1]
            if not _NEGATED_CONTEXT_RE.search(ctx):
                return pattern
    return None


# Step 3: Conditional Hard-Reject Signals — disqualifying visa sponsorship, PhD mandatory, or experience
_CONDITIONAL_HARD_REJECT_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"no (?:visa|immigration) sponsorship", re.I), "no_sponsorship", "No visa sponsorship"),
    (re.compile(r"will not sponsor", re.I), "no_sponsorship", "Will not sponsor"),
    (re.compile(r"(?:not|cannot|unable to)\s+(?:be\s+)?considering.{0,80}(?:visa|immigration)\s+sponsorship", re.I), "no_sponsorship", "Not considering sponsorship"),
    (re.compile(r"(?:unable|not able) to sponsor", re.I), "no_sponsorship", "Unable to sponsor"),
    (re.compile(r"do(?:es)? not (offer|provide)( (?:visa|immigration))? sponsorship", re.I), "no_sponsorship", "Does not offer sponsorship"),
    (re.compile(r"cannot (provide|offer)( (?:visa|immigration))? sponsorship", re.I), "no_sponsorship", "Cannot provide sponsorship"),
    (re.compile(r"sponsorship (is )?not (available|offered)", re.I), "no_sponsorship", "Sponsorship not available"),
    (re.compile(r"without (?:visa |immigration )?sponsorship", re.I), "no_sponsorship", "Requires work auth without sponsorship"),
    (re.compile(r"\bph\.?d\.?\s+(?:is\s+)?required\b", re.I), "phd_required", "PhD degree required"),
    (re.compile(r"\bphd\s+(?:is\s+)?required\b", re.I), "phd_required", "PhD degree required"),
    (re.compile(r"\bmust\s+(?:have|hold)\s+(?:a\s+)?ph\.?d\b", re.I), "phd_required", "Must have a PhD"),
    (re.compile(r"\bdoctorate\s+(?:degree\s+)?(?:is\s+)?required\b", re.I), "phd_required", "Doctorate required"),
    (re.compile(r"\bph\.?d\.?\s+degree\s+(?:is\s+)?required\b", re.I), "phd_required", "PhD degree required"),
    (re.compile(r"3\+?\s+years", re.I), "experience_years", "3+ years experience required"),
    (re.compile(r"three or more years", re.I), "experience_years", "3+ years experience required"),
    (re.compile(r"minimum (of )?3 years", re.I), "experience_years", "Minimum 3 years experience required"),
]

# Step 4: Soft-pass signals — new grad / target graduation years / degree level
_SOFT_PASS_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bnew\s*grad(uate)?\b",
        r"\bentry.?level\b",
        r"class of (2025|2026|2027)",
        r"\b2026\b",
        r"\b2027\b",
        r"bachelor'?s (degree|of science|of arts)",
        r"\bbs\b|\bb\.s\.\b",
        r"master'?s (degree|of science|of arts)",
        r"\bms\b|\bm\.s\.\b",
        r"0.?2 years (of )?experience",
        r"(recent|upcoming) graduate",
    ]
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def evaluate_eligibility(job_text: str, title: str = "") -> str:
    """
    Evaluate a raw job description for eligibility.

    Returns 'PASS', 'HARD_REJECT', 'INELIGIBLE', or 'REVIEW'.
    """
    res = explain_eligibility(job_text, title=title)
    return res["status"]


def explain_eligibility(job_text: str, title: str = "") -> dict:
    """
    Detailed eligibility evaluation with pattern matching and rejection reasoning.
    """
    # ── Step 0: Title-Level Ineligibility ──────────────────────────────────
    title_check = check_title_ineligibility(title, job_text)
    if title_check:
        logger.info(
            "%s [%s] matched pattern %r in title %r: %s",
            title_check["status"], title_check["label"], title_check["matched_pattern"], title, title_check["reason"],
        )
        return title_check

    if not job_text or not job_text.strip():
        return {"status": "REVIEW", "matched_pattern": None, "label": "empty_input"}

    # ── Step 1: Absolute Clearance & Citizenship Gate ─────────────────────
    # Cannot be bypassed by F-1/OPT fast-pass under any circumstances
    for pattern, label, reason in _ABSOLUTE_HARD_REJECT_PATTERNS:
        m = pattern.search(job_text)
        if m:
            logger.info(
                "HARD_REJECT [%s] matched pattern %r at pos %d: %s",
                label, pattern.pattern, m.start(), reason,
            )
            return {
                "status": "HARD_REJECT",
                "matched_pattern": pattern.pattern,
                "label": label,
                "reason": reason,
            }

    # ── Step 2: Fast-Pass Override (Visa/OPT) ──────────────────────────────
    fast_pattern = _find_positive_fast_pass(job_text)
    if fast_pattern:
        logger.debug("Fast-pass matched: %s", fast_pattern.pattern)
        return {"status": "PASS", "matched_pattern": fast_pattern.pattern, "label": "fast_pass"}

    # ── Step 3: Conditional Hard-Reject Gate (Visa/PhD/Experience) ──────────
    for pattern, label, reason in _CONDITIONAL_HARD_REJECT_PATTERNS:
        m = pattern.search(job_text)
        if m:
            logger.info(
                "HARD_REJECT [%s] matched pattern %r at pos %d: %s",
                label, pattern.pattern, m.start(), reason,
            )
            return {
                "status": "HARD_REJECT",
                "matched_pattern": pattern.pattern,
                "label": label,
                "reason": reason,
            }

    # ── Step 4: Soft-Pass Signals ───────────────────────────────────────────
    for pattern in _SOFT_PASS_PATTERNS:
        if pattern.search(job_text):
            logger.debug("Soft-pass matched: %s", pattern.pattern)
            return {"status": "PASS", "matched_pattern": pattern.pattern, "label": "soft_pass"}

    # ── Step 5: Ambiguous — send to Gemini ─────────────────────────────────
    return {"status": "REVIEW", "matched_pattern": None, "label": "no_signal"}
