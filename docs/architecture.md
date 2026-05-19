# Architecture

## The Three-Tier Reliability Model

Going Concern Tracker classifies SEC filings for going-concern language. This sounds simple, but the failure modes differ sharply depending on what part of the system is doing the work — so the codebase enforces a hard boundary between three tiers.

**Tier 1 — Deterministic.** Everything that touches raw data is deterministic and reproducible. Filing retrieval from EDGAR, XBRL parsing, citation links, database reads and writes, and arithmetic are all Tier 1. Code in this tier does not call an LLM. Given the same inputs, it will produce the same outputs every time. Tests are cheap, coverage is high, and debugging is straightforward.

**Tier 2 — Structured LLM.** Going-concern classification involves reading auditor prose and making a judgment call, which is genuinely a language task. We delegate this to Claude, but with strict constraints: the output must conform to a Pydantic schema (via `instructor`), which means the model's response is validated before it touches the database. There is no free-form text generation in production — every field the model fills in is type-checked and range-checked. This tier is logged end-to-end in Langfuse so every classification is auditable. Classifier version (`classifier_version` on `GoingConcernFlag`) is stored alongside each result so historical comparisons remain meaningful when we upgrade models.

**Tier 3 — Generative LLM.** Reserved for a future Q&A interface where users ask questions about specific filings. Not implemented.

The rule is simple: **no financial figure, no confidence score, no structured flag is ever derived from a free-form LLM string**. Tier 1 handles facts; Tier 2 handles judgment within a validated envelope.

## Why Pydantic + Instructor

`instructor` patches the Anthropic client to enforce structured output via JSON mode and Pydantic schema validation. If the model returns malformed JSON, instructor retries. If validation fails after retries, we raise rather than silently write garbage. This is meaningfully different from prompt-engineering a model to "return JSON" and then hoping — instructor makes the contract enforceable in code. The schemas live in `apps/api/src/gct/schemas/` and are the single source of truth for what a valid classification looks like.

## Why Neon

Neon is managed Postgres 16 with a free permanent tier and no connection limit surprises for low-traffic workloads. It is also pgvector-ready, which matters if Tier 3 (semantic Q&A over filing text) is ever built. The operational cost of running a VPS for a demo-scale project is not justified. The connection-drop risk of Neon's serverless proxy is mitigated by `pool_pre_ping=True` in `apps/api/src/gct/database.py`, which validates the connection before each query rather than trusting the pool's cached state.

## Why Claude

Structured-output reliability varies significantly between models on the going-concern task. The judgment requires reading dense accounting prose, recognizing hedged language ("there is substantial doubt…"), and distinguishing a true going-concern paragraph from related disclosures (liquidity notes, risk factors). Claude Sonnet performs better on this task than alternatives at comparable cost, and instructor's retry logic is well-tested against the Anthropic API. If this changes, `classifier_version` makes it straightforward to A/B test.

## Why Decimal, Not Float

`classification_confidence` and any future monetary field use `sqlalchemy.Numeric` (Python `Decimal`), never `float`. IEEE 754 floating-point arithmetic is inappropriate for values that will be compared, aggregated, or displayed to users with financial interpretations. A confidence of `0.987` stored as a float is `0.9869999999999999289...` — this is fine for ML training but wrong for a public-facing audit trail. The schema enforces `Numeric(4, 3)`, which is exact. See `apps/api/src/gct/models/__init__.py` for the constraint and `apps/api/src/gct/schemas/__init__.py` for the corresponding Pydantic `Decimal` field.

## Tier-1 Ingestion Layer

The ingestion pipeline (`apps/api/src/gct/ingestion/`) is purely deterministic. It consists of five focused modules:

**`edgar_client.py`** — The only module that makes network calls. It enforces the SEC's 10-requests/second fair-use cap via a sliding-window rate limiter (`_SlidingWindowRateLimiter`) and retries 429/503 responses with exponential backoff. The `User-Agent` header is always set to `"Going Concern Tracker {email}"` as required by SEC policy. Every public method is async.

**`ticker_lookup.py`** — Resolves ticker symbols to 10-digit zero-padded CIKs using the SEC's `company_tickers.json`. The map is cached for the process lifetime (one CLI run) to avoid redundant fetches. A miss against the cached map returns `None` immediately; a miss after a fresh fetch raises `TickerNotFoundError`.

**`filing_fetcher.py`** — Orchestrates per-company retrieval. It reads the company's submission history from `data.sec.gov/submissions/CIK{cik}.json` and selects the N most recent filings of each requested form type. Raw HTML is fetched per filing and returned as a typed `FetchedFiling` Pydantic model.

**`filing_parser.py`** — The auditor-report extractor. It uses BeautifulSoup (lxml backend) to convert HTML to plain text, then applies precompiled regexes to locate the auditor's report heading and its end boundary. It tries to identify the audit firm name and reports extraction confidence (`"high"` when the section boundary is unambiguous, `"medium"` or `"low"` for fallbacks). Returns `None` for 10-Q filings (which don't contain formal auditor opinions). **No LLM is involved.**

**`persistence.py`** — Idempotent `INSERT … ON CONFLICT DO UPDATE` writes. Re-running the backfill for the same ticker updates existing rows without creating duplicates. Raw HTML is written to `data/raw_filings/{cik}/{accession}.html` so re-extraction never requires a second EDGAR request — this is critical for reproducibility: when we improve the parser in a later prompt, we can re-process the same source HTML.

### Why we store raw HTML

Reproducibility. If the parser is improved (e.g., better going-concern detection heuristics), we can re-extract from the same HTML without re-fetching from SEC. This also means we're not relying on EDGAR's uptime for anything other than the initial backfill. The raw files are gitignored (`data/`) but should be backed up to object storage in production.

### Auditor-report locator heuristics and known limitations

The locator uses three strategies, tried in order per heading match:
1. **TOC guard** (`_TOC_INDICATOR`): After finding a candidate heading, the parser inspects the next 200 characters. If a standalone page number or a financial-statement section name appears at the start of a line (e.g., `57\nConsolidated Balance Sheets`), the hit is classified as a table-of-contents entry and skipped. The line-start anchor (`^` + MULTILINE) is critical — it prevents "consolidated balance sheets" appearing mid-sentence inside the actual report from triggering a false TOC skip.
2. **Real-report confirmation** (`_REAL_REPORT_INDICATOR`): Phrases like "To the Stockholders", "We have audited", or "In our opinion" confirm the heading is the genuine section. Confirmed hits use `confidence="high"` (v1, clear section boundary) or `confidence="medium"` (v2 fallback, signature-block boundary).
3. **Ambiguous fallback**: If neither indicator matches, the section is still extracted but tagged `extraction_method="heading_match_v2_ambiguous"` and `confidence="low"` for human review.

## Tier-2 Classification Layer

The classifier (`apps/api/src/gct/classifier/`) reads each `AuditorReport` row, sends the text to Claude, receives a validated Pydantic response, and writes a `GoingConcernFlag` row. Key design decisions:

### Why Instructor (guaranteed structured output)

`instructor` patches the Anthropic client so that the LLM _must_ return JSON conforming to `ClassifierResponse`. If validation fails, instructor automatically retries with the error message appended to the conversation (up to `classifier_max_retries=3` times). Without instructor, a model returning malformed JSON would silently fail or require bespoke parsing logic. With it, validation is enforced in the library layer, not the prompt.

### Why Claude (best at following strict legal-language instructions)

Going-concern classification requires:
- Reading dense accounting prose
- Distinguishing a formal PCAOB AS 2415 opinion modifier ("substantial doubt about its ability to continue as a going concern") from boilerplate ("prepared on the going-concern basis of accounting")
- Quoting language verbatim rather than paraphrasing

Claude's instruction-following on these constraints outperforms alternatives at comparable cost. The system prompt is frozen as `CLASSIFIER_VERSION = "v1.0-claude"` and stored on every `GoingConcernFlag` row so future model changes are A/B-comparable.

### Why Haiku → Sonnet escalation (cost-effective routing)

Approximately 80% of auditor reports are clean unqualified opinions — no going-concern language. Claude Haiku 4.5 handles these confidently at $1/M input tokens. When Haiku's `classification_confidence` falls below 0.7 (ambiguous reports), the classifier automatically re-runs with Claude Sonnet 4.5 ($3/M input). This routing costs roughly $0.015 per clean report and $0.04 per escalated report, keeping the full 25-report batch well under $0.50.

### Why we validate quotes via substring matching (defense against hallucination)

The LLM is instructed to quote language verbatim. After each classification, `validator.validate_classification()` performs a `str.find()` against the original report text. If the quote is not present, validation fails hard — the flag is not written. This catches hallucinated or paraphrased quotes before they enter the database. Warnings (not failures) are issued for very low confidence or critical severity without the canonical phrase pattern.

### Why offsets are computed deterministically (LLMs are bad at character counting)

`char_offset_start` and `char_offset_end` on `GoingConcernFlag` are computed from `str.find(quoted_language)` after the LLM returns, not asked from the model. LLMs are unreliable at byte-exact character counting; substring search is O(n) and exact.

## File Map

| Principle | Where it's enforced |
|-----------|-------------------|
| Tier 1 / no LLM in data path | `gct/services/` (no LLM imports) |
| Structured LLM output | `gct/llm/` + `gct/schemas/` |
| Pydantic validation on write | `gct/schemas/__init__.py` |
| Decimal for numeric fields | `gct/models/__init__.py` (Numeric columns) |
| DB resilience | `gct/database.py` (`pool_pre_ping=True`) |
| Rate limiting (SEC fair use) | `gct/ingestion/edgar_client.py` (`_SlidingWindowRateLimiter`) |
| Raw HTML storage | `gct/ingestion/persistence.py` (`save_raw_html`) |
| Auditor-report extraction | `gct/ingestion/filing_parser.py` |
| Idempotent DB writes | `gct/ingestion/persistence.py` (`upsert_*` functions) |
| Langfuse logging | `gct/classifier/claude_client.py` (`start_as_current_observation`) |
| Classifier versioning | `GoingConcernFlag.classifier_version` column |
| Quote hallucination guard | `gct/classifier/validator.py` (`validate_classification`) |
| Cost-conscious routing | `ClaudeClassifier` Haiku→Sonnet escalation on low confidence |
| Offset computation | `validator.py` (`str.find`) — never from LLM |
