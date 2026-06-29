---
name: serialize-jobs-on-single-runner
paths: [".github/workflows/*.{yml,yaml}", "Dockerfile", "**/*.sh"]
---

# Serialize Jobs When Using a Single Self-Hosted Runner to Prevent Queue Deadlock

Category: ci
Tags: [ci, github-actions, self-hosted, runner]

## Rule

Use `needs:` with `if: always()` to serialize CI jobs on a single self-hosted runner. Never rely on implicit queue ordering.

## Why

Two jobs targeting the same self-hosted runner without `needs:` can race on the filesystem. Even though GitHub Actions queues them on a single runner, adding a second runner later (or GitHub scheduling quirks) can cause workspace collisions. `needs: job-a` with `if: always()` serializes execution while still running the dependent job when the first fails.

## Examples

### Bad

```yaml
e2e-ios:
  runs-on: [self-hosted, macmini]
e2e-android:
  runs-on: [self-hosted, macmini]  # May race with iOS
```

### Good

```yaml
e2e-ios:
  runs-on: [self-hosted, macmini]
e2e-android:
  needs: e2e-ios
  if: always()  # Run even if iOS failed
  runs-on: [self-hosted, macmini]
```

## References

- a prior E2E project: iOS simulator and Android emulator contend on same Mac Mini

## Verify

"Do parallel jobs on the same self-hosted runner use `needs:` to serialize? Does the dependent job use `if: always()` to run even when the first fails?"

## Patterns

Bad — parallel jobs on single runner without serialization:

```yaml
jobs:
  e2e-ios:
    runs-on: [self-hosted, macmini]
    steps:
      - run: xcodebuild test
  e2e-android:
    runs-on: [self-hosted, macmini]
    steps:
      - run: ./gradlew connectedAndroidTest
    # Both jobs may start simultaneously on the same machine
    # iOS simulator + Android emulator = OOM and filesystem races
```

Good — serialized with `needs:` and `if: always()`:

```yaml
jobs:
  e2e-ios:
    runs-on: [self-hosted, macmini]
    steps:
      - run: xcodebuild test
  e2e-android:
    needs: e2e-ios
    if: always()  # Still runs if iOS job fails
    runs-on: [self-hosted, macmini]
    steps:
      - run: ./gradlew connectedAndroidTest
```
