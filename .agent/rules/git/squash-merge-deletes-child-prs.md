---
name: squash-merge-deletes-child-prs
paths: ["**/*"]
---

# Squash-Merging a Base Branch Auto-Closes Downstream PRs - Retarget Children First

## Rule

When squash-merging a stacked PR with `--delete-branch`, GitHub auto-closes all downstream PRs that target the deleted branch. Those PRs cannot be reopened through the UI if the branch no longer exists.

## Why

GitHub detects the base branch deletion and marks downstream PRs as "closed" with reason "head branch was deleted" or "base branch was deleted." The PR shows as closed and grayed out.

## Fix

Before squash-merging any PR in a stack:

1. Retarget all child PRs to a surviving branch (usually the parent's base)
2. Only then merge with `--delete-branch`

If you already deleted the branch:

1. `git push origin <branch-name>` to recreate it
2. Use the REST API to reopen: `gh api repos/{owner}/{repo}/pulls/{number} -f state=open`
3. Retarget to the correct base
4. Rebase onto the new base (squash commits have different SHAs)

## Origin

pawrrtal stacked PRs #78-#83 — merging #78 with --delete-branch auto-closed #79 and #80. Required branch recreation via git push and API reopening.

## Verify

"Before squash-merging with `--delete-branch`, have all child PRs been retargeted to a surviving base branch? Are there any downstream PRs still pointing at the branch being deleted?"

## Patterns

Bad — merge with delete-branch while children still target it:

```bash
gh pr merge 78 --squash --delete-branch
# PRs #79, #80 auto-close because their base branch was deleted
```

Good — retarget children first, then merge:

```bash
# 1. Retarget children to parent's base (e.g. main)
gh pr edit 79 --base main
gh pr edit 80 --base main

# 2. Now safe to squash-merge with branch deletion
gh pr merge 78 --squash --delete-branch

# 3. Rebase children onto new base to pick up the squash commit
git checkout branch-79 && git rebase main && git push --force-with-lease
```
