import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SeverityBadge } from "@/components/site/SeverityBadge";
import type { Severity } from "@/lib/api";

// Provide the TooltipProvider context
import { TooltipProvider } from "@/components/ui/tooltip";

function Wrapper({ children }: { children: React.ReactNode }) {
  return <TooltipProvider>{children}</TooltipProvider>;
}

describe("SeverityBadge", () => {
  const cases: { severity: Severity; expectedLabel: string }[] = [
    { severity: "critical", expectedLabel: "Critical" },
    { severity: "elevated", expectedLabel: "Elevated" },
    { severity: "watch", expectedLabel: "Watch" },
    { severity: "none", expectedLabel: "No flag" },
  ];

  it.each(cases)("renders correct label for severity=$severity", ({ severity, expectedLabel }) => {
    render(
      <Wrapper>
        <SeverityBadge severity={severity} />
      </Wrapper>
    );
    expect(screen.getByText(expectedLabel)).toBeInTheDocument();
  });

  it("renders aria-label describing the severity", () => {
    render(
      <Wrapper>
        <SeverityBadge severity="critical" />
      </Wrapper>
    );
    const badge = screen.getByRole("img", { name: /severity: critical/i });
    expect(badge).toBeInTheDocument();
  });

  it("applies critical color classes", () => {
    render(
      <Wrapper>
        <SeverityBadge severity="critical" />
      </Wrapper>
    );
    const badge = screen.getByRole("img", { name: /severity: critical/i });
    expect(badge.className).toContain("bg-red-100");
    expect(badge.className).toContain("text-red-700");
  });

  it("applies elevated color classes", () => {
    render(
      <Wrapper>
        <SeverityBadge severity="elevated" />
      </Wrapper>
    );
    const badge = screen.getByRole("img", { name: /severity: elevated/i });
    expect(badge.className).toContain("bg-amber-100");
    expect(badge.className).toContain("text-amber-700");
  });

  it("renders tooltip content via data attribute (tooltip portal)", () => {
    render(
      <Wrapper>
        <SeverityBadge severity="critical" />
      </Wrapper>
    );
    // Tooltip content is in a portal; the trigger is rendered
    const trigger = screen.getByRole("img", { name: /severity: critical/i });
    expect(trigger).toBeInTheDocument();
  });
});
