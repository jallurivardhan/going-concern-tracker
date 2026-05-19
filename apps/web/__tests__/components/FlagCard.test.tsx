import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { FlagCard } from "@/components/flags/FlagCard";
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
      filing_url: "https://www.sec.gov/Archives/edgar/data/886158/000088615823000123/bbby-20230225.htm",
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

describe("FlagCard", () => {
  it("renders the display_name, not the raw legal name", () => {
    render(
      <Wrapper>
        <FlagCard flag={makeFlag()} />
      </Wrapper>
    );
    expect(screen.getByText("Bed Bath & Beyond Inc. (pre-bankruptcy)")).toBeInTheDocument();
    expect(screen.queryByText("BED BATH & BEYOND INC")).not.toBeInTheDocument();
  });

  it("renders the audit firm when present", () => {
    render(
      <Wrapper>
        <FlagCard flag={makeFlag({ audit_firm: "PricewaterhouseCoopers LLP" })} />
      </Wrapper>
    );
    expect(screen.getByText("Audited by PricewaterhouseCoopers LLP")).toBeInTheDocument();
  });

  it("renders nothing for audit_firm row when audit_firm is null", () => {
    render(
      <Wrapper>
        <FlagCard flag={makeFlag({ audit_firm: null })} />
      </Wrapper>
    );
    expect(screen.queryByText(/audited by/i)).not.toBeInTheDocument();
  });

  it("shows ticker when present", () => {
    render(
      <Wrapper>
        <FlagCard flag={makeFlag({ company: { ...makeFlag().company, ticker: "BBBY" } })} />
      </Wrapper>
    );
    expect(screen.getByText("BBBY")).toBeInTheDocument();
  });

  it("shows Delisted / Private when ticker is null", () => {
    render(
      <Wrapper>
        <FlagCard flag={makeFlag({ company: { ...makeFlag().company, ticker: null } })} />
      </Wrapper>
    );
    expect(screen.getByText("Delisted / Private")).toBeInTheDocument();
  });

  it("links to the flag detail page", () => {
    render(
      <Wrapper>
        <FlagCard flag={makeFlag()} />
      </Wrapper>
    );
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "/flags/550e8400-e29b-41d4-a716-446655440000");
  });

  it("shows clean opinion text when quoted_language is null", () => {
    render(
      <Wrapper>
        <FlagCard flag={makeFlag({ quoted_language: null })} />
      </Wrapper>
    );
    expect(
      screen.getByText("Auditor issued a clean unqualified opinion.")
    ).toBeInTheDocument();
  });

  it("truncates long quoted language to 240 characters", () => {
    const longQuote = "A".repeat(300);
    render(
      <Wrapper>
        <FlagCard flag={makeFlag({ quoted_language: longQuote })} />
      </Wrapper>
    );
    // Should truncate — the rendered text should contain an ellipsis
    const quoteEl = screen.getByText(/\u201c[A]+\u2026\u201d/);
    expect(quoteEl).toBeInTheDocument();
  });
});
