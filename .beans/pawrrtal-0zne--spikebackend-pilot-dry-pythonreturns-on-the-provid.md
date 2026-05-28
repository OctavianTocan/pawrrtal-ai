---
# pawrrtal-0zne
title: 'spike(backend): pilot dry-python/returns on the provider seam'
status: completed
type: task
priority: deferred
created_at: 2026-05-28T09:14:50Z
updated_at: 2026-05-28T10:46:23Z
blocked_by:
    - pawrrtal-ca8v
---

From paw v3 brainstorm Thread 1. NOT a blanket adoption — pilot on backend/app/core/providers/ only, where 8 providers funnel into a single chat-router caller (textbook FutureResult fit). 4-week trial; re-evaluate. Do NOT migrate API routes / pydantic-adjacent code / scheduler. Owner + start date TBD by user. See brainstorm doc for full rationale + costs.



## Updated scope (2026-05-28 grilling)

This is now PHASE 3 of a phased experiment. Do NOT start until Phases 0/1/2 (pawrrtal-67rg / pawrrtal-3lnz / pawrrtal-ca8v) have produced positive signals. See docs/superpowers/specs/2026-05-28-returns-adoption-grilling.md for the full rationale.

## Summary of Changes (Phase 3 — implementation)

**Chose Option B** from the bean prompt: wrap the *connection / setup* phase in `FutureResult`, leave the streamed-iterator phase exception-driven. Rationale — `FutureResult` is ergonomic for "could we open the call?" (auth, rate-limit, unsupported param, timeout-on-connect) but trying to push mid-stream errors into the container adds ceremony for no gain. The existing `make_litellm_stream_fn` already handles mid-stream `LiteLLMAPIError` by emitting an in-band `error` StreamEvent; that contract is untouched.

**Shipped**

- `backend/app/core/providers/_errors.py` (new) — closed `ProviderError` discriminated union (frozen `@dataclass(slots=True)` variants with `kind: Literal[...]` tags). Shared module so future provider migrations import the same types.
  - `ProviderAuthError(kind="auth")`
  - `ProviderRateLimitError(kind="rate_limit", retry_after: float | None = None)`
  - `ProviderUnsupportedParamError(kind="unsupported_param", param, model)`
  - `ProviderTimeoutError(kind="timeout")`
  - `ProviderUnknownError(kind="unknown")` — fallback bucket
- `backend/app/core/providers/litellm_provider.py`
  - Added `open_litellm_stream(vendor, model, workspace_root, *, messages, reasoning_effort) -> FutureResult[AsyncIterator[Any], ProviderError]`.
  - Added `_classify_litellm_exception(exc, *, model) -> ProviderError` — maps SDK exception types onto the closed `ProviderError` set. Order matters (subclass narrowest-first): `LiteLLMAuthenticationError → ProviderAuthError`, `LiteLLMRateLimitError → ProviderRateLimitError`, `LiteLLMUnsupportedParamsError → ProviderUnsupportedParamError`, `LiteLLMTimeout → ProviderTimeoutError`, all others (incl. `LiteLLMAPIError`) → `ProviderUnknownError`.
  - Missing API key surfaces through the same path: synthesises a `LiteLLMAuthenticationError` so callers can pattern-match a single `ProviderAuthError` arm regardless of whether the upstream or our key-resolution rejected.
- `backend/tests/test_litellm_provider.py` — 15 new tests covering the classifier (5 cases) and `open_litellm_stream` (5 cases incl. happy path + 4 failure mappings + missing-key).

**Compat preserved.** Existing `make_litellm_stream_fn`, `LiteLLMLLM.stream`, and every caller (factory + chat router) are untouched. The chat router did NOT need any change — the new surface is strictly additive, and nothing currently consumes it. When the next migration step lands (chat-router consumer or sibling provider), it imports `open_litellm_stream` + matches on `ProviderError` variants.

**Verification**

- `uv run ruff check` / `ruff format --check` clean on the touched files.
- `uv run mypy app/core/providers/litellm_provider.py app/core/providers/_errors.py` clean (returns mypy plugin is already enabled globally per `backend/pyproject.toml`).
- `pytest -k litellm`: 26 passed, 1 skipped (15 new + 11 pre-existing).
- Full backend suite (excluding Phase 1 sibling-agent in-progress `tests/test_external_mcp_tools.py`): 1923 passed, 1 skipped, 3 xfailed, 7 xpassed.



## Phase 0 verdict on broader provider expansion (2026-05-28)

The Phase 0 reading-glasses corpus (`docs/superpowers/specs/2026-05-28-returns-phase-0-corpus.md`) walked the 6 un-migrated providers (claude, gemini, gemini_cli, xai, opencode_go, openai_codex). Verdict: **REJECT broader provider expansion.** 6 of 7 use blanket `except Exception` and would only produce the `Result[T, Exception]` anti-pattern the returns-for-pawrrtal skill bans. Only Claude has the multi-branch typed-error shape. Future expansion of returns into providers is gated on those providers first growing typed failure modes — orthogonal to this bean's scope. The litellm pilot shipped here stands as the high-water mark for the provider seam unless that landscape changes.
