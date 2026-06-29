---
name: verify-artifacts-exist-before-testing
paths: [".github/workflows/*.{yml,yaml}", "Dockerfile", "**/*.sh"]
---

# Verify Build Artifacts Exist and Are Non-Empty Before Running Tests Against Them

Category: ci
Tags: [ci, e2e, fail-fast, ios, android]

## Rule

Add verification steps after build and before test that assert secrets, bundles, and config are present in the built artifact.

## Why

Without verification, a misconfigured build produces an artifact that looks correct (build succeeds, app installs) but fails silently at runtime. Auth screens show "config missing," RN surfaces mount but JS never renders, and Maestro waits until timeout. A 30-second PlistBuddy/unzip check saves 15 minutes of E2E wall time.

## Examples

### Bad

```yaml
- name: Build app
  run: xcodebuild build
- name: Run E2E  # Fails after 15 min timeout
  run: maestro test .maestro/flows/
```

### Good

```yaml
- name: Build app
  run: xcodebuild build

- name: Verify Auth0 in built plist
  run: |
    for KEY in AUTH0_DOMAIN AUTH0_CLIENT_ID; do
      VAL=$(/usr/libexec/PlistBuddy -c "Print :$KEY" "$PLIST")
      [ -z "$VAL" ] && echo "::error::$KEY empty" && exit 1
    done

- name: Verify JS bundle in APK
  run: |
    unzip -l "$APK" | grep -q "assets/index.android.bundle" || exit 1
```

## References

- a prior E2E project: iOS auth showed "config missing" for 5+ runs before verification step was added

## Verify

"After each build step, does the workflow check that the artifact contains expected contents (secrets, bundles, config)? Could a missing config silently survive until E2E timeout?"

## Patterns

Bad — build then test without verification:

```yaml
- name: Build app
  run: xcodebuild build
- name: Run E2E
  run: maestro test .maestro/flows/
  # If Auth0 secrets are missing from plist → app shows "config missing"
  # Maestro waits 15 minutes until timeout, no useful error
```

Good — verify artifact contents before testing:

```yaml
- name: Build app
  run: xcodebuild build

- name: Verify Auth0 in built plist
  run: |
    for KEY in AUTH0_DOMAIN AUTH0_CLIENT_ID; do
      VAL=$(/usr/libexec/PlistBuddy -c "Print :$KEY" "$PLIST")
      [ -z "$VAL" ] && echo "::error::$KEY empty" && exit 1
    done

- name: Verify JS bundle in APK
  run: |
    unzip -l "$APK" | grep -q "assets/index.android.bundle" || exit 1

- name: Run E2E
  run: maestro test .maestro/flows/
```
