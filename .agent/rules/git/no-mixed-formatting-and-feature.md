---
name: no-mixed-formatting-and-feature
paths: [".github/**", "**/*.sh", "**/.git*"]
---

# No Mixed Formatting and Feature Changes

Never mix formatting/linting changes with feature changes in a single PR. If a file needs reformatting, do it in a separate commit or PR before the feature work.

**Why:** Formatting changes create massive diffs that obscure the actual logic change. Reviewers skip over reformatted lines and miss bugs. Blame history becomes useless.

**Learned from:** Code review corrections (Sourcery feedback).

## Verify

"Does this PR mix formatting changes with feature changes? Should formatting be in a separate PR?"

## Patterns

Bad — formatting + feature in same PR:

```bash
# PR: "feat: add user profile"
# 500 line diff: 480 lines are auto-formatting, 20 are actual feature
# Reviewer can't find the real changes
# Blame points to formatting commit, not the feature commit
```

Good — separate PRs for formatting and feature:

```bash
# PR 1: "chore: format auth module" (auto-merge)
# PR 2: "feat: add user profile" (20 line diff, clean review)
# Blame history is meaningful
```
