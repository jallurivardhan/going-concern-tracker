import Link from "next/link";
import { fetchPipelineStatus } from "@/lib/api";

function _relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const diffHours = diffMs / (1000 * 60 * 60);
  if (diffHours < 1) return "less than 1 hour ago";
  if (diffHours < 24) return `${Math.floor(diffHours)} hour${Math.floor(diffHours) === 1 ? "" : "s"} ago`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays} day${diffDays === 1 ? "" : "s"} ago`;
}

async function FooterMeta() {
  try {
    const status = await fetchPipelineStatus();
    const run = status.last_successful_run;
    if (!run) {
      return <p className="text-xs text-slate-400">MIT License</p>;
    }
    const diffMs = Date.now() - new Date(run.completed_at ?? run.started_at).getTime();
    const stale = diffMs > 36 * 60 * 60 * 1000; // > 36 hours
    const relTime = _relativeTime(run.completed_at ?? run.started_at);
    const completedAt = new Date(run.completed_at ?? run.started_at).toLocaleString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "UTC",
      timeZoneName: "short",
    });

    return (
      <p className="text-xs text-slate-400" title={`Pipeline runs daily. Last successful run: ${completedAt}. Watching ${status.watchlist_size} companies.`}>
        {stale && (
          <span className="mr-1 inline-block h-2 w-2 rounded-full bg-amber-400" aria-label="Pipeline may be behind" />
        )}
        Last refreshed {relTime} &middot; MIT License
      </p>
    );
  } catch {
    return <p className="text-xs text-slate-400">MIT License</p>;
  }
}

export function Footer() {
  return (
    <footer className="border-t border-slate-200 bg-slate-50">
      <div className="mx-auto max-w-5xl px-4 py-10 md:px-6 md:py-14">
        <div className="grid grid-cols-1 gap-8 md:grid-cols-3">
          {/* Column 1: Brand */}
          <div>
            <p className="font-serif text-sm font-semibold text-slate-900">
              Going Concern Tracker
            </p>
            <p className="mt-2 text-sm text-slate-500">
              A free public tracker of going-concern opinions in SEC filings.
            </p>
          </div>

          {/* Column 2: Links */}
          <div>
            <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">
              Links
            </p>
            <ul className="space-y-2 text-sm">
              <li>
                <Link href="/feed" className="text-slate-600 no-underline hover:text-slate-900">
                  Feed
                </Link>
              </li>
              <li>
                <Link
                  href="/methodology"
                  className="text-slate-600 no-underline hover:text-slate-900"
                >
                  Methodology
                </Link>
              </li>
              <li>
                <a
                  href="https://github.com/jalludevs/going-concern-tracker"
                  target="_blank"
                  rel="noreferrer"
                  className="text-slate-600 no-underline hover:text-slate-900"
                >
                  GitHub
                </a>
              </li>
              <li>
                <a
                  href="https://github.com/jalludevs/going-concern-tracker"
                  target="_blank"
                  rel="noreferrer"
                  className="text-slate-600 no-underline hover:text-slate-900"
                >
                  Source code
                </a>
              </li>
            </ul>
          </div>

          {/* Column 3: Data source */}
          <div>
            <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">
              Data
            </p>
            <p className="text-sm text-slate-500">
              All filings sourced from{" "}
              <a
                href="https://www.sec.gov/edgar"
                target="_blank"
                rel="noreferrer"
                className="text-slate-700 hover:text-slate-900"
              >
                SEC EDGAR
              </a>
              . Every flag links to the exact filing.
            </p>
          </div>
        </div>

        {/* Small-print row */}
        <div className="mt-10 border-t border-slate-200 pt-6">
          <FooterMeta />
        </div>
      </div>
    </footer>
  );
}
