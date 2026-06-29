---
name: empty-commit-retrigger-ci
paths: [".github/**", "**/*.sh", "**/.git*"]
---

# Empty Commit to Retrigger CI

When CI doesn't trigger (queue saturation, webhook failure, or GitHub glitch), push an empty commit to force a new run.

## Rule

```bash
git commit --allow-empty -m "ci: retrigger checks"
git push
```

## Why

GitHub Actions occasionally fails to trigger on push events, especially during runner saturation (10+ concurrent runs). An empty commit is the fastest way to force a new workflow run without modifying code.

## Verify

"Did CI fail to trigger? Can I retrigger with an empty commit instead of making a code change?"

## Patterns

Bad — make a trivial code change just to trigger CI:

```bash
# Add a comment to trigger CI
echo "// trigger" >> src/index.ts
git add -A && git commit -m "trigger ci"
# Unnecessary code change in the diff
```

Good — empty commit retriggers cleanly:

```bash
git commit --allow-empty -m "ci: retrigger checks"
git push
# CI retriggered with no code changes
```
