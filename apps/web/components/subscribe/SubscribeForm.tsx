"use client";

import { useState } from "react";
import { subscribe } from "@/lib/api";

type FormState = "idle" | "loading" | "success" | "already_subscribed" | "error" | "rate_limited";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function SubscribeForm() {
  const [email, setEmail] = useState("");
  const [state, setState] = useState<FormState>("idle");
  const [errorMessage, setErrorMessage] = useState("");

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!EMAIL_RE.test(email)) {
      setState("error");
      setErrorMessage("Please enter a valid email address.");
      return;
    }

    setState("loading");
    setErrorMessage("");

    try {
      const res = await subscribe(email);
      if (res.already_subscribed) {
        setState("already_subscribed");
      } else {
        setState("success");
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "";
      if (msg.includes("Too many requests") || msg.includes("429")) {
        setState("rate_limited");
        setErrorMessage("Too many requests. Please try again in a few minutes.");
      } else {
        setState("error");
        setErrorMessage("Couldn\u2019t subscribe. Please try again.");
      }
    }
  }

  if (state === "success") {
    return (
      <div
        className="flex items-center gap-2 rounded-md border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700"
        role="status"
      >
        <span aria-hidden="true">&#10003;</span>
        <span>
          <strong>Subscribed.</strong> Check your inbox to confirm.
        </span>
      </div>
    );
  }

  if (state === "already_subscribed") {
    return (
      <div
        className="flex items-center gap-2 rounded-md border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700"
        role="status"
      >
        <span aria-hidden="true">&#10003;</span>
        <span>You&rsquo;re already subscribed. We&rsquo;ll see you Monday.</span>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} noValidate>
      <div className="flex flex-col gap-3 sm:flex-row sm:justify-center">
        <label htmlFor="subscribe-email" className="sr-only">
          Email address
        </label>
        <input
          id="subscribe-email"
          type="email"
          value={email}
          onChange={(e) => {
            setEmail(e.target.value);
            if (state === "error" || state === "rate_limited") setState("idle");
          }}
          placeholder="Email address"
          required
          disabled={state === "loading"}
          className="h-12 rounded-md border border-slate-300 bg-white px-4 text-sm text-slate-900 placeholder:text-slate-400 focus:border-slate-500 focus:outline-none focus:ring-1 focus:ring-slate-500 disabled:opacity-50 sm:w-64"
          aria-describedby={
            state === "error" || state === "rate_limited" ? "subscribe-error" : undefined
          }
        />
        <button
          type="submit"
          disabled={state === "loading"}
          className="inline-flex h-12 min-w-[44px] items-center justify-center rounded-md bg-slate-900 px-6 text-sm font-medium text-white transition-colors hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-900 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {state === "loading" ? "Subscribing\u2026" : "Subscribe"}
        </button>
      </div>

      {(state === "error" || state === "rate_limited") && (
        <p id="subscribe-error" className="mt-2 text-center text-sm text-red-600" role="alert">
          {errorMessage}
        </p>
      )}
    </form>
  );
}
