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
# US-Only Geographic Filter
# ---------------------------------------------------------------------------

_US_STATE_CODES: set[str] = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "DC", "FL", "GA", "HI",
    "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN",
    "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH",
    "OK", "OR", "PA", "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
    "WV", "WI", "WY",
}

_US_STATE_NAMES_RE = re.compile(
    r"\b(?:alabama|alaska|arizona|arkansas|california|colorado|connecticut|"
    r"delaware|district of columbia|florida|georgia|hawaii|idaho|illinois|"
    r"indiana|iowa|kansas|kentucky|louisiana|maine|maryland|massachusetts|"
    r"michigan|minnesota|mississippi|missouri|montana|nebraska|nevada|"
    r"new hampshire|new jersey|new mexico|new york|north carolina|north dakota|"
    r"ohio|oklahoma|oregon|pennsylvania|rhode island|south carolina|"
    r"south dakota|tennessee|texas|utah|vermont|virginia|washington|"
    r"west virginia|wisconsin|wyoming)\b",
    re.IGNORECASE,
)

_US_EXPLICIT_RE = re.compile(
    r"\b(?:usa|u\.s\.a\.|u\.s\.|united states|us\s+remote|remote\s+(?:in\s+)?(?:the\s+)?us\b|"
    r"remote\s*\(us\)|sf|nyc|san francisco|new york|seattle|austin|boston|chicago|"
    r"san jose|sunnyvale|cupertino|menlo park|mountain view|palo alto|redmond|"
    r"los angeles|san diego|bellevue|atlanta|denver|pittsburgh|houston|dallas|"
    r"silicon valley|bay area)\b",
    re.IGNORECASE,
)

_NON_US_COUNTRY_OR_REGION_RE = re.compile(
    r"\b(?:uk|u\.k\.|united kingdom|england|scotland|wales|northern ireland|great britain|"
    r"canada|ontario|quebec|british columbia|alberta|manitoba|nova scotia|saskatchewan|"
    r"germany|deutschland|france|spain|italy|netherlands|holland|belgium|switzerland|"
    r"austria|sweden|norway|denmark|finland|poland|portugal|ireland|czech|romania|"
    r"hungary|greece|luxembourg|europe|emea|apac|latam|"
    r"india|singapore|australia|new zealand|japan|china|hong kong|taiwan|"
    r"south korea|korea|israel|brazil|mexico|argentina|colombia|chile|uae|dubai|"
    r"south africa|philippines|vietnam|malaysia|indonesia)\b",
    re.IGNORECASE,
)

_NON_US_PROVINCE_RE = re.compile(r",\s*(?:ON|BC|QC|AB|MB|SK|NS|NB|NL|PE)\b")

# Unambiguously international cities (checked BEFORE 2-letter US state codes to prevent
# ISO country code collisions like "Berlin, DE", "Toronto, CA", "Bangalore, IN", "Tel Aviv, IL")
_UNAMBIGUOUS_NON_US_CITIES_RE = re.compile(
    r"\b(?:london|edinburgh|glasgow|belfast|leeds|sheffield|liverpool|cardiff|"
    r"brighton|newcastle|nottingham|hatfield|reigate|telford|harwell|didcot|swinton|"
    r"toronto|vancouver|montreal|ottawa|waterloo|calgary|edmonton|winnipeg|"
    r"mississauga|markham|etobicoke|st\.\s*catharines|"
    r"berlin|munich|frankfurt|hamburg|paris|amsterdam|zurich|geneva|stockholm|"
    r"madrid|barcelona|milan|rome|warsaw|krakow|prague|vienna|brussels|copenhagen|oslo|helsinki|lisbon|"
    r"bengaluru|bangalore|hyderabad|pune|mumbai|delhi|gurgaon|gurugram|noida|chennai|kolkata|"
    r"sydney|melbourne|brisbane|perth|auckland|tokyo|osaka|beijing|shanghai|shenzhen|"
    r"seoul|taipei|tel aviv|herzliya|bogota|medellin|buenos aires|jakarta)\b",
    re.IGNORECASE,
)

# Ambiguous cities that exist in both UK/Ireland and the US (only flagged non-US if NOT paired with a US state)
_AMBIGUOUS_NON_US_CITIES_RE = re.compile(
    r"\b(?:manchester|cambridge|dublin|birmingham|oxford|bristol|reading|york)\b",
    re.IGNORECASE,
)

_NON_US_URL_RE = re.compile(
    r"(?:\.co\.uk/|\.ca/|job-boards\.eu\.greenhouse\.io|uk\.applytojob\.com|"
    r"/(?:uk|london|manchester|toronto|vancouver|montreal|canada|en-gb|en-ca|uk-[a-z]+)/|"
    r"Toronto-ON-CAN|UK-Harwell)",
    re.IGNORECASE,
)


def _classify_location_segment(seg: str) -> str:
    """Classify a single location string segment as 'US', 'NON_US', or 'UNKNOWN'."""
    s = seg.strip()
    if not s:
        return "UNKNOWN"
    if (
        _NON_US_COUNTRY_OR_REGION_RE.search(s)
        or _NON_US_PROVINCE_RE.search(s)
        or _UNAMBIGUOUS_NON_US_CITIES_RE.search(s)
    ):
        return "NON_US"
    if _US_EXPLICIT_RE.search(s) or _US_STATE_NAMES_RE.search(s):
        return "US"
    for tok in re.findall(r"\b[A-Z]{2}\b", s):
        if tok in _US_STATE_CODES:
            return "US"
    if _AMBIGUOUS_NON_US_CITIES_RE.search(s):
        return "NON_US"
    return "UNKNOWN"


def is_us_location(location: str = "", apply_url: str = "") -> bool:
    """
    Return True if the job listing is located in the United States (or US-eligible Remote).
    Multi-location strings (e.g., 'Remote in USA / Remote in Canada') return True if AT LEAST
    ONE segment is in the US. Purely international roles (UK, Canada, EU, India, etc.) return False.
    """
    segments = [p.strip() for p in re.split(r"[/;|\n]+", location or "") if p.strip()]
    if not segments:
        return not bool(_NON_US_URL_RE.search(apply_url or ""))

    results = [_classify_location_segment(seg) for seg in segments]
    if "US" in results:
        return True
    if "NON_US" in results:
        return False
    if apply_url and _NON_US_URL_RE.search(apply_url):
        return False
    return True


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
    r"\b(?:senior|sr\.?|staff|principal|lead|head\s+of|manager|director|vp|chief|architect|fellow)\b",
    re.IGNORECASE,
)

_EXPERIENCED_OR_LEVEL2_TITLE_RE = re.compile(
    r"\b(?:level\s*[2-9]|l[2-9]|ic[3-9])\b|"
    r"\b(?:swe|sde|engineer|developer|scientist|specialist)\s*(?:[2-9]|ii|iii|iv|v)\b|"
    r"\b(?:ii|iii|iv|v)\b|"
    r"\b(?:mid[\s\-]?level|intermediate|experienced|specialist)\b",
    re.IGNORECASE,
)

_PURE_RESEARCH_TITLE_RE = re.compile(
    r"\b(?:research\s+scientist|applied\s+scientist|researcher|research\s+fellow|post[\s\-]?doc\w*|quantum\s+research)\b",
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
      4. Experienced / Level 2+ / Specialist roles
      5. Pure research / academic / theoretical researcher roles
      6. Non-technical / business / analyst roles
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

    # 4. Experienced / Level 2+ / Specialist
    m_exp = _EXPERIENCED_OR_LEVEL2_TITLE_RE.search(target)
    if m_exp:
        return {
            "status": "HARD_REJECT",
            "matched_pattern": m_exp.group(0),
            "label": "experienced_level_role",
            "reason": f"Experienced/Level 2+/Specialist role ({m_exp.group(0)!r})",
        }

    # 5. Pure research / academic / theoretical researcher
    m_res = _PURE_RESEARCH_TITLE_RE.search(target)
    if m_res:
        return {
            "status": "HARD_REJECT",
            "matched_pattern": m_res.group(0),
            "label": "pure_research_role",
            "reason": f"Pure research or doctoral scientist role ({m_res.group(0)!r})",
        }

    # 6. Non-technical / Business
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
    (re.compile(r"\b(?:[3-9]|\d{2,})(?:&#43;|\+)?\s*years?\b", re.I), "experience_years", "3+ years experience required"),
    (re.compile(r"\b(?:three|four|five|six|seven|eight|nine|ten)\s+(?:or\s+more\s+)?years?\b", re.I), "experience_years", "3+ years experience required"),
    (re.compile(r"\b(?:[3-9]|\d{2,})\s*(?:to|-)\s*\d+\s+years?\b", re.I), "experience_years", "3+ years experience required"),
    (re.compile(r"\bminimum\s+(?:of\s+)?(?:[2-9]|\d{2,})\s+years?\b", re.I), "experience_years", "Minimum 2+ years experience required"),
    (re.compile(r"\bat\s+least\s+(?:[2-9]|\d{2,})\s+years?\b", re.I), "experience_years", "At least 2+ years experience required"),
    (re.compile(r"\b[2-9](?:&#43;|\+)?\s*years?\s+(?:of\s+)?(?:full[\s\-]time|professional|industry|commercial)\s+experience\b", re.I), "experience_years", "Prior full-time/professional experience required"),
    (re.compile(r"\bprior\s+(?:full[\s\-]time|industry|professional)\s+experience\s+(?:is\s+)?(?:required|mandatory)\b", re.I), "experience_years", "Prior professional experience required"),
    (re.compile(r"\bprogressive\s+post-baccalaureate\s+.*?experience\b", re.I), "experience_years", "Post-baccalaureate experience required"),
]

# Step 4: Soft-pass signals — genuine new grad / early career / class year signals
_SOFT_PASS_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bnew\s*grad(uate)?s?\b",
        r"\bentry[\s\-]level\b",
        r"\bearly\s*career\b",
        r"\bclass\s+of\s+(?:2025|2026|2027)\b",
        r"\b(?:graduating|graduated)\s+(?:in\s+)?(?:2025|2026|2027)\b",
        r"\buniversity\s+grad(uate)?\b",
        r"\b(?:recent|upcoming)\s+grad(uate)?\b",
        r"\bcollege\s+(?:grad(uate)?|hire)\b",
        r"\bcampus\s+recruiting\b",
        r"\b0[\s\-–—]?[12]\s+years?(?:\s+of)?\s+experience\b",
        r"\bno\s+(?:prior\s+)?experience\s+required\b",
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
