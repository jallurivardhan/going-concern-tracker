"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { searchCompanies, type SearchResult } from "@/lib/api";

export function SearchBar() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const router = useRouter();

  // Debounced search — simple cleanup pattern avoids ref-stale issues in Strict Mode
  useEffect(() => {
    if (query.trim().length < 2) {
      setResults([]);
      setOpen(false);
      return;
    }

    setLoading(true);
    const timer = setTimeout(async () => {
      try {
        const data = await searchCompanies(query.trim());
        setResults(data);
        setOpen(true);
      } catch (err) {
        console.error("Search failed:", err);
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 200);

    return () => clearTimeout(timer);
  }, [query]);

  // Close dropdown on outside click
  useEffect(() => {
    const onClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const handleSelect = (cik: string) => {
    setOpen(false);
    setQuery("");
    router.push(`/companies/${cik}`);
  };

  return (
    <div ref={containerRef} className="relative w-full md:w-72">
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onFocus={() => results.length > 0 && setOpen(true)}
        placeholder="Search company or ticker…"
        className="h-10 w-full rounded-md border border-slate-300 bg-white px-3 text-sm text-slate-900 placeholder:text-slate-400 focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500"
        aria-label="Search companies"
        aria-autocomplete="list"
      />

      {open && (
        <div className="absolute left-0 right-0 top-full z-50 mt-1 max-h-80 overflow-y-auto rounded-md border border-slate-200 bg-white shadow-md">
          {loading && results.length === 0 ? (
            <p className="px-3 py-2 text-sm text-slate-500">Searching…</p>
          ) : results.length === 0 ? (
            <p className="px-3 py-2 text-sm text-slate-500">No matches found</p>
          ) : (
            <ul className="py-1">
              {results.map((r) => (
                <li key={r.cik}>
                  <button
                    type="button"
                    onClick={() => handleSelect(r.cik)}
                    className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left hover:bg-slate-50 focus:bg-slate-50 focus:outline-none"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-serif text-sm font-medium text-slate-900">
                        {r.display_name ?? r.name}
                      </p>
                      <p className="text-xs text-slate-500">
                        {r.ticker ? `${r.ticker} · CIK ${r.cik}` : `CIK ${r.cik}`}
                      </p>
                    </div>
                    {r.has_critical_flag && (
                      <span className="shrink-0 rounded bg-red-100 px-1.5 py-0.5 text-xs font-medium uppercase text-red-700">
                        Critical
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
