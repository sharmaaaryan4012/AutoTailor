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

import re
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pattern sets — all compiled once at import time, case-insensitive
# ---------------------------------------------------------------------------

# Step 1: Fast-pass signals — explicit sponsorship / visa support language
_FAST_PASS_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bf-1\b",
        r"\bopt\b",          # Optional Practical Training
        r"\bcpt\b",          # Curricular Practical Training
        # Positive-only: require "available/offered/provided" NOT preceded by "no/not/cannot"
        r"(?<!no )(?<!not )(?<!cannot )visa sponsorship (is )?(available|offered|provided)",
        r"we (do |will )?sponsor",
        r"sponsorship (is )?provided",
    ]
]

# Step 2: Hard-reject signals — disqualifying language
_HARD_REJECT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(p, re.IGNORECASE), label)
    for p, label in [
        (r"u\.s\.?\s*citizen",                          "us_citizenship"),
        (r"united states citizen",                       "us_citizenship"),
        (r"no visa sponsorship",                                  "no_sponsorship"),
        (r"will not sponsor",                                     "no_sponsorship"),
        (r"do(?:es)? not (offer|provide)( visa)? sponsorship",   "no_sponsorship"),
        (r"cannot (provide|offer)( visa)? sponsorship",           "no_sponsorship"),
        (r"sponsorship (is )?not (available|offered)",            "no_sponsorship"),
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

def evaluate_eligibility(job_text: str) -> str:
    """
    Evaluate a raw job description for eligibility.

    Parameters
    ----------
    job_text : str
        The full text of the job description (title + body).

    Returns
    -------
    str
        One of:
          'PASS'        — Eligible; proceed to AI tailoring.
          'HARD_REJECT' — Ineligible; discard immediately (no API call).
          'REVIEW'      — Ambiguous; Gemini makes the final classification.
    """
    if not job_text or not job_text.strip():
        logger.warning("evaluate_eligibility called with empty job_text; returning REVIEW")
        return "REVIEW"

    # ── Step 1: Fast-pass override ──────────────────────────────────────────
    for pattern in _FAST_PASS_PATTERNS:
        if pattern.search(job_text):
            logger.debug("Fast-pass matched: %s", pattern.pattern)
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


def explain_eligibility(job_text: str) -> dict:
    """
    Like evaluate_eligibility, but returns a detailed dict for audit logging.

    Returns
    -------
    dict with keys:
        status          : 'PASS' | 'HARD_REJECT' | 'REVIEW'
        matched_pattern : str | None   (the regex that triggered the decision)
        label           : str | None   (human-readable category)
    """
    if not job_text or not job_text.strip():
        return {"status": "REVIEW", "matched_pattern": None, "label": "empty_input"}

    for pattern in _FAST_PASS_PATTERNS:
        if pattern.search(job_text):
            return {"status": "PASS", "matched_pattern": pattern.pattern, "label": "fast_pass"}

    for pattern, label in _HARD_REJECT_PATTERNS:
        if pattern.search(job_text):
            return {"status": "HARD_REJECT", "matched_pattern": pattern.pattern, "label": label}

    for pattern in _SOFT_PASS_PATTERNS:
        if pattern.search(job_text):
            return {"status": "PASS", "matched_pattern": pattern.pattern, "label": "soft_pass"}

    return {"status": "REVIEW", "matched_pattern": None, "label": "no_signal"}
