---
name: increasing-timeout-is-not-the-fix
paths: ["**/*"]
---

# If a Step Times Out, Find the Root Cause - Increasing Timeout Masks the Real Issue

Category: debugging
Tags: [debugging, ci, build]

## Rule

Never bump `timeout-minutes` to fix a slow CI build — find what changed that made it slow.

## Why

A build that normally takes 20 minutes doesn't suddenly need 180 minutes. Bumping the timeout masks the real problem (config regression, cache invalidation, web server bundle deadlock, cold build OOM). Worse, when the timeout is the actual cause of failure (timeout-induced cache starvation loop), bumping it creates an infinite cycle where every build times out, never saves cache, and the next build is also cold.

## Verify

When a build times out: have you identified the root cause rather than just increasing the timeout?

## Patterns

### Pattern (bad)

```yaml
# Build suddenly takes 45 min instead of 20 min
jobs:
  build:
    timeout-minutes: 120  # "Just give it more time"
```

### Pattern (good)

```bash
# Diagnose WHY it's slow — bucket log lines by minute
gh run view $ID --log 2>&1 | grep "build-android" | \
  awk -F'T|Z' '{print $2}' | awk -F: '{print $1":"$2}' | sort | uniq -c
# 0 lines for 60+ min = hung, not slow. Find root cause.
```

## References

- debug-ci-build-hangs skill: Don't use timeout as a diagnostic
- Timeout-induced cache starvation loop pattern
