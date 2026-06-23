# Contract 2 — Provider / Harness Taxonomy + Capability Manifest

**Purpose**: Every provider declares a **role** and a **CapabilityManifest** the turn pipeline reads to decide loop ownership, safety application, tool wiring, and what the UI may truthfully claim. Evolves the single undifferentiated `AILLM.stream()` (`providers/base.py:104`) + `factory.HOST_TO_PROVIDER` (`factory.py:54`). Implements the rot-audit split that was recommended but never built.

## Role (exactly one)

- **ModelProvider** — host owns the loop; Pawrrtal runs `run_model_tool_loop` and dispatches `AgentTool`s. Today: Gemini, xAI, LiteLLM, claude_code_pty (`claude_code_pty/provider.py:215`).
- **AgentProvider** — provider owns its own loop (SDK/CLI harness); Pawrrtal forwards a turn and consumes native events. Today: openai_codex (SDK app-server), agy_cli (one-shot subprocess).

## CapabilityManifest (declared, never inferred)

- **`tool_enforcement`**: `enforced | native-only | none`
  - `enforced` — Pawrrtal's `permission_check` gates every tool call (claude_code_pty via `default_tool_permission_check` inside the loop).
  - `native-only` — tools run inside the provider's harness; Pawrrtal cannot gate them, the provider gates natively (openai_codex installs a deny-all SDK approval handler, `provider.py:214`).
  - `none` — provider ignores Pawrrtal tools entirely (agy_cli, `provider.py:83`).
- **`streaming_tier`**: `incremental` (true token/part deltas) | `turn-final` (one delta with the whole answer at end — agy_cli `provider.py:144`).
- **`session_model`**: `stateless` (Pawrrtal replays full history each turn) | `provider-session` (provider keeps a native thread; Pawrrtal stores an opaque handle — see [session-record.md](./session-record.md)).
- **`reasoning`**: `none | summary | raw` — which reasoning parts it can emit (drives the verbosity tiers, `aggregator.py:65`).
- **`multimodal_in`**: `bool` — accepts image parts (`base.py:144`).
- **`safety_honored`**: which `AgentSafetyConfig` guards actually apply. ModelProviders honor all; AgentProviders declare a subset (codex bypasses `run_model_tool_loop`, so `max_iterations`/wall-clock are provider-internal).

## Enforcement rules

- Tool-surface composition (`agents/tool_surface.py`) passes enforceable `AgentTool`s to **ModelProviders**; for **native-only** it records that gating is delegated; for **none** it MUST NOT claim tools are available (the UI/audit stop lying).
- The **`no-tools-in-providers` rule is unchanged** — providers still translate `AgentTool`→SDK shape and never import `app.tools.*` (`.claude/rules/architecture/no-tools-in-providers.md`).
- The picker/manifest surfaces the true enforcement level so a `none` provider can't masquerade as gated.

## Open

- For AgentProviders that own their loop, does `AgentSafetyConfig` apply or only the provider's own limits? The manifest's `safety_honored` declares which guards are real.
- A shared `CLIHarnessProvider` base class is an implementation detail (none exists today); the **contract is the manifest**, not the base class.
