"""Instructor + Anthropic + Langfuse wrapper for auditor-report classification.

Design notes
------------
* Uses instructor.from_anthropic(AsyncAnthropic) so every call is awaitable.
* create_with_completion() returns (ClassifierResponse, raw_Message) so we can
  read token counts from the raw Message without a second API call.
* Langfuse v4 low-level API: start_as_current_observation() context manager for
  each generation, update_current_generation() to post token/cost metadata.
* If Langfuse is not configured the classifier still works — tracing is optional.
* total_cost_estimate accumulates across all calls on this instance.

Pricing constants (as of 2025-Q4, verify at https://www.anthropic.com/pricing):
    Haiku 4.5 :  $1.00 / M input tokens,   $5.00 / M output tokens
    Sonnet 4.5:  $3.00 / M input tokens,  $15.00 / M output tokens
"""

from __future__ import annotations

import logging
import time
from datetime import date

import anthropic
import instructor

from gct.classifier.prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from gct.classifier.schemas import ClassifierResponse

logger = logging.getLogger(__name__)

# ── Pricing (per-million tokens) ─────────────────────────────────────────────

_PRICING: dict[str, dict[str, float]] = {
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
    "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
}
_DEFAULT_PRICING = {"input": 1.00, "output": 5.00}  # safe fallback


def _compute_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    p = _PRICING.get(model, _DEFAULT_PRICING)
    return (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000


# ── Main client ──────────────────────────────────────────────────────────────


class ClaudeClassifier:
    """Reusable async client wrapping Claude + Instructor + Langfuse."""

    def __init__(
        self,
        anthropic_api_key: str,
        primary_model: str = "claude-haiku-4-5",
        fallback_model: str = "claude-sonnet-4-5",
        confidence_threshold: float = 0.7,
        max_retries: int = 3,
        langfuse_public_key: str | None = None,
        langfuse_secret_key: str | None = None,
        langfuse_host: str = "https://us.cloud.langfuse.com",
    ) -> None:
        self.primary_model = primary_model
        self.fallback_model = fallback_model
        self.confidence_threshold = confidence_threshold
        self.max_retries = max_retries
        self.total_cost_estimate: float = 0.0
        self._model_used: str = primary_model

        # Instructor-patched async Anthropic client
        self._async_anthropic = anthropic.AsyncAnthropic(api_key=anthropic_api_key)
        self._client = instructor.from_anthropic(self._async_anthropic)

        # Langfuse v4 (optional)
        self._lf = None
        if langfuse_public_key and langfuse_secret_key:
            try:
                from langfuse import Langfuse

                self._lf = Langfuse(
                    public_key=langfuse_public_key,
                    secret_key=langfuse_secret_key,
                    host=langfuse_host,
                )
                logger.info("Langfuse tracing enabled (host=%s)", langfuse_host)
            except Exception as exc:
                logger.warning("Langfuse init failed — tracing disabled: %s", exc)

    # ── Public interface ──────────────────────────────────────────────────────

    async def classify(
        self,
        report_text: str,
        company_name: str,
        filing_form_type: str,
        filing_date: date,
    ) -> tuple[ClassifierResponse, str | None]:
        """Classify a single auditor report.

        Returns
        -------
        (ClassifierResponse, trace_url)  — trace_url is None when Langfuse is off.

        Auto-escalates to fallback_model when primary reports
        classification_confidence < confidence_threshold.
        """
        messages = self._build_messages(report_text, company_name, filing_form_type, filing_date)
        trace_url: str | None = None

        if self._lf:
            # _AgnosticContextManager from langfuse v4 / OTel is synchronous even in async code
            with self._lf.start_as_current_observation(
                name="classify_auditor_report",
                as_type="span",
                input={"report_length": len(report_text), "company": company_name},
                metadata={"form_type": filing_form_type, "filing_date": str(filing_date)},
            ):
                response, cost = await self._run_with_escalation(messages)
                self._lf.update_current_span(
                    output={
                        "severity": response.severity,
                        "confidence": response.classification_confidence,
                        "model_used": self._model_used,
                    },
                )
                trace_id = self._lf.get_current_trace_id()
                trace_url = self._lf.get_trace_url(trace_id=trace_id)
            self._lf.flush()
        else:
            response, cost = await self._run_with_escalation(messages)

        self.total_cost_estimate += cost
        logger.info(
            "Classification complete — severity=%s conf=%.2f model=%s cost=$%.4f",
            response.severity,
            response.classification_confidence,
            self._model_used,
            cost,
        )
        return response, trace_url

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _run_with_escalation(
        self,
        messages: list[dict[str, str]],
    ) -> tuple[ClassifierResponse, float]:
        """Call primary model; escalate to fallback if confidence is low."""
        response, cost = await self._call_model(self.primary_model, messages, "primary_classify")
        self._model_used = self.primary_model

        if response.classification_confidence < self.confidence_threshold:
            logger.info(
                "Low confidence (%.2f < %.2f) — escalating to %s",
                response.classification_confidence,
                self.confidence_threshold,
                self.fallback_model,
            )
            fallback_response, fallback_cost = await self._call_model(
                self.fallback_model, messages, "fallback_classify"
            )
            self._model_used = self.fallback_model
            return fallback_response, cost + fallback_cost

        return response, cost

    async def _call_model(
        self,
        model: str,
        messages: list[dict[str, str]],
        call_name: str,
    ) -> tuple[ClassifierResponse, float]:
        """Make one Instructor call, log to Langfuse, return (response, cost)."""
        t0 = time.perf_counter()

        if self._lf:
            with self._lf.start_as_current_observation(
                name=call_name,
                as_type="generation",
                model=model,
                input=messages,
                model_parameters={"max_tokens": 1024, "temperature": 0.0},
            ):
                response, completion = await self._client.messages.create_with_completion(
                    model=model,
                    max_tokens=1024,
                    temperature=0.0,
                    system=SYSTEM_PROMPT,
                    messages=messages,
                    response_model=ClassifierResponse,
                    max_retries=self.max_retries,
                )
                input_tokens: int = completion.usage.input_tokens
                output_tokens: int = completion.usage.output_tokens
                cost = _compute_cost(model, input_tokens, output_tokens)
                self._lf.update_current_generation(
                    output=response.model_dump(),
                    usage_details={"input": input_tokens, "output": output_tokens},
                    cost_details={"total": cost},
                )
        else:
            response, completion = await self._client.messages.create_with_completion(
                model=model,
                max_tokens=1024,
                temperature=0.0,
                system=SYSTEM_PROMPT,
                messages=messages,
                response_model=ClassifierResponse,
                max_retries=self.max_retries,
            )
            input_tokens = completion.usage.input_tokens
            output_tokens = completion.usage.output_tokens
            cost = _compute_cost(model, input_tokens, output_tokens)

        elapsed = time.perf_counter() - t0
        logger.info(
            "[%s] in=%d out=%d cost=$%.4f latency=%.1fs severity=%s conf=%.2f",
            model,
            input_tokens,
            output_tokens,
            cost,
            elapsed,
            response.severity,
            response.classification_confidence,
        )
        return response, cost

    @staticmethod
    def _build_messages(
        report_text: str,
        company_name: str,
        filing_form_type: str,
        filing_date: date,
    ) -> list[dict[str, str]]:
        user_content = USER_PROMPT_TEMPLATE.format(
            company_name=company_name,
            filing_form_type=filing_form_type,
            filing_date=filing_date,
            report_text=report_text,
        )
        return [{"role": "user", "content": user_content}]

    def get_model_used(self) -> str:
        """Return the model that handled the most recent classification."""
        return self._model_used
