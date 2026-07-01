---
name: three-dot-diff-for-patches
paths: ["**/*.sh", ".github/**"]
---
# Use Three-Dot Diff for Generating Patches

`git diff base..head` (two dots) shows the symmetric difference — ALL changes between the two commits, including commits on `base` that `head` doesn't have. This produces patches that include unrelated changes from `main` since the branch diverged.

`git diff base...head` (three dots) shows only the changes introduced by `head` since it diverged from `base`. This is almost always what you want when generating a patch, reviewing a PR, or producing a changeset.

The same applies to `git log`: `git log base...head` shows commits on either side, while `git log base..head` shows commits reachable from head but not base (which IS what you usually want for log — note the semantics are swapped compared to diff).

## Verify

"Am I generating a diff of what this branch changed? If so, am I using three dots (base...head)?"

## Patterns

Bad — two-dot diff includes unrelated changes from base:

```bash
# main has had 50 commits since you branched
git diff main..feature-branch > changes.patch
# Patch includes reverse of 50 main commits + your changes
```

Good — three-dot diff shows only branch changes since divergence:

```bash
git diff main...feature-branch > changes.patch
# Patch includes only commits introduced by feature-branch
```

Good — explicit merge-base for scripts that need clarity:

```bash
MERGE_BASE=$(git merge-base main feature-branch)
git diff "$MERGE_BASE" feature-branch > changes.patch
# Equivalent to three-dot, but explicit
```
