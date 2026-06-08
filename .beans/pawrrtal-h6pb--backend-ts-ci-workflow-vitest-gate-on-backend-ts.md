---
# pawrrtal-h6pb
title: backend-ts CI workflow — Vitest gate on backend-ts/**
status: todo
type: feature
priority: high
tags:
    - backend-ts
    - ci
    - github-actions
created_at: 2026-06-08T12:36:02Z
updated_at: 2026-06-08T12:36:02Z
---

## Goal

Add a GitHub Actions workflow that runs the backend-ts Vitest suite on every PR and push that
touches `backend-ts/**`, mirroring the layout of `.github/workflows/tests.yml` (the Python
pytest + frontend Vitest split). Without this gate, regressions on Service trim rules, Repo
SQL, or HTTP 404 mapping can land silently.

## Why now

Slice 1 (tests bean) adds the test suite but it only runs locally. CI parity is the rule
from `AGENTS.md` ("local dev gate is the fast default loop… `bun run typecheck` and
`just check` plus any scoped test you actually need") and from the existing `tests.yml`
header comment. Every new test suite in this repo has a matching workflow — backend pytest
in `tests.yml:backend`, frontend Vitest in `tests.yml:frontend`, backend ruff in
`backend-check.yml`. backend-ts is the only suite without one.

## Files

- `.github/workflows/backend-ts-tests.yml` — new workflow (new file)
- `backend-ts/package.json` — already has `test` script after slice 1; verify
- `justfile` — add `test-backend-ts` recipe; wire into existing `test` target

## Steps

### 1. Create the workflow

Create `.github/workflows/backend-ts-tests.yml` with this body. Mirrors
`.github/workflows/tests.yml:1-65` for the actor gate, self-hosted runner, and PR-failure
comment pattern.

```yaml
name: Backend-TS Tests

# Mirrors tests.yml but for the Effect TS strangler in backend-ts/.
# Runs @effect/vitest on apps/api + packages/api-core.

on:
  pull_request:
    branches: [development, main]
    paths:
      - 'backend-ts/**'
      - 'bun.lock'
      - 'backend-ts/bun.lock'
      - '.github/workflows/backend-ts-tests.yml'
  push:
    branches: [development, main]
    paths:
      - 'backend-ts/**'
      - 'bun.lock'
      - 'backend-ts/bun.lock'
      - '.github/workflows/backend-ts-tests.yml'

permissions:
  contents: read
  pull-requests: write

concurrency:
  group: backend-ts-tests-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  vitest:
    name: backend-ts Vitest
    if: >-
      (github.actor == 'OctavianTocan' || github.actor == 'octagent') &&
      (github.event_name != 'pull_request' ||
        github.event.pull_request.head.repo.full_name == github.repository)
    runs-on: [self-hosted, pawrrtal]
    timeout-minutes: 10
    steps:
      - name: Checkout repository
        uses: actions/checkout@v6.0.2
        with:
          submodules: recursive

      - name: Setup Bun
        uses: oven-sh/setup-bun@v2
        with:
          bun-version: latest

      - name: Setup Node
        uses: actions/setup-node@v6.4.0
        with:
          node-version: '22'

      - name: Install dependencies
        run: bun install --frozen-lockfile

      - name: Run @effect/vitest
        working-directory: backend-ts
        id: test
        run: |
          set +e
          bun run test 2>&1 | tee ../backend-ts-test-output.txt
          status=${PIPESTATUS[0]}
          {
            echo 'output<<EOF'
            cat ../backend-ts-test-output.txt
            echo 'EOF'
          } >> "$GITHUB_OUTPUT"
          exit "$status"

      - name: Comment PR on failure
        if: failure() && github.event_name == 'pull_request'
        uses: actions/github-script@v9
        env:
          TEST_OUTPUT: ${{ steps.test.outputs.output }}
        with:
          script: |
            const output = process.env.TEST_OUTPUT || '';
            const body = [
              '### `backend-ts` Vitest failed',
              '',
              'Reproduce locally with `cd backend-ts && bun run test`.',
              '',
              '<details><summary>output (last 6000 chars)</summary>',
              '',
              '```',
              output.slice(-6000),
              '```',
              '',
              '</details>',
            ].join('\n');
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body,
            });
```

### 2. Wire into `just`

Edit `justfile`. The existing `test` recipe is:

```just
# Run both suites. Use before pushing — local + CI parity (#271).
test: test-backend test-frontend
```

Add a new recipe and update `test`:

```just
# Run backend-ts Vitest suite (CI-style, no watcher)
test-backend-ts:
    cd backend-ts && bun run test

# Run all three suites. Use before pushing — local + CI parity (#271).
test: test-backend test-backend-ts test-frontend
```

Match the style of the surrounding `test-backend` and `test-frontend` recipes (single-line
description, single command line). Keep alphabetical-ish order: `test-backend`,
`test-backend-ts`, `test-frontend`.

## Rules

- **Do not** widen the actor gate beyond `OctavianTocan || octagent` (matches
  `.github/workflows/tests.yml:42-44` and the rule in
  `.claude/rules/github-actions/octaviantocan-only-and-self-hosted-runner.md`).
- **Do not** add a coverage gate. v8 reports stay local; CI just runs the suite.
- **Do not** add a `pull_request_target` trigger. This workflow runs user code under
  `bun run test`; per the safe-PR-target rule, that's only safe on `pull_request`.
- Runner stays `[self-hosted, pawrrtal]` — matches every other test workflow in the repo.

## Local gate before committing

```bash
# Sanity-check the workflow file parses
yamllint .github/workflows/backend-ts-tests.yml  # optional, project doesn't gate on it
# Confirm justfile still parses
just --list | grep -E "test-(backend|frontend)"
```

## Out of scope

- Coverage threshold (deferred; matches existing backend/frontend policy).
- Integration tests against a real Effect TS server (Phase D; until then the unit +
  HTTP-client tests in slice 1 are the only signal).
- Postgres / Railway deploy smoke (Phase D-3).
