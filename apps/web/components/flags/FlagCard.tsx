import Link from "next/link";
import { SeverityBadge } from "@/components/site/SeverityBadge";
import type { Flag } from "@/lib/api";

function formatFilingDate(isoDate: string): string {
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(isoDate));
}

function truncateQuote(text: string, maxChars = 240): string {
  if (text.length <= maxChars) return text;
  return text.slice(0, maxChars).trimEnd() + "\u2026";
}

interface FlagCardProps {
  flag: Flag;
}

export function FlagCard({ flag }: FlagCardProps) {
  const { company, filing, severity, quoted_language, audit_firm } = flag;

  return (
    <Link
      href={`/flags/${flag.id}`}
      className={[
        "block rounded-md border border-slate-200 p-4 no-underline transition-colors",
        "hover:border-slate-400 focus-visible:outline-none focus-visible:ring-2",
        "focus-visible:ring-slate-900 focus-visible:ring-offset-2 md:p-6",
      ].join(" ")}
      aria-label={`${company.display_name} — ${severity} going-concern flag, filed ${formatFilingDate(filing.filing_date)}`}
    >
      {/* Top row: badge + date */}
      <div className="flex items-center justify-between gap-2">
        <SeverityBadge severity={severity} />
        <span className="shrink-0 text-xs text-slate-500">
          Filed {formatFilingDate(filing.filing_date)}
        </span>
      </div>

      {/* Company name */}
      <h2 className="mt-3 font-serif text-xl font-medium leading-snug text-slate-900 md:text-2xl">
        {company.display_name}
      </h2>

      {/* Ticker / status */}
      <p className="mt-0.5 text-sm text-slate-500">
        {company.ticker ? (
          <span className="font-mono">{company.ticker}</span>
        ) : (
          <span>Delisted / Private</span>
        )}
      </p>

      {/* Auditor quote */}
      <p className="mt-3 text-sm italic leading-relaxed text-slate-700">
        {quoted_language
          ? `\u201c${truncateQuote(quoted_language)}\u201d`
          : "Auditor issued a clean unqualified opinion."}
      </p>

      {/* Bottom row: audit firm + CTA */}
      <div className="mt-4 flex items-center justify-between gap-2">
        <span className="text-xs text-slate-500">
          {audit_firm ? `Audited by ${audit_firm}` : ""}
        </span>
        <span className="shrink-0 text-sm font-medium text-slate-900">View flag &rarr;</span>
      </div>
    </Link>
  );
}
