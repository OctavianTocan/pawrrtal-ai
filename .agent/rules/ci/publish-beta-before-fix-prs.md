---
name: publish-beta-before-fix-prs
paths: [".github/workflows/*.{yml,yaml}", "Dockerfile", "**/*.sh"]
---

# Publish a Beta Release Before Merging Fix PRs to Verify the Pipeline Works

Category: ci
Tags: [ci, release, brownfield]

## Rule

Set up beta publish from the development branch BEFORE merging fix PRs — without it, merged fixes have no way to reach native teams for testing.

## Why

Native teams need testable builds to validate fixes. Without a beta publish pipeline, merged fixes sit in a branch with no way to produce artifacts. Ship one fix at a time through beta so you can isolate what helped. The native team's feedback loop is the constraint, not your merge speed.

## Examples

### Bad

```bash
# Merge 3 fix PRs to development, then realize there's no way to publish
gh pr merge fix-1 && gh pr merge fix-2 && gh pr merge fix-3
# Native team: "Can we test it?" You: "...let me set up publishing"
```

### Good

```bash
# 1. Set up beta publish first (auto-triggers on push to development)
# 2. Merge fix #1 → beta auto-publishes → native team tests
# 3. If it works, merge fix #2. If not, iterate on fix #1.
```

## References

- brownfield-aar-native-crash-diagnosis skill: Shipping Fix Builds section
- rn-twinmind-brownfield-ci skill: Beta publish from development

## Verify

"Is there a working beta publish pipeline on the development branch before I merge this fix PR?"

## Patterns

Bad — merging fixes with no publish pipeline:

```bash
# Merge all fixes first, set up publishing later
gh pr merge fix-crash
gh pr merge fix-build
gh pr merge fix-perf
# Native team asks for a test build → scramble to set up publishing
# Can't isolate which fix actually helped
```

Good — publish pipeline ready before any fixes merge:

```bash
# 1. Create publish-android-beta.yml triggered on push to development
# 2. Merge fix-crash → wait for beta publish → native team tests
# 3. Confirmed fix? Merge next PR. Not confirmed? Iterate on fix-crash.
```
