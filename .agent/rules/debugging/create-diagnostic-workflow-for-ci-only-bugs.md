---
name: create-diagnostic-workflow-for-ci-only-bugs
paths: [".github/workflows/**"]
---

# Bugs That Only Reproduce in CI Get a Dedicated Diagnostic Workflow, Not Guesswork

Category: debugging
Tags: [debugging, ci, remote]

## Rule

When a failure only reproduces in CI, ship a standalone diagnostic workflow with labeled theory-testing steps — don't trace source code locally.

## Why

Spending 30 minutes reading source code and forming theories about a CI-only failure is wasteful when the environment differs (different Xcode, prebuilt binaries, different module maps). A standalone `diag-*.yml` workflow with labeled steps (T1/T2/T3) that each log proves or disproves a specific theory answers in one CI run what local reading cannot. Delete the diagnostic workflow after diagnosis.

## Verify

"When a bug only reproduces in CI, did I create a dedicated diagnostic workflow with labeled theory-testing steps instead of guessing locally?"

## Patterns

Bad — reading source locally when the bug is CI-only:

```bash
# Reading source locally when the bug is CI-only
cat node_modules/@callstack/react-native-brownfield/ios/ReactBrownfield.swift
# Form theory from training data... push speculative fix... fail... repeat
```

Good — diagnostic workflow with labeled theories:

```yaml
# diag-issue-name.yml — standalone throwaway workflow
- name: "T1: Check if prebuilt pods have module maps"
  if: always()
  run: find Pods -name "*.*.modulemap" | head -20

- name: "T2: Check ReactBrownfield build intermediates"
  if: always()
  run: ls -la ios/.brownfield/package/build/

- name: "T3: Compare clang versions"
  if: always()
  run: clang --version && xcodebuild -version
```

## References

- systematic-debugging skill: Phase 1.4b — When You Can't Reproduce Locally
- rn-twinmind-brownfield-ci skill: Diagnostic CI pattern
