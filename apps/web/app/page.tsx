import Link from "next/link";
import { fetchFlags, fetchMethodology, fetchStats } from "@/lib/api";
import { FlagCard } from "@/components/flags/FlagCard";
import type { Flag } from "@/lib/api";

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDate(isoDate: string): string {
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  }).format(new Date(isoDate));
}

// ── Hero section ──────────────────────────────────────────────────────────────

async function Hero() {
  let stats;
  try {
    stats = await fetchStats();
  } catch {
    stats = null;
  }

  const flag = stats?.most_recent_critical_flag ?? null;
  const displayName = flag?.company_display_name ?? flag?.company_name ?? null;

  const isRecent =
    flag && Date.now() - new Date(flag.detected_at).getTime() < 7 * 24 * 60 * 60 * 1000;

  return (
    <section className="mx-auto max-w-3xl px-4 py-10 md:px-6 md:py-16">
      {flag && displayName ? (
        <>
          <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">
            Most Recent Critical Flag
          </p>
          <h1 className="mt-3 font-serif text-4xl font-medium leading-tight text-slate-900 md:text-5xl">
            {displayName}&rsquo;s auditor expressed substantial doubt about its ability to
            continue operating.
          </h1>
          <p className="mt-4 text-lg text-slate-600">
            {isRecent && flag.minutes_to_detect != null
              ? `Flagged ${flag.minutes_to_detect.toLocaleString()} minutes after the filing went live.`
              : `Filed ${formatDate(flag.filing_date)}. From the auditor\u2019s report in their 10-K.`}
          </p>
        </>
      ) : (
        <>
          <h1 className="font-serif text-4xl font-medium leading-tight text-slate-900 md:text-5xl">
            Tracking going-concern opinions in SEC filings.
          </h1>
          <p className="mt-4 text-lg text-slate-600">
            We read every 10-K filing the moment it appears, find the auditor&rsquo;s
            going-concern opinions, and surface them with citation back to the source.
          </p>
        </>
      )}

      <div className="mt-8 flex flex-col gap-3 sm:flex-row">
        <Link
          href="/feed"
          className="inline-flex min-h-[44px] items-center justify-center rounded-md bg-slate-900 px-5 py-2.5 text-sm font-medium text-white no-underline transition-colors hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2"
        >
          View all flags
        </Link>
        <Link
          href="/methodology"
          className="inline-flex min-h-[44px] items-center justify-center rounded-md border border-slate-300 px-5 py-2.5 text-sm font-medium text-slate-900 no-underline transition-colors hover:border-slate-400 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2"
        >
          How we measure
        </Link>
      </div>
    </section>
  );
}

// ── Placeholder flag card ─────────────────────────────────────────────────────

function PlaceholderCard() {
  return (
    <div className="rounded-md border border-dashed border-slate-200 p-4 md:p-6">
      <p className="text-sm text-slate-400">
        More flags will appear here as new SEC filings are ingested.
      </p>
    </div>
  );
}

// ── Example flags section ─────────────────────────────────────────────────────

async function ExampleFlags() {
  let flags: Flag[] = [];
  try {
    const res = await fetchFlags({ limit: 3, severity: ["critical", "elevated", "watch"] });
    flags = res.items;
  } catch {
    flags = [];
  }

  const placeholders = Math.max(0, 3 - flags.length);

  return (
    <section className="border-t border-slate-100 bg-slate-50 py-10 md:py-16">
      <div className="mx-auto max-w-3xl px-4 md:px-6">
        <h2 className="font-serif text-2xl font-medium text-slate-900">Recent flags</h2>
        <p className="mt-1 text-sm text-slate-600">
          Click any flag to see the auditor&rsquo;s exact language and the source filing.
        </p>

        <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-3">
          {flags.map((flag) => (
            <FlagCard key={flag.id} flag={flag} />
          ))}
          {Array.from({ length: placeholders }).map((_, i) => (
            <PlaceholderCard key={`placeholder-${i}`} />
          ))}
        </div>
      </div>
    </section>
  );
}

// ── Trust signals section ─────────────────────────────────────────────────────

async function TrustSignals() {
  let totalCases = 0;
  let precision = 0;
  let recall = 0;

  try {
    const m = await fetchMethodology();
    if (m.current_metrics) {
      totalCases = m.current_metrics.total_cases;
      precision = Math.round(parseFloat(m.current_metrics.precision) * 100);
      recall = Math.round(parseFloat(m.current_metrics.recall) * 100);
    }
  } catch {
    // non-fatal — show zeros
  }

  return (
    <section className="py-10 md:py-16">
      <div className="mx-auto max-w-3xl px-4 md:px-6">
        <div className="grid grid-cols-1 gap-8 md:grid-cols-3">
          <div>
            <p className="font-serif text-base font-semibold text-slate-900">
              Sourced from SEC EDGAR
            </p>
            <p className="mt-2 text-sm text-slate-600">
              We read every 10-K directly from the SEC&rsquo;s official archive. Every flag links
              to the exact filing.
            </p>
          </div>

          <div>
            <p className="font-serif text-base font-semibold text-slate-900">Open methodology</p>
            <p className="mt-2 text-sm text-slate-600">
              Our classification logic, evaluation set, and accuracy metrics are public.{" "}
              {totalCases > 0 ? (
                <>
                  {totalCases} cases hand-labeled with {precision}% precision and {recall}% recall.
                </>
              ) : (
                <>See the methodology page for full details.</>
              )}{" "}
              An automated pipeline checks SEC EDGAR every day at 6am UTC for new filings.
            </p>
          </div>

          <div>
            <p className="font-serif text-base font-semibold text-slate-900">Free, no signup</p>
            <p className="mt-2 text-sm text-slate-600">
              Browse and search freely. No account, no paywall &mdash; every flag links straight to
              the source filing.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function HomePage() {
  return (
    <>
      <Hero />
      <ExampleFlags />
      <TrustSignals />
    </>
  );
}