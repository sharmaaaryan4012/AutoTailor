# Architectural Decision Records (ADR)

This is a living document. Add a new entry for every non-trivial design choice, especially when a tempting alternative was rejected.

---

## ADR-001: Local Playwright over Paid Scraping APIs

**Date**: 2026-11-01  
**Status**: Accepted

### Context

Modern job boards (LinkedIn, Greenhouse, Lever) are heavy JavaScript single-page applications. Naive `requests`-based HTTP scraping fails because content is rendered client-side. Two broad options exist:

1. **Paid scraping APIs** (ScrapingBee, Apify, Bright Data) — handle JS rendering, proxy rotation, and CAPTCHA solving via managed infrastructure.
2. **Local Playwright** — open-source browser automation that drives a real Chromium instance locally.

### Decision

Use **local Playwright** with Chromium.

### Rationale

- **Zero cost**: Paid scraping APIs charge per-request or per-GB. At scale, this becomes significant. Our constraint is zero recurring cost.
- **No vendor lock-in**: Playwright is open-source (Microsoft) and integrates natively with Python.
- **Full DOM access**: Playwright can interact with the rendered DOM, execute JS, handle cookies/sessions, and wait for network idle — covering all SPA patterns.
- **Detectability tradeoffs accepted**: While managed scraping APIs offer residential proxy pools, LinkedIn's anti-bot measures are primarily fingerprinting-based. We mitigate this with: realistic user-agent strings, randomized delays, and persistent browser contexts (to preserve login sessions).

### Consequences

- Must maintain Playwright adapter per job board as DOM structures change.
- Scraping is IP-bound; aggressive scraping on home IP may trigger rate limits. Mitigated by conservative per-run limits (max 50 listings/run) and randomized timing.
- Requires Chromium binary installed locally (`playwright install chromium`).

### Rejected Alternatives

| Alternative | Reason Rejected |
|---|---|
| ScrapingBee | \$49/mo minimum — violates zero-cost constraint |
| Apify | Free tier is very limited (10 actor runs/mo); not viable for daily polling |
| `requests` + BeautifulSoup | Fails on JS-rendered SPAs |

---

## ADR-002: Google AI Studio Free Tier (Gemini) over Paid LLMs

**Date**: 2026-11-01  
**Status**: Accepted

### Context

The pipeline needs an LLM for two tasks:
1. **Track classification**: Does this JD target AI Engineering or Data Science?
2. **Resume bullet patching**: Rewrite 3–5 resume bullets to mirror JD keywords.

Both tasks require a capable language model. Options: OpenAI GPT-4o, Anthropic Claude, or Google Gemini.

### Decision

Use **Gemini via Google AI Studio** with the `google-genai` Python SDK, on the **free tier**.

### Rationale

- **Zero cost**: Google AI Studio provides a free tier with generous daily quotas (as of late 2026, Gemini 1.5 Flash: 1,500 requests/day, 1M tokens/min). Our pipeline processes at most ~50 JDs/day, well within limits.
- **Structured output (JSON mode)**: Gemini natively supports constrained JSON output via `response_schema`, allowing us to enforce a Pydantic schema without prompt engineering hacks. This is critical for our deterministic patching approach.
- **No credit card required**: Google AI Studio free tier requires only a Google account — no payment method needed, eliminating financial risk.
- **`google-genai` SDK**: The official SDK provides clean Python bindings, streaming, and schema-enforced generation.

### Consequences

- Free tier rate limits must be respected. The pipeline must include exponential backoff on `429` responses.
- Model output quality is slightly below GPT-4o for complex reasoning, but for structured JSON patching of resume bullets, Gemini 1.5 Flash is more than sufficient.
- API key must be stored in `.env` (never committed).

### Rejected Alternatives

| Alternative | Reason Rejected |
|---|---|
| OpenAI GPT-4o | No perpetual free tier; requires billing setup |
| Anthropic Claude | No free tier for API access |
| Local Ollama (Llama 3) | Insufficient VRAM on typical dev machine for quality results; adds complexity |

---

## ADR-003: Deterministic JSON Patching over Full AI Rewrites

**Date**: 2026-11-01  
**Status**: Accepted

### Context

The most obvious approach to "AI resume tailoring" is to feed the entire resume text to an LLM and ask it to rewrite the document. This is simple to implement but has serious failure modes:

- **Formatting destruction**: LLMs hallucinate whitespace, bullet styles, and section ordering.
- **Content fabrication**: LLMs sometimes invent job titles, dates, or skills.
- **PDF instability**: Any change to content length can break a carefully tuned 1-page layout.
- **Non-determinism**: Two identical inputs can produce structurally different outputs.

### Decision

Use **deterministic JSON patching**: the base resume is stored as structured JSON (or Markdown with a defined schema). Gemini is only permitted to return a bounded patch — a JSON object specifying which bullet IDs to update and their new text. A separate Python `patch_applier.py` applies the patch surgically, leaving all other fields untouched.

### Schema Contract

```json
{
  "track": "ai_engineering | data_science",
  "patches": [
    {
      "section": "experience",
      "job_id": "job_2",
      "bullet_index": 2,
      "new_text": "Reduced model inference latency by 40% via ONNX quantization"
    }
  ],
  "skills_addendum": ["ONNX", "TensorRT"],
  "confidence_score": 0.87
}
```

### Rationale

- **Formatting is sacred**: The base resume is hand-tuned to fit exactly one page. Only content changes, never structure.
- **Auditability**: Every patch is logged. We can diff the original vs. tailored resume bullet-by-bullet.
- **Bounded hallucination surface**: Gemini can only touch designated text fields. It cannot add sections, reorder bullets, or change dates.
- **Idempotency**: Applying the same patch twice produces the same result.

### Consequences

- Base resumes must be stored in a structured, patchable format (Markdown with named anchors, or JSON).
- The Pydantic schema in `config/ai_patch_schema.json` must be kept in sync with the base resume structure.
- Gemini's `response_schema` must exactly match the Pydantic model to enforce output constraints.

### Rejected Alternatives

| Alternative | Reason Rejected |
|---|---|
| Full resume rewrite via LLM | Formatting destruction, fabrication risk, non-determinism |
| Template-based substitution (no AI) | Cannot capture nuanced JD-specific language |
| LangChain agent chains | Adds heavy dependency, no benefit over direct SDK usage for this bounded task |

---

## ADR-004: Aggressive Regex Visa Gating Before AI Processing

**Date**: 2026-11-01  
**Status**: Accepted

### Context

As an international student, applying to roles that explicitly require US citizenship, security clearance, or that do not offer visa sponsorship is a waste of API quota and creates a false positive in the pipeline output. These roles must be caught before any LLM call is made.

### Decision

Implement a **hard-reject regex filter** in `src/filtering/eligibility.py` that runs immediately after scraping and before any Gemini API call.

### Rejection Patterns

```python
HARD_REJECT_PATTERNS = [
    r"must be (a )?us citizen",
    r"us citizenship required",
    r"security clearance (required|needed|mandatory)",
    r"(active|current) (secret|top secret|ts/sci) clearance",
    r"no (visa )?sponsorship",
    r"sponsorship (is )?not (available|provided|offered)",
    r"must be (legally )?authorized .{0,20} without sponsorship",
    r"only (us|u\.s\.) citizens? (or )?(permanent residents?)?",
    r"must have (permanent|unrestricted) work authorization",
    r"green card (holders? )?only",
]
```

All patterns are case-insensitive and applied to the full job description text.

### Rationale

- **Protect free tier quota**: Every hard-rejected listing is one Gemini API call saved.
- **Correctness**: It is always wrong (for this operator) to send a tailored resume to a no-sponsorship role. Zero false negatives are acceptable at the cost of some false positives (the regex may over-reject ambiguous phrasing).
- **Speed**: Regex is O(n) on text length, adding microseconds per listing vs. seconds for an LLM call.
- **Auditability**: Rejected listings are logged with the matching pattern for manual review.

### Consequences

- Regex patterns must be maintained as job board language evolves. Review quarterly.
- Some legitimate roles may be rejected if they phrase sponsorship availability awkwardly (e.g., "we do not sponsor H1B but do sponsor OPT/STEM OPT"). This is an acceptable false-positive tradeoff — manual review log allows correction.
- Patterns should be stored in `config/job_search.yaml` under `hard_reject_patterns` to allow runtime updates without code changes.

### Rejected Alternatives

| Alternative | Reason Rejected |
|---|---|
| Let Gemini classify sponsorship eligibility | Adds latency and cost; LLMs occasionally hallucinate on binary classification of legal text |
| No filtering (apply to everything) | Wastes quota; introduces noise into output; violates correctness requirement |
| External eligibility API | No free option exists; adds vendor dependency |

