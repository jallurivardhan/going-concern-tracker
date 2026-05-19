"use client";

import { useEffect } from "react";
import Link from "next/link";

export default function CompanyError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Company detail error:", error);
  }, [error]);

  return (
    <div className="mx-auto max-w-2xl px-4 py-24 text-center">
      <p className="text-3xl font-serif font-semibold text-slate-900">Unable to load company</p>
      <p className="mt-3 text-slate-600">Company data could not be retrieved. Please try again.</p>
      <div className="mt-8 flex items-center justify-center gap-4">
        <button
          onClick={reset}
          className="inline-flex h-10 items-center rounded-md bg-slate-900 px-5 text-sm font-medium text-white hover:bg-slate-700"
        >
          Try again
        </button>
        <Link
          href="/feed"
          className="inline-flex h-10 items-center rounded-md border border-slate-300 px-5 text-sm font-medium text-slate-900 no-underline hover:bg-slate-50"
        >
          Back to feed
        </Link>
      </div>
    </div>
  );
}
