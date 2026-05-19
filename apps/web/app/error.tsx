"use client";

import { useEffect } from "react";
import Link from "next/link";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Unhandled error:", error);
  }, [error]);

  return (
    <div className="mx-auto max-w-2xl px-4 py-24 text-center">
      <p className="text-4xl font-serif font-semibold text-slate-900">Something went wrong</p>
      <p className="mt-4 text-slate-600">
        The page encountered an unexpected error. Please try again.
      </p>
      <div className="mt-8 flex items-center justify-center gap-4">
        <button
          onClick={reset}
          className="inline-flex h-10 items-center rounded-md bg-slate-900 px-5 text-sm font-medium text-white hover:bg-slate-700"
        >
          Try again
        </button>
        <Link
          href="/"
          className="inline-flex h-10 items-center rounded-md border border-slate-300 px-5 text-sm font-medium text-slate-900 no-underline hover:bg-slate-50"
        >
          Go home
        </Link>
      </div>
      {error.digest && (
        <p className="mt-6 font-mono text-xs text-slate-400">Error ID: {error.digest}</p>
      )}
    </div>
  );
}
