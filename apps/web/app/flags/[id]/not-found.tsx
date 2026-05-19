import Link from "next/link";

export default function FlagNotFound() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-16 md:px-6">
      <h1 className="font-serif text-3xl font-medium text-slate-900">Flag not found</h1>
      <p className="mt-3 text-slate-600">
        It may have been removed or the ID is incorrect.
      </p>
      <Link
        href="/feed"
        className="mt-6 inline-block text-sm font-medium text-slate-900 no-underline hover:underline"
      >
        &larr; Back to feed
      </Link>
    </div>
  );
}
