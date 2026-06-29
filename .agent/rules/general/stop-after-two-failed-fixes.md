---
name: stop-after-two-failed-fixes
paths: ["**/*"]
---

# After 2 Failed Fix Attempts, Stop and Diff Working vs Broken Before Changing More Code

## Rule

After two failed fix attempts, stop changing code. Create a structured comparison between a known-working state and the broken state. Diff the two, identify exactly what changed, then fix only the identified delta.

## Why

Trial-and-error fixes compound. Each failed attempt adds noise. After two failures, you're fighting both the original bug and the side effects of your attempted fixes.

## Process

1. Identify the last known-working commit/version
2. `git diff <working>..<broken> -- <relevant-files>`
3. List every behavioral difference
4. For each difference, determine if it could cause the symptom
5. Fix only the identified cause

## Origin

Recurring pattern across a prior project debugging sessions — structured diagnosis after halt consistently found the root cause within minutes.

## Verify

"Have I tried and failed twice? Am I now diffing working vs broken instead of trying a third guess?"

## Patterns

Bad — third attempt compounds noise:

```text
1. Try fix A → still broken, plus new side effect
2. Try fix B → still broken, plus another side effect
3. Try fix C → now fighting 3 side effects + original bug
// Each attempt makes the state harder to reason about
```

Good — structured comparison after two failures:

```text
1. Try fix A → still broken
2. Try fix B → still broken
3. STOP. git stash. Diff working vs broken.
4. Identify: config value changed from 5000 to 50
5. Fix only that → works
```
