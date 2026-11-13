# AI Developer Context: AutoTailor

This document provides architectural context and strict design constraints for AI coding agents (Cursor, Copilot, Gemini, etc.) interacting with this codebase. Read this before suggesting architectural changes or refactors.

## System Objective
AutoTailor is a headless, zero-touch job watcher and resume tailoring pipeline. It scrapes job boards, filters roles via regex, extracts missing technical keywords using an LLM, deterministically injects those keywords into a master resume, and renders a pixel-perfect ATS-friendly PDF.

## Core Architecture & Stack
- **Scraping:** Headless Chromium via `playwright`.
- **Filtering:** Pure Python regex and string matching (`src/filtering/eligibility.py`). Bans business/analyst roles, senior roles, and clearance-required roles.
- **Inference (Read-Only):** `google-genai` SDK (`gemini-3.8-flash`). Uses structured Pydantic outputs (`ResumePatch`) strictly to classify the role (AI vs. Data Science) and extract up to 5 missing core technical skills.
- **Tailoring (Deterministic):** `src/ai_tailor/patch_applier.py`. Uses a canonical dictionary to fix capitalization (e.g., "pytorch" -> "PyTorch") and appends keywords to specific `<!-- ID: SKILLS_* -->` HTML comments. 
- **Rendering:** Jinja2 interpolates `config/candidate_profile.yaml` into `templates/resume_template.html`. Playwright renders the HTML to PDF. `pypdf` enforces a strict 1-page limit.
- **Automation:** macOS `launchd` / `cron` scheduling with Discord webhook delivery.

## Strict Design Constraints (DO NOT VIOLATE)

### 1. Zero LLM Bullet Hallucination
**Rule:** The LLM is NEVER allowed to rewrite, rephrase, or generate project/experience bullet points. 
**Rationale:** LLMs hallucinate experience to match job descriptions, destroying candidate integrity. The LLM is strictly confined to a read-only extraction role. All tailoring is done via deterministic Python string injection into the Skills section only. Do not suggest features that use the LLM to rewrite history.

### 2. Raw HTML/CSS for PDF Rendering
**Rule:** Do not attempt to revert the resume templates to pure Markdown.
**Rationale:** Standard Markdown parsers flatten columns and destroy the visual hierarchy required for a single-page ATS format (e.g., right-aligned dates opposite left-aligned companies). The templates MUST use raw HTML (`<div class="row">`, `<ul>`) and CSS Flexbox to guarantee layout retention when Playwright prints to PDF.

### 3. Strict 1-Page PDF Limit
**Rule:** The system must reject any PDF that exceeds 1 page.
**Rationale:** Resumes for new-grad and junior roles must strictly be one page. The pipeline will automatically discard any generated PDF where `pypdf` detects > 1 page.

## How to Customize (For the End User)
1. **Profile:** Duplicate `config/candidate_profile.example.yaml` to `config/candidate_profile.yaml` and fill in your details.
2. **Templates:** Duplicate `data/base_resumes/template_*.md` to `base_*.md` and update the bullets with your actual experience, preserving the `<!-- ID: SKILLS_* -->` tags.
3. **Sources:** Configure job board feeds and search parameters in `config/job_search.yaml`.
4. **Keywords:** Update `CANONICAL_KEYWORDS` in `patch_applier.py` with your specific tech stack.