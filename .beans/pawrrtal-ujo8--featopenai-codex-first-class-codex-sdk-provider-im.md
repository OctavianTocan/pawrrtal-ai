---
# pawrrtal-ujo8
title: 'feat(openai_codex): first-class Codex SDK provider + image-gen plugin (commented implementation only)'
status: todo
type: feature
priority: high
tags:
    - codex
    - provider
    - plugin
    - backend
created_at: 2026-05-26T19:48:37Z
updated_at: 2026-05-26T19:48:37Z
---

# Plan: Codex Integration via Official Python SDK

**Status:** Draft plan for review (plan mode output)  
**Date:** 2026-05-26 (session context)  
**Related GitHub issue (pawrrtal-ai repo):** #433 "Refactor: Agent Architecture Clarity + Sub-Agent Infrastructure" (explicitly calls out Codex's `Session` as reference architecture for stateful `AgentSession` + sub-agents; also references Pi, Claude Code, OpenHands, etc.)  
**Primary external references (authoritative):**  
- https://github.com/openai/codex/tree/main/sdk/python (the actual SDK source the plan must follow exactly — package is `openai_codex`, not the older `codex_app_server` name that appears in some public docs)  
- https://developers.openai.com/codex/sdk#python-library (high-level overview)  
**Complementary internal docs:** `docs/design/codex-oauth-text-provider.md` (current reverse-engineered Responses API path for images + planned text models via Codex OAuth)

---

## Context & Why This Work

Pawrrtal already has partial Codex integration:
- Image generation (`backend/app/core/tools/image_gen.py`) uses Codex OAuth tokens (from `OPENAI_CODEX_OAUTH_TOKEN` override or `~/.codex/auth.json` written by the official `@openai/codex` CLI / OpenClaw). It hits the private `https://chatgpt.com/backend-api/codex/responses` endpoint with the `image_generation` tool.
- A detailed design doc (`docs/design/codex-oauth-text-provider.md`) exists for lifting the auth helpers and adding a full text-model provider (`OpenAICodexProvider`) speaking the same Responses API shape (with reasoning summaries, encrypted_content for stateless multi-turn, strict header rules, originator bypass, etc.). This complements the existing LiteLLM-routed "Codex family" models (gpt-5.3-codex, gpt-5.1-codex-max, etc.) in `catalog/openai.py`.
- Codex OAuth is preferred over plain `OPENAI_API_KEY` for subscription-tier features (fast mode, reasoning summaries) and because the `/codex` sub-path bypasses certain ChatGPT OAuth scope gates.

The official **Codex Python SDK** (experimental, `from codex_app_server import Codex` / `AsyncCodex`) is a different surface:
- It speaks JSON-RPC to a local Codex **app-server** (the background daemon that powers the Codex desktop app, CLI, IDE extension).
- Requires Python 3.10+ and a local checkout of the open-source Codex repo (`cd sdk/python && pip install -e .`).
- Primary use: programatically start/resume `thread`s, run prompts, and get structured results (`final_response`, events, etc.). This gives full access to Codex's agentic coding loop (shell tool, file edits, sandbox, approvals, memories, subagents, skills, MCP, etc.) without reimplementing the wire protocol.
- The SDK is the supported path for "control Codex as part of your CI/CD pipeline", "create your own agent that can engage with Codex", or "build Codex into your own internal tools".

**The gap / opportunity (updated per user direction):**  
The existing reverse-engineered `chatgpt.com/backend-api/codex/responses` path (used for image generation today and sketched for text in `docs/design/codex-oauth-text-provider.md`) is a **rudimentary** approach. It is **not** the recommended way once the official SDK exists. The SDK path (`openai_codex` package) is what we actually want — it is the first-class, butter-smooth, officially supported integration.

Pawrrtal will keep the LiteLLM OpenAI surface exactly as-is (it can continue to serve OpenAI models for users who prefer that route). The new `openai_codex` provider is an **additional, superior** path for Codex-powered models and agentic workflows. It must feel **as native as native means** (full streaming, model selection, reasoning, tool use, cost tracking, etc. indistinguishable from Claude/Gemini/xAI in the UI).

The image-generation-via-Codex-agent capability must be delivered as a **plugin** (exact same structure and patterns as `backend/app/plugins/active_recall/`, but **not** driven by a pre-turn hook).

The provider must feel **native** in the Pawrrtal interfaces: model picker, reasoning effort, streaming deltas + thinking summaries, tool use, etc.

No dedicated GitHub issue titled "Codex Python SDK integration" was located via `search_issues` (the only open issue hitting "codex" is #433, which uses it as an existence proof for clean session/agent abstractions). The practical tracking lives in the design doc + scattered TASKS / logs referencing "Codex provider". This plan makes the official SDK the source of truth for a first-class provider + the requested image plugin.

**Hard requirements from the user (this revision):**
- First-class, full `openai_codex` provider (package name matches the real SDK).
- Follow the official SDK at https://github.com/openai/codex/tree/main/sdk/python **exactly** for everything (threads, models, turn streaming, login, etc.). "Whatever they say we should do."
- "Latest all the way."
- The provider must feel **butter smooth** and completely native.
- Codex "threads" have a specific meaning in the SDK — research the actual source tree (not just the high-level docs page) before designing the provider layer.
- The image generation tool that drives a Codex agent is implemented as a plugin (active-recall style), not as a hook-driven sub-agent.
- LiteLLM's OpenAI / Codex-family routing is left completely untouched.

---

## Recommended Approach (Chosen Path)

**Add a dedicated `codex` provider package** (following the established multi-file pattern from `agy_cli/` and `gemini_cli/`) that wraps the **official `openai_codex` Python SDK** (the real package name from https://github.com/openai/codex/tree/main/sdk/python).

**Core implementation discipline (non-negotiable for this task):**  
You are **not making real changes to live code**. All work consists of writing the intended final code and then **commenting it out** (or prefixing with `# TODO: UNCOMMENT WHEN APPLYING` / `# NEW CODE:` blocks).  
- When creating a new file: write the complete, compilable implementation, then comment the entire body (or large logical sections) so the file is a safe, reviewable artifact.  
- When editing an existing file: leave the original code untouched; immediately below or beside the change site, add a clearly marked block showing the new version (or a "DELETE THIS BLOCK" marker for removals). Use consistent markers such as:
  ```python
  # === CODEX-SDK-PLAN: START NEW ===
  # (the exact code that should exist after the plan is applied)
  # === CODEX-SDK-PLAN: END NEW ===
  ```
  or
  ```python
  # === CODEX-SDK-PLAN: DELETE ===
  # (the lines that should be removed)
  ```
- Deletions of whole files are described in comments or a companion `DELETE-FILES.md` rather than `git rm`.
- The delivered PR(s) are therefore a **living specification + commented implementation**. A later human or follow-up agent can mechanically apply the comments to produce the real diff. This makes every review step trivial and reversible.

**Positioning (per user direction):**
- This is a **first-class, full `openai_codex` provider** (package name matches the real SDK), on equal footing with Gemini, Claude, xAI, etc.
- It must feel **butter smooth** and completely native (as native as native means).
- We follow the official SDK at https://github.com/openai/codex/tree/main/sdk/python **exactly** ("whatever they say we should do" + "latest all the way"). Research the actual source tree first — especially what a Codex "thread" really is.
- LiteLLM's OpenAI surface stays untouched.

**Required additional deliverable (explicit user request):**
As part of this same plan we will also produce a working image-generation tool implemented as a **plugin** (exact structure and patterns as `plugins/active_recall/`, but not hook-driven) that uses the new first-class `openai_codex` provider to spin up a Codex-backed agent and instruct it to produce the image.

Key technical decisions:
- Re-use (and lift into shared `openai_codex/auth.py`) the existing Codex OAuth resolution from `image_gen.py` and the design doc.
- The provider implements the full native streaming contract (following exactly what the official SDK exposes for threads / turns) and maps everything into our `StreamEvent` union so the rest of Pawrrtal is unchanged.
- Follow the SDK's own guidance on threads, models, `AppServerConfig`, etc. (research the tree first).
- The image-gen-via-Codex-agent tool is a plugin (active-recall style layout) that creates a Codex-backed agent via the new provider and instructs it to produce the image.

This plan makes the official SDK the source of truth for a true first-class, butter-smooth `openai_codex` provider while delivering the requested image plugin as a first-class citizen of the plugin system.

### High-Level Architecture
```
Paw chat turn / AgentSession
          │
          ▼ (for coding-heavy prompts or explicit delegation)
   codex.CodexSdkLLM (or CodexSession wrapper)
          │
          ▼ (AsyncCodex / thread_start / thread.run)
   local Codex app-server (JSON-RPC, uses same auth.json)
          │
          ▼ (Codex does shell, edits, subagents, etc. in workspace)
   workspace files + Paw tools (via MCP or bridged tools)
```

### File / Module Changes (Critical Paths) — All Work Is Commented

Every new or modified file produced by this plan **must** follow the "write-then-comment" rule above. The PR artifact is a set of files that contain both the original state (where relevant) and clearly delineated "what the final code should be" blocks.

Concrete list (all subject to the commenting discipline):

- **New (fully commented after writing):** `backend/app/core/providers/codex/__init__.py`
- **New (fully commented):** `backend/app/core/providers/codex/provider.py` — the first-class `CodexLLM` (or `OpenAICodexSdkProvider`) that implements the full `AILLM` / `stream(...)` contract using the official `openai_codex` SDK. Full streaming via `thread.turn(...)`, model passing, auth, lifecycle, and `StreamEvent` mapping. This is the core deliverable.
- **New (fully commented):** `backend/app/core/providers/codex/auth.py` — lifted shared auth (the exact merge of `image_gen.py` + design-doc sketch + any SDK `AppServerConfig` needs). Must show clear "before/after" comment blocks.
- **New or inline (commented):** event mapping helpers (inside provider.py or a small `events.py`).
- **New or update (commented diff blocks):** catalog entries (`catalog/codex.py` or additions to `openai.py` / `entries.py`) for the models the SDK surfaces. Follow whatever the official SDK tree recommends for model IDs.
- **Update (commented blocks only):** `backend/app/core/providers/factory.py` — registration under the new `Host.codex` (or `Host.codex_sdk`) and construction path. Guarded by the presence of the SDK / a feature flag.
- **New (fully commented):** the image-generation tool that uses the new provider to drive a Codex agent for image production (`backend/app/core/tools/image_gen_codex_agent.py` or equivalent). This is the second explicit deliverable.
- **Update (commented):** `backend/app/core/keys.py`, `backend/app/core/config.py`, `backend/pyproject.toml` (notes + any new env vars for the SDK path).
- **Update (commented):** `docs/design/codex-oauth-text-provider.md` (SDK vs. direct Responses comparison) + a focused new or extended section/doc for the first-class provider + the image-via-Codex-agent tool.
- **New (fully commented):** `backend/tests/test_codex_sdk_provider.py` (provider contract, streaming, auth, model handling) **and** tests for the new image-gen-via-Codex-agent tool.
- **Docs updates (commented):** README, developer setup docs (the exact steps from the official `sdk/python` README + our local Codex OAuth notes), and any AGENTS.md guidance.

For every changed site, the submitted code must contain both the "before" (original or clearly marked) and the "after" (commented exact text), so a reviewer or later applicator can see the precise transformation with zero ambiguity.

### Setup for Developers / Users (Critical for Plan Success)
1. Users must have the Codex app/CLI installed and authenticated (`codex login` or equivalent) so `~/.codex/auth.json` exists (re-uses existing image-gen path).
2. For SDK path: clone `https://github.com/openai/codex`, `cd sdk/python && pip install -e .` (or uv equivalent in the backend venv). Document in `docs/` and a new `docs/codex-sdk-setup.md`.
3. The SDK can point at a local `codex` binary via `AppServerConfig(codex_bin=...)`.
4. Guard the feature behind `CODEX_SDK_ENABLED=true` (off by default) because it requires the local daemon + source checkout.

### Event / Tool Bridging Strategy
- Map Codex `final_response`, deltas, and any visible tool calls to our `StreamEvent`.
- For deeper integration, expose a subset of Paw tools (Notion, memory, etc.) to the Codex thread via MCP (Codex already supports MCP servers) or by running the Codex thread inside a Paw workspace that has the Paw MCP server running. This is the "Paw tools available to Codex" direction.
- Reverse: allow the main Paw agent to call a `codex_engineer(prompt, workspace_scope)` tool that creates a Codex-backed sub-`AgentSession`.

---

## Alternatives Considered (and Why Not Primary)

1. **Pure HTTP reverse-engineer only (current design doc path):** Already in progress for text models. Good for lightweight "use Codex models without local daemon". Keep it; the SDK path is additive for full agentic power.
2. **Treat Codex purely as a CLI subprocess (like early agy_cli before SDK):** The official SDK exists precisely to avoid this fragility. Use the supported JSON-RPC wrapper.
3. **Make Codex the default / only LLM for all turns:** Overkill. Codex is a coding specialist with its own UI/approval flows. Better as a targeted sub-agent or tool.
4. **No new provider, just a Python tool that shells out to `codex` binary:** Loses the structured SDK surface, thread management, and clean event stream. The Python SDK is the right abstraction.

---

## Verification (End-to-End Gates) — Emphasis on Commented Artifacts

The primary deliverable is **not** a green `main` branch with live Codex code. The deliverable is a set of PRs whose diffs are almost entirely comments that describe the exact final state.

Before the plan is considered complete:
1. Every new file and every edit site contains the commented implementation blocks (or "DELETE" markers) exactly as specified in the "Implementation Discipline" section above. A mechanical "uncomment / apply" pass must be obviously correct from the comments alone.
2. `just check` + backend ruff/mypy/pytest still pass on the commented code (the commented code must be syntactically valid Python even while commented-out where required).
3. The test files (`test_codex_sdk_provider.py` + tests for the image-gen-via-Codex-agent tool) are written and commented; they document the intended first-class provider behavior + the image tool behavior.
4. Manual review of the commented artifacts confirms:
   - The provider is a true first-class `AILLM` implementation (full streaming, native model IDs from the SDK, auth, lifecycle).
   - It follows the official `openai_codex` package surface from https://github.com/openai/codex/tree/main/sdk/python (package name, `Codex()`, `thread_start(model=...)`, turn streaming, etc.).
   - Auth lift is correct and matches the existing image-gen + design doc.
   - The new image-generation tool that drives a Codex agent (via the provider) to produce images is fully specified in commented form and re-uses the Codex OAuth path.
   - Workspace boundary, event mapping, and error/refresh paths are clearly expressed.
5. Documentation updates (README + design doc) explicitly call out the "commented implementation" workflow, the "latest all the way" rule, the requirement to follow the official SDK tree, and the one-time "apply the comments" activation step.
6. No live behavior changes have been made to existing image generation, other providers, the catalog, or the agent loop.
7. A bean was created (via `beans create`) that references this plan, the first-class provider requirement, the image-via-Codex-agent tool requirement, and the "commented only" rule.

Only after the commented PRs are reviewed and landed does a subsequent (small, mechanical) PR exist that actually removes the comment markers and activates the feature + the image tool. That later PR is out of scope for this plan.

---

## Risks & Mitigations

- **SDK is experimental / wire can change:** Mitigate by pinning to a known-good Codex commit in docs; treat as "best effort" integration; add clear "experimental" badges and fallback to the direct Responses text provider.
- **Local daemon / source checkout friction:** Document exhaustively; provide a one-liner bootstrap script if possible; keep the pure-OAuth Responses path as the zero-install Codex model option.
- **Auth contention (single-use refresh tokens, see design doc #15502):** Central lock (already planned) + re-read `auth.json` after 401.
- **Workspace boundary / sandbox leakage:** Codex has its own sandbox; test `--add-dir` / equivalent thoroughly; surface Codex's approval decisions.
- **File-line / nesting budgets:** Keep new modules small; follow the 500-line Python rule and nesting-depth script.
- **Sentrux / architecture drift:** New `Host.codex_sdk` fits the provider layer; no cross-stack violations.

---

## Open Questions for User (Narrow Clarifications)

(If any of these are true, the plan can be adjusted before execution.)
- Do you want Codex threads surfaced as selectable "models" in the picker (like `codex-sdk:openai/gpt-5.5-codex-agent`), or strictly as an explicit tool / sub-agent invocation?
- Should the SDK integration require the full local Codex source checkout, or is there a PyPI path / bundled binary story we should investigate first?
- Priority: first get the lightweight text Responses provider (per design doc) shipped, then layer the SDK on top; or do the SDK path in parallel because it unlocks qualitatively different workflows?
- Any preference on whether Codex sub-agents should share the exact same `AgentSession` machinery as the LCM recall agent (recommended) or get a bespoke wrapper?

---

## Next Steps After Plan Approval

1. Create the bean for this epic (using `beans create`). The bean body must quote the "Implementation Discipline" section + the "first-class provider + image-via-Codex-agent tool" requirements verbatim.
2. Execute the plan **exclusively in commented form** (no live mutations):
   - PR(s) that add the new `codex/` package as a first-class provider (following the exact `openai_codex` SDK surface from the official tree), the catalog wiring, the auth lift, full streaming support, and the new image-generation tool that drives a Codex agent to produce images.
   - All tests and docs updated under the same commented-block discipline.
   - CI stays green on the commented state.
3. The review process focuses on "does the commented code, once the markers are removed, give us a native-feeling first-class Codex provider + the requested image tool?" 
4. Only after the commented PR(s) are accepted and merged does a subsequent (tiny, mostly mechanical) change exist that actually activates the provider and the image tool by removing the comment guards. That activation step is explicitly **out of scope** for the work tracked under this plan.
5. Update `DESIGN.md` (via commented blocks) if any new tokens or UI surfaces are described.
6. Close the loop by updating the design doc + bean with links to the commented PRs and a note that the "apply comments" activation PR is a separate, later task.

This plan delivers a **first-class, fully streaming Codex provider** (following the official SDK at https://github.com/openai/codex/tree/main/sdk/python exactly, "latest all the way") plus the explicit image-generation-via-Codex-agent tool, while re-using the existing Codex OAuth surface and following the project's multi-file provider conventions + the strict "comment everything, change nothing live" rule.
