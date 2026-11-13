"""
src/renderer/pdf_generator.py
------------------------------
Renders a raw HTML resume directly to a single-page PDF via Playwright.

Pipeline:
  1. Strip internal <!-- ID: ... --> tracking tags from the patched HTML string.
  2. Populate candidate profile placeholders from config/candidate_profile.yaml.
  3. Embed raw HTML directly into templates/resume_template.html via Jinja2
     (preserving Flexbox layout, columns, tables, and exact CSS hierarchy).
  4. Playwright (headless Chromium) prints to A4 PDF.
  5. pypdf validates page_count == 1 (deletes and returns False if overflow occurs).
"""

import logging
import os
import re
import tempfile
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader
from pypdf import PdfReader

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Template and Configuration Paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_TEMPLATES_DIR = _PROJECT_ROOT / "templates"
_CANDIDATE_PROFILE_PATH = _PROJECT_ROOT / "config" / "candidate_profile.yaml"
_CANDIDATE_PROFILE_EXAMPLE_PATH = _PROJECT_ROOT / "config" / "candidate_profile.example.yaml"

_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=False,
)


def load_candidate_profile(config_path: Path | str | None = None) -> dict:
    """
    Load candidate profile information from YAML config.
    Prioritizes config/candidate_profile.yaml (local/gitignored),
    falling back to config/candidate_profile.example.yaml if not present.
    """
    path = Path(config_path) if config_path else _CANDIDATE_PROFILE_PATH
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if isinstance(data, dict):
                    return data
        except Exception as exc:
            logger.warning("Could not read candidate profile from %s: %s", path, exc)

    if _CANDIDATE_PROFILE_EXAMPLE_PATH.exists():
        try:
            with _CANDIDATE_PROFILE_EXAMPLE_PATH.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if isinstance(data, dict):
                    return data
        except Exception as exc:
            logger.warning("Could not read example candidate profile: %s", exc)

    return {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_to_pdf(html_content: str, output_path: str, profile_data: dict | None = None) -> bool:
    """
    Render raw HTML resume string to a PDF and validate it is strictly 1 page.

    Parameters
    ----------
    html_content : str
        The raw HTML resume content (with or without <!-- ID: ... --> tags).
    output_path : str
        Destination path for the PDF file. Parent directories are created
        automatically.
    profile_data : dict, optional
        Candidate profile dictionary. If omitted, loaded automatically from
        config/candidate_profile.yaml (or example fallback).

    Returns
    -------
    bool
        True  — PDF written and confirmed 1 page.
        False — PDF exceeded 1 page (file deleted) or an error occurred.
    """
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    if profile_data is None:
        profile_data = load_candidate_profile()

    # Clean out internal comment tags before rendering
    clean_html = re.sub(r"<!--\s*ID:[^>]*-->", "", html_content)

    # Render any Jinja placeholders embedded directly inside html_content
    try:
        content_template = _jinja_env.from_string(clean_html)
        rendered_content = content_template.render(**profile_data)
    except Exception as exc:
        logger.warning("Failed to interpolate profile variables into content: %s", exc)
        rendered_content = clean_html

    # Render master external resume template
    try:
        template = _jinja_env.get_template("resume_template.html")
        full_html = template.render(content=rendered_content, **profile_data)
    except Exception as exc:
        logger.error("Failed to render resume_template.html: %s", exc)
        return False

    # Write HTML to temporary file for Playwright
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", encoding="utf-8", delete=False
    ) as tmp:
        tmp.write(full_html)
        tmp_html_path = tmp.name

    try:
        return _playwright_print(tmp_html_path, output)
    finally:
        try:
            os.unlink(tmp_html_path)
        except OSError:
            pass


def _playwright_print(html_path: str, output: Path) -> bool:
    """
    Print the HTML file to PDF via Playwright synchronous API.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        logger.error("Playwright not installed: %s", exc)
        return False

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page = browser.new_page()

            page.goto(f"file://{html_path}", wait_until="networkidle")

            page.pdf(
                path=str(output),
                format="A4",
                margin={
                    "top": "0.4in",
                    "bottom": "0.4in",
                    "left": "0.4in",
                    "right": "0.4in",
                },
                print_background=True,
                display_header_footer=False,
            )
            browser.close()
    except Exception as exc:
        logger.error("Playwright PDF rendering failed: %s", exc)
        return False

    # Validate page count using pypdf
    try:
        reader = PdfReader(str(output))
        page_count = len(reader.pages)
    except Exception as exc:
        logger.error("pypdf failed to read rendered PDF: %s", exc)
        _safe_delete(output)
        return False

    if page_count > 1:
        logger.warning(
            "PDF overflow: %s rendered %d pages (expected 1). File deleted.",
            output.name, page_count,
        )
        _safe_delete(output)
        return False

    logger.info("PDF rendered: %s (%d page)", output.name, page_count)
    return True


def _safe_delete(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Could not delete overflowed PDF %s: %s", path, exc)
