---
name: fail-fast-after-build
paths: [".github/workflows/*.{yml,yaml}", "Dockerfile", "**/*.sh"]
---

# Run Fast Checks (lint, typecheck) After Build Steps to Catch All Errors in One Run

Category: ci
Tags: [ci, debugging, fail-fast]

## Rule

Add a verification step after every non-trivial build operation — each check adds 2 seconds but saves 15 minutes when it catches a failure.

## Why

CI pipelines have long feedback loops. Without fail-fast checks, a broken intermediate output (missing .so files, wrong install names, empty plist values, missing JS bundle in APK) isn't discovered until 10-20 minutes later during E2E or runtime. Verification steps like `otool -L`, `find ~/.m2`, `unzip -l *.apk | grep bundle`, and `maestro hierarchy` catch issues immediately.

## Examples

### Bad

```yaml
# Build → Install → Run E2E. If install names are wrong,
# discover it 15 minutes later via cryptic dyld crash
- name: Build
  run: pnpm run brownfield:package:ios
- name: Run Maestro
  run: maestro test .maestro/
```

### Good

```yaml
- name: Build
  run: pnpm run brownfield:package:ios
- name: Verify install names
  run: |
    for bin in "$APP/"*.dylib "$APP/AppTestHost"; do
      if otool -L "$bin" | grep '/Library/Frameworks/' | grep -qv '/System/Library/'; then
        echo "::error::Absolute framework paths remain!"
        exit 1
      fi
    done
- name: Run Maestro
  run: maestro test .maestro/
```

## References

- Maestro E2E mobile skill: CI Optimization Patterns — otool fail-fast
- brownfield-native-test-hosts skill: fail-fast verification

## Verify

"After each build step, is there a verification that the output is correct? Could a broken intermediate artifact survive undetected for 15+ minutes?"

## Patterns

Bad — build then immediately test with no verification:

```yaml
- name: Build
  run: pnpm run brownfield:package:ios
- name: Run E2E
  run: maestro test .maestro/
  # If dylibs have wrong install names → 15 min of E2E timeouts
  # before the real error is discovered
```

Good — verify build output before expensive steps:

```yaml
- name: Build
  run: pnpm run brownfield:package:ios

- name: Verify install names
  run: |
    for bin in "$APP/"*.dylib "$APP/AppTestHost"; do
      if otool -L "$bin" | grep '/Library/Frameworks/' | grep -qv '/System/Library/'; then
        echo "::error::Absolute framework paths remain!"
        exit 1
      fi
    done

- name: Run E2E
  run: maestro test .maestro/
```
