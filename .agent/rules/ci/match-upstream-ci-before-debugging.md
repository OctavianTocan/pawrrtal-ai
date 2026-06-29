---
name: match-upstream-ci-before-debugging
paths: [".github/workflows/*.{yml,yaml}", "Dockerfile", "**/*.sh"]
---

# Match Upstream CI Before Debugging

Before debugging a library integration failure, replicate the library's own CI configuration. If their CI passes, the bug is in your setup, not the library.

## Rule

When a build fails with a third-party library:

1. Find the library's CI workflow (usually `.github/workflows/` in their repo)
2. Compare: runner OS, Xcode version, Node version, package manager version, build commands
3. Match your setup to theirs first
4. Only after matching, investigate remaining differences

## Why

Two days were spent assuming `@callstack/react-native-brownfield` was broken with Xcode 16.4. The library's own CI pinned Xcode 16.3 and passed. Matching the pin fixed the build immediately.

## Verify

"Have I checked the library's CI workflow and matched their tool versions before assuming the library is broken?"

## Patterns

Bad — assuming the library is broken:

```bash
# "The library doesn't support Xcode 16.4"
# Spend 2 days filing issues and trying workarounds
# while the library pins Xcode 16.3 in their CI
```

Good — match upstream CI first:

```bash
# 1. Check the library's .github/workflows/
# 2. Find they pin Xcode 16.3
# 3. Pin your runner to 16.3
# 4. Build succeeds immediately
```
