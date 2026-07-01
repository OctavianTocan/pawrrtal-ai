---
name: conventional-commits
paths: [".github/**", "**/*.sh", "**/.git*"]
---

# Use Conventional Commit Format With Atomic Single-Logical-Change Commits

Use conventional commit format: `fix:`, `feat:`, `refactor:`, `chore:`, `test:`, `docs:`, `ci:`. Keep commits small and atomic. Each commit should represent one logical change.

**Why:** Conventional commits enable automatic changelog generation, semantic versioning, and filtered history searches. Small commits make bisect useful. Atomic commits make revert safe.

**Learned from:** Multi-repo convention across the vendored app, pawrrtal, tap, openclaw plugins.

## Verify

"Do my commits use conventional prefixes? Does each commit represent exactly one logical change?"

## Patterns

Bad — vague, multi-concern commits:

```bash
git commit -m "stuff"
git commit -m "fix bugs and update deps"
# Can't generate changelog, can't bisect, can't revert safely
```

Good — conventional, atomic commits:

```bash
git commit -m "fix: resolve auth token refresh race condition"
git commit -m "chore: bump react-native to 0.76.2"
# Changelog auto-generated, bisect works, revert is safe
```
