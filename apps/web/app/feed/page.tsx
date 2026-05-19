import { fetchFlags } from "@/lib/api";
import { FeedList } from "./FeedList";

export const metadata = {
  title: "All Flags — Going Concern Tracker",
  description: "All going-concern flags detected in SEC 10-K filings, sorted by detection date.",
};

export default async function FeedPage() {
  let initialData;
  let fetchError = false;

  try {
    initialData = await fetchFlags({
      severity: ["critical", "elevated", "watch"],
      limit: 20,
      sort: "detected_at_desc",
    });
  } catch {
    fetchError = true;
    initialData = { items: [], next_cursor: null, has_more: false, total_returned: 0 };
  }

  if (fetchError) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-10 md:px-6 md:py-16">
        <h1 className="font-serif text-3xl font-medium text-slate-900">All flags</h1>
        <p className="mt-4 text-slate-600">
          Unable to load flags. Please try again in a moment.
        </p>
      </div>
    );
  }

  const total = initialData.total_returned + (initialData.has_more ? "+" : "");

  return (
    <div className="mx-auto max-w-3xl px-4 py-10 md:px-6 md:py-16">
      <h1 className="font-serif text-3xl font-medium text-slate-900">All flags</h1>
      <p className="mt-1 text-slate-600">
        Sorted by detection date.{" "}
        {initialData.total_returned > 0 && (
          <span>
            {total} flag{initialData.total_returned !== 1 ? "s" : ""} total.
          </span>
        )}
      </p>

      <div className="mt-8">
        <FeedList initialData={initialData} />
      </div>
    </div>
  );
}
