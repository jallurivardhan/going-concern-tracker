import Link from "next/link";
import { notFound } from "next/navigation";
import { fetchCompany } from "@/lib/api";
import { SeverityBadge } from "@/components/site/SeverityBadge";
import type { FilingWithFlag, Severity } from "@/lib/api";

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(isoDate: string): string {
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(isoDate));
}

const SEVERITY_ORDER: Severity[] = ["critical", "elevated", "watch", "none"];

// ── Timeline row ──────────────────────────────────────────────────────────────

function TimelineRow({ filing }: { filing: FilingWithFlag }) {
  const flag = filing.going_concern_flag;
  const severity = (flag?.severity ?? "none") as Severity;
  const preview = flag?.quoted_language
    ? flag.quoted_language.length > 200
      ? `\u201c${flag.quoted_language.slice(0, 200).trimEnd()}\u2026\u201d`
      : `\u201c${flag.quoted_language}\u201d`
    : "Clean unqualified opinion.";

  return (
    <div className="relative flex gap-4">
      {/* Timeline line marker */}
      <div className="flex flex-col items-center">
        <div className="mt-1 h-3 w-3 shrink-0 rounded-full border-2 border-slate-300 bg-white" />
        <div className="flex-1 border-l-2 border-slate-100" />
      </div>

      {/* Content */}
      <div className="mb-6 min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium text-slate-700">
            {formatDate(filing.filing_date)}
          </span>
          {severity !== "none" ? (
            <SeverityBadge severity={severity} />
          ) : (
            <span className="inline-flex items-center rounded-md bg-emerald-50 px-2 py-0.5 text-xs font-medium uppercase tracking-wide text-emerald-700">
              Clean
            </span>
          )}
          {filing.audit_firm && (
            <span className="text-xs text-slate-500">{filing.audit_firm}</span>
          )}
        </div>

        <p className="mt-1 text-sm italic leading-relaxed text-slate-600">{preview}</p>

        {flag && severity !== "none" && (
          <Link
            href={`/flags/${flag.id}`}
            className="mt-1 inline-block text-xs font-medium text-slate-900 no-underline hover:underline"
          >
            View flag &rarr;
          </Link>
        )}
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default async function CompanyDetailPage({ params }: { params: { cik: string } }) {
  let company;
  try {
    company = await fetchCompany(params.cik);
  } catch (err) {
    if (err instanceof Error && err.message === "not_found") notFound();
    return (
      <div className="mx-auto max-w-3xl px-4 py-10 md:px-6 md:py-16">
        <p className="text-slate-600">Unable to load company data. Please try again.</p>
        <Link href="/feed" className="mt-4 inline-block text-sm text-slate-600 no-underline hover:text-slate-900">
          &larr; Back to feed
        </Link>
      </div>
    );
  }

  const displayName = company.display_name ?? company.name;
  const { flag_summary, filings } = company;

  // Sort filings most-recent first
  const sortedFilings = [...filings].sort(
    (a, b) => new Date(b.filing_date).getTime() - new Date(a.filing_date).getTime()
  );

  const hasSomeFlags =
    flag_summary.critical > 0 || flag_summary.elevated > 0 || flag_summary.watch > 0;

  return (
    <>
      <title>{`${displayName} — Going Concern Tracker`}</title>

      <div className="mx-auto max-w-3xl px-4 py-8 md:px-6 md:py-12">
        {/* Breadcrumb */}
        <Link href="/feed" className="text-sm text-slate-600 no-underline hover:text-slate-900">
          &larr; Back to feed
        </Link>

        {/* Header */}
        <h1 className="mt-6 font-serif text-3xl font-medium leading-tight text-slate-900 md:text-4xl">
          {displayName}
        </h1>
        <p className="mt-2 text-sm text-slate-500">
          {company.ticker && <span className="font-mono">{company.ticker}</span>}
          {company.ticker && " \u00b7 "}
          CIK {company.cik} &middot; {company.total_filings} filings analyzed
        </p>

        {/* Flag summary panel */}
        <div className="mt-6 rounded-md border border-slate-200 bg-slate-50 p-4">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">
            Flag summary
          </p>
          <div className="flex flex-wrap gap-3">
            {SEVERITY_ORDER.filter((s) => s !== "none").map((s) => (
              <div key={s} className="flex items-center gap-1.5">
                <SeverityBadge severity={s} />
                <span className="text-sm font-medium text-slate-700">
                  {flag_summary[s]}
                </span>
              </div>
            ))}
            <div className="flex items-center gap-1.5">
              <span className="inline-flex items-center rounded-md bg-emerald-50 px-2 py-0.5 text-xs font-medium uppercase tracking-wide text-emerald-700">
                Clean
              </span>
              <span className="text-sm font-medium text-slate-700">{flag_summary.none}</span>
            </div>
          </div>
        </div>

        {/* Timeline */}
        <section className="mt-10">
          <h2 className="font-serif text-xl font-medium text-slate-900">Filings and flags</h2>
          <p className="mt-1 text-sm text-slate-500">Most recent first.</p>

          {sortedFilings.length === 0 ? (
            <p className="mt-4 text-sm text-slate-500">
              Filings ingested but auditor reports not yet processed for this company.
            </p>
          ) : (
            <div className="mt-6">
              {sortedFilings.map((filing) => (
                <TimelineRow key={filing.id} filing={filing} />
              ))}
            </div>
          )}
        </section>

        {!hasSomeFlags && sortedFilings.length > 0 && (
          <p className="mt-4 rounded-md border border-emerald-100 bg-emerald-50 p-3 text-sm text-emerald-700">
            All audit opinions we&rsquo;ve classified for this company were clean.
          </p>
        )}
      </div>
    </>
  );
}
