---
name: test-isolation-ephemeral
paths: ["**/*.test.ts", "**/*.test.tsx", "**/*.spec.ts", "**/*.spec.tsx"]
---

# Test Isolation: Fully Ephemeral

Tests must be fully ephemeral and self-contained:

- Leave no trace (no leftover data, no dangling resources)
- Never modify existing workspace/production content
- Create dedicated test fixtures (parent pages, temp directories) in beforeAll
- Clean up in afterAll, even on failure
- Each test file gets its own isolated scope

**Why:** Tests that leak state cause flaky failures in other test files. Tests that modify production data are dangerous and non-repeatable. Ephemeral tests can run in any order, in parallel, and on any environment.

**Learned from:** openclaw-notion — Vitest test architecture with createTestParent() pattern.

## Verify

- Run tests in isolation: each test file passes alone and in parallel with others
- Confirm no leftover data: run tests multiple times in a row, verify consistent behavior
- Verify cleanup: check that afterAll runs even when tests fail (use `vitest --bail` to simulate failures)
- Confirm no production modification: grep for direct writes to production paths or shared state

## Patterns

- **beforeAll/create pattern:** Create all test fixtures once in `beforeAll`, store in a shared variable, clean up in `afterAll`
- **Unique naming:** Use UUIDs or timestamps for fixture names to avoid collisions when tests run in parallel
- **Explicit cleanup even on failure:** Wrap cleanup in `finally {}` within `afterAll` to ensure it runs regardless of test outcomes
