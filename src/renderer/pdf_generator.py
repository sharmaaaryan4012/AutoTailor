"""
src/renderer/pdf_generator.py
------------------------------
Renders a raw HTML resume directly to a single-page PDF via Playwright.

Pipeline:
  1. Strip internal <!-- ID: ... --> tracking tags from the patched HTML string.
  2. Embed raw HTML directly into the Jinja2 master template (no markdown conversion
     to preserve Flexbox layout, columns, tables, and exact CSS hierarchy).
  3. Playwright (headless Chromium) prints to A4 PDF.
  4. pypdf validates page_count == 1 (deletes and returns False if overflow occurs).
"""

import logging
import os
import re
import tempfile
from pathlib import Path

from jinja2 import Environment, BaseLoader
from pypdf import PdfReader

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ATS-friendly Jinja2 HTML template with Flexbox layout
# ---------------------------------------------------------------------------

_RESUME_TEMPLATE = """\
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8" />
<style>
    @page { margin: 0.4in; size: A4; }
    body { 
        font-family: 'Times New Roman', Times, serif; 
        font-size: 10.5pt; 
        line-height: 1.2; 
        color: black; 
    }
    .header { text-align: center; margin-bottom: 6px; }
    .header h1 { margin: 0; font-size: 24pt; font-weight: normal; }
    .header p { margin: 2px 0 0 0; font-size: 10.5pt; }
    .header a { color: black; text-decoration: none; }
    h2 { 
        border-bottom: 1px solid black; 
        text-transform: uppercase; 
        font-size: 12pt; 
        margin-top: 7px; 
        margin-bottom: 3px; 
        padding-bottom: 2px; 
        font-weight: bold;
    }
    .row { display: flex; justify-content: space-between; align-items: baseline; }
    .bold { font-weight: bold; }
    .skills-row { display: flex; margin-bottom: 2px; }
    .skills-category { width: 170px; font-weight: bold; flex-shrink: 0; }
    ul { margin-top: 2px; margin-bottom: 5px; padding-left: 16px; }
    li { margin-bottom: 1.5px; text-align: justify; }
</style>
</head>
<body>
    {{ content }}
</body>
</html>
"""

_jinja_env = Environment(loader=BaseLoader(), autoescape=False)
_template = _jinja_env.from_string(_RESUME_TEMPLATE)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_to_pdf(html_content: str, output_path: str) -> bool:
    """
    Render raw HTML resume string to a PDF and validate it is strictly 1 page.

    Parameters
    ----------
    html_content : str
        The raw HTML resume content (with or without <!-- ID: ... --> tags).
    output_path : str
        Destination path for the PDF file. Parent directories are created
        automatically.

    Returns
    -------
    bool
        True  — PDF written and confirmed 1 page.
        False — PDF exceeded 1 page (file deleted) or an error occurred.
    """
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    # Clean out internal comment tags before rendering
    clean_html = re.sub(r"<!--\s*ID:[^>]*-->", "", html_content)

    # Pass directly into Jinja2 template without markdown preprocessing
    full_html = _template.render(content=clean_html)

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
