---
name: binary-search-error-origin
paths: [".github/**", "**/*.sh"]
---
# Binary Search for the Earliest Failing PR in a Stack

When a stack of PRs (A → B → C → D) has a failing CI check on the top branch, don't start fixing from the top. The failure likely originates in an earlier PR, and fixing it at the top means the fix will conflict when the earlier PRs are merged.

Find the earliest failing PR by checking out each branch in the stack and running the failing check locally. Once you find the PR that introduced the failure, fix it there, then rebase all downstream branches. This prevents fix conflicts and keeps each PR's diff clean.

This is the same principle as `git bisect` but applied to a PR stack. The cost of running CI locally 3-4 times is much less than the cost of fixing in the wrong place and having to redo the fix.

## Verify

"Is this CI failure actually introduced in this PR, or did it come from an earlier PR in the stack?"

## Patterns

Bad — fix at the top of the stack:

```bash
# CI fails on feature-d (top of stack A → B → C → D)
git checkout feature-d
# Fix the typecheck error here
git commit -m "fix: resolve type error"
git push --force origin feature-d
# ❌ When feature-b is merged, this fix conflicts
```

Good — find the earliest failure and fix there:

```bash
# CI fails on feature-d. Binary search the stack:
git checkout feature-b && pnpm typecheck  # ✅ passes
git checkout feature-c && pnpm typecheck  # ❌ fails
# feature-c introduced the error. Fix here:
git checkout feature-c
# ... apply fix ...
git commit -m "fix: resolve type error in renamed import"
git push --force origin feature-c
# Rebase downstream
git checkout feature-d && git rebase feature-c
git push --force origin feature-d
```
