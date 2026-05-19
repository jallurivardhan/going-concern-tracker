import Link from "next/link";
import { SearchBar } from "@/components/search/SearchBar";

export function Header() {
  return (
    <header className="sticky top-0 z-40 border-b border-slate-200 bg-white">
      <div className="mx-auto max-w-5xl px-4 md:px-6">
        {/* Primary row: logo + nav */}
        <div className="flex items-center justify-between py-3 md:py-4">
          <Link
            href="/"
            className="font-serif text-base font-semibold text-slate-900 no-underline hover:text-slate-700 md:text-lg"
          >
            Going Concern Tracker
          </Link>

          <div className="flex items-center gap-4 md:gap-6">
            <nav aria-label="Site navigation">
              <ul className="flex items-center gap-4 text-sm md:gap-6">
                <li>
                  <Link
                    href="/feed"
                    className="font-sans text-slate-700 no-underline hover:text-slate-900"
                  >
                    Feed
                  </Link>
                </li>
                <li>
                  <Link
                    href="/methodology"
                    className="font-sans text-slate-700 no-underline hover:text-slate-900"
                  >
                    Methodology
                  </Link>
                </li>
                <li>
                  <a
                    href="https://github.com/jalludevs/going-concern-tracker"
                    target="_blank"
                    rel="noreferrer"
                    className="font-sans text-slate-700 no-underline hover:text-slate-900"
                  >
                    GitHub
                  </a>
                </li>
              </ul>
            </nav>

            {/* Desktop search */}
            <div className="hidden md:block">
              <SearchBar />
            </div>
          </div>
        </div>

        {/* Mobile search row */}
        <div className="pb-3 md:hidden">
          <SearchBar />
        </div>
      </div>
    </header>
  );
}
