# Paw Coding Agent Tool

## Goal

Give the main Paw agent a controlled way to delegate medium-complexity coding work to a real coding agent, without exposing raw shell/process control as a normal chat tool.

## Recommendation

Build Pawrrtal's own `coding_agent` tool surface and make ACP one pluggable runner behind it. ACP is a good interoperability boundary for editor-style agent servers, but Pawrrtal still needs to own the product contract: durable jobs, permissions, artifacts, cancellation, and status.

Use the native Codex runner first because Pawrrtal already has a first-class `openai_codex` provider built around Codex app-server sessions, dynamic tools, and thread persistence. Add ACP and Claude runners behind the same interface after the job layer exists.

## Key Interfaces

Expose three AgentTools:

| Tool | Purpose |
| --- | --- |
| `coding_agent_start` | Start a durable coding job for the active workspace. |
| `coding_agent_status` | Read current status, progress events, summary, and changed files. |
| `coding_agent_cancel` | Cancel a running job. |

`coding_agent_start` accepts:

| Field | Default | Notes |
| --- | --- | --- |
| `task` | required | Natural-language coding task. |
| `runner` | `codex_native` | Later: `claude_sdk`, `acp`. |
| `mode` | `patch` | One of `plan`, `patch`, `apply_workspace`. |
| `allowed_paths` | workspace root | Optional workspace-relative path allowlist. |
| `max_minutes` | configured cap | Hard wall-clock limit. |

Persist each job with:

```text
id, user_id, workspace_id, conversation_id, runner, mode, status,
task, summary, changed_files, error, created_at, started_at, finished_at
```

Store capped event/output records separately so the UI and CLI can show progress without letting a noisy agent fill the database.

## Runner Design

Define a backend runner interface with `start`, `poll/read`, and `cancel`.

`codex_native`:

- Reuse the existing `openai_codex` app-server path.
- Run inside the active workspace root.
- Use workspace-write only for coding jobs that explicitly need file edits.
- Return changed files and a summary; do not commit or push.

`acp`:

- Pawrrtal acts as an ACP client over stdio.
- Launch an ACP agent server such as a Codex or Claude ACP adapter.
- Map ACP session updates to job events.
- Map ACP permission, filesystem, and terminal requests through Pawrrtal's existing permission gate.

`claude_sdk`:

- Prefer Claude Agent SDK for a direct server-side Claude Code runner.
- Set cwd, tools, permissions, and environment explicitly.
- Keep it behind the same durable job contract so the main agent does not care which runner did the work.

## Safety Defaults

- Off by default behind `CODING_AGENT_ENABLED=true`.
- Workspace-root containment is mandatory.
- Secrets are resolved from workspace env and redacted from logs.
- No auto commit, push, destructive delete, or full-access sandboxing in v1.
- Network access is off unless a later setting explicitly enables it.
- Jobs have hard time, output, and event caps.
- Cancellation must terminate the child runner process/session.

## Verification

Add `paw verify coding-agent --json`.

Default verification should use a fake runner so CI can exercise job lifecycle without Codex or Claude auth. Live verification can accept `--runner codex_native` and should:

1. Create a scratch workspace file.
2. Start a tiny deterministic coding task.
3. Poll until completion.
4. Assert status, changed files, and summary.
5. Assert no commit was created.

Add backend tests for:

- Tool exposure gating.
- Start/status/cancel lifecycle.
- Path containment and permission denial.
- Timeout and output cap handling.
- Fake runner event persistence.
- Codex runner availability/auth skip behavior.
- ACP runner protocol mapping with a fake stdio ACP server.

## Sources

- Pawrrtal Codex provider docs: `docs/codex-sdk-provider.md`
- Pawrrtal native Codex implementation: `backend/app/providers/openai_codex/`
- Pawrrtal tool composition: `backend/app/agents/tools.py`
- Active Recall sub-agent precedent: `backend/app/plugins/active_recall/recall_agent.py`
- ACP official docs: https://agentclientprotocol.com/
- Zed external agents docs: https://zed.dev/docs/ai/external-agents
- Codex ACP adapter: https://github.com/zed-industries/codex-acp
- Claude ACP adapter: https://github.com/zed-industries/claude-agent-acp
