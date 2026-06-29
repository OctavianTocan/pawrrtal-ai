---
name: retarget-before-merge
paths: [".github/**", "**/*.sh"]
---
# Retarget Child PR Before Merging Parent in a Stack

When squash-merging stacked PRs, the child PR's base branch is the parent PR's branch. If you merge and delete the parent branch first, GitHub sees the child PR's base branch as gone and **auto-closes** the child PR. Closed PRs whose base branch no longer exists cannot be reopened — the "Reopen" button is grayed out.

This is a silent data loss scenario: the child PR's review comments, approvals, and CI history are effectively orphaned. You have to create a new PR from the same branch, losing all context.

Always retarget the child PR to `main` (or the parent's target) BEFORE merging the parent. GitHub UI: PR → Edit → change base branch. GitHub CLI: `gh pr edit --base main`.

## Verify

"Before merging this PR, are there child PRs targeting this branch? Have I retargeted them first?"

## Patterns

Bad — merge parent first, child PR auto-closes:

```bash
# Parent PR: feature-a → main
# Child PR: feature-b → feature-a
gh pr merge feature-a --squash --delete-branch
# feature-a branch deleted
# feature-b PR is auto-closed by GitHub — cannot reopen
```

Good — retarget child, then merge parent:

```bash
# Retarget child PR from feature-a to main
gh pr edit feature-b --base main
# Now safe to merge parent
gh pr merge feature-a --squash --delete-branch
# feature-b PR remains open, now targeting main
```
