import Link from "next/link";
import { SeverityBadge } from "@/components/site/SeverityBadge";
import type { Flag } from "@/lib/api";

function formatDate(isoDate: string): string {
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(isoDate));
}

interface FlagCardCompactProps {
  flag: Flag;
}

export function FlagCardCompact({ flag }: FlagCardCompactProps) {
  const quote = flag.quoted_language;
  const preview = quote
    ? quote.length > 150
      ? `\u201c${quote.slice(0, 150).trimEnd()}\u2026\u201d`
      : `\u201c${quote}\u201d`
    : "Clean unqualified opinion.";

  return (
    <Link
      href={`/flags/${flag.id}`}
      className={[
        "flex flex-col gap-1 rounded-md border border-slate-200 p-3 no-underline transition-colors",
        "hover:border-slate-400 focus-visible:outline-none focus-visible:ring-2",
        "focus-visible:ring-slate-900 focus-visible:ring-offset-2",
      ].join(" ")}
      aria-label={`${flag.company.display_name ?? flag.company.name} — ${flag.severity}, filed ${formatDate(flag.filing.filing_date)}`}
    >
      <div className="flex items-center justify-between gap-2">
        <SeverityBadge severity={flag.severity} />
        <span className="shrink-0 text-xs text-slate-500">{formatDate(flag.filing.filing_date)}</span>
      </div>
      <p className="text-xs italic leading-relaxed text-slate-600">{preview}</p>
    </Link>
  );
}
