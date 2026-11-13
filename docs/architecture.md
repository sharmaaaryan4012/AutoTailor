# System Architecture

## Overview

This system is a headless data pipeline that runs on a daily cron schedule. It ingests raw job listings, applies layered filtering, uses Gemini to classify and patch a resume, renders a tailored PDF, and delivers it to a Discord channel.

All state is persisted locally as JSON files. There is no database, no cloud storage, and no external services beyond the Gemini API and Discord webhooks.

---

## Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DAILY CRON TRIGGER                           │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 1: SCRAPE                                                     │
│  src/scraper/adapters.py                                             │
│                                                                      │
│  • Playwright headless Chromium drives each job board               │
│  • Extracts: title, company, location, JD text, apply URL           │
│  • Computes fingerprint: SHA256(company + title + url)               │
│  • Deduplicates against watch_state.json (skip seen fingerprints)    │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  new_listings[]
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 2: REGEX HARD FILTER                                          │
│  src/filtering/eligibility.py                                        │
│                                                                      │
│  • Apply visa/citizenship/clearance reject patterns (ADR-004)        │
│  • Apply graduation date / experience level filters                  │
│  • REJECT → log to data/rejected.jsonl with matching pattern         │
│  • PASS → forward to AI phase                                        │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  eligible_listings[]
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 3: GEMINI CLASSIFICATION                                      │
│  src/ai_tailor/gemini_client.py                                      │
│                                                                      │
│  • Call Gemini with JD text + classification prompt                  │
│  • Structured output (Pydantic schema) → {track, relevance_score}   │
│  • track ∈ {ai_engineering, data_science, irrelevant}               │
│  • irrelevant → log and skip (no resume patch)                       │
│  • ai_engineering → load base_ai_engineer.md                         │
│  • data_science   → load base_data_science.md                        │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  (track, base_resume, jd_text)
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 4: JSON PATCH GENERATION                                      │
│  src/ai_tailor/gemini_client.py  (second Gemini call)               │
│                                                                      │
│  • Feed: base_resume JSON + JD text + patch prompt                   │
│  • Gemini returns: ResumePatch (see ai_patch_schema.json)            │
│  • Pydantic validates the response schema strictly                   │
│  • On validation failure: retry up to 2x, then skip listing          │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  ResumePatch
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 5: PATCH APPLICATION                                          │
│  src/ai_tailor/patch_applier.py                                      │
│                                                                      │
│  • Apply ResumePatch to base resume JSON → patched_resume dict       │
│  • Validate: no new sections added, no dates changed                 │
│  • Render patched dict → Jinja2 HTML template                        │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  rendered_html
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 6: PDF RENDER + VALIDATION                                    │
│  src/renderer/pdf_generator.py                                       │
│                                                                      │
│  • Playwright print-to-PDF (A4, 0.5in margins, no headers/footers)  │
│  • Validate: pypdf page count == 1 (hard failure if >1 page)         │
│  • Save to: data/output/{company}_{role}_{date}.pdf                  │
└──────────────────────────────┬──────────────────────────────────────┘
                               │  pdf_path
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 7: DELIVERY                                                   │
│  src/delivery/discord_webhook.py                                     │
│                                                                      │
│  • POST to Discord webhook with:                                     │
│    - Embed: company, role, track, location, apply URL, score        │
│    - File attachment: tailored PDF                                   │
│  • src/delivery/file_sync.py: copy PDF to ~/Documents/resume_out/   │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 8: STATE PERSISTENCE                                          │
│  src/scraper/state_manager.py                                        │
│                                                                      │
│  • Atomically write new fingerprints to watch_state.json            │
│  • Write-then-rename (tmp file) to prevent corruption on interrupt   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Module Reference

### `src/scraper/adapters.py`
Playwright-based scrapers for each job board. Each adapter implements a common interface:

```python
class JobBoardAdapter(Protocol):
    async def fetch_listings(self, query: SearchQuery) -> list[RawListing]: ...
```

Adapters handle: login session reuse, pagination, rate-limit delays, and DOM extraction.

### `src/scraper/state_manager.py`
Manages `data/watch_state.json`. Responsibilities:
- Load existing seen fingerprints on startup.
- Provide `is_seen(fingerprint: str) -> bool`.
- Atomically persist new fingerprints after a successful run (write to `.tmp`, then `os.replace`).
- Prune fingerprints older than 90 days to bound file growth.

### `src/filtering/eligibility.py`
Pure-function regex filter. Takes a `RawListing`, returns `FilterResult(status, reason, matched_pattern)`. No side effects, fully testable in isolation.

### `src/ai_tailor/gemini_client.py`
Wraps the `google-genai` SDK. Two public methods:
- `classify_track(jd_text: str) -> TrackClassification`
- `generate_patch(jd_text: str, base_resume: dict, track: str) -> ResumePatch`

Both methods enforce Pydantic schemas via `response_schema`. Implements exponential backoff for `429` rate-limit errors.

### `src/ai_tailor/patch_applier.py`
Applies a `ResumePatch` to a base resume dict. Pure function, no I/O. Returns a new patched dict without mutating the original. Validates that patch targets exist in the base resume before applying.

### `src/renderer/pdf_generator.py`
Renders a patched resume dict to PDF:
1. Jinja2 renders the dict into an HTML string using a resume template.
2. Playwright prints the HTML page to PDF.
3. `pypdf` reads the output and asserts `page_count == 1`.

### `src/delivery/discord_webhook.py`
Sends a `requests.post` multipart payload to the configured Discord webhook URL. Includes a rich embed for quick scanning and the PDF as a file attachment.

### `src/delivery/file_sync.py`
Copies completed PDFs to a local sync directory (configurable via `.env`). Optional integration point for cloud sync (e.g., Google Drive desktop sync folder).

### `src/main.py`
The entry point. Wires all phases together in sequence. Handles:
- Config loading from `config/job_search.yaml` and `.env`.
- Per-listing try/except to ensure one bad listing doesn't abort the run.
- Final summary logging: X scraped, Y filtered, Z tailored, W delivered.

---

## Data State: `watch_state.json`

```json
{
  "schema_version": 1,
  "last_run": "2026-11-01T21:00:00Z",
  "seen_fingerprints": {
    "a3f1c9...": "2026-11-01T21:00:00Z",
    "b72e44...": "2026-10-31T21:00:00Z"
  }
}
```

**Fingerprint formula**: `SHA256(normalize(company) + "|" + normalize(title) + "|" + url)` where `normalize` lowercases and strips whitespace.

---

## Configuration

### `config/job_search.yaml`
Controls scraper behavior:
- Target keywords per track.
- Location tiers (preferred / acceptable / rejected).
- Hard-reject patterns (visa/clearance strings).
- Max listings per run.
- Per-board enable/disable flags.

### `config/ai_patch_schema.json`
Defines the Pydantic model structure that Gemini must conform to. Kept as a standalone JSON Schema file so it can be version-controlled independently of the Python code.

### `.env`
Secrets and local paths (never committed):
- `GEMINI_API_KEY`
- `DISCORD_WEBHOOK_URL`
- `FILE_SYNC_DIR`

---

## Directory Layout

```
recruiting/
├── config/
│   ├── job_search.yaml          # Search config, hard-reject patterns
│   └── ai_patch_schema.json     # Pydantic/JSON Schema for Gemini output
├── data/                        # .gitignored
│   ├── watch_state.json         # Seen fingerprint ledger
│   ├── base_resumes/
│   │   ├── base_ai_engineer.md
│   │   └── base_data_science.md
│   └── output/                  # Rendered PDFs (per-run output)
├── docs/
│   ├── context.md               # Project purpose and constraints
│   ├── decisions.md             # ADR log
│   └── architecture.md          # This file
├── src/
│   ├── scraper/
│   │   ├── adapters.py
│   │   └── state_manager.py
│   ├── filtering/
│   │   └── eligibility.py
│   ├── ai_tailor/
│   │   ├── gemini_client.py
│   │   └── patch_applier.py
│   ├── renderer/
│   │   └── pdf_generator.py
│   ├── delivery/
│   │   ├── discord_webhook.py
│   │   └── file_sync.py
│   └── main.py
├── .env.example
├── .gitignore
└── requirements.txt
```

---

## Failure Modes and Mitigations

| Failure | Mitigation |
|---|---|
| Gemini `429` rate limit | Exponential backoff (1s, 2s, 4s), max 3 retries |
| Pydantic validation failure on Gemini output | Retry up to 2x; if still failing, skip listing and log |
| PDF renders >1 page | Hard fail: do not deliver; log which patch caused overflow |
| Scraper DOM change (job board redesign) | Per-adapter try/except; pipeline continues with other boards |
| `watch_state.json` corruption | Atomic write (tmp + rename); keep rolling backup of last 3 versions |
| Discord rate limit | Simple retry with 1s delay; webhook delivery is best-effort |

