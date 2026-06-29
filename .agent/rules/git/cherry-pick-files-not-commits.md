---
name: cherry-pick-files-not-commits
paths: [".github/**", "**/*.sh", "**/.git*"]
---

# Cherry-Pick Files, Not Commits

When building stacked PRs, cherry-pick specific files from the source branch rather than cherry-picking entire commits. This avoids dragging in unrelated changes.

## Rule

```bash
# Instead of: git cherry-pick <commit-hash>
# Do this:
git checkout source-branch -- path/to/file1.ts path/to/file2.ts
git add -A && git commit -m "feat: description"
```

Precise control over which files land in each stack level. Full commit cherry-picks bring along formatting changes, unrelated fixes, and config tweaks that pollute the diff.

## Why

A stacked PR chain (#40-#48) was rebuilt three times. The first attempt used commit cherry-picks, which brought cascading merge conflicts. Switching to file-level cherry-picks made each rebuild clean and predictable.

## Verify

"Am I cherry-picking entire commits or specific files? Could the commit contain unrelated changes that pollute the diff?"

## Patterns

Bad — cherry-pick commit brings unrelated changes:

```bash
git cherry-pick abc123
# Commit contains 3 formatting changes + 1 bug fix + 2 config tweaks
# Only need the bug fix — the rest pollute the PR diff
```

Good — cherry-pick specific files:

```bash
git checkout source-branch -- src/fix.ts
git add -A && git commit -m "fix: specific bug"
# Only the file you need, clean diff
```
