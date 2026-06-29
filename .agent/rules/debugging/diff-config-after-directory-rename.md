---
name: diff-config-after-directory-rename
paths: [".no-match"]
---

# After Renaming Directories, Diff All Config Files to Find Stale Path References

Category: debugging
Tags: [debugging, config, ci, refactoring]

## Rule

After renaming a project directory, explicitly diff build-critical config files against the originals — directory renames silently introduce config regressions.

## Why

When copying or renaming directories (`mobile/` → `react-native/`), config files often drift: missing `CODE_SIGNING_ALLOWED=NO`, dropped `pnpm.onlyBuiltDependencies`, added `reactCompiler: true`, changed `name`/`slug`, dropped `platforms` array. These regressions cause builds to hang, double in duration, or fail with signing errors — and they affect ALL open PRs simultaneously because every branch was created from the old config.

## Verify

"After renaming a directory, did I diff every build-critical config file (package.json, app.json, build scripts) against the original? Did I check for dropped settings, changed names, and stale path references?"

## Patterns

Bad — copy directory without verifying config:

```bash
# Copy directory without verifying config
cp -r brownfield-test/ react-native/
git add react-native/ && git commit -m "rename"
# Missed: CODE_SIGNING_ALLOWED=NO was dropped
# Missed: pnpm.onlyBuiltDependencies was removed
# Result: builds hang for ALL open PRs
```

Good — diff every build-critical file after rename:

```bash
# After rename, diff every build-critical file
git diff HEAD~1:brownfield-test/package.json react-native/package.json
git diff HEAD~1:brownfield-test/app.json react-native/app.json
# Check: scripts, pnpm config, experiments, name/slug/platforms, plugin config
```

## References

- debug-ci-build-hangs skill: Directory rename config drift
- hermes-engine-compat-debugging skill: rename don't split delete + recreate
- Caused ALL PRs to fail simultaneously on one project
