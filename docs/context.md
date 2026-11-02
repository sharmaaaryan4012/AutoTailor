# Project Context

## Purpose

This project automates the job-hunting workflow for an international student graduating in **May 2027**. The system continuously monitors job boards, filters listings for sponsorship eligibility, tailors a resume using AI, and delivers the output to a personal Discord channel — all without human intervention after initial setup.

> [!IMPORTANT]
> The operator is an **international student** on an F-1 visa, requiring H-1B or OPT sponsorship. Any role that explicitly excludes visa sponsorship or requires US citizenship/security clearance must be **hard-rejected** before any AI processing occurs. This is a non-negotiable constraint enforced at the regex filtering layer.

---

## Dual-Track Resume Strategy

The system maintains two distinct resume tracks, each targeting a different job-market persona:

| Track | Target Roles | Emphasis |
|---|---|---|
| **AI Engineering** | AI/ML Engineer, LLM Engineer, Applied AI, Inference Engineer | Systems, MLOps, model serving, inference optimization, production deployment |
| **Data Science** | Data Scientist, Research Scientist, Quantitative Analyst | Statistical modeling, experimentation, causal inference, applied ML research |

For each inbound job listing, Gemini classifies the role into one of these two tracks (or rejects it as irrelevant). The base resume for the matched track is then surgically patched — only bullet points and skills are rewritten, never structure or formatting.

### Why Two Tracks?

The job markets for AI Engineering and Data Science have diverged significantly. A resume optimized for an AI Eng role (emphasizing Kubernetes, ONNX, CUDA, model serving SLAs) will score poorly on an ATS for a Data Science role (which expects hypothesis testing, A/B experimentation, SQL-heavy work). Maintaining two curated base resumes prevents the "averaged-out" problem of a single general resume.

---

## Hard Constraints

### Zero-Cost Constraint

The system operates entirely on **free tiers and open-source tooling**. No paid APIs or SaaS scraping products are used at any point.

| Component | Free Alternative | Rationale |
|---|---|---|
| Job scraping | Local Playwright (headless) | Zero cost, full HTML access |
| LLM inference | Google AI Studio free tier (Gemini) | Generous free quota, structured output support |
| PDF rendering | Playwright (Chromium print-to-PDF) | No external service needed |
| Delivery | Discord Webhook | Free, supports file attachments |
| Storage | Local JSON + filesystem | No database subscription |

### Graduation Timeline

- **Expected Graduation**: May 2027
- **OPT Eligibility Window**: The system should surface roles that either (a) start after May 2027, (b) accept new grads, or (c) have a flexible start date. Roles that require "immediate start" or "currently active clearance" are rejected.

---

## Target Job Boards

- LinkedIn Jobs
- Greenhouse (direct company career pages)
- Lever (direct company career pages)
- Handshake (new grad / internship focused)

---

## Graduation Class Year Filtering

The system accepts roles tagged as:
- New Graduate / New Grad
- Entry Level (0–2 years experience)
- Class of 2025, 2026, or **2027**

Roles requiring 3+ years of experience are soft-flagged (not hard-rejected) to allow Gemini to make the final call.

