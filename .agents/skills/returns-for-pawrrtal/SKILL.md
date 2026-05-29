---
name: returns-for-pawrrtal
description: How to use dry-python/returns containers (Maybe, Result, IOResult, FutureResult) effectively inside the pawrrtal backend. Use when adding railway-style error handling, replacing Optional + try/except chains, or evaluating whether to wrap a new module in Result-style containers. Trigger keywords - returns library, Maybe, Result, IOResult, FutureResult, railway-oriented, dry-python.
paths:
  - "backend/app/providers/**/*.py"
  - "backend/app/**/crud.py"
  - "backend/app/lcm/**/*.py"
  - "backend/app/channels/telegram/finalize.py"
---

# returns for pawrrtal

`dry-python/returns` provides typed containers (`Maybe`, `Result`, `IO`, `IOResult`, `Future`, `FutureResult`) that replace `None`-and-exception chains with railway-oriented composition. This skill exists because the team is **considering**, not committed to, adopting it. See `docs/superpowers/plans/2026-05-28-paw-cli-v3-brainstorm.md` Thread 1 for the analysis that led here.

## TL;DR posture

**Don't blanket-adopt.** Pilot it on **one surgical surface** where many callees funnel into a single caller, then re-evaluate after 4 weeks. That surface is the **provider seam** (`backend/app/providers/*`). A second candidate is domain CRUD modules such as **`backend/app/conversations/crud.py`** (replace `Optional[Row]` with `Maybe[Row]`).

Everything else — FastAPI routes, pydantic-adjacent code, schedulers, settings, voice, transcribers — keeps the existing exception idiom. The mypy plugin is global-only, so do **not** enable it unless the pilot explicitly accepts project-wide plugin behavior.

## The four containers we'd reach for

| Container | Replaces | When to use in pawrrtal |
|---|---|---|
| `Maybe[T]` | `Optional[T]` + `if x is not None` | CRUD reads that may return no row (`crud/conversation.get_conversation`) |
| `Result[T, E]` | "may raise" sync functions | Pure validation / parsing where the failure shape is known |
| `IOResult[T, E]` | sync I/O that may fail | Disk/file ops in workspace files, ledger writes |
| `FutureResult[T, E]` | `async def` with multiple failure modes | **Provider streams** — the textbook fit. Many callees, one chat-router caller |

`IO` and `Future` (without `Result`) are usually overkill for our code — we always care about the failure path.

## When the railway pattern is worth it

- **Many callees → one caller.** Providers (8) → chat router. One pattern, eight implementations, declarative composition (`failover`, `retry`, `map`, `bind`).
- **Failure types form a closed set.** `ProviderError = UnauthorizedError | RateLimitedError | TimeoutError | ContextWindowError`. If a new error type would be added more often than once a quarter, the container won't keep up.
- **The caller wants to react differently per error type.** `Result[Stream, ProviderError]` + pattern-matching on `failure()` is cleaner than 4 nested `except` blocks.
- **You'd otherwise write a manual error-discriminated union** in dict form. The container is just the typed version of what you'd build anyway.

## When NOT to use returns (90%+ of pawrrtal code)

- **FastAPI routes.** `HTTPException` is the documented contract. Wrapping returns containers and unwrapping at the route boundary adds ceremony.
- **Pydantic models / SQLAlchemy queries.** Container values fall out of mypy narrowing at the boundary. Adapter layer becomes a friction surface.
- **Single-step async functions.** `async def` + `try/except` is already ergonomic. `FutureResult` shines at 5+ steps.
- **Hot paths.** Every container is a heap allocation. The chat router emits thousands of `delta` events per turn; don't wrap each one.
- **Code that other agents will write or modify.** Agents trained on idiomatic Python produce `try/except`. Asking them to write `IOResult` chains creates a friction surface every code-review cycle.

## Canonical pawrrtal example (hypothetical, for the pilot)

Before (current):
```python
# backend/app/providers/Codex/provider.py
async def stream(self, request: ChatRequest) -> AsyncIterator[StreamEvent]:
    try:
        async for chunk in self._client.messages.stream(...):
            yield chunk
    except anthropic.AuthenticationError as e:
        raise ProviderAuthError(str(e)) from e
    except anthropic.RateLimitError as e:
        raise ProviderRateLimitError(str(e)) from e
    # ... and so on
```

After (with returns, pilot):
```python
# backend/app/providers/Codex/provider.py
async def stream(self, request: ChatRequest) -> FutureResult[AsyncIterator[StreamEvent], ProviderError]:
    return await (
        FutureResult.do(
            chunks async for chunks in self._connect(request)
        )
        .map_failure(_classify_anthropic_error)
    )

# backend/app/chat/router.py (caller orchestrates)
result = await provider.stream(request)
match result:
    case Success(stream):
        async for chunk in stream: ...
    case Failure(ProviderRateLimitError()):
        # fall back to a cheaper model
    case Failure(ProviderAuthError()):
        raise HTTPException(401, "...")
```

The point isn't that this is shorter (it isn't, much). The point is that the failure shape is **in the signature** — anyone calling `provider.stream()` cannot forget to handle `ProviderRateLimitError`.

## Decision rubric for "should I use a container here?"

Walk these in order. First "no" → don't use a container.

1. Does this function have multiple distinct, named failure modes the caller acts on differently?
2. Will at least 3 callers care about the failure-mode distinction?
3. Is this function part of a 3+ step chain where the same failure types propagate?
4. Would replacing this with a `Result` make the **caller** simpler (not just the callee)?

If you can't answer "yes" to all four, stick with `try/except`.

## The mypy plugin

`returns` ships a mypy plugin (`returns.contrib.mypy.returns_plugin`) that enforces container-aware type narrowing. Mypy plugins are **global-only**; `plugins` is not valid inside `[[tool.mypy.overrides]]`. Do not document or add a fake per-module plugin override.

```toml
[tool.mypy]
# Only add this after the pilot explicitly accepts global plugin cost.
plugins = ["returns.contrib.mypy.returns_plugin"]
```

Before that decision, run the pilot without the plugin or use a separate local-only mypy config file for experiments. Do not claim the plugin is scoped unless mypy adds per-module plugin support.

## Migration recipe (when pilot starts)

1. **Pin the version** in `backend/pyproject.toml` (`returns = "==0.23.0"` or whatever current at pilot time).
2. **Pick one provider** (start with `litellm_provider.py` — smallest, well-tested).
3. **Decide plugin posture**: no plugin for the first pass, or enable the returns plugin globally in a dedicated pilot commit.
4. **Convert `stream()` to return `FutureResult[Stream, ProviderError]`**.
5. **Add `_classify_*_error` helper** that maps SDK exceptions → typed errors.
6. **Update the chat-router call site** to pattern-match on `Result.failure()`.
7. **Run** `paw verify chat-roundtrip --model litellm:openai/gpt-4o-mini --json` to confirm behavior unchanged.
8. **Commit** as a single PR labeled `refactor(providers): pilot returns on litellm provider`.

After 4 weeks of living with one provider:
- If the team's PR review velocity didn't drop and bugs surfaced are real (not container ceremony), expand to the next provider.
- If review velocity dropped or agents started producing wrong `FutureResult` chains, revert and document why.

## Anti-patterns to flag in review

- **Returning `Result[T, Exception]`.** The whole point of `Result` is a typed failure. Bare `Exception` defeats it.
- **Long chains with `lambda` instead of helper functions.** If a `.map(lambda x: …)` chain is more than 3 deep, refactor each step to a named function for traceability.
- **Wrapping a synchronous function as `FutureResult`.** Use `Result` for sync; `FutureResult` adds an event-loop boundary you don't need.
- **`unwrap()` outside the route boundary.** Unwrapping mid-chain destroys the railway. The only place `unwrap()` is acceptable is the final translation to `HTTPException` / SSE event.
- **A new `Maybe[T]` that wraps a `Sequence[T]`.** Empty sequences already convey "nothing"; don't add another container.

## How to evaluate at the 4-week mark

Re-read this skill and answer:

- Did the pilot reduce backend bugs in the provider path? (Run `git log --oneline backend/app/providers/litellm_provider.py` and count fixes since pilot started vs the prior quarter.)
- Did PR reviews on the migrated file run faster or slower than the surrounding provider files?
- Did agents produce wrong `Result` chains? (Search the session memory for "wrap me in returns" / "what's the right `bind` here?" friction.)
- Would expanding to the next provider be additive complexity or duplicate ceremony?

If three of four answers favor returns → expand to one more provider. Otherwise, freeze the pilot and document the why.

## See also

- `docs/superpowers/plans/2026-05-28-paw-cli-v3-brainstorm.md` (Thread 1: full cost-benefit analysis)
- Bean `pawrrtal-0zne` — the pilot bean (deferred, awaits user green-light)
- Upstream docs: https://returns.readthedocs.io/en/latest/
- Cloned vendor source: `/tmp/Codex/research/returns/` (read-only research checkout)
