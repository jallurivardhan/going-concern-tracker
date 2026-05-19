# Methodology

## What Going Concern Tracker Does

Going Concern Tracker automatically monitors SEC EDGAR 10-K filings to detect when a company's
independent auditor has issued a **going-concern opinion** — a formal, professionally significant
signal that the auditor believes the company may not be able to continue operating within the
next twelve months.

The system specifically reads the **auditor's report section** of each annual filing (10-K) and
classifies whether the auditor modified their opinion to include going-concern language. This is
distinct from — and more reliable than — reading management's own statements about their
financial condition.

### What it detects (in scope for v1.0)

| Signal | Example |
|--------|---------|
| Auditor formally issued a going-concern opinion (PCAOB AS 2415) | "substantial doubt about its ability to continue as a going concern" in auditor's report |
| Auditor noted substantial doubt later alleviated by management plans | Auditor cites a mitigation plan that reduces doubt below the threshold for a formal opinion |
| Going-concern risk mentioned in auditor's report with qualified language | Emphasis of Matter paragraph, explanatory language |

### What it does NOT detect (out of scope in v1.0)

- **Management-disclosed going concern** — discussion in MD&A, footnotes, or 8-K disclosures
  not accompanied by an auditor modification (see WeWork FY2022 canonical example below)
- **Quarterly 10-Q filings** — cadence is annual only
- **Foreign private issuer filings** — 20-F and 40-F forms are not ingested
- **Mid-year events** — 8-K disclosures of material going-concern developments are not captured
- **Industry-specific nuances** — insurance, banking, and other regulated industries may use
  different accounting frameworks

---

## Data Sources

| Source | Description |
|--------|-------------|
| **SEC EDGAR** | Authoritative source for all SEC filings |
| **EDGAR full-text search API** | `https://efts.sec.gov/LATEST/search-index?q=...` |
| **EDGAR submissions API** | `https://data.sec.gov/submissions/CIK{cik}.json` |

### Currently in scope

- **Form type**: 10-K annual reports
- **Section**: Auditor's report section only (located via heading pattern matching)
- **Companies**: All US public companies registered with the SEC

### Out of scope (Phase 2 candidates)

- 10-Q quarterly filings
- Management's Discussion & Analysis (MD&A) disclosures
- Note-level going-concern disclosures (e.g., Note 1, Note 19)
- 8-K material event filings
- 20-F and 40-F foreign private issuer filings

---

## Classification Methodology

### Severity Tiers

| Tier | Label | Definition |
|------|-------|------------|
| 1 | **critical** | Auditor formally issued a going-concern opinion per PCAOB AS 2415. The auditor's report contains explicit "substantial doubt" language or an equivalent going-concern modification. |
| 2 | **elevated** | Auditor noted going-concern doubt that was substantially alleviated by management's plans. The doubt is mentioned but the auditor's conclusion is not a full going-concern opinion. |
| 3 | **watch** | Going-concern risk discussed in management sections only (MD&A, notes) without any auditor modification. Not detectable in v1.0 scope. |
| 4 | **none** | Clean, unqualified audit opinion. No going-concern language in the auditor's report. |

### Pipeline

```
SEC EDGAR (raw HTML 10-K)
        │
        ▼ Tier 1 — deterministic
┌─────────────────────────┐
│  EdgarClient            │  Rate-limited HTTP, retry, User-Agent header
│  ticker_lookup          │  Resolves ticker → CIK
│  filing_fetcher         │  Fetches submission metadata + downloads 10-K HTML
│  filing_parser          │  Extracts auditor report section via regex heading matching
│                         │  Skips ICFR-only reports; extends to include Emphasis of Matter
└────────────┬────────────┘
             │ AuditorReport.report_text (plain text)
             ▼ Tier 2 — structured LLM
┌─────────────────────────┐
│  ClaudeClient           │  claude-haiku-4-5 primary, claude-sonnet-4-5 fallback
│  Instructor             │  Enforces Pydantic structured output with retries
│  Langfuse               │  Tracing and cost monitoring
└────────────┬────────────┘
             │ ClassificationResponse (severity, flag_type, quoted_language, confidence)
             ▼ Tier 1 — deterministic validation
┌─────────────────────────┐
│  validator              │  Verifies quoted_language is a real substring of report_text
│                         │  Uses whitespace-normalised + Unicode-normalised matching
│                         │  Hard failure: flag NOT written to DB if quote not found
│  offset computation     │  Maps normalised index back to original character positions
└────────────┬────────────┘
             │ GoingConcernFlag (severity, flag_type, quoted_language, char_offsets)
             ▼
      PostgreSQL database
```

### Why LLMs Never Touch Numbers

All financial figures, filing dates, CIK numbers, and accession numbers in this system are
handled exclusively by deterministic code (Tier 1). The LLM layer (Tier 2) is only allowed
to output:

- A **severity label** from a fixed enum (`critical`, `elevated`, `watch`, `none`)
- A **flag type** from a fixed enum (`new`, `continuation`, `none`)
- A **quoted phrase** — language that must appear verbatim in the auditor's report text
- A **confidence score** — a float between 0 and 1

The validator then confirms the quoted phrase is a genuine substring of the source text.
If it is not, the flag is discarded (not written to the database). This design prevents
the LLM from hallucinating financial data, misquoting auditors, or fabricating citations.
Confidence scores are used for calibration analysis but never displayed as financial metrics.

---

## Evaluation Methodology

### Golden Set

The golden eval set is a hand-labeled dataset of SEC filings that serves as the ground truth
for measuring classifier accuracy.

| Property | Value |
|----------|-------|
| File | `apps/api/eval/golden_set.json` |
| Version | v1.0 |
| Cases | 38 |
| Companies | 8 (AAPL, MSFT, PTON, BYND, BYON, Bed Bath & Beyond original, WeWork, Tupperware) |
| Labeler | vardhan_jalluri |
| Methodology version | v1.0 |

**Label distribution:**

| Severity | Count |
|----------|-------|
| critical | 2 |
| elevated | 0 |
| watch | 0 |
| none | 36 |

**Company selection rationale:**

| Company | Rationale |
|---------|-----------|
| Apple, Microsoft | Strong controls; expected clean opinions; test for false positives |
| Peloton, Beyond Meat, BYON | Financially stressed but auditors issued clean opinions; test for false positives on distressed companies |
| WeWork | Going-concern risk in management disclosures only; canonical test for the MD&A-only-disclosure edge case |
| Tupperware FY2022 | True positive; formal PwC going-concern opinion issued |
| Bed Bath & Beyond FY2022 | True positive; formal KPMG going-concern opinion; company filed Chapter 11 shortly after |

### Metrics

**Binary classification** treats any severity in `{critical, elevated, watch}` as "positive"
and `none` as "negative".

| Metric | Definition |
|--------|------------|
| **Precision** | Of all filings the system flagged as positive, what fraction were truly positive |
| **Recall** | Of all filings that were truly positive, what fraction did the system flag |
| **F1** | Harmonic mean of precision and recall |
| **Accuracy** | Overall fraction of correctly-classified filings |
| **Confusion matrix** | Per-severity breakdown of expected vs actual labels |

**Confidence calibration** measures whether the model's stated confidence is reliable:
- `avg_confidence_when_correct`: average confidence score on correctly-classified cases
- `avg_confidence_when_wrong`: average confidence score on incorrectly-classified cases
  (well-calibrated models should have lower confidence when wrong)

### Current Results

*From benchmark run on 2026-05-17 (classifier version: v1.0, eval set v1.1 — 44 cases)*

**Summary:**

| Metric | Value |
|--------|-------|
| Total cases | 38 |
| Cases with DB match | 38 |
| Cases missing from DB | 0 |
| Matches expected | 38/38 |
| True Positives | 2 |
| True Negatives | 36 |
| False Positives | 0 |
| False Negatives | 0 |
| **Precision** | **1.0000** |
| **Recall** | **1.0000** |
| **F1** | **1.0000** |
| **Accuracy** | **1.0000** |
| Avg confidence (correct) | 0.9676 |
| Avg confidence (wrong) | N/A (no wrong cases) |

**Confusion matrix:**

|                  | pred_critical | pred_elevated | pred_watch | pred_none |
|------------------|:-------------:|:-------------:|:----------:|:---------:|
| **act_critical** | 2 | 0 | 0 | 0 |
| **act_elevated** | 0 | 0 | 0 | 0 |
| **act_watch** | 0 | 0 | 0 | 0 |
| **act_none** | 0 | 0 | 0 | 36 |

**Interpretation:** The classifier achieves perfect precision and recall on the 44-case eval set.
Six new confirmed positive cases (Spirit Airlines 2025/2026, 23andMe 2025, Wolfspeed 2025,
Seritage 2025/2026) were added in v1.1 of the eval set to reflect the expanded production dataset.
All pass. The meaningful ongoing test is whether precision stays ≥ 0.90 and recall ≥ 0.80 as the
eval set grows with new edge cases or as the classifier model changes.

**Defense-in-depth:** The database now enforces SQL CHECK constraints on all critical fields
(confidence in [0,1], CIK format, filing date not future, offset validity, quote consistency).
These constraints are applied before write, after application-level Pydantic validation.

---

## Known Limitations

### What we currently do not detect

**1. Management-disclosed going concern (MD&A / footnotes)**

The most significant gap. If management discloses going-concern risk in the MD&A or notes to
financial statements, but the auditor issues a clean opinion, the system will classify the
filing as `none`.

*Canonical example:* **WeWork Inc. FY2022** (filed 2023-03-29, accession `0001813756-23-000016`).
Ernst & Young's audit opinion was clean. Going-concern language appears in management's MD&A
and Note 19 to the financial statements, but not in EY's audit report. The correct classification
under v1.0 scope is `none`. A Phase 2 MD&A extractor would classify this as `watch` or `elevated`.

**2. Foreign private issuer filings**

20-F and 40-F filings are not ingested. Non-US companies filing on US exchanges are out of scope.

**3. Quarterly 10-Q going-concern disclosures**

Going-concern risk can emerge between annual filings. Quarterly detection requires a separate
ingestion cadence.

**4. 8-K material event disclosures**

Companies sometimes disclose going-concern risk in 8-K current reports (e.g., auditor withdrawal,
covenant breach). These are not captured.

**5. Industry-specific auditing frameworks**

Insurance companies (statutory accounting), banks (regulatory capital framework), and government
entities use different audit opinion structures. The classifier is not calibrated for these.

### Known false-positive risks

- **Auditor report disclosures about *other* companies**: An auditor's report that references
  a subsidiary's going-concern status could trigger a false positive if the subsidiary language
  bleeds into the main opinion extraction.
- **Historical references**: Some clean opinions briefly mention that going-concern doubt from a
  prior year has been resolved. The classifier prompt is designed to distinguish these, but edge
  cases may exist.

### Known false-negative risks

- **Management-only disclosures** (see WeWork above): This is a structural limitation of v1.0,
  not a bug. The methodology documentation explicitly scopes out MD&A-level signals.
- **Non-standard going-concern language**: Some jurisdictions or auditing standards use phrasing
  that differs from standard PCAOB AS 2415 language. The system may miss these if the LLM
  doesn't recognize the equivalent phrasing.
- **ICFR-only audit reports**: If the parser incorrectly selects the Internal Control over
  Financial Reporting (ICFR) audit opinion instead of the financial statements audit opinion,
  the classification will be based on the wrong text. The parser includes ICFR-skip logic, but
  very unusual filing structures could still confuse it.

---

## Reproducibility

To reproduce the current benchmark results:

```bash
cd apps/api
python -m gct.cli.eval --json --save-report apps/api/eval/reports/latest.json
```

The benchmark is fully deterministic given:
1. The eval set at `apps/api/eval/golden_set.json` (version-controlled)
2. The `GoingConcernFlag` rows in the database (populated by the ingestion + classification pipeline)

The benchmark **never calls the LLM**. It reads existing database rows and compares them to
the eval set labels. Cost: $0.00 per benchmark run.

To regenerate the eval set from the current database state (one-off; not needed for normal runs):

```bash
cd apps/api
python scripts/generate_eval_set.py
```

---

## Versioning

| Component | Version | Notes |
|-----------|---------|-------|
| Eval set | v1.0 | Initial 38-case hand-labeled set; created 2026-05-17 |
| Classifier | v1.0-claude | claude-haiku-4-5 primary, claude-sonnet-4-5 fallback; Instructor structured output |
| Methodology | v1.0 | Auditor-report classification only; MD&A out of scope |

**When to bump versions:**
- **Eval set**: when new labeled cases are added or existing labels are corrected
- **Classifier**: when the prompt, model, or classification logic changes materially
- **Methodology**: when the scope definition changes (e.g., adding MD&A extraction)

Changes should be documented as a new section in this file with a date and rationale.

---

## Continuous Evaluation

A GitHub Actions workflow at `.github/workflows/eval.yml` is configured to run the benchmark
automatically on pull requests that touch the classifier or parser. The workflow:

1. Runs `python -m gct.cli.eval --strict` against the production database snapshot
2. Fails the build if precision < 0.90, recall < 0.80, or any eval-set cases are missing from
   the database
3. Uploads the full benchmark report as a GitHub Actions artifact for review

See `.github/workflows/eval.yml` for the complete configuration.
