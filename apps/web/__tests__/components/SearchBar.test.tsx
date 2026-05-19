import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { SearchBar } from "@/components/search/SearchBar";
import { TooltipProvider } from "@/components/ui/tooltip";

// Top-level mock — hoisted before any imports by Vitest
const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush }),
}));

const MOCK_RESULTS = [
  {
    cik: "0001008654",
    ticker: "TUP",
    name: "TUPPERWARE BRANDS CORPORATION",
    display_name: "Tupperware Brands Corporation",
    match_type: "ticker_exact",
    has_critical_flag: true,
  },
];

function mockFetch(data: unknown, ok = true) {
  return vi.fn().mockResolvedValue({
    ok,
    status: ok ? 200 : 500,
    json: async () => data,
  } as Response);
}

beforeEach(() => {
  mockPush.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function Wrapper({ children }: { children: React.ReactNode }) {
  return <TooltipProvider>{children}</TooltipProvider>;
}

function getInput() {
  return screen.getByLabelText("Search companies");
}

describe("SearchBar", () => {
  it("renders the input field", () => {
    render(
      <Wrapper>
        <SearchBar />
      </Wrapper>
    );
    expect(getInput()).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/search company or ticker/i)).toBeInTheDocument();
  });

  it("does not fire a fetch for a single-character query", async () => {
    const spy = mockFetch({ results: MOCK_RESULTS });
    vi.stubGlobal("fetch", spy);

    render(
      <Wrapper>
        <SearchBar />
      </Wrapper>
    );

    fireEvent.change(getInput(), { target: { value: "t" } });

    // Wait longer than debounce to confirm fetch was never called
    await new Promise((r) => setTimeout(r, 300));
    expect(spy).not.toHaveBeenCalled();
  });

  it("shows results after typing 2+ characters", async () => {
    const spy = mockFetch({ results: MOCK_RESULTS, query: "tu", total_returned: 1 });
    vi.stubGlobal("fetch", spy);

    render(
      <Wrapper>
        <SearchBar />
      </Wrapper>
    );

    fireEvent.change(getInput(), { target: { value: "tu" } });

    await waitFor(
      () => expect(screen.getByText("Tupperware Brands Corporation")).toBeInTheDocument(),
      { timeout: 1000 }
    );
  });

  it("shows 'No matches found' when API returns empty results", async () => {
    const spy = mockFetch({ results: [], query: "xyz", total_returned: 0 });
    vi.stubGlobal("fetch", spy);

    render(
      <Wrapper>
        <SearchBar />
      </Wrapper>
    );

    fireEvent.change(getInput(), { target: { value: "xy" } });

    await waitFor(() => expect(screen.getByText(/no matches found/i)).toBeInTheDocument(), {
      timeout: 1000,
    });
  });

  it("navigates to /companies/{cik} on result click", async () => {
    const spy = mockFetch({ results: MOCK_RESULTS, query: "tu", total_returned: 1 });
    vi.stubGlobal("fetch", spy);

    render(
      <Wrapper>
        <SearchBar />
      </Wrapper>
    );

    fireEvent.change(getInput(), { target: { value: "tu" } });
    await waitFor(() => screen.getByText("Tupperware Brands Corporation"), { timeout: 1000 });

    fireEvent.click(screen.getByText("Tupperware Brands Corporation"));

    expect(mockPush).toHaveBeenCalledWith("/companies/0001008654");
    expect(getInput()).toHaveValue("");
  });
});
