# Grilling the `dry-python/returns` adoption recommendation

Date: 2026-05-28
Spec type: brainstorming output (decision spec, not implementation spec)
Source recommendation: `docs/superpowers/plans/2026-05-28-paw-cli-v3-brainstorm.md` Thread 1
Source skill: `.claude/skills/returns-for-pawrrtal/SKILL.md`
Candidate pilot bean: `pawrrtal-0zne`

The session's existing recommendation: **don't blanket-adopt; pilot on the provider seam for 4 weeks**. The user asked: grill this. What would CHANGE the verdict? What costs are underestimated? Is there a smaller experiment that proves or disproves fit first?

This spec is the grilling output. It does NOT trigger writing-plans — the verdict at the bottom is "run a 1-week reading-glasses experiment before the 4-week provider-seam pilot."

---

## 1 — Steel-manning the existing recommendation (what it gets right)

- **Correctly identifies the textbook fit.** The provider seam genuinely is the place railway-oriented error handling earns its keep: 8 callees, 1 caller, closed failure-mode set, declarative `failover`/`retry` composition.
- **Correctly rejects blanket adoption.** FastAPI canon is exceptions; Pydantic / SQLAlchemy don't compose with containers cleanly; agent-trained idiom is `try/except`. All real.
- **Correctly proposes scoped mypy plugin** rather than global. The plugin's strictness flags would fire on 200+ files unnecessarily.
- **Correctly proposes a time-bounded trial.** 4 weeks is enough to feel the friction; not so much it becomes irreversible.

The recommendation is not wrong. The question is whether it's the cheapest experiment that produces a real signal.

---

## 2 — Costs the existing analysis is underestimating

### 2.1 Vendored type stubs / SDK signatures

Every provider SDK (anthropic, openai, google.genai, codex, xai, opencode-go, gemini, agy_cli) returns its own typed `AsyncIterator[Chunk]`. Wrapping those in `FutureResult[AsyncIterator[Chunk], ProviderError]` means mypy has to track the inner generic through the container. The existing analysis assumes this is free; in practice mypy ≥1.10 has known issues with `returns`' HKT (higher-kinded types) emulation around `AsyncIterator` (see returns issues #1574, #1684). **Probability of friction: high.** Cost: 2-3 days of stub workarounds the analysis didn't budget.

### 2.2 Stack traces

Today, when `anthropic.RateLimitError` propagates, the stack trace surfaces in Sentry / logger.exception with the original SDK frames intact. With `FutureResult`'s `.map_failure(_classify_anthropic_error)`, the original exception is captured but the stack-trace topology changes — the classifier becomes the "raise site." Debuggability degrades; on-call sees `_classify_anthropic_error` at the top of the stack, not the SDK call. **Cost: subtle but real.** Mitigation: preserve `__cause__` chain manually. The analysis doesn't mention this.

### 2.3 The pilot is not actually 4 weeks — it's 4 weeks plus a rollback window

The "4 weeks, then evaluate" framing implies the rollback is cheap. It isn't. After 4 weeks of provider-seam migration:
- Provider error types are typed; the chat router now pattern-matches on `Result.failure()`
- Other code that touches the chat router was modified to consume the new shape
- Reverting requires un-modifying the chat router too, plus any tests that assert on the new pattern-match shape

The real commitment is **4 weeks of migration + ~1 week of revert window + ~1 week of "we kept some of it but not all"**. Total: 6 weeks of mostly-engineering-time-not-feature-time.

### 2.4 Agent friction is not a one-time cost

The analysis frames "agents need re-training" as a startup cost. In practice it's a **per-PR cost**: every new agent session reads `try/except` idiomatic Python first and produces wrong `FutureResult` chains until it reads the project skill. Even with the skill in place, agents drift. We just landed 15 commits where every agent produced idiomatic Python first try; introducing `FutureResult` adds a re-correction step to every provider-touching session.

### 2.5 Code review velocity

The pilot will require explicit "did this `bind` chain do what I think?" review for every PR in the migrated area. The other reviewers in this session (loop-review, pr-review-toolkit, codex) all use idiomatic Python patterns as their reference. They will flag `FutureResult` chains as questionable until *they* learn the idiom — and they don't persist learning across reviews.

### 2.6 The "many callees, one caller" framing has an asymmetry

Providers funnel into the chat router. But the chat router *also* calls other things: cost ledger writes, audit events, channel delivery, scheduled jobs. If we migrate the provider seam, the chat router becomes the boundary where `FutureResult` is unwrapped. Every non-provider call site inside the router has to bridge the container back to exceptions. The seam stops being clean.

---

## 3 — What would CHANGE the verdict

| Change | New verdict |
|---|---|
| We grow to 15+ providers (currently 8) | Pilot is more clearly worth it — the railway pattern's leverage scales with callee count |
| The team starts shipping a **second** product that shares the provider seam | Provider-seam library extraction becomes the real reason; `returns` is the right hosting container for that library |
| The provider-seam refactor was needed for another reason (e.g. unified streaming protocol) | Bundle the `returns` adoption into that work; otherwise the migration cost stands alone |
| We hire a Python eng with strong railway-oriented experience | Lower agent friction (Section 2.4 / 2.5) — the human reviewer carries the idiom forward |
| A mypy 1.10+ blocker bug lands upstream in `returns` for AsyncIterator generics | Postpone indefinitely; the pilot would burn on stubs, not on producing a real signal |
| Our exception-based error handling produces an incident traceable to "we missed a branch" | The pilot becomes urgent — "we need this for safety, not ergonomics" reframes the cost |

None of these are true today. The least-far away is "incident traceable to missed branch" — which is exactly the kind of thing we should pre-emptively avoid, but not at the cost of 6 weeks of engineer-time without a concrete near-term incident vector.

---

## 4 — Pilot scope critique

The existing recommendation: pilot on `backend/app/core/providers/*`. Three alternatives worth considering:

### 4A — `crud/*` instead of providers

Lower blast radius. `crud/conversation.py`, `crud/message.py`, `crud/workspace.py` — every read returns `Optional[Row]` today. Switching to `Maybe[Row]` is the simplest possible `returns` application. Failure mode is "no row" — already typed as `None`. Migration is mechanical.

**Pro:** Smallest possible experiment, fastest signal, doesn't touch the chat-router boundary.
**Con:** Doesn't exercise the railway pattern's main strength (chained error propagation). The signal is narrow — "do `Maybe[T]` containers feel right?" — and tells us little about whether `FutureResult` would work at the provider seam.

### 4B — Single MCP tool call

MCP tool calls are: one HTTP request, returns either a tool result or one of N typed errors (timeout, auth, malformed response, server-side error). Textbook `IOResult[ToolOutput, McpError]` shape. Currently has broad `except Exception` (loop-review flagged this).

**Pro:** Bounded surface (one function), typed failure shape exists naturally, replaces an actual smell.
**Con:** Even smaller than crud — one function. The signal is whether the container *feels right at a single call site*, which is a narrow signal.

### 4C — Provider seam (current recommendation)

**Pro:** Highest leverage if it works.
**Con:** Highest cost if it doesn't.

### 4D — The actual proposal: reading-glasses experiment FIRST, then 4B, then 4A, then 4C

Run a 1-week, **non-code** experiment before any of the above. **More on this in section 5.**

---

## 5 — The smaller-blast-radius experiment

### Phase 0 — Reading-glasses experiment (1 week, ~4 hours of effort)

**Don't write `returns` code yet.** Instead:

1. Add a code-review checklist item: "could this be a `Result`?" When reviewing a provider PR, the reviewer (human or agent) annotates the diff with where a container would have changed the shape — what `try/except` blocks would have collapsed, what error union would have been typed.
2. Do this for 2-3 weeks of normal provider work.
3. Re-read the annotations.

**Signal:** Did the annotations point at consistent wins (same `Result[Stream, ProviderError]` shape 5 times)? Or was every annotation a different container? If the former, the container is real; if the latter, the railway pattern wouldn't have helped much.

This produces a written signal without writing any `returns` code. Cost: a handful of comments per PR.

### Phase 1 — Single MCP tool call (Option 4B above), 3 days

If Phase 0 surfaces a consistent win:
- Pick `backend/app/core/tools/external_mcp.py`'s outermost call.
- Migrate it to return `IOResult[ToolOutput, McpError]`.
- Keep the call site exception-bridged (the caller can still `except` to maintain compat).
- Re-do the reading-glasses on the migrated code for 1 week. Does it feel cleaner? Does anyone trip on it?

### Phase 2 — `crud/*` (Option 4A), 1 week

If Phase 1 was net-positive:
- Migrate `crud/conversation.get_conversation` and `crud/message.get_message_by_id` to return `Maybe[Row]`.
- Two callsites. Watch the diff land in code review.
- Decide based on review velocity, agent-produced bugs in the migrated area, and whether the team is asking for more or asking to revert.

### Phase 3 — Provider seam (Option 4C), 4 weeks

Only if Phases 0–2 all signal positive. By then, the cost-benefit is much more legible — Phases 0–2 will have produced concrete data points the original 4-week pilot would have invented after the fact.

---

## 6 — Final verdict

**Recommendation: phased experiment (Section 5), starting with the reading-glasses (Phase 0).**

**Do NOT start `pawrrtal-0zne` (the provider-seam pilot) yet.** Refile / re-scope it as Phase 3, blocked on Phase 0–2 completion.

**File two new beans:**

- *Phase 0 reading-glasses experiment* (1 week, ~4 hours): annotate provider/CRUD/MCP PRs with "where would a Result help?"
- *Phase 1 MCP single-call pilot* (3 days): migrate one MCP tool call to `IOResult` after Phase 0 produces a signal

**Decision rule for proceeding past each phase:**
- Phase 0 → Phase 1 only if reviewer annotations cluster around a consistent container shape across 3+ PRs.
- Phase 1 → Phase 2 only if the migrated MCP call site shipped without bugs, review velocity didn't drop, and at least one team member says "I want this more places."
- Phase 2 → Phase 3 only if the `Maybe[Row]` CRUD migration revealed clear wins that exceptions wouldn't have caught.

**What this changes vs the existing recommendation:**

- Total cost in the worst case (we never adopt): ~4 hours of reading-glasses, no code.
- Total cost in the best case (we adopt at the provider seam): same 6 weeks, but with 3 phases of accumulated evidence that justifies it.
- Total cost in the realistic case (we adopt at crud/* but not providers): ~1 week, with a real artifact (`Maybe[Row]` everywhere in crud) and no chat-router upheaval.

The existing recommendation is good. The phased experiment is **strictly cheaper** in the bad cases (we don't adopt) and **equally fast** in the good case (we adopt at providers).

---

## 7 — Action items

- [ ] Re-prioritise `pawrrtal-0zne` from "deferred" to "blocked-by Phase 0/1/2 evidence"
- [ ] File bean: *Phase 0: reading-glasses experiment* (priority: low, 1 week)
- [ ] File bean: *Phase 1: MCP single-call pilot* (priority: deferred, blocked-by Phase 0)
- [ ] File bean: *Phase 2: crud Maybe[Row] pilot* (priority: deferred, blocked-by Phase 1)
- [ ] Update `.claude/skills/returns-for-pawrrtal/SKILL.md` Section "Migration recipe (when pilot starts)" — re-frame as "Phase 3 recipe" and document Phases 0–2 first.

---

## 8 — Open questions for the user

1. Do you accept the phased proposal in Section 5, or do you want to commit straight to the provider-seam 4-week pilot per the original recommendation?
2. If Phase 0 produces a strongly positive signal, do you want to skip Phase 1 (MCP) and go straight to Phase 2 (`crud/*`)? Phase 1's signal is narrow; Phase 2's signal is broader.
3. Does the team have any planned provider-seam refactor (unified streaming protocol, retry policy harmonisation) in the next 6 weeks? If yes, bundle the `returns` pilot into that work; if no, keep them separate.
