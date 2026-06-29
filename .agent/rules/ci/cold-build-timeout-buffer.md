---
name: cold-build-timeout-buffer
paths: [".github/workflows/*.{yml,yaml}", "Dockerfile", "**/*.sh"]
---

# Set 180-Minute Timeout for Cold Native Builds Without Cache

Cold dual-arch native builds (iOS + Android without cache) require a minimum 180-minute timeout. 120 minutes is insufficient.

## Rule

When CI runs a full native build without build caches (first run, cache miss, new runner), the build takes significantly longer than cached incremental builds. iOS framework compilation + Android AAR from scratch regularly exceeds 120 minutes. Set `timeout-minutes: 180` and adjust downward only after collecting cache-hit timing data.

## Why

The first cold iOS build on a Mac Mini took 56 minutes, Android AAR took 26 minutes. Combined with prebuild, pod install, and dependency resolution, total wallclock exceeded 120 minutes. Builds killed at the timeout leave no artifacts and waste the entire run.

## Verify

"Does the workflow set `timeout-minutes: 180` for jobs that do full native builds? Have you verified the timeout is sufficient after observing a cold run?"

## Patterns

Bad — default timeout kills cold builds:

```yaml
jobs:
  build:
    runs-on: self-hosted
    # Default timeout is 360 minutes but other jobs may set lower
    steps:
      - run: npx expo prebuild --platform ios
      - run: ./gradlew assembleRelease
  # If another job has timeout-minutes: 120, the cold build dies at 120 min
```

Bad — assuming cached timing applies to cold builds:

```yaml
jobs:
  build-ios:
    timeout-minutes: 90
    # Works fine when Gradle cache hits (30 min total)
    # First cold build: 56 min iOS alone + prebuild = exceeds 90 min
```

Good — generous timeout with separate fast-path for cached builds:

```yaml
jobs:
  build:
    runs-on: self-hosted
    timeout-minutes: 180
    steps:
      - uses: actions/checkout@v4

      - name: Restore build caches
        uses: actions/cache@v4
        with:
          path: |
            ~/Library/Developer/Xcode/DerivedData
            ~/.gradle/caches
          key: native-build-${{ hashFiles('package-lock.json') }}

      - name: Build
        run: |
          npx expo prebuild --platform ios
          # Cold: ~56 min, Cached: ~15 min
          # timeout-minutes: 180 handles both cases
