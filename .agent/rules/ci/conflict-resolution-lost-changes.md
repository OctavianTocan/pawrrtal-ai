---
name: conflict-resolution-lost-changes
paths: [".github/workflows/*.{yml,yaml}", "Dockerfile", "**/*.sh"]
---

# Verify conflict resolution didn't drop changes from either side

## Explanation

When resolving merge conflicts by taking one side's version of a file (`git checkout HEAD -- file`), you may lose changes that only existed on the other side. After the v0.3.2 merge, development's workflow was missing the transitive deps injection because we took development's clean version and lost main's additions. Always diff the resolved file against both parents to verify nothing critical was dropped.

## Verify

After resolving conflicts: did you diff the result against both sides to check for lost changes?

## Patterns

Bad — taking one side wholesale:

```bash
# Take development's version wholesale — silently drops main-only additions
git checkout HEAD -- .github/workflows/publish.yml
git commit
# Missing: transitive deps injection that was only on main
```

Good — take one side then verify against the other:

```bash
# Take development's version as base, then manually port main-only additions
git checkout HEAD -- .github/workflows/publish.yml
# Check what main had that development doesn't
git diff HEAD origin/main -- .github/workflows/publish.yml
# Manually add missing sections
```

Good — systematic verification after resolution:

```bash
# After resolving all conflicts, check for dropped changes
# Compare resolved result against both parents
git diff HEAD...MERGE_HEAD -- .          # What main had that's now missing
git diff MERGE_HEAD...HEAD -- .          # What dev had that's now missing

# For specific files, check both sides
git show HEAD:path/to/file > /tmp/ours
git show MERGE_HEAD:path/to/file > /tmp/theirs
diff tool path/to/file /tmp/ours /tmp/theirs
