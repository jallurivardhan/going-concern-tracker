"use client";

import { useState, useTransition } from "react";
import { FlagCard } from "@/components/flags/FlagCard";
import { Skeleton } from "@/components/ui/skeleton";
import { fetchFlags } from "@/lib/api";
import type { Flag, FlagsResponse } from "@/lib/api";

function FlagCardSkeleton() {
  return (
    <div className="rounded-md border border-slate-200 p-4 md:p-6">
      <div className="flex items-center justify-between gap-2">
        <Skeleton className="h-5 w-20" />
        <Skeleton className="h-4 w-24" />
      </div>
      <Skeleton className="mt-3 h-7 w-3/4" />
      <Skeleton className="mt-1 h-4 w-16" />
      <Skeleton className="mt-3 h-16 w-full" />
      <div className="mt-4 flex items-center justify-between gap-2">
        <Skeleton className="h-4 w-40" />
        <Skeleton className="h-4 w-16" />
      </div>
    </div>
  );
}

interface FeedListProps {
  initialData: FlagsResponse;
}

export function FeedList({ initialData }: FeedListProps) {
  const [flags, setFlags] = useState<Flag[]>(initialData.items);
  const [cursor, setCursor] = useState<string | null>(initialData.next_cursor);
  const [hasMore, setHasMore] = useState(initialData.has_more);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function loadMore() {
    if (!cursor || isPending) return;

    startTransition(async () => {
      try {
        const res = await fetchFlags({
          severity: ["critical", "elevated", "watch"],
          limit: 20,
          cursor,
          sort: "detected_at_desc",
        });
        setFlags((prev) => [...prev, ...res.items]);
        setCursor(res.next_cursor);
        setHasMore(res.has_more);
      } catch {
        setError("Unable to load more flags. Please try again.");
      }
    });
  }

  if (flags.length === 0) {
    return (
      <p className="py-12 text-center text-slate-500">
        No flags yet. As new SEC filings are ingested, going-concern opinions will appear here.
      </p>
    );
  }

  return (
    <div>
      <div className="flex flex-col gap-4 md:gap-6">
        {flags.map((flag) => (
          <FlagCard key={flag.id} flag={flag} />
        ))}

        {isPending &&
          Array.from({ length: 3 }).map((_, i) => <FlagCardSkeleton key={`sk-${i}`} />)}
      </div>

      {error && <p className="mt-4 text-sm text-red-600">{error}</p>}

      {hasMore && !isPending && (
        <div className="mt-8 flex justify-center">
          <button
            onClick={loadMore}
            className="min-h-[44px] rounded-md border border-slate-300 px-6 py-2.5 text-sm font-medium text-slate-900 transition-colors hover:border-slate-400 hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2"
          >
            Load more
          </button>
        </div>
      )}
    </div>
  );
}
