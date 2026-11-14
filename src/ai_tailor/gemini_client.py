"""
src/ai_tailor/gemini_client.py
-------------------------------
Gemini API client for read-only role classification and technical keyword extraction.

Uses the `google-genai` SDK with structured output (response_json_schema)
to enforce the ResumePatch Pydantic model.

Model: gemini-3.5-flash-lite
The LLM does NOT rewrite resume bullets. It only classifies the role and extracts
missing technical keywords from the JD that match the candidate's domain.
"""

import json
import logging
import os
import time
from typing import Literal

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field, field_validator

load_dotenv()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model configuration
# ---------------------------------------------------------------------------

_MODEL = "gemini-3.5-flash-lite"
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0  # seconds


# ---------------------------------------------------------------------------
# Pydantic output schema (Read-Only Role)
# ---------------------------------------------------------------------------

class ResumePatch(BaseModel):
    """
    Read-only output schema from Gemini for job classification, keyword extraction,
    and modular project selection.
    No bullet point rewrites are performed.
    """

    track: Literal["AI_ENGINEERING", "DATA_SCIENCE", "IRRELEVANT"] = Field(
        description=(
            "Which resume track this role targets. "
            "AI_ENGINEERING: ML/AI infra, model serving, MLOps, LLM systems, deep learning engineering. "
            "DATA_SCIENCE: statistical modeling, A/B testing, analytics, research science, quantitative modeling. "
            "IRRELEVANT: role is out of scope (e.g. general IT, hardware-only, accounting, marketing)."
        )
    )
    fit_score: int = Field(
        ge=0,
        le=100,
        description=(
            "Estimated fit score 0–100. "
            "80–100: strong alignment with new grad / entry-level CS/Stats requirements. "
            "60–79: good fit, minor domain gaps. "
            "Below 60: moderate to poor fit."
        ),
    )
    extracted_keywords: list[str] = Field(
        default_factory=list,
        description=(
            "Max 5 core technical skills/tools/libraries explicitly required in the JD. "
            "Extract ONLY Core Requirements, strictly excluding nice-to-haves and low-level hardware/systems "
            "unless the role is explicitly Systems/HPC."
        ),
    )
    selected_projects: list[Literal["DEX", "PLANSIGHT", "SKYRIPPLE", "TOUDM", "NETRESCUE", "PACKETLENS"]] = Field(
        ...,
        description="Exactly 2 or 3 projects that best fit the job description.",
    )

    @field_validator("extracted_keywords")
    @classmethod
    def max_five_keywords(cls, v: list[str]) -> list[str]:
        # Clean up whitespace and limit to at most 5 items
        cleaned = [item.strip() for item in v if item and item.strip()]
        return cleaned[:5]

    @field_validator("selected_projects")
    @classmethod
    def validate_projects(cls, v: list[str]) -> list[str]:
        seen = set()
        deduped = []
        for p in v:
            if p not in seen:
                seen.add(p)
                deduped.append(p)
        if len(deduped) > 3:
            return deduped[:3]
        if len(deduped) < 2:
            defaults = ["TOUDM", "SKYRIPPLE", "PLANSIGHT"]
            for d in defaults:
                if d not in deduped:
                    deduped.append(d)
                if len(deduped) == 2:
                    break
        return deduped


# ---------------------------------------------------------------------------
# System Prompt (Classification & Keyword Extraction ONLY)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an expert technical recruiter and resume analyst.
Your job is to read the provided Job Description (JD) and perform ONLY three tasks:

1. Classification & Scoring:
   - Categorize the role as AI_ENGINEERING, DATA_SCIENCE, or IRRELEVANT.
   - Compute a fit_score (0-100) assessing suitability for a new graduate (BS Math & CS + Master in Management).
   - SCORING RULES:
     * Strongly prioritize core technical roles: "Machine Learning", "AI Engineer", "Research Scientist", and "Data Scientist".
     * Apply a severe penalty (-50 points) for generic titles like "Data and Analytics", "Data Analytics", or business-oriented roles that do NOT have "Engineer" or "Scientist" attached.
     * Hard-classify non-technical/business roles (advisors, generic business analysts, operations, sales, rotational development programs) as IRRELEVANT with fit_score < 40.

2. Technical Keyword Extraction:
   - Extract ONLY "Core Requirements" rather than "Nice-to-haves" or preferred qualifications.
   - Strictly adhere to this negative prompt: Do not extract hardware-level or highly specialized systems skills (e.g., CUDA, eBPF) unless the role is explicitly a Systems, Hardware, or High-Performance Computing role. For general Data Science or standard ML roles, restrict extractions to core modeling, data manipulation, and deployment frameworks (e.g., PyTorch, TensorFlow, scikit-learn, Pandas, Spark, Polars, Docker, FastAPI).
   - Identify up to 5 key technical skills, libraries, frameworks, or tools explicitly required in the JD matching these criteria.
   - Do NOT rewrite or modify any resume bullets.
   - Do NOT hallucinate credentials or skills outside technical software/data domain.

3. Project Selection:
   - Based on the Job Description, select EXACTLY 2 or 3 projects from the available list that demonstrate the most relevant skills.
   - For systems/infrastructure roles, prefer NETRESCUE, PACKETLENS, or TOUDM.
   - For modeling/AI roles, prefer PLANSIGHT, SKYRIPPLE, or DEX.
   - You must output exactly 2 or 3 project IDs.
   - Available projects: DEX, PLANSIGHT, SKYRIPPLE, TOUDM, NETRESCUE, PACKETLENS.

Return ONLY valid JSON matching the requested schema.
"""


# ---------------------------------------------------------------------------
# Client factory (lazy singleton)
# ---------------------------------------------------------------------------

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GEMINI_API_KEY is not set. "
                "Ensure GEMINI_API_KEY is defined in your .env file."
            )
        _client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=30000),  # 30 second request timeout
        )
    return _client


# ---------------------------------------------------------------------------
# Retry wrapper
# ---------------------------------------------------------------------------

def _call_with_retry(fn, *args, **kwargs):
    delay = _RETRY_BASE_DELAY
    last_exc: Exception | None = None

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            exc_str = str(exc).lower()
            is_retryable = any(
                signal in exc_str
                for signal in (
                    "429", "500", "503", "rate limit", "quota",
                    "resource exhausted", "unavailable", "timeout",
                    "timed out", "network", "connection reset"
                )
            )
            if not is_retryable or attempt == _MAX_RETRIES:
                logger.error("Gemini call failed (attempt %d/%d): %s", attempt, _MAX_RETRIES, exc)
                raise
            logger.warning(
                "Gemini transient error (attempt %d/%d), retrying in %.1fs: %s",
                attempt, _MAX_RETRIES, delay, exc,
            )
            time.sleep(delay)
            delay *= 2

    raise last_exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_patch(job_description: str) -> ResumePatch:
    """
    Send a job description to Gemini and receive a structured ResumePatch containing
    track, fit_score, and extracted_keywords.
    """
    if not job_description or not job_description.strip():
        raise ValueError("job_description must be non-empty")

    client = _get_client()

    def _make_request():
        return client.models.generate_content(
            model=_MODEL,
            contents=job_description,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_json_schema=ResumePatch.model_json_schema(),
                temperature=0.1,
            ),
        )

    response = _call_with_retry(_make_request)
    raw_json: str = response.text

    if not raw_json:
        raise ValueError("Gemini returned an empty response")

    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Gemini returned invalid JSON: {exc}\nRaw: {raw_json[:500]}") from exc

    try:
        patch = ResumePatch.model_validate(data)
    except Exception as exc:
        raise ValueError(
            f"Gemini JSON failed Pydantic validation: {exc}\nData: {data}"
        ) from exc

    logger.info(
        "Classification complete — track=%s fit=%d keywords=%s projects=%s",
        patch.track, patch.fit_score, patch.extracted_keywords, patch.selected_projects,
    )
    return patch
