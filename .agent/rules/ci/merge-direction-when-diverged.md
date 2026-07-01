---
name: merge-direction-when-diverged
paths: [".github/workflows/*.{yml,yaml}", "Dockerfile", "**/*.sh"]
---

# Merge main INTO development first when branches diverge

## Explanation

When `main` and `development` have different directory structures (e.g., main has `brownfield-test/`, development has `react-native/`), always merge main into development first. Development has the canonical structure and the conflict resolution is clearer: development's paths win, main's deleted files stay deleted, and content changes from main get slotted into development's layout. The reverse merge (development→main) is harder because main's file tree is the old layout.

## Verify

Before merging diverged branches: are you merging the OLD structure INTO the NEW one?

## Patterns

Bad — merge new structure into old:

```bash
# Merge development (new layout) into main (old layout) first
# Creates confusing conflicts where both sides have valid but different paths
git checkout main && git merge development
```

Good — merge old into new:

```bash
# Merge main (old) into development (new) — cleaner resolution
git checkout development && git merge origin/main
# Take development's file structure for conflicts, port main's logic changes
```
