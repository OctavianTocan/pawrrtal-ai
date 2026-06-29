---
name: update-workflow-paths-after-directory-rename
paths: [".github/workflows/*.{yml,yaml}", "Dockerfile", "**/*.sh"]
---

# After Renaming Directories, Update All workflow paths: and working-directory: References

When a repo restructure renames or moves directories (e.g., `mobile/` → `react-native/`, `brownfield-test/` → `react-native/`), every GitHub Actions workflow that references the old path must be updated in the same merge or immediately after.

## What breaks

- **`paths:` trigger filters** — pushes to `react-native/**` won't match `brownfield-test/**`, so publish workflows silently stop triggering
- **`working-directory:`** — job steps fail with "directory not found" or cryptic tool errors (pnpm returning garbage store paths, Gradle not finding build files)
- **`cache-dependency-path:`** — `setup-node` with `cache: pnpm` resolves the store path from the lockfile location; a missing lockfile produces `pnpm store path --silent` → garbage path → `Error: Some specified paths were not resolved, unable to cache dependencies`
- **`hashFiles()` in cache keys** — hashing non-existent files returns empty strings, so every run gets a cache miss

## Checklist after directory rename

1. `grep -rn 'old-dir-name' .github/workflows/` — find all references
2. Update `paths:` triggers, `working-directory:`, `cache-dependency-path:`, `hashFiles()` args, and any hardcoded paths in `run:` scripts
3. Update release notes templates that reference the old directory name
4. Push the workflow fix, then **cancel any already-queued runs** — they evaluate the OLD workflow version (see stale-workflow-after-push)
5. Trigger a fresh run via `gh workflow run` to pick up the new paths

## Why cancel + re-dispatch

GitHub evaluates workflow files at the commit that triggered the run, not the latest on the branch. A merge commit triggers a publish run using the pre-merge workflow file. Even if you push a fix one second later, the queued run still has the old paths. Cancel it and dispatch fresh.

## Verify

"Did I grep for the old directory name across all workflow files? Are there any queued runs that still reference the old paths?"

## Patterns

Bad — rename directory without updating workflows:

```bash
# Renamed mobile/ → react-native/ but forgot workflows
git mv mobile/ react-native/
git commit -m "rename mobile to react-native"
git push
# publish-android.yml still has paths: ["mobile/**"] → never triggers
# quality.yml still has working-directory: mobile → "directory not found"
```

Good — update all workflow references in the same commit:

```bash
git mv mobile/ react-native/
# Update all workflow references
sed -i 's|mobile/|react-native/|g' .github/workflows/*.yml
grep -rn 'mobile/' .github/workflows/  # Verify nothing remains
git add .github/workflows/
git commit -m "rename mobile to react-native + update workflows"
# Cancel stale queued runs, then dispatch fresh
gh run cancel $(gh run list --limit 1 --json databaseId -q '.[0].databaseId')
```
