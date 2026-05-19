import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { SubscribeForm } from "@/components/subscribe/SubscribeForm";

function mockFetch(data: unknown, ok = true, status = 200) {
  return vi.fn().mockResolvedValue({
    ok,
    status,
    json: async () => data,
  } as Response);
}

afterEach(() => {
  vi.unstubAllGlobals();
});

function fillEmail(value: string) {
  fireEvent.change(screen.getByLabelText(/email address/i), { target: { value } });
}

function clickSubmit() {
  fireEvent.click(screen.getByRole("button", { name: /^subscribe$/i }));
}

describe("SubscribeForm", () => {
  it("renders email input and subscribe button", () => {
    render(<SubscribeForm />);
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^subscribe$/i })).toBeInTheDocument();
  });

  it("validates email format and shows error for invalid email", async () => {
    render(<SubscribeForm />);

    fillEmail("not-an-email");
    clickSubmit();

    await waitFor(() => {
      expect(screen.getByText(/valid email/i)).toBeInTheDocument();
    });
  });

  it("disables button while submitting", async () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));

    render(<SubscribeForm />);

    fillEmail("test@example.com");
    clickSubmit();

    await waitFor(() => {
      expect(screen.getByRole("button")).toBeDisabled();
    });
  });

  it("shows loading text while submitting", async () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));

    render(<SubscribeForm />);

    fillEmail("test@example.com");
    clickSubmit();

    await waitFor(() => {
      expect(screen.getByRole("button")).toHaveTextContent(/subscribing/i);
    });
  });

  it("shows success message after successful subscribe", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({ ok: true, message: "Subscribed", already_subscribed: false })
    );

    render(<SubscribeForm />);

    fillEmail("test@example.com");
    clickSubmit();

    await waitFor(() => {
      expect(screen.getByText(/subscribed/i)).toBeInTheDocument();
      expect(screen.getByText(/check your inbox/i)).toBeInTheDocument();
    });
  });

  it("shows already-subscribed message when already_subscribed=true", async () => {
    vi.stubGlobal(
      "fetch",
      mockFetch({ ok: true, message: "Already subscribed", already_subscribed: true })
    );

    render(<SubscribeForm />);

    fillEmail("existing@example.com");
    clickSubmit();

    await waitFor(() => {
      expect(screen.getByText(/already subscribed/i)).toBeInTheDocument();
      expect(screen.getByText(/see you monday/i)).toBeInTheDocument();
    });
  });

  it("shows error message on API failure", async () => {
    vi.stubGlobal("fetch", mockFetch({}, false, 500));

    render(<SubscribeForm />);

    fillEmail("test@example.com");
    clickSubmit();

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
      expect(screen.getByText(/couldn.*t subscribe/i)).toBeInTheDocument();
    });
  });

  it("shows rate limit message on 429", async () => {
    // 429 throws before json() — mock fetch to reject with the rate-limit error
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 429,
        json: async () => ({}),
      })
    );

    render(<SubscribeForm />);

    fillEmail("test@example.com");
    clickSubmit();

    await waitFor(() => {
      expect(screen.getByText(/too many requests/i)).toBeInTheDocument();
    });
  });
});
