---
name: concurrency-groups-cancel-in-progress
paths: [".github/workflows/*.{yml,yaml}", "Dockerfile", "**/*.sh"]
---

# Concurrency Groups With Cancel-in-Progress

PR quality workflows must use concurrency groups with `cancel-in-progress: true`. Publish workflows must NOT cancel in progress.

## Rule

```yaml
# Quality gate — cancel stale runs when new push arrives
concurrency:
  group: quality-${{ github.ref }}
  cancel-in-progress: true

# Publish — never cancel mid-release
concurrency:
  group: publish
  cancel-in-progress: false
```

## Why

Without concurrency groups, pushing 3 quick commits to a PR runs 3 full CI pipelines. The first two are wasted. With cancel-in-progress, only the latest commit runs. But publish workflows must never be cancelled mid-run because a half-uploaded artifact corrupts the release.

## Verify

"Does every quality gate workflow have `cancel-in-progress: true`? Does every publish workflow have `cancel-in-progress: false`? Could a stale run waste CI minutes?"

## Patterns

Bad — no concurrency group, stale runs pile up:

```yaml
# quality.yml — no concurrency group
on: pull_request
jobs:
  quality:
    run: pnpm lint && pnpm test
# Push 3 times → 3 parallel runs, first 2 are wasted
```

Good — cancel stale quality runs, protect publish runs:

```yaml
# quality.yml
concurrency:
  group: quality-${{ github.ref }}
  cancel-in-progress: true
# Only the latest commit's run survives

# publish.yml
concurrency:
  group: publish
  cancel-in-progress: false
# Never cancels a publish mid-upload
```
