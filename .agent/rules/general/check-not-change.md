---
name: check-not-change
paths: ["**/*"]
---

# Check ≠ Change

When someone says "check X", report what you find. Don't fix, refactor, or modify anything until explicitly asked.

## Rule

- "Check if the tests pass" → run tests, report results
- "Check the brownfield surfaces" → inspect and list them
- "Check the CI status" → report green/red/pending

Do not silently fix issues you discover during a check. Report them and wait for instruction.

## Why

Unexpected changes during a check break trust. The person asking wants information, not action. Making changes during a check can introduce new bugs while the person thinks nothing was modified.

## Verify

"Am I being asked to check or to fix? If I find issues, did I report them before acting?"

## Patterns

Bad — checking turns into unrequested fixing:

```text
"Check if the tests pass"
→ Tests fail
→ Fix the failing tests
→ Push the fix
// Person asked for info, got unexpected code changes
```

Good — report findings, wait for instruction:

```text
"Check if the tests pass"
→ Run tests
→ "3 tests fail: auth.test.ts, api.test.ts, ui.test.ts"
→ Wait for user to decide next steps
```
