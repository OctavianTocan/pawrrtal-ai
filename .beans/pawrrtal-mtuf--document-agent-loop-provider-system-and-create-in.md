---
# pawrrtal-mtuf
title: Document agent loop provider system and create in-depth examples
status: completed
type: task
priority: normal
created_at: 2026-05-21T20:14:38Z
updated_at: 2026-05-21T20:20:45Z
---

Add documentation for how the actual provider stuff works in backend/app/core/agent_loop/README.md, and make the examples more in-depth and broken up into sections.



## Summary of Changes

- Created [README.md](file:///Volumes/WorkDriveExternal/Projects/Personal/Pawrrtal-Two-Ai/Pawrrtal-AI/backend/app/core/providers/README.md) in the `backend/app/core/providers/` directory with a comprehensive architectural overview of the provider system.
- Documented the `resolve_llm` resolution pipeline, catalog mechanics, and `ParsedModelId` parsing.
- Detailed the design rationale for using wire-format strings (`[host:]vendor/model`) instead of hardcoded Python constants.
