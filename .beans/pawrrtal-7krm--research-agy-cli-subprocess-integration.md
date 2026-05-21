---
# pawrrtal-7krm
title: Research agy CLI subprocess integration
status: completed
type: task
priority: normal
created_at: 2026-05-21T13:03:05Z
updated_at: 2026-05-21T13:08:28Z
---

Probe Antigravity agy CLI programmatic behavior: non-interactive execution, cwd/workspace handling, logs, session continuation, state files, timeout/cancellation, and integration fit for Pawrrtal.



Probe summary: Mapped agy CLI subprocess behavior. --print works for one-shot execution; --add-dir is required for reliable workspace file access; keyring auth uses Antigravity/Code Assist and selects Gemini 3.5 Flash High; --conversation and --continue resume sessions; --log-file contains conversation/model/network/tool events; print timeouts return exit 0 with timeout text.
