import { fetchMethodology } from "@/lib/api";

export const metadata = {
  title: "Methodology — Going Concern Tracker",
  description:
    "How Going Concern Tracker detects and classifies going-concern opinions in SEC 10-K filings.",
};

// Severity tiers are static — not in the API response, defined by the system.
const SEVERITY_TIERS = [
  {
    name: "Critical",
    description:
      "The auditor formally issued a going-concern opinion. The auditor has stated in writing that the company may not be able to continue operating.",
  },
  {
    name: "Elevated",
    description:
      "The auditor noted substantial doubt about the company's ability to continue, but management's plans were sufficient to alleviate the doubt.",
  },
  {
    name: "Watch",
    description:
      "Going-concern risk was discussed in management's MD&A or notes, but the auditor did not formally modify their opinion.",
  },
  {
    name: "None",
    description: "The auditor issued a clean unqualified opinion. No going-concern language present.",
  },
];

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th className="border border-slate-200 bg-slate-50 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
      {children}
    </th>
  );
}

function Td({ children }: { children: React.ReactNode }) {
  return (
    <td className="border border-slate-200 px-3 py-2 text-sm text-slate-700">{children}</td>
  );
}

export default async function MethodologyPage() {
  let m;
  try {
    m = await fetchMethodology();
  } catch {
    return (
      <div className="mx-auto max-w-3xl px-4 py-10 md:px-6 md:py-16">
        <h1 className="font-serif text-3xl font-medium text-slate-900">Methodology</h1>
        <p className="mt-4 text-slate-600">
          Unable to load methodology data. Please try again in a moment.
        </p>
      </div>
    );
  }

  const metrics = m.current_metrics;

  return (
    <div className="mx-auto max-w-3xl px-4 py-10 md:px-6 md:py-16">
      {/* Heading */}
      <h1 className="font-serif text-3xl font-medium text-slate-900">Methodology</h1>

      {/* Intro */}
      <p className="mt-4 text-slate-600">
        Going Concern Tracker monitors SEC EDGAR 10-K filings to detect auditor-issued
        going-concern opinions. Here&rsquo;s how it works.
      </p>

      {/* What we detect */}
      <section className="mt-10">
        <h2 className="font-serif text-xl font-medium text-slate-900">What we detect</h2>
        <ul className="mt-3 space-y-1 text-sm text-slate-700">
          {m.in_scope.map((item) => (
            <li key={item} className="flex gap-2">
              <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-slate-400" />
              {item}
            </li>
          ))}
        </ul>
      </section>

      {/* What we don't detect */}
      {m.out_of_scope.length > 0 && (
        <section className="mt-8">
          <h2 className="font-serif text-xl font-medium text-slate-900">
            What we don&rsquo;t detect (yet)
          </h2>
          <ul className="mt-3 space-y-1 text-sm text-slate-700">
            {m.out_of_scope.map((item) => (
              <li key={item} className="flex gap-2">
                <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-slate-300" />
                {item}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Current accuracy */}
      <section className="mt-8">
        <h2 className="font-serif text-xl font-medium text-slate-900">Current accuracy</h2>
        <p className="mt-1 text-sm text-slate-500">
          {metrics?.last_run
            ? `Last evaluated: ${new Date(metrics.last_run).toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })}`
            : "Evaluation pending."}
        </p>
        {metrics ? (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full border-collapse text-sm">
              <thead>
                <tr>
                  <Th>Metric</Th>
                  <Th>Value</Th>
                  <Th>Notes</Th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <Td>Cases</Td>
                  <Td>{metrics.total_cases}</Td>
                  <Td>Hand-labeled gold set</Td>
                </tr>
                <tr>
                  <Td>Precision</Td>
                  <Td>{(parseFloat(metrics.precision) * 100).toFixed(1)}%</Td>
                  <Td>Of flags raised, how many were correct</Td>
                </tr>
                <tr>
                  <Td>Recall</Td>
                  <Td>{(parseFloat(metrics.recall) * 100).toFixed(1)}%</Td>
                  <Td>Of true flags, how many were caught</Td>
                </tr>
                <tr>
                  <Td>F1</Td>
                  <Td>{(parseFloat(metrics.f1) * 100).toFixed(1)}%</Td>
                  <Td>Harmonic mean of precision and recall</Td>
                </tr>
              </tbody>
            </table>
          </div>
        ) : (
          <p className="mt-3 text-sm text-slate-500">No evaluation data available yet.</p>
        )}
      </section>

      {/* Severity tiers */}
      <section className="mt-8">
        <h2 className="font-serif text-xl font-medium text-slate-900">Severity tiers</h2>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr>
                <Th>Tier</Th>
                <Th>Description</Th>
              </tr>
            </thead>
            <tbody>
              {SEVERITY_TIERS.map((tier) => (
                <tr key={tier.name}>
                  <Td>
                    <span className="font-medium">{tier.name}</span>
                  </Td>
                  <Td>{tier.description}</Td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Link to full doc */}
      <section className="mt-10 border-t border-slate-100 pt-8">
        <p className="text-sm text-slate-600">
          <a
            href="https://github.com/jalludevs/going-concern-tracker/blob/main/docs/methodology.md"
            target="_blank"
            rel="noreferrer"
            className="font-medium text-slate-900"
          >
            Full methodology document on GitHub &rarr;
          </a>
        </p>
      </section>
    </div>
  );
}
