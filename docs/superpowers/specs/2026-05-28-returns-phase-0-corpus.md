# Phase 0 reading-glasses corpus

Date: 2026-05-28
Bean: pawrrtal-67rg
Followup-to: docs/superpowers/specs/2026-05-28-returns-adoption-grilling.md

## Methodology

Phase 0 was originally a one-week "annotate live PRs with `could this be a
Result?`" exercise. We shipped Phases 1, 2, and 3 on three narrow pilot
surfaces (`tools/external_mcp.py`, `crud/conversation.py`,
`providers/litellm_provider.py`) before doing the Phase 0 evidence pass, so
this document runs the same reading-glasses **retrospectively** over the
**un-migrated** code in the three target zones.

Files walked (un-migrated only — the three pilot surfaces are deliberately
out of scope):

- Providers: `claude/provider.py`, `gemini/provider.py`,
  `gemini_cli/provider.py`, `xai/provider.py`, `opencode_go/provider.py`,
  `openai_codex/provider.py`, `agy_cli/provider.py`.
- CRUD: `crud/channel.py`, `crud/chat_message.py`, `crud/cost.py`,
  `crud/mcp_servers.py`, `crud/memory.py`, `crud/project.py`,
  `crud/workspace.py`, `crud/audit.py`.
- Tools: every `backend/app/tools/*.py` except `external_mcp.py`.

Rubric is the decision walk from
`.claude/skills/returns-for-pawrrtal/SKILL.md`:

1. Distinct, named failure modes the caller acts on differently?
2. >=3 callers care about the failure-mode distinction?
3. Function is part of a 3+ step chain where the same failures propagate?
4. Does the caller (not the callee) become simpler?

A site only gets a **YES** when all four are answered yes for that site.

Out of scope: any code path touched by the three pilot surfaces; rewrites
of unrelated patterns; behaviour changes of any kind (annotation only).

## Annotations by module

### backend/app/providers/claude/provider.py

| Site | Verdict | Container | Rationale |
|---|---|---|---|
| `stream()` lines 317-398: five typed except branches (`CLINotFoundError`, `CLIConnectionError`, `ProcessError`, `CLIJSONDecodeError`, `ClaudeSDKError`) | **YES** | `FutureResult[AsyncIterator[StreamEvent], ClaudeError]` with a closed `ClaudeError = NotInstalled \| ConnectionLost \| ProcessExited \| JSONDecode \| SDKError` union | This is the textbook fit: many distinct failure modes, each with a tailored user message; the retry loop at 343-364 already pattern-matches by exception type. Caller (chat router) currently can't see the union; with `Result.failure()` the retry/fallback logic could live at the caller boundary instead of being smeared through the except branches. |
| `stream()` retry loop (lines 343-364) — `_is_retryable_cli_connection` + attempt counter inside the except | MAYBE | `Result` + a `.retry(policy)` combinator | Returns ships a retry combinator. Worth one PR-sized experiment but the bespoke "resume-failure fallback" logic at 343-349 is not generic — it would need a custom step regardless. |
| `_logged_error_event` (lines 412-416) | NO | — | Side-effect helper, no failure path. Container would add ceremony with no payoff. |

### backend/app/providers/gemini/provider.py

| Site | Verdict | Container | Rationale |
|---|---|---|---|
| `make_gemini_stream_fn.stream_fn` line 174-202: single `try / except Exception` over the entire `generate_content_stream` loop | NO | — | Failure is bare `Exception`, flattened into one error text + done event. No caller acts differently on Gemini auth vs rate-limit vs network — the only behaviour is "render the message verbatim into the chat bubble." Wrapping in `FutureResult[…, Exception]` is the anti-pattern flagged in the skill. |
| `GeminiLLM.stream` lines 332-345: outer `try / except Exception` over `agent_loop` | NO | — | Same shape, same reason. |

### backend/app/providers/gemini_cli/provider.py

| Site | Verdict | Container | Rationale |
|---|---|---|---|
| `_run_handshake_and_prompt` lines 245-249: `except AcpFatalError as err: yield _error_event(str(err))` | MAYBE | `Result[SessionId, AcpFatalError]` at `open_session` boundary | Single typed failure with one caller. Doesn't pass the "3+ callers care" gate but is the cleanest example of a typed-error site in this file. Skill says stick with `try/except` here. |
| `_drive_acp_turn` finally block at lines 230-233: tuple-narrowed close-timeout | NO | — | Best-effort cleanup. Not a result-bearing path. |
| `_spawn_subprocess` lines 289-306: `FileNotFoundError` / `OSError` → return `None` | MAYBE | `Maybe[Process]` | One caller. Already idiomatic with `if proc is None: yield _error_event(...)`. No payoff. |
| `_shutdown_subprocess` lines 318-334: best-effort terminate/kill | NO | — | Side effects, no result. |

### backend/app/providers/xai/provider.py

| Site | Verdict | Container | Rationale |
|---|---|---|---|
| `make_xai_stream_fn.stream_fn` lines 201-223: blanket `except Exception` | NO | — | Identical shape to Gemini — no typed failures, no caller differentiation. |
| `XaiLLM.stream` lines 402-425: blanket `except Exception` over `agent_loop` | NO | — | Same. |
| `_resolve_xai_api_key` line 142: `return None` on missing key | MAYBE | `Maybe[str]` | One caller, simple `Optional[str]`. Mechanical rename. No payoff. |

### backend/app/providers/opencode_go/provider.py

| Site | Verdict | Container | Rationale |
|---|---|---|---|
| `make_opencode_go_stream_fn.stream_fn` lines 146-178: blanket `except Exception` | NO | — | Same shape as Gemini/xAI. |
| `OpenCodeGoLLM.stream` lines 324-345: blanket `except Exception` over `agent_loop` | NO | — | Same. |

### backend/app/providers/openai_codex/provider.py

| Site | Verdict | Container | Rationale |
|---|---|---|---|
| `OpenAICodexProvider.stream` lines 222-245: thread_start/resume `except Exception` → error event | MAYBE | `Result[Thread, CodexThreadError]` | Two failure shapes are observed in practice (auth-expired + transport), but they're not yet enumerated. If the SDK ever exposes typed thread errors this site becomes a YES. Today it's a single-line `except` and the railway costs more than it earns. |
| `OpenAICodexProvider.stream` lines 250-258: `build_codex_run_input` fallback to `TextInput` | NO | — | Pure local recovery, no caller differentiation. |
| `OpenAICodexProvider.stream` lines 262-279: turn streaming `except Exception` | NO | — | Same blanket-except pattern. |

### backend/app/providers/agy_cli/provider.py

| Site | Verdict | Container | Rationale |
|---|---|---|---|
| `stream()` lines 97-117: `_spawn` returns `None` → `_communicate` timeout → final-marker missing | MAYBE | `Result[str, AgyError]` over the spawn → communicate → extract chain | Three step chain with three distinct failures (spawn failed / timeout / unframed response), each rendered to a different `_error_event`. Passes rubric step 1 and 3, fails step 2 (one caller). |
| `_spawn` lines 144-158: returns `None` on `FileNotFoundError`/`OSError` | MAYBE | `Maybe[Process]` | Mechanical. No payoff in isolation. |
| `_communicate` line 161-165 | NO | — | No failure path. |
| `_shutdown_process` lines 168-184 | NO | — | Side-effect cleanup. |

### backend/app/crud/channel.py

| Site | Verdict | Container | Rationale |
|---|---|---|---|
| `redeem_link_code` lines 102-133: three `return None` branches (missing code / wrong provider / used-or-expired) | **YES** | `Result[ChannelBinding, RedemptionError]` where `RedemptionError = NotFound \| WrongProvider \| Expired \| AlreadyUsed` | This is the strongest CRUD-side case in the corpus. The docstring explicitly says "the caller maps `None` to a generic 'code not recognized or already used' message — never leak which case it was." That's a security policy that should live in the **type**, not in a docstring comment. With `Result` the caller cannot accidentally branch on the variant; with `Optional` nothing stops a future agent from adding `if outcome is None and last_attempt: ...`. |
| `get_binding` / `get_user_id_for_external` (line 199, 220) — `Optional[ChannelBinding]` reads | YES | `Maybe[ChannelBinding]` | Mechanical. Clusters with the `crud/conversation.get_conversation` pilot. |
| `normalize_conversation_reasoning_effort` line 423 `return None, None` | MAYBE | `Maybe[tuple[X, Y]]` | Tuple-of-None is the anti-shape `Maybe` was designed for. |

### backend/app/crud/chat_message.py

| Site | Verdict | Container | Rationale |
|---|---|---|---|
| `get_messages_for_conversation` (line 41) | NO | — | Returns `list[ChatMessage]` — empty list is the natural "nothing" value. Skill anti-pattern: don't wrap sequences in `Maybe`. |
| `append_user_message` / `append_assistant_placeholder` / `finalize_assistant_message` | NO | — | Always-succeed writes (or raise on DB connection death — `Result` doesn't help). |

### backend/app/crud/cost.py

| Site | Verdict | Container | Rationale |
|---|---|---|---|
| `cumulative_window_usd` lines 59-62: `try: float(value) except (TypeError, ValueError): return 0.0` | NO | — | Catches a coercion edge case with a clear default. `Result` would force the caller to handle a case the function already absorbed. |
| All three functions | NO | — | Return aggregates or lists. No `Optional`, no error union. |

### backend/app/crud/mcp_servers.py

| Site | Verdict | Container | Rationale |
|---|---|---|---|
| `get_mcp_server` / `update_mcp_server` / `delete_mcp_server` — `Optional[McpServer]` reads | YES | `Maybe[McpServer]` | Mechanical, clusters with channel.py and the conversation pilot. |
| `parse_mcp_config` lines 136-138: `except json.JSONDecodeError: return {}` | NO | — | Defensive fallback documented in the docstring; caller does not need to know. |

### backend/app/crud/memory.py

| Site | Verdict | Container | Rationale |
|---|---|---|---|
| `mark_memory_referenced` lines 119-133: get-or-noop | NO | — | Fire-and-forget. Caller doesn't care. |
| `insert_memory` / `list_memories_for_user` / `find_similar_memories` | NO | — | Always-succeed or list-returning. |

### backend/app/crud/project.py

| Site | Verdict | Container | Rationale |
|---|---|---|---|
| `get_project` / `update_project` / `delete_project` — three `Optional[Project]` reads | YES | `Maybe[Project]` | Same shape as mcp_servers + channel + conversation. |

### backend/app/crud/workspace.py

| Site | Verdict | Container | Rationale |
|---|---|---|---|
| `ensure_default_workspace` lines 130-161: nested-savepoint + `IntegrityError` recovery + re-fetch | **YES** | `Result[Workspace, EnsureWorkspaceError]` where the error covers `Conflict` (concurrent insert) and `Inconsistent` (constraint fired but row missing) | Three-step chain (savepoint → create → recover) with two distinct named outcomes; the inner `RuntimeError(...) from None` on line 157 is exactly the "I had to invent an error type" smell the skill calls out. |
| `ensure_dev_admin_workspace` lines 186-213 | YES | Same shape | Duplicate of the above; one container would dedupe both. |
| `_remove_orphan_workspace_dir` lines 273-292 | NO | — | Best-effort cleanup. |
| `get_default_workspace` / `list_workspaces` / `update_workspace` / `delete_workspace` | YES (for `Optional` reads) / NO (for writes) | `Maybe[Workspace]` for reads | Mechanical. |

### backend/app/crud/audit.py

| Site | Verdict | Container | Rationale |
|---|---|---|---|
| All four functions | NO | — | List or aggregate returns. No `Optional`, no error union. |

### backend/app/tools/*

Tools already use a **hand-rolled Result equivalent**: `ToolError` carrying
a `ToolErrorCode` enum (see `tools/errors.py`). Tool bodies either `raise
ToolError` (caught and rendered by the agent-loop bridge) or `return
ToolError(...).render()` directly into the model's view. This is the
pattern `Result[T, ToolError]` would formalise; the cost-benefit is
whether typing it would change any caller.

| Site | Verdict | Container | Rationale |
|---|---|---|---|
| `tools/markitdown_convert.py` lines 75-105 — five `return ToolError(...).render()` branches | YES | `Result[str, ToolError]` | Each branch is a distinct named failure (`INVALID_PATH`, `OUT_OF_ROOT`, `NOT_FOUND`, `WRONG_KIND`, `IO_ERROR`). This is exactly what the existing `ToolError` enum encodes. Clusters with `external_mcp.py`'s `IOResult[ToolOutput, McpError]`. |
| `tools/skill_invocation.py` — `discover`/`read` both have the same five-branch shape | YES | `Result[str, ToolError]` | Identical cluster. |
| `tools/workspace_files.py` — read/write/list with `ToolError` branches | YES | `Result[str, ToolError]` | Identical cluster. |
| `tools/exa_search.py` lines 140-176 — returns a dict with `"error": "..."` instead of raising | YES | `Result[dict, ExaError]` | Three distinct failure modes (transport / HTTP / decode) currently encoded as magic strings in a dict shape. Typing them would catch the "did the tool body remember to set `error`?" question at compile time. |
| `tools/image_gen.py` lines 49-81: `resolve_codex_oauth_token` raise-or-return | MAYBE | `Result[str, AuthError]` | One caller; mechanical. |
| `tools/cron_tools.py` lines 96-126 — schedule tool with `ValueError` / `Exception` branches | MAYBE | `Result[Schedule, CronError]` | Two failure types, one caller, low payoff. |
| `tools/python_exec.py` — exception-based contract (raises `PermissionError`, `ValueError`, etc.) | NO | — | The docstring (lines 125-130) explicitly chose exceptions over containers for the executed-Python sandbox: "the model already knows how to `try/except`." This decision is correct for an in-Python sandbox and should not be reversed. |
| `tools/agents_md.py`, `tools/now.py`, `tools/tasks_md.py`, `tools/send_message.py`, `tools/report_issue.py`, the lcm/exa/artifact agent wrappers | NO | — | Either trivial single-step happy paths or already routed through the `ToolError`-raise + bridge pattern; container would not change either side. |

## Synthesis

### Annotation cluster count

| Container shape | Strong YES sites | MAYBE sites |
|---|---|---|
| `Maybe[Row]` (CRUD Optional reads) | 4 (channel, mcp_servers, project, workspace) | 2 |
| `Result[T, ToolError]` (tool failure unions) | 4 (markitdown, skill_invocation, workspace_files, exa_search) | 2 |
| `Result[T, NamedError]` (provider/CRUD multi-branch) | 3 (Claude `stream`, channel `redeem_link_code`, workspace `ensure_*`) | 4 |
| `FutureResult` / `IOResult` (async multi-step) | 0 strong sites outside the existing `external_mcp.py` pilot | 2 |

Total strong YES sites: **11**. Total MAYBE: **10**. The MAYBE column is
the noise floor — almost all of those are one-caller mechanical renames
that pass two of four rubric questions but fail "would the caller be
simpler?"

### Cluster boundaries

The annotations cluster into **two distinct shapes** with one outlier:

- **Shape A — `Maybe[Row]`**: spread evenly across crud/* with no
  surprises. This is the pattern Phase 2 already piloted on
  `crud/conversation.get_conversation`.
- **Shape B — `Result[T, ToolError]`**: concentrated in tools/* and
  already typed at the enum level. Phase 1 piloted this on
  `tools/external_mcp.py`. Three more tool files (markitdown,
  skill_invocation, workspace_files) have the identical shape.
- **Outlier — provider `Result[Stream, ProviderError]`**: the skill's
  original target. Reading the seven un-migrated providers shows the
  pattern is **a Claude-only opportunity** — six of seven providers use
  blanket `except Exception` and flatten everything to one
  `error_text` event. The "many callees with shared typed errors"
  premise that motivated the original 4-week pilot is **not present**
  in the actual code.

### Decision rule outcome

> "Phase 0 → Phase 1 only if reviewer annotations cluster around a
> consistent container shape across 3+ PRs."

**PASS — but not for the surface the original spec assumed.**

The clustering signal is real and crosses the 3-site threshold twice:

1. `Maybe[Row]` across at least four CRUD modules (channel, mcp_servers,
   project, workspace) plus the conversation pilot.
2. `Result[str, ToolError]` across at least four tool modules
   (markitdown, skill_invocation, workspace_files, exa_search) plus the
   external_mcp pilot.

The provider-seam signal **fails**: only Claude has the typed-error
shape; the other six providers actively use anti-patterns the skill
warns about (`except Exception` → single failure event).

### Recommended next move

**Expand `Maybe[Row]` and `Result[T, ToolError]`; do not expand to the
provider seam.** Concretely:

- Extend Phase 2 (`Maybe[Row]`) to the four CRUD modules above as a
  single follow-up PR — the shape is identical to the conversation
  pilot, the diff is mechanical, and the cluster is broad enough to
  justify carrying the dependency.
- Extend Phase 1 (`Result[T, ToolError]`) to three more tool modules
  (markitdown_convert, skill_invocation, workspace_files) — they
  already encode the `ToolErrorCode` union, so `Result` just types
  what's already there.
- **Freeze the provider-seam pilot** (the original `pawrrtal-0zne`).
  Six of seven un-migrated providers don't have the failure-type
  diversity the railway needs; forcing the pattern would create the
  "Result[T, Exception]" anti-pattern the skill explicitly bans.
  Re-evaluate only if a future PR adds typed errors to the
  non-Claude providers.

## Action items

- [ ] File new bean: *Phase 2-expand: Maybe[Row] across crud/channel,
  crud/mcp_servers, crud/project, crud/workspace* (small, mechanical
  follow-up to the conversation.py pilot). One PR.
- [ ] File new bean: *Phase 1-expand: Result[T, ToolError] across
  tools/markitdown_convert, tools/skill_invocation,
  tools/workspace_files* (already encodes the union via
  `ToolErrorCode`; this just types the seam). One PR.
- [ ] File new bean: *Phase 3 freeze: re-scope pawrrtal-0zne from
  "deferred" to "rejected — provider seam lacks failure-type
  diversity; revisit only if non-Claude providers add typed errors."*
- [ ] Update `.claude/skills/returns-for-pawrrtal/SKILL.md` Section
  "When the railway pattern is worth it" with the corpus result: the
  "many callees → one caller" premise didn't hold once we counted
  actual typed-error sites.
