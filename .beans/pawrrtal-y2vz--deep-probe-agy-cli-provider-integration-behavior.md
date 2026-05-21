---
# pawrrtal-y2vz
title: Deep-probe agy CLI provider integration behavior
status: completed
type: task
priority: normal
created_at: 2026-05-21T13:08:54Z
updated_at: 2026-05-21T13:14:28Z
---

Test Antigravity agy CLI behavior needed for a Pawrrtal provider: continuation, workspace access, permission flags, sandbox behavior, cancellation/timeout, stdout framing, log tailing, and configuration/state isolation.



## Summary of Changes

Deep-probed agy CLI behavior needed for provider integration.

Findings:
- Non-interactive print mode works with keyring auth and selects Gemini 3.5 Flash High.
- --add-dir is required for reliable workspace file access; multiple --add-dir values work.
- Conversations can resume with --conversation and --continue, but resumed stdout replays prior printed output before the new answer.
- Unique delimiters can isolate the latest final answer by taking the last marker block.
- --log-file exposes auth/model/conversation/network lifecycle events, but not full assistant text and not every tool detail.
- With current global toolPermission=always-proceed, sandbox mode still allowed reading /etc/hosts and writing /private/tmp outside --add-dir.
- Print timeout and Ctrl-C cancellation return exit code 0 with timeout text, so provider wrappers must detect timeout/cancel themselves.
- Concurrent agy subprocesses worked and used distinct local random ports/conversation IDs.
- Global settings live under ~/.gemini/antigravity-cli; attempted non-mutating app-data env override did not move appDataDir.
- Permission ask-mode testing requires explicit approval to temporarily edit global Antigravity settings and restore it.
