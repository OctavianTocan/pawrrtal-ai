---
# pawrrtal-mopa
title: 'Fix workspace .env path: use DB path column instead of UUID directory'
status: completed
type: bug
priority: normal
created_at: 2026-05-19T05:45:12Z
updated_at: 2026-05-19T06:25:57Z
---

Core key functions in keys.py resolve .env path as {base}/{uuid}/.env but workspaces can have custom paths in the DB. Change all key functions to accept workspace_root: Path instead of workspace_id: UUID. ~14 source files, ~50 mechanical renames.

## Summary of Changes\n\nFixed issue #339: workspace .env path now uses the DB  column instead of deriving from UUID.\n\n- : 4 core functions (, , , ) changed from  to \n- :  →  returns full  row; endpoints pass \n- 5 providers + factory:  →  throughout\n- 4 tools/integrations:  calls use \n- , : updated to pass  instead of UUID\n- ~14 source files, ~50 call-site renames\n- New regression test: custom workspace root lands .env at correct path\n- 1235 tests pass, lint clean
