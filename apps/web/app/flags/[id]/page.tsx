import Link from "next/link";
import { notFound } from "next/navigation";
import { fetchFlag, fetchFlags } from "@/lib/api";
import { SeverityBadge } from "@/components/site/SeverityBadge";
import { FlagCardCompact } from "@/components/flags/FlagCardCompact";
import type { Severity } from "@/lib/api";

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(isoDate: string): string {
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  }).format(new Date(isoDate));
}

function formatDateTime(iso: string): string {
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(iso));
}

function formatShortDate(isoDate: string): string {
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(isoDate));
}

const SEVERITY_EXPLANATIONS: Record<Severity, string> = {
  critical:
    "The auditor formally issued a going-concern opinion. Under PCAOB Auditing Standard 2415, this means the auditor has stated in writing that there is substantial doubt about the company\u2019s ability to continue operating within the next 12 months.",
  elevated:
    "The auditor noted conditions that raised substantial doubt, but determined that management\u2019s plans to address those conditions were sufficient to alleviate the doubt.",
  watch:
    "Going-concern risk was discussed in management\u2019s MD\u0026A or footnotes, but the auditor did not modify their opinion.",
  none: "The auditor issued a clean unqualified opinion. No going-concern language present.",
};

// ── Page ──────────────────────────────────────────────────────────────────────

export default async function FlagDetailPage({ params }: { params: { id: string } }) {
  let flag;
  try {
    flag = await fetchFlag(params.id);
  } catch (err) {
    if (err instanceof Error && err.message === "not_found") notFound();
    return (
      <div className="mx-auto max-w-3xl px-4 py-10 md:px-6 md:py-16">
        <p className="text-slate-600">Unable to load this flag. Please try again in a moment.</p>
        <Link href="/feed" className="mt-4 inline-block text-sm text-slate-600 no-underline hover:text-slate-900">
          &larr; Back to feed
        </Link>
      </div>
    );
  }

  const { company, filing, severity } = flag;
  const displayName = company.display_name ?? company.name;

  // Build metadata title
  const pageTitle = `${displayName} — ${severity.charAt(0).toUpperCase() + severity.slice(1)} going-concern flag`;

  // Fetch other flags for this company (excluding this one)
  let otherFlags: import("@/lib/api").Flag[] = [];
  try {
    const otherRes = await fetchFlags({ cik: company.cik, severity: ["critical", "elevated", "watch"], limit: 10 });
    otherFlags = otherRes.items.filter((f) => f.id !== flag.id);
  } catch {
    otherFlags = [];
  }

  // Build sub-line parts
  const subLineParts: string[] = [];
  if (company.ticker) subLineParts.push(company.ticker);
  else subLineParts.push("Delisted");
  subLineParts.push(`Filed ${formatShortDate(filing.filing_date)}`);
  if (flag.audit_firm) subLineParts.push(`Audited by ${flag.audit_firm}`);
  const subLine = subLineParts.join(" \u00b7 ");

  return (
    <>
      <title>{pageTitle}</title>

      <div className="mx-auto max-w-3xl px-4 py-8 md:px-6 md:py-12">
        {/* Breadcrumb */}
        <Link
          href="/feed"
          className="text-sm text-slate-600 no-underline hover:text-slate-900"
        >
          &larr; Back to feed
        </Link>

        {/* Header */}
        <div className="mt-6">
          <SeverityBadge severity={severity} size="large" />
          <h1 className="mt-3 font-serif text-3xl font-medium leading-tight text-slate-900 md:text-4xl">
            {displayName}
          </h1>
          <p className="mt-2 text-sm text-slate-500">{subLine}</p>
        </div>

        {/* Quote section */}
        {flag.quoted_language && (
          <div className="mt-8 border-l-4 border-slate-200 bg-slate-50 p-4 md:p-6">
            <blockquote className="font-serif text-xl italic leading-relaxed text-slate-800 md:text-2xl">
              {flag.quoted_language.split("\n").map((line, i) => (
                <span key={i}>
                  {line}
                  {i < flag.quoted_language!.split("\n").length - 1 && <br />}
                </span>
              ))}
            </blockquote>
            {flag.char_offset_start != null && flag.char_offset_end != null && (
              <p className="mt-4 text-xs text-slate-400">
                Quoted verbatim from the auditor&rsquo;s report. Characters{" "}
                {flag.char_offset_start}&ndash;{flag.char_offset_end} of the audit section.
              </p>
            )}
          </div>
        )}

        {/* Severity explanation */}
        <div className="mt-6 rounded-md border border-slate-100 bg-white p-4">
          <p className="text-sm font-semibold text-slate-700">
            What does &ldquo;{severity}&rdquo; mean?
          </p>
          <p className="mt-1 text-sm leading-relaxed text-slate-600">
            {SEVERITY_EXPLANATIONS[severity]}
          </p>
        </div>

        {/* Filing context */}
        <div className="mt-8 grid grid-cols-1 gap-4 md:grid-cols-2">
          {/* Filing details */}
          <div className="rounded-md border border-slate-200 p-4">
            <h2 className="mb-3 font-serif text-base font-medium text-slate-900">
              Filing details
            </h2>
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between gap-2">
                <dt className="text-slate-500">Form type</dt>
                <dd className="font-mono text-slate-800">{filing.form_type}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-slate-500">Filing date</dt>
                <dd className="text-slate-800">{formatDate(filing.filing_date)}</dd>
              </div>
              {filing.period_of_report && (
                <div className="flex justify-between gap-2">
                  <dt className="text-slate-500">Period of report</dt>
                  <dd className="text-slate-800">{formatDate(filing.period_of_report)}</dd>
                </div>
              )}
              <div className="flex justify-between gap-2">
                <dt className="text-slate-500">Accession</dt>
                <dd className="break-all font-mono text-xs text-slate-600">
                  {filing.accession_number}
                </dd>
              </div>
            </dl>
          </div>

          {/* Classification details */}
          <div className="rounded-md border border-slate-200 p-4">
            <h2 className="mb-3 font-serif text-base font-medium text-slate-900">
              Classification details
            </h2>
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between gap-2">
                <dt className="text-slate-500">Severity</dt>
                <dd className="capitalize text-slate-800">{severity}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-slate-500">Flag type</dt>
                <dd className="capitalize text-slate-800">{flag.flag_type}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-slate-500">Confidence</dt>
                <dd className="text-slate-800">{flag.classification_confidence}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-slate-500">Classifier</dt>
                <dd className="font-mono text-xs text-slate-600">{flag.classifier_version}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-slate-500">Detected</dt>
                <dd className="text-slate-800">{formatDateTime(flag.detected_at)}</dd>
              </div>
            </dl>
          </div>
        </div>

        {/* Source filing CTA */}
        <div className="mt-8">
          <a
            href={filing.filing_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex min-h-[44px] items-center gap-2 rounded-md bg-slate-900 px-5 py-2.5 text-sm font-medium text-white no-underline transition-colors hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2"
          >
            Read the full filing on SEC.gov &rarr;
          </a>
        </div>

        {/* Company link */}
        <div className="mt-4">
          <Link
            href={`/companies/${company.cik}`}
            className="text-sm text-slate-600 no-underline hover:text-slate-900"
          >
            View all filings for {displayName} &rarr;
          </Link>
        </div>

        {/* Prior history */}
        <section className="mt-10 border-t border-slate-100 pt-8">
          <h2 className="font-serif text-xl font-medium text-slate-900">
            Other flags for this company
          </h2>
          {otherFlags.length > 0 ? (
            <div className="mt-4 flex flex-col gap-3">
              {otherFlags.map((f) => (
                <FlagCardCompact key={f.id} flag={f} />
              ))}
            </div>
          ) : (
            <p className="mt-3 text-sm text-slate-500">
              No other flags for this company. All other audit opinions we&rsquo;ve classified
              were clean.
            </p>
          )}
        </section>
      </div>
    </>
  );
}
