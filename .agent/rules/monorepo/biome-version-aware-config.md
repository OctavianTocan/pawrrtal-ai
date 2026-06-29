---
name: biome-version-aware-config
paths: ["**/package.json", "pnpm-workspace.yaml", "pnpm-lock.yaml"]
---

# Biome Version-Aware Config

Before adding Biome linting rules, check the documentation for your installed version. Nursery rules are unstable and frequently move, rename, or get removed between releases.

## Rule

1. Check installed version: `npx biome --version`
2. Reference docs for that version, not latest
3. Avoid adding rules from the `nursery` group unless you pin the exact Biome version
4. If a rule doesn't exist in your version, Biome fails silently or with a cryptic "unknown rule" error

## Why

Adding `reactnative` domain rules and nursery rules that existed in Biome docs but not in the installed version produced an invalid config. The error message didn't clearly identify which rules were the problem. Cost an hour of debugging across a stacked PR chain.

## Verify

"Before adding a Biome rule, did you check `npx biome --version` and confirm the rule exists in that version's docs? Are you avoiding nursery rules or pinning the exact Biome version if you use them?"

## Patterns

Bad — adding rules from latest docs without checking version:

```json
{
  "linter": {
    "rules": {
      "nursery": {
        "useExhaustiveDependencies": "warn"
      }
    }
  }
}
```

Good — check version, then reference correct docs:

```bash
# 1. Check what's installed
npx biome --version
# → 1.7.3

# 2. Reference docs for 1.7.3, not latest
# https://biomejs.dev/linter/rules/?version=1.7.3

# 3. Pin Biome version if using nursery rules
# package.json: "@biomejs/biome": "1.7.3"
```
