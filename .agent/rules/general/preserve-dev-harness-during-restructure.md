---
name: preserve-dev-harness-during-restructure
paths: [".no-match"]
---

# When Restructuring a Repo, Preserve the Dev Harness (scripts, configs, test fixtures)

Category: general
Tags: [refactoring, development-environment, brownfield]

## Rule

Verify the replacement directory has dev scripts (`start`, `web`, `ios`), routes, and login harness BEFORE deleting the original — never leave a window where the dev harness is gone.

## Why

A brownfield Expo project is both a standalone dev app AND a brownfield SDK source. If a cleanup PR removes the standalone Expo app shell (routes, tabs, login harness) before porting it to the replacement directory, all local visual testing capability is lost. The brownfield package alone has no routes, no `expo start`, no way to render surfaces. Use `git mv` to rename, not delete + recreate.

## Examples

### Bad

```bash
# PR A: delete old dir (dev harness lost)
git rm -rf mobile/
# PR B: create new dir (no routes, no login)
mkdir react-native/
```

### Good

```bash
# Single PR: rename preserves everything
git mv mobile react-native
git rm -rf brownfield-test/  # Delete redundant subset
```

## References

- hermes-engine-compat-debugging skill: never delete the dev app shell
- a prior project restructure incident: dev harness vanished between PRs

## Verify

"Does the replacement directory have all dev scripts, routes, and login harness before I delete the original? Am I using `git mv` instead of delete + recreate?"

## Patterns

Bad — delete before verifying replacement:

```bash
git rm -rf mobile/
# Now there's no way to run the dev app locally
# Can't visually test brownfield surfaces
# Blocks all visual development until replacement is complete
```

Good — rename preserves everything, then clean up:

```bash
git mv mobile react-native
# Dev harness still works
# Verify all routes and scripts work
# Then remove redundant files
```
