# 003 Plan removal-completeness note

The 003 plan should explicitly list all planned removals before the migration starts. Current plan gaps to close:

- Make a **single Removal Completeness Matrix** in `plan.md` before code-deletion PRs.
- Inventory all deprecated auth/session/authz surfaces and require explicit replacements (profiles, tailnet headers, session binding).
- Inventory legacy provider/persisted-state/runtime assumptions that are tied only to removed systems.
- Inventory all deployment/docker compose paths that are to be removed, retained as substrate-only, or replaced.
- Add acceptance evidence per row (build/import/runtime checks) so removals are verifiable, not inferential.

This note is not a spec change by itself; it is a reminder to update the umbrella plan into an explicit removal checklist before Step 6.
