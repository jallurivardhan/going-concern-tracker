const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api";

// Types mirror the FastAPI response schemas exactly.
// Source of truth: apps/api/src/gct/schemas/api.py

export type Severity = "critical" | "elevated" | "watch" | "none";
export type FlagType = "new" | "continuation" | "resolved" | "none";
export type MatchType = "ticker_exact" | "ticker_prefix" | "name_substring";

// ── Shared inline types ────────────────────────────────────────────────────────

export interface CompanyInline {
  cik: string;
  ticker: string | null;
  name: string; // raw SEC legal name
  display_name: string | null; // human-friendly; always set after model_validator
}

export interface FilingInline {
  id: string;
  accession_number: string;
  form_type: string;
  filing_date: string; // ISO date "2023-06-14"
  period_of_report: string | null; // ISO date, added to FilingBrief in Prompt 7
  filing_url: string;
}

// ── Flag types ────────────────────────────────────────────────────────────────

export interface Flag {
  id: string;
  company: CompanyInline;
  filing: FilingInline;
  severity: Severity;
  flag_type: FlagType;
  quoted_language: string | null;
  char_offset_start: number | null;
  char_offset_end: number | null;
  classification_confidence: string; // Decimal as string, e.g. "0.990"
  classifier_version: string;
  detected_at: string; // ISO timestamp
  audit_firm: string | null;
}

export interface FlagDetail extends Flag {
  report_excerpt: string | null;
  report_total_length: number | null;
}

export interface FlagsResponse {
  items: Flag[];
  next_cursor: string | null;
  has_more: boolean;
  total_returned: number;
}

// ── Company types ─────────────────────────────────────────────────────────────

export interface FlagSummary {
  critical: number;
  elevated: number;
  watch: number;
  none: number;
}

export interface FlagBrief {
  id: string;
  severity: string;
  filing_date: string;
  detected_at: string;
}

export interface CompanyDetail extends CompanyInline {
  sector: string | null;
  industry: string | null;
  total_filings: number;
  total_10ks: number;
  flag_summary: FlagSummary;
  most_recent_flag: FlagBrief | null;
  most_recent_filing_date: string | null;
  flag_history: Flag[];
  filings: FilingWithFlag[];
}

// ── Filing types ──────────────────────────────────────────────────────────────

export interface FilingWithFlag {
  id: string;
  accession_number: string;
  form_type: string;
  filing_date: string;
  period_of_report: string | null;
  filing_url: string;
  company: CompanyInline;
  auditor_report_excerpt: string | null;
  audit_firm: string | null;
  going_concern_flag: Flag | null;
}

export interface FilingListResponse {
  items: FilingWithFlag[];
  next_cursor: string | null;
  has_more: boolean;
}

// ── Search types ──────────────────────────────────────────────────────────────

export interface SearchResult {
  cik: string;
  ticker: string | null;
  name: string;
  display_name: string | null;
  match_type: "ticker_exact" | "ticker_prefix" | "name_substring";
  has_critical_flag: boolean;
}

// ── Stats & methodology ───────────────────────────────────────────────────────

export interface Stats {
  total_companies_tracked: number;
  total_filings_analyzed: number;
  total_auditor_reports_extracted: number;
  total_flags_active: number;
  flag_breakdown: Record<Severity, number>;
  most_recent_critical_flag: {
    id: string;
    company_name: string;
    company_ticker: string | null;
    company_display_name?: string;
    severity: Severity;
    filing_date: string;
    detected_at: string;
    minutes_to_detect: number | null;
  } | null;
  last_pipeline_run: string | null;
}

export interface MethodologyResponse {
  methodology_version: string;
  classifier_version: string;
  eval_set_version: string;
  current_metrics: {
    total_cases: number;
    precision: string; // Decimal serialized as string, e.g. "1.000"
    recall: string;
    f1: string;
    accuracy: string;
    last_run: string; // ISO timestamp
  } | null;
  in_scope: string[];
  out_of_scope: string[];
}

// ── Subscription types ────────────────────────────────────────────────────────

export interface SubscribeResponse {
  ok: boolean;
  message: string;
  subscription_id?: string;
  already_subscribed?: boolean;
}

// ── API functions ─────────────────────────────────────────────────────────────

export async function fetchStats(): Promise<Stats> {
  const res = await fetch(`${API_BASE}/stats`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to fetch stats: ${res.status}`);
  return res.json();
}

export async function fetchFlags(params?: {
  severity?: Severity[];
  flag_type?: FlagType[];
  cik?: string;
  since?: string;
  limit?: number;
  cursor?: string;
  sort?: "detected_at_desc" | "detected_at_asc";
}): Promise<FlagsResponse> {
  const url = new URL(`${API_BASE}/flags`);
  if (params?.severity) url.searchParams.set("severity", params.severity.join(","));
  if (params?.flag_type) url.searchParams.set("flag_type", params.flag_type.join(","));
  if (params?.cik) url.searchParams.set("cik", params.cik);
  if (params?.since) url.searchParams.set("since", params.since);
  if (params?.limit) url.searchParams.set("limit", String(params.limit));
  if (params?.cursor) url.searchParams.set("cursor", params.cursor);
  if (params?.sort) url.searchParams.set("sort", params.sort);
  const res = await fetch(url.toString(), { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to fetch flags: ${res.status}`);
  return res.json();
}

export async function fetchFlag(id: string): Promise<FlagDetail> {
  const res = await fetch(`${API_BASE}/flags/${id}`, { cache: "no-store" });
  if (res.status === 404) throw new Error("not_found");
  if (!res.ok) throw new Error(`Failed to fetch flag: ${res.status}`);
  return res.json();
}

export async function fetchCompany(cik: string): Promise<CompanyDetail> {
  const res = await fetch(`${API_BASE}/companies/${cik}`, { cache: "no-store" });
  if (res.status === 404) throw new Error("not_found");
  if (!res.ok) throw new Error(`Failed to fetch company: ${res.status}`);
  return res.json();
}

export async function fetchCompanyFilings(cik: string): Promise<FilingListResponse> {
  const res = await fetch(`${API_BASE}/companies/${cik}/filings`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to fetch filings: ${res.status}`);
  return res.json();
}

export async function fetchMethodology(): Promise<MethodologyResponse> {
  const res = await fetch(`${API_BASE}/methodology`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to fetch methodology: ${res.status}`);
  return res.json();
}

export async function searchCompanies(q: string): Promise<SearchResult[]> {
  if (q.trim().length < 2) return [];
  const url = new URL(`${API_BASE}/search`);
  url.searchParams.set("q", q.trim());
  const res = await fetch(url.toString(), { cache: "no-store" });
  if (!res.ok) return [];
  const data = await res.json();
  return (data.results as SearchResult[]) || [];
}

// ── Pipeline status ───────────────────────────────────────────────────────────

export interface PipelineRunBrief {
  id: string;
  started_at: string;
  completed_at: string | null;
  status: string;
  filings_checked: number;
  filings_new: number;
  filings_classified: number;
  flags_created: number;
  total_cost_estimate: string;
  trigger: string;
}

export interface PipelineStatus {
  last_successful_run: PipelineRunBrief | null;
  last_run: PipelineRunBrief | null;
  watchlist_size: number;
  schedule: string;
}

export async function fetchPipelineStatus(): Promise<PipelineStatus> {
  const res = await fetch(`${API_BASE}/pipeline/status`, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to fetch pipeline status: ${res.status}`);
  return res.json();
}

export async function subscribe(email: string): Promise<SubscribeResponse> {
  const res = await fetch(`${API_BASE}/subscriptions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
  if (res.status === 429) {
    throw new Error("Too many requests. Please try again in a few minutes.");
  }
  if (!res.ok) {
    throw new Error(`Subscribe failed: ${res.status}`);
  }
  return res.json();
}
