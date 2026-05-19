import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { FlagCardCompact } from "@/components/flags/FlagCardCompact";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { Flag } from "@/lib/api";

function Wrapper({ children }: { children: React.ReactNode }) {
  return <TooltipProvider>{children}</TooltipProvider>;
}

function makeFlag(overrides: Partial<Flag> = {}): Flag {
  return {
    id: "550e8400-e29b-41d4-a716-446655440000",
    company: {
      cik: "0000886158",
      ticker: "BBBY",
      name: "BED BATH & BEYOND INC",
      display_name: "Bed Bath & Beyond Inc. (pre-bankruptcy)",
    },
    filing: {
      id: "aabbcc",
      accession_number: "0000886158-23-000123",
      form_type: "10-K",
      filing_date: "2023-04-26",
      period_of_report: null,
      filing_url: "https://www.sec.gov/",
    },
    severity: "critical",
    flag_type: "new",
    quoted_language:
      "There is substantial doubt about the company's ability to continue as a going concern.",
    char_offset_start: 100,
    char_offset_end: 200,
    classification_confidence: "0.990",
    classifier_version: "v1.0-claude-haiku-4-5",
    detected_at: "2023-04-26T14:32:00Z",
    audit_firm: "KPMG LLP",
    ...overrides,
  };
}

describe("FlagCardCompact", () => {
  it("renders severity badge", () => {
    render(
      <Wrapper>
        <FlagCardCompact flag={makeFlag()} />
      </Wrapper>
    );
    expect(screen.getByRole("img", { name: /severity: critical/i })).toBeInTheDocument();
  });

  it("truncates quote to 150 characters", () => {
    const longQuote = "A".repeat(200);
    render(
      <Wrapper>
        <FlagCardCompact flag={makeFlag({ quoted_language: longQuote })} />
      </Wrapper>
    );
    // Should end with ellipsis
    expect(screen.getByText(/\u2026\u201d/)).toBeInTheDocument();
  });

  it("shows full quote when under 150 characters", () => {
    const shortQuote = "Short going concern language.";
    render(
      <Wrapper>
        <FlagCardCompact flag={makeFlag({ quoted_language: shortQuote })} />
      </Wrapper>
    );
    expect(screen.getByText(`\u201c${shortQuote}\u201d`)).toBeInTheDocument();
  });

  it("shows 'Clean unqualified opinion' when quoted_language is null", () => {
    render(
      <Wrapper>
        <FlagCardCompact flag={makeFlag({ quoted_language: null })} />
      </Wrapper>
    );
    expect(screen.getByText("Clean unqualified opinion.")).toBeInTheDocument();
  });

  it("links to the flag detail page", () => {
    render(
      <Wrapper>
        <FlagCardCompact flag={makeFlag()} />
      </Wrapper>
    );
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "/flags/550e8400-e29b-41d4-a716-446655440000");
  });
});
