---
name: use-pipefail-with-tee
paths: [".github/workflows/*.{yml,yaml}", "Dockerfile", "**/*.sh"]
---

# Use set -o pipefail When Piping to tee, Not tail -f Workarounds

Category: ci
Tags: [ci, shell, debugging]

## Rule

Use `set -o pipefail` and pipe through `tee` to preserve exit codes — piping xcodebuild through `tail` swallows failures.

## Why

`xcodebuild ... 2>&1 | tail -50` always exits 0 even if xcodebuild failed, because `tail` succeeds. This hides build failures in CI, making the job continue to the next step as if the build passed. Using `set -o pipefail` preserves the first non-zero exit code in the pipeline.

## Examples

### Bad

```bash
# Always exits 0, even if xcodebuild fails
xcodebuild -project MyApp.xcodeproj -scheme MyApp build 2>&1 | tail -80
```

### Good

```bash
# Preserves xcodebuild exit code + captures full log
set -o pipefail
xcodebuild -project MyApp.xcodeproj -scheme MyApp build 2>&1 | tee /tmp/xcodebuild.log | tail -80
```

## References

- brownfield-native-test-hosts skill: iOS CI pitfall #5

## Verify

"Does every pipeline in the workflow use `set -o pipefail`? Will a failure in the first command of any pipeline cause the step to fail?"

## Patterns

Bad — pipeline without pipefail swallows errors:

```bash
# xcodebuild fails but tail succeeds → exit code 0
xcodebuild -scheme MyApp build 2>&1 | tail -80
# CI shows green, but the build actually failed
# Next step tries to upload a .app that doesn't exist
```

Good — pipefail preserves the real exit code:

```bash
set -o pipefail
xcodebuild -scheme MyApp build 2>&1 | tee /tmp/xcodebuild.log | tail -80
# xcodebuild failure → pipeline exits non-zero → CI shows red
# Full log preserved in /tmp/xcodebuild.log for debugging
```
