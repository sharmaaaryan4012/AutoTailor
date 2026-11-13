"""
src/filtering/eligibility.py
-----------------------------
Regex-based hard-reject / pass / review filter for visa and eligibility gating.

Evaluation order (short-circuit logic):
  1. PASS immediately  — if any fast-pass signal is present (F-1/OPT/CPT explicit mention)
  2. HARD_REJECT       — if any hard-reject pattern matches
  3. PASS              — if any soft-pass signal matches (new grad, target grad years, degree)
  4. REVIEW            — everything else (Gemini makes the final call)

Design note: PASS signals take priority over HARD_REJECT because a JD that says
"We support F-1 OPT/CPT but do not sponsor H-1B" is still potentially viable.
"""

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

# Step 0: Non-technical / Business titles blacklist
NON_TECH_TITLES: list[str] = [
    "advisor",
    "analyst",
    "rotational",
    "development program",
    "early career program",
    "consultant",
    "business intelligence",
    "bi ",
    "marketing",
    "sales",
    "operations",
    "clerk",
    "admin",
]


def _check_non_tech_title(title: str = "", job_text: str = "") -> str | None:
    """Check if the job title matches any blacklisted non-technical role patterns."""
    target = title.strip().lower()
    if not target and job_text:
        first_line = job_text.strip().splitlines()[0]
        if " at " in first_line:
            target = first_line.split(" at ")[0].strip().lower()
        else:
            target = first_line.strip().lower()

    if target:
        for pattern in NON_TECH_TITLES:
            if pattern in target:
                return pattern
    return None


# Step 1: Fast-pass signals — explicit sponsorship / visa support language
_FAST_PASS_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bf-1\b",
        r"\bf1-opt\b",
        r"\bopt\b",          # Optional Practical Training
        r"\bcpt\b",          # Curricular Practical Training
        # Positive-only: require "available/offered/provided" NOT preceded by "no/not/cannot"
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
            # Restrict context check to the same paragraph if a blank line separates sections
            if "\n\n" in ctx:
                ctx = ctx.rsplit("\n\n", 1)[-1]
            if not _NEGATED_CONTEXT_RE.search(ctx):
                return pattern
    return None

# Step 2: Hard-reject signals — disqualifying language
_HARD_REJECT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(p, re.IGNORECASE), label)
    for p, label in [
        (r"u\.s\.?\s*citizen",                          "us_citizenship"),
        (r"united states citizen",                       "us_citizenship"),
        (r"no (?:visa|immigration) sponsorship",                  "no_sponsorship"),
        (r"will not sponsor",                                     "no_sponsorship"),
        (r"(?:not|cannot|unable to)\s+(?:be\s+)?considering.{0,80}(?:visa|immigration)\s+sponsorship", "no_sponsorship"),
        (r"(?:unable|not able) to sponsor",                       "no_sponsorship"),
        (r"do(?:es)? not (offer|provide)( (?:visa|immigration))? sponsorship",   "no_sponsorship"),
        (r"cannot (provide|offer)( (?:visa|immigration))? sponsorship",           "no_sponsorship"),
        (r"sponsorship (is )?not (available|offered)",            "no_sponsorship"),
        (r"without (?:visa |immigration )?sponsorship",           "no_sponsorship"),
        (r"green card (required|holders? only)",         "green_card_only"),
        (r"must have (permanent|unrestricted) work auth","green_card_only"),
        (r"security clearance",                          "clearance"),
        (r"(secret|top secret|ts/sci) clearance",        "clearance"),
        (r"\bstaff (engineer|scientist|researcher)\b",   "seniority"),
        (r"\bprincipal (engineer|scientist|researcher)\b","seniority"),
        (r"\b(engineering|product|program) manager\b",  "management"),
        (r"\bph\.?d\.?\s+required\b",                   "phd_required"),
        (r"\bphd\s+required\b",                          "phd_required"),
        (r"3\+?\s+years",                                "experience_years"),
        (r"three or more years",                         "experience_years"),
        (r"minimum (of )?3 years",                       "experience_years"),
    ]
]

# Step 3: Soft-pass signals — new grad / target graduation years / degree level
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

    Parameters
    ----------
    job_text : str
        The full text of the job description (title + body).
    title : str, optional
        The job title string. If omitted, extracted from the first line of job_text.

    Returns
    -------
    str
        One of:
          'PASS'        — Eligible; proceed to AI tailoring.
          'HARD_REJECT' — Ineligible; discard immediately (no API call).
          'INELIGIBLE'  — Ineligible due to non-technical/business role.
          'REVIEW'      — Ambiguous; Gemini makes the final classification.
    """
    # ── Step 0: Non-technical / Business title hard-reject ──────────────────
    bad_title = _check_non_tech_title(title, job_text)
    if bad_title:
        logger.info(
            "INELIGIBLE [Non-technical/Business role] matched %r in title %r",
            bad_title, title,
        )
        return "INELIGIBLE"

    if not job_text or not job_text.strip():
        if not title:
            logger.warning("evaluate_eligibility called with empty job_text; returning REVIEW")
        return "REVIEW"

    # ── Step 1: Fast-pass override ──────────────────────────────────────────
    fast_pattern = _find_positive_fast_pass(job_text)
    if fast_pattern:
        logger.debug("Fast-pass matched: %s", fast_pattern.pattern)
        return "PASS"

    # ── Step 2: Hard-reject gate ────────────────────────────────────────────
    for pattern, label in _HARD_REJECT_PATTERNS:
        m = pattern.search(job_text)
        if m:
            logger.info(
                "HARD_REJECT [%s] matched pattern %r at pos %d",
                label, pattern.pattern, m.start(),
            )
            return "HARD_REJECT"

    # ── Step 3: Soft-pass signals ───────────────────────────────────────────
    for pattern in _SOFT_PASS_PATTERNS:
        if pattern.search(job_text):
            logger.debug("Soft-pass matched: %s", pattern.pattern)
            return "PASS"

    # ── Step 4: Ambiguous — send to Gemini ─────────────────────────────────
    return "REVIEW"


def explain_eligibility(job_text: str, title: str = "") -> dict:
    """
    Like evaluate_eligibility, but returns a detailed dict for audit logging.

    Returns
    -------
    dict with keys:
        status          : 'PASS' | 'HARD_REJECT' | 'INELIGIBLE' | 'REVIEW'
        matched_pattern : str | None   (the regex that triggered the decision)
        label           : str | None   (human-readable category)
        reason          : str | None   (human-readable explanation if rejected)
    """
    # ── Step 0: Non-technical / Business title hard-reject ──────────────────
    bad_title = _check_non_tech_title(title, job_text)
    if bad_title:
        return {
            "status": "INELIGIBLE",
            "matched_pattern": bad_title,
            "label": "non_technical_role",
            "reason": "Non-technical/Business role",
        }

    if not job_text or not job_text.strip():
        return {"status": "REVIEW", "matched_pattern": None, "label": "empty_input"}

    fast_pattern = _find_positive_fast_pass(job_text)
    if fast_pattern:
        return {"status": "PASS", "matched_pattern": fast_pattern.pattern, "label": "fast_pass"}

    for pattern, label in _HARD_REJECT_PATTERNS:
        if pattern.search(job_text):
            return {"status": "HARD_REJECT", "matched_pattern": pattern.pattern, "label": label}

    for pattern in _SOFT_PASS_PATTERNS:
        if pattern.search(job_text):
            return {"status": "PASS", "matched_pattern": pattern.pattern, "label": "soft_pass"}

    return {"status": "REVIEW", "matched_pattern": None, "label": "no_signal"}
