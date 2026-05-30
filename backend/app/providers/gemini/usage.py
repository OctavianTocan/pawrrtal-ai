"""Gemini usage / cost helpers.

Split out of ``gemini_provider`` to keep that module under the
project's 500-line file budget. The Gemini API doesn't ship a
server-reported USD figure, so each request's ``usage_metadata`` is
folded into a :class:`GeminiUsageAccumulator` whose totals
:class:`~.gemini_provider.GeminiLLM` reads after the agent loop
finishes — we then compute cost from the catalog's per-mtok rates
via :func:`app.governance.cost_tracker.compute_cost_usd`.

Mirrors ``_xai_stream.UsageAccumulator`` so the chat aggregator sees
the same ``StreamEvent(type="usage")`` shape from every provider.
"""

from __future__ import annotations

from typing import Any

from app.providers.catalog import MODEL_CATALOG, ModelEntry
from app.providers.model_id import Host


class GeminiUsageAccumulator:
    """Per-request usage totals summed across every StreamFn invocation.

    Gemini bills thinking tokens against ``maxOutputTokens`` and reports
    them under ``usage_metadata.thoughts_token_count`` (separate from
    ``candidates_token_count`` which is visible output only). We bill
    both as output tokens to match Gemini's pricing model — see
    https://ai.google.dev/gemini-api/docs/thinking ("Pricing & Token
    Counting").

    Mutable on purpose: the StreamFn closure owns one and writes into
    it from inside the stream; the surrounding ``GeminiLLM.stream``
    reads the totals after :func:`agent_loop` returns and emits the
    terminal ``StreamEvent(type="usage")``.
    """

    __slots__ = ("input_tokens", "output_tokens", "saw_any", "thoughts_tokens")

    def __init__(self) -> None:
        self.input_tokens: int = 0
        self.output_tokens: int = 0
        self.thoughts_tokens: int = 0
        self.saw_any: bool = False

    def absorb_request(
        self,
        *,
        prompt_tokens: int,
        candidates_tokens: int,
        thoughts_tokens: int,
    ) -> None:
        """Fold one request's terminal usage into the running totals.

        Each StreamFn invocation is one request (one LLM → tool →
        LLM round-trip). Gemini emits cumulative counts on the
        terminal chunk of every request, so callers pass that final
        snapshot here and we sum across requests.
        """
        if prompt_tokens == 0 and candidates_tokens == 0 and thoughts_tokens == 0:
            return
        self.saw_any = True
        self.input_tokens += prompt_tokens
        self.output_tokens += candidates_tokens + thoughts_tokens
        self.thoughts_tokens += thoughts_tokens


def coerce_int(value: Any) -> int:
    """Read a token count off Gemini's ``usage_metadata`` blob.

    Public (no leading underscore) because two modules use it — the
    Gemini StreamFn and ``GeminiLLM.stream`` — and we want a single
    parsing rule for the SDK's loosely-typed counts.
    """
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def absorb_request_usage(
    sink: GeminiUsageAccumulator | None,
    usage_metadata: Any,
) -> None:
    """Fold ``usage_metadata`` from a finished Gemini request into ``sink``.

    Splitting this out keeps ``make_gemini_stream_fn`` under the
    project's cyclomatic-complexity budget. Each StreamFn invocation
    is one Gemini request, so the caller passes the last (cumulative)
    ``usage_metadata`` it saw during the chunk loop. No-op when
    either argument is missing.
    """
    if sink is None or usage_metadata is None:
        return
    sink.absorb_request(
        prompt_tokens=coerce_int(getattr(usage_metadata, "prompt_token_count", None)),
        candidates_tokens=coerce_int(getattr(usage_metadata, "candidates_token_count", None)),
        thoughts_tokens=coerce_int(getattr(usage_metadata, "thoughts_token_count", None)),
    )


def gemini_catalog_entry(model_id: str) -> ModelEntry | None:
    """Look up the catalog entry for a Gemini model by bare model slug.

    ``GeminiLLM`` is constructed with the bare model name
    (e.g. ``"gemini-3.5-flash"``) rather than the full
    ``host:vendor/model`` wire form, so we filter on
    ``host == Host.google_ai`` to disambiguate against any future
    overlap.
    """
    for entry in MODEL_CATALOG:
        if entry.host is Host.google_ai and entry.model == model_id:
            return entry
    return None
