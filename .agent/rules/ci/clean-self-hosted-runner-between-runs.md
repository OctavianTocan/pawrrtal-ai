---
name: clean-self-hosted-runner-between-runs
paths: [".github/workflows/*.{yml,yaml}", "Dockerfile", "**/*.sh"]
---

# Clean Generated Directories Between Runs on Persistent Self-Hosted Runners

## Rule

Self-hosted runners persist state between workflow runs. Always clean generated directories (`ios/`, `android/`, `Pods/`, `node_modules/`, `.expo/`) in a post-checkout step.

## Why

Unlike ephemeral GitHub-hosted runners, self-hosted runners keep the workspace between runs. Stale native directories from a previous build can mask errors or cause conflicts when Expo prebuild expects a clean slate.

## Good

```yaml
- name: Clean generated directories
  run: rm -rf ios android Pods .expo

- name: Install dependencies
  run: pnpm install --frozen-lockfile
```

## Verify

"Does the workflow clean generated directories (`ios/`, `android/`, `Pods/`, `.expo/`) immediately after checkout on self-hosted runners?"

## Patterns

Bad — assuming clean state on self-hosted runners:

```yaml
steps:
  - uses: actions/checkout@v4
  - run: npx expo prebuild --platform ios
    # Fails intermittently: stale ios/ from previous run conflicts
    # CocoaPods may resolve differently with leftover Pods/
```

Good — explicit cleanup after checkout:

```yaml
steps:
  - uses: actions/checkout@v4

  - name: Clean generated directories
    run: rm -rf ios android Pods .expo node_modules

  - name: Install dependencies
    run: pnpm install --frozen-lockfile

  - name: Prebuild
    run: npx expo prebuild --platform ios
```

Good — targeted cleanup in a reusable composite action:

```yaml
# .github/actions/clean-runner/action.yml
runs:
  using: composite
  steps:
    - name: Remove stale generated directories
      shell: bash
      run: rm -rf ios android Pods .expo
```

## Origin

a prior iOS CI on Mac Mini — stale Pods directory from a previous build caused intermittent CocoaPods resolution failures.
