---
name: separate-publish-from-quality
paths: [".github/workflows/*.{yml,yaml}", "Dockerfile", "**/*.sh"]
---

# Isolate Publish Workflows From PR Quality Gates

Publishing native artifacts (AAR, XCFramework, npm packages) must run in dedicated workflows, isolated from PR quality gates.

## Rule

Quality gate workflows (`quality.yml`) run on every PR push and must be fast (<5 min). Publish workflows (`publish-android.yml`, `publish-ios.yml`) run on release events or manual dispatch, are slow (25-60 min), and produce artifacts. Never combine them.

## Why

Mixing publish steps into quality gates means every PR push triggers a 30-minute native build. Developers stop pushing small commits because each push costs 30 minutes of CI. Separate workflows let quality checks stay fast while publish runs only when needed.

## Verify

"Are publish and quality gate steps in separate workflow files? Does every PR push complete in under 5 minutes?"

## Patterns

Bad — publish mixed into quality gate:

```yaml
# quality.yml — runs on every PR push
on: pull_request
jobs:
  quality:
    steps:
      - run: pnpm lint
      - run: pnpm test
      - run: ./gradlew assembleRelease  # 25 min native build on every PR!
      - run: ./gradlew publishToMaven   # Publish on every PR push!
```

Good — separate workflows:

```yaml
# quality.yml — fast feedback on every PR
on: pull_request
jobs:
  lint:
    steps:
      - run: pnpm lint
  test:
    steps:
      - run: pnpm test

# publish-android.yml — only on release or manual trigger
on:
  push:
    tags: ['v*']
  workflow_dispatch:
jobs:
  publish:
    steps:
      - run: ./gradlew assembleRelease
      - run: ./gradlew publishToMaven
```
