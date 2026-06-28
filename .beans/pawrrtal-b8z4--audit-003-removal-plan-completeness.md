---
# pawrrtal-b8z4
title: Audit 003 Plan for complete removals
status: in-progress
type: task
priority: high
tags:
  - plan
  - architecture
  - migration
created_at: 2026-06-28T00:00:00Z
updated_at: 2026-06-28T00:00:00Z
---

## Goal
Capture every obsolete auth, runtime, and subsystems-removal item in the 003 overhaul plan before implementation proceeds, so no unused code path is accidentally retained because it was never explicitly listed.

## Files
- `specs/003-pawrrtal-overhaul/plan.md`
- `specs/003-pawrrtal-overhaul/spec.md`
- `specs/003-pawrrtal-overhaul/research.md`

## Steps
1. Enumerate all currently deprecated or replaced systems (auth/session stack, provider adapters, permission and workspace systems, compose/runtime paths, and dead UI/auth flow surfaces).
2. Add a locked “Removal Completeness Matrix” section to the plan listing each removal and the file-level replacement path.
3. Add a corresponding acceptance scenario for each removal row (import/build/runtime behavior proves the old path is no longer active).
4. Cross-link that section from the sequencing roadmap and from Step 4 (dead-weight removal).
5. Track this bean as complete only after `specs/003-pawrrtal-overhaul/plan.md` has an explicit table of removals and owners.

## Safety rule
**Off by default:** avoid deleting production files until each removal row has a replacement strategy and a validation step.
