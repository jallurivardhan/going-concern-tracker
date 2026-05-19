# Demo Video Script (2 minutes)

**Audience:** AlgoFest 2026 judges / technically literate general audience.
**Format:** Screen recording with voiceover. No slides.
**Pacing:** Speak at a measured pace; do not rush the data.

---

## 0:00 – 0:15 — The Problem

> "Every year, US public companies file thousands of 10-K annual reports with the SEC. Buried inside some of them is the most legally loaded warning a company can receive — a going-concern opinion. The auditor saying, in writing, that the company may not survive the next 12 months. These opinions are powerful early-warning signals of corporate distress. And they're nearly impossible to find at scale because they're buried inside 200-page filings that almost nobody reads."

**[Screen: SEC EDGAR full-text search — show the raw 10-K filing for Spirit Airlines, scroll slowly to demonstrate length. Then ctrl+F for "going concern" — let the browser highlight count the results.]**

---

## 0:15 – 0:30 — The Product

> "Going Concern Tracker is a free public service. It automatically monitors SEC filings, finds going-concern opinions, and surfaces them with full citation — linked to the exact paragraph in the auditor's report."

**[Screen: Navigate to http://localhost:3000. Pause on the hero section — show the most recent critical flag card (Spirit Airlines or Wolfspeed, whichever is showing). Let it breathe.]**

---

## 0:30 – 0:55 — The Demo: Flag Detail

> "Here's the most recent critical flag: Wolfspeed, the semiconductor company. Their auditor issued a going-concern opinion in their August 2025 10-K."

**[Click the flag card → navigates to /flags/{id}]**

> "Here's the exact quote from the auditor's report, verbatim. Every word came directly from the source document. Our pipeline never invents quotes — the LLM classifies and then we verify the classification with deterministic substring matching against the original text."

**[Highlight the quoted language block on the detail page.]**

> "Click here to read the full filing on SEC.gov."

**[Click the SEC EDGAR link — let it briefly open the actual filing, then return.]**

---

## 0:55 – 1:15 — Search

> "Let's search across the 35 companies we actively monitor."

**[Click into the search bar in the header. Type 's', then 'p', then 'i' slowly — pause when the dropdown opens showing Spirit Airlines.]**

> "Spirit Airlines. Two critical flags — their 2025 filing and their 2026 post-emergence filing. They filed Chapter 11 in November 2024 and emerged in March 2025."

**[Click the Spirit Airlines result → /companies/0001498710. Show the company timeline — two red 'Critical' badges.]**

---

## 1:15 – 1:35 — The Engineering

> "Three things make this trustworthy."

**[Brief cut to the methodology page at /methodology]**

> "First: LLMs never produce numbers or citations directly. We use Claude with structured output via Instructor, then verify every quote against the source with substring matching. If the quote can't be found — the flag is never written to the database."

> "Second: Every claim is hand-evaluated. We have a 44-case golden eval set with 100% precision and recall on the going-concern classification task."

> "Third: The data refreshes automatically. A GitHub Actions workflow runs every morning at 6am UTC. You can see the last refresh time in the footer."

**[Scroll to footer — show 'Last refreshed X hours ago'.]**

---

## 1:35 – 1:50 — Honesty

> "We're honest about what we don't catch. WeWork's 2022 audit opinion was clean — Ernst & Young didn't issue a formal going-concern. The language was in management's MD&A, not the auditor's report. Catching that is a known limitation and it's on our roadmap. We document all limitations openly — because that's what real engineering looks like."

**[Briefly show the methodology page 'Known Limitations' section, or just scroll methodology]**

---

## 1:50 – 2:00 — The Close

> "Going Concern Tracker. Free, open-source, MIT-licensed. 35 companies monitored today, more on demand. Daily refresh, under one dollar a month to run. Source code on GitHub."

**[Navigate to the GitHub repository page as the final frame.]**

---

## Production Notes

- **Most recent flag to feature:** Check `/api/pipeline/status` before recording — use whichever flag was most recently added as the hero example.
- **Search demo timing:** The debounce is 200ms; type at normal human speed and the dropdown will appear naturally.
- **Total runtime target:** 1:55 – 2:05. Cut the engineering section if running long.
- **Environment:** Use production URLs (Vercel + Render), not localhost.
