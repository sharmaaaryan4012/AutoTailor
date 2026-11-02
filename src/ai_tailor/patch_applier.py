"""
src/ai_tailor/patch_applier.py
-------------------------------
Deterministic keyword injection into resume skills section.

Contract:
  - Leaves ALL experience and project bullets untouched (zero risk of LLM hallucination).
  - Appends missing technical keywords to the targeted skills row (<!-- ID: SKILLS_AI_ML -->
    or <!-- ID: SKILLS_SWE --> in AI Engineering; <!-- ID: SKILLS_ML --> or <!-- ID: SKILLS_AI_SYS --> in DS).
  - Deduplicates keywords against already present skills.
"""

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def apply_patch(base_md_path: str, extracted_keywords: list[str]) -> str:
    """
    Deterministically inject extracted keywords into the skills section of the resume.

    Parameters
    ----------
    base_md_path : str
        Path to the base resume (HTML-infused Markdown).
    extracted_keywords : list[str]
        List of technical keywords extracted from the JD by Gemini.

    Returns
    -------
    str
        The updated resume content with keywords cleanly appended.
    """
    path = Path(base_md_path)
    if not path.exists():
        raise FileNotFoundError(f"Base resume not found: {path.resolve()}")

    content = path.read_text(encoding="utf-8")

    if not extracted_keywords:
        logger.debug("No keywords to inject — returning base resume unmodified")
        return content

    # Clean and filter incoming keywords
    clean_kws = [k.strip() for k in extracted_keywords if k and k.strip()]
    if not clean_kws:
        return content

    # Find the primary skill injection target:
    # Look for SKILLS_AI_ML or SKILLS_ML first, otherwise SKILLS_SWE or SKILLS_AI_SYS
    primary_target = re.search(r"<!--\s*ID:\s*(SKILLS_AI_ML|SKILLS_ML)\s*-->", content, re.IGNORECASE)
    if not primary_target:
        primary_target = re.search(r"<!--\s*ID:\s*(SKILLS_SWE|SKILLS_AI_SYS)\s*-->", content, re.IGNORECASE)

    if not primary_target:
        logger.warning("No target skills tag found in %s — returning unmodified", path.name)
        return content

    tag_name = primary_target.group(1)

    # Pattern matches the skill line containing the tag:
    # <div><!-- ID: TAG --> Existing skills...</div></div>
    line_pattern = re.compile(
        rf"(?P<prefix><div[^>]*><!--\s*ID:\s*{tag_name}\s*-->\s*)(?P<skills>.*?)(?P<suffix></div>\s*</div>)",
        re.IGNORECASE,
    )

    def _inject(match: re.Match) -> str:
        prefix = match.group("prefix")
        existing_skills = match.group("skills").strip()
        suffix = match.group("suffix")

        # Parse existing skills to avoid adding duplicates
        existing_tokens = {
            token.strip().lower() for token in re.split(r"[,;]+", existing_skills)
        }

        # Filter out keywords that already exist in this skills line
        new_kws = [kw for kw in clean_kws if kw.lower() not in existing_tokens]

        if not new_kws:
            return match.group(0)

        # Append new keywords comma-separated
        appended_str = ", ".join(new_kws)
        if existing_skills:
            updated_skills = f"{existing_skills}, {appended_str}"
        else:
            updated_skills = appended_str

        logger.info(
            "Injected %d keywords into %s [%s]: %s",
            len(new_kws), path.name, tag_name, appended_str,
        )
        return f"{prefix}{updated_skills}{suffix}"

    updated_content, count = line_pattern.subn(_inject, content, count=1)
    if count == 0:
        logger.warning("Could not match line structure for %s — content unchanged", tag_name)
        return content

    return updated_content
