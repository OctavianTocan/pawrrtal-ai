---
name: ci-quality-gate-order
paths: [".github/workflows/*.{yml,yaml}"]
---
# Run CI Quality Gates in Order: Lint → Typecheck → Test → Build

Structure CI checks in order of speed and blast radius. Format/lint runs in seconds and catches the most common issues. Typecheck catches logic errors without running code. Unit tests catch runtime behavior. Build catches integration issues.

Each gate should be a separate CI step (or job) so that when something fails, the developer sees exactly which gate failed without scrolling through logs. If lint and typecheck are combined into one step, a type error is buried under 200 lines of lint output.

Running faster checks first also saves CI minutes: if lint fails in 5 seconds, there's no point running a 10-minute build. Use job dependencies (`needs:`) to enforce ordering and early termination.

## Verify

"Are my CI checks ordered from fastest to slowest? Is each check a separate step with a clear name?"

## Patterns

Bad — everything in one step:

```yaml
jobs:
  ci:
    steps:
      - run: |
          pnpm lint
          pnpm typecheck
          pnpm test
          pnpm build
        # If typecheck fails, you still wait for lint output to scroll past
        # If lint fails, you still wait for the step to finish
```

Good — separate jobs with dependencies:

```yaml
jobs:
  lint:
    steps:
      - run: pnpm lint
      # ~5 seconds, catches formatting + import issues

  typecheck:
    needs: lint
    steps:
      - run: pnpm typecheck
      # ~15 seconds, catches type errors

  test:
    needs: typecheck
    steps:
      - run: pnpm test
      # ~30 seconds, catches runtime behavior

  build:
    needs: test
    steps:
      - run: pnpm build
      # ~2 minutes, catches integration issues
```
