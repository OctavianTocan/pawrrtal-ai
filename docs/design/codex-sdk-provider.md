# Codex SDK Provider — Full Implementation Plan

**Status:** Approved plan (2026-05-26) — **Implementation complete (Phases 1–3)**  
**Related GitHub issue:** [#433](https://github.com/OctavianTocan/pawrrtal-ai/issues/433) — "Refactor: Agent Architecture Clarity + Sub-Agent Infrastructure" (references Codex's `Session` as architectural inspiration)  
**Primary authoritative sources:**
- https://github.com/openai/codex/tree/main/sdk/python (the real SDK source — must be followed exactly)
- https://developers.openai.com/codex/sdk#python-library

**Complementary internal reference:** `docs/design/codex-oauth-text-provider.md` (the earlier reverse-engineered Responses API work for images and planned text models).

---

## Context & Why This Work

Pawrrtal already has partial Codex integration:
- Image generation (`backend/app/core/tools/image_gen.py`) uses Codex OAuth tokens (from `OPENAI_CODEX_OAUTH_TOKEN` or `~/.codex/auth.json` written by the official `@openai/codex` CLI / OpenClaw). It calls the private `https://chatgpt.com/backend-api/codex/responses` endpoint.
- A detailed design doc (`docs/design/codex-oauth-text-provider.md`) exists for extending that same Responses API path to text models.

The official **Codex Python SDK** (`openai_codex` package) is a fundamentally different and superior surface:
- It controls the local Codex app-server over JSON-RPC.
- It gives first-class access to Codex threads (persistent, stateful agent sessions with their own models, tools, sandbox, approvals, memories, sub-agents, etc.).
- This is the supported, recommended way to programmatically drive Codex.

The existing reverse-engineered HTTP path is now considered **rudimentary**. The official SDK path is what we actually want.

**Hard user requirements captured in this plan:**
- This must be a **first-class provider** (not a sub-agent or side tool), named to match the real package (`openai_codex`).
- It must feel **butter smooth** and completely native in Pawrrtal (streaming, reasoning, tools, cost tracking, picker, etc.).
- Follow the official SDK at https://github.com/openai/codex/tree/main/sdk/python **exactly** ("whatever they say we should do" + "latest all the way").
- Codex "threads" must be understood from the actual source (research was required).
- The image generation capability that uses a Codex agent must be delivered as a **plugin** (exact structure and patterns as `plugins/active_recall/`, but **not** pre-turn-hook driven).
- LiteLLM's OpenAI routing must remain completely untouched.
- **Strict "commented implementation only" rule** — no live code changes. All intended production code must be written and then commented with clear markers so that a later mechanical activation PR can apply it safely.

---

## Core Implementation Discipline (Non-Negotiable)

You are **not making real changes to live code**.

- Every new file: write the complete, intended implementation, then comment the entire body (or large logical sections).
- Every edit to an existing file: leave the original code untouched. Immediately below or beside the change site, add a clearly marked block with the new version (or a "DELETE THIS BLOCK" marker).
- Use consistent markers:
  ```python
  # === CODEX-SDK-PLAN: START NEW ===
  # (the exact code that should exist after activation)
  # === CODEX-SDK-PLAN: END NEW ===
  ```
  or
  ```python
  # === CODEX-SDK-PLAN: DELETE ===
  # (the lines that should be removed)
  ```
- The delivered artifacts are a **living specification + commented implementation**. A later small PR can mechanically remove the markers.

This rule applies to code, tests, and documentation updates.

---

## Recommended Approach

Create a dedicated first-class provider package at:

`backend/app/core/providers/openai_codex/`

(following the multi-file package pattern established by `agy_cli/` and `gemini_cli/`).

The package name matches the real SDK (`openai_codex`).

Deliverables (all in commented form):

- `openai_codex/__init__.py`
- `openai_codex/auth.py` — unified, refresh-safe Codex OAuth resolution (shared with image generation)
- `openai_codex/provider.py` — the core `OpenAICodexProvider` (or `CodexLLM`) implementing the full streaming `AILLM` contract
- `openai_codex/events.py` — high-fidelity mapping from Codex notifications/turns to Pawrrtal `StreamEvent`s
- Catalog entries + `Host.openai_codex` registration (commented blocks in existing files)
- Factory wiring (commented blocks)
- Image generation via Codex agent, implemented as a plugin:
  - `backend/app/plugins/openai_codex_image_gen/` (exact layout and style of `active_recall`, but not hook-driven)
- Tests (commented)
- Documentation updates (commented blocks in README, design docs, new `docs/codex-sdk-provider.md`, etc.)

The image generation plugin is an explicit additional deliverable: it must use the new first-class provider to spin up a Codex-backed agent and instruct it to produce the image.

---

## File / Module Changes (Critical Paths)

All changes must be produced under the commented discipline described above.

**New files (fully commented after writing the intended code):**
- `backend/app/core/providers/openai_codex/__init__.py`
- `backend/app/core/providers/openai_codex/provider.py`
- `backend/app/core/providers/openai_codex/auth.py`
- `backend/app/core/providers/openai_codex/events.py`
- `backend/app/plugins/openai_codex_image_gen/__init__.py`
- `backend/app/plugins/openai_codex_image_gen/plugin.py`
- `backend/app/plugins/openai_codex_image_gen/codex_image_agent.py`
- `backend/tests/test_openai_codex_provider.py`
- Supporting docs (`docs/codex-sdk-provider.md`, package README, etc.)

**Updates via commented blocks only (original code left untouched):**
- `backend/app/core/providers/model_id.py` (new `Host.openai_codex`)
- `backend/app/core/providers/factory.py` (imports, `HOST_TO_PROVIDER`, auth keys, `host_authenticated`)
- `backend/app/core/providers/catalog/openai.py` (example entries for Codex SDK models)
- `docs/design/codex-oauth-text-provider.md` (SDK vs. Responses comparison + status note)
- Root `README.md` and developer setup docs (as needed)

---

## Verification Requirements

The primary deliverable is **not** working code on `main`. It is a set of PRs consisting almost entirely of commented specifications.

Before the plan is considered complete:
- All new and modified files contain the exact commented blocks with clear markers.
- Commented code must still be syntactically valid Python and pass basic compilation.
- `just check` / ruff / mypy must pass on the commented state where applicable.
- The image plugin must be fully specified in the active-recall plugin style.
- Documentation must clearly explain the "commented only → later activation" workflow.
- A tracking bean must exist that references this plan and the strict discipline.

Activation (removing the comment markers) is explicitly out of scope for this plan and will be a small, mechanical follow-up step.

---

## Risks & Mitigations

- SDK is still experimental → Pin to known-good commits in docs; keep the Responses path as fallback.
- Local source checkout friction → Excellent documentation + one-liner bootstrap notes.
- Single-use refresh tokens → Centralized locking (already designed in auth.py).
- Architecture drift → New `Host.openai_codex` fits cleanly in the existing provider model.

---

## Next Steps After Plan Approval (Historical)

1. Create tracking bean (done — `pawrrtal-ujo8`).
2. Produce all artifacts exclusively in commented form.
3. Pass gates on the commented state.
4. Land the commented PRs.
5. (Later, out of scope) Small mechanical activation PR.

---

This document is the canonical, complete record of the approved plan for the first-class Codex SDK integration in Pawrrtal.

**All execution work (scaffolding, provider, plugin, auth, events, registration points, tests, docs) must follow the rules and deliverables defined above.**

---

## Post-Implementation Status (2026)

Phases 1–3 have been executed:

- Full wiring (`Host.openai_codex`, factory, catalog, re-exports)
- SDK surface compatibility fixes against the vendored tree
- Rich history/images via `inputs.py`
- Thread resume + persistence (`codex_thread_id` on `Conversation`)
- Image generation moved to the modern plugin registry (`openai_codex_image_gen`)

Phase 4 (marker hygiene + docs) is the final cleanup pass.

The original "commented implementation only" discipline was followed for the initial landing, then the provider core was activated incrementally with the necessary compatibility work. The strict mechanical activation PR never happened as a single step; instead the work was done in reviewed phases.
