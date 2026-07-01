---
name: stacked-pr-cascade-fixes
paths: [".github/**", "**/*.sh", "**/.git*"]
---

# Stacked PR Cascade Fixes

When you fix something in a base PR of a stack, you must propagate the fix through every PR above it. A fix that only lands in the base breaks all children.

## Rule

If PR #2 in a 5-deep stack gets a bug fix:

1. Apply the fix on #2's branch
2. Rebase #3 onto #2 (or cherry-pick the fix file)
3. Rebase #4 onto #3
4. Continue through the top of the stack
5. Force-push all affected branches

Run the full check suite at the top of the stack to verify nothing broke.

## Why

A biome config fix on one stack level needed to cascade through 6 levels above it. Without propagation, all child PRs failed CI because they inherited the broken config from before the fix. The entire stack had to be rebuilt three times before this pattern was established.

## Verify

"When a fix lands on a middle PR in a stack, have all child PRs above it been rebased or cherry-picked? Did you run CI at the top of the stack to confirm the fix propagated?"

## Patterns

Bad — fix only the base PR, children still carry the bug:

```bash
# Fix applied to PR #2 only
git checkout pr-2
# edit fix, commit, push
# PRs #3, #4, #5 still have the old broken code → all fail CI
```

Good — cascade the fix through the entire stack:

```bash
# Apply fix on PR #2
git checkout pr-2 && git commit -m "fix: biome config" && git push

# Rebase each child onto its updated parent
git checkout pr-3 && git rebase pr-2 && git push --force-with-lease
git checkout pr-4 && git rebase pr-3 && git push --force-with-lease
git checkout pr-5 && git rebase pr-4 && git push --force-with-lease

# Or cherry-pick just the fix commit if a full rebase is too risky
git checkout pr-3 && git cherry-pick <fix-sha> && git push --force-with-lease
```
