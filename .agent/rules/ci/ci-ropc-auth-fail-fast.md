---
name: ci-ropc-auth-fail-fast
paths: [".github/workflows/*.{yml,yaml}", "Dockerfile", "**/*.sh"]
---

# CI ROPC Auth Should Fail Fast - No Silent Retries on Wrong Credentials

Category: ci
Tags: [ci, auth, e2e, fail-fast]

## Rule

Test authentication credentials with a lightweight curl check before spending 15+ minutes on builds. Fail the job in under 5 seconds if secrets are wrong.

## Why

E2E workflows that depend on auth (Auth0 ROPC, Firebase, etc.) waste 15-25 minutes building artifacts only to discover at runtime that credentials are expired, rotated, or misconfigured. A pre-build curl check against the auth endpoint costs 2 seconds and saves entire CI cycles.

## Examples

### Bad

```yaml
# Discovers broken credentials 20 minutes into the run
- name: Build (15 min)
  run: xcodebuild build
- name: Run E2E
  run: maestro test  # Auth fails here
```

### Good

```yaml
- name: Verify Auth0 ROPC (fail-fast)
  run: |
    HTTP_CODE=$(curl -s -w "%{http_code}" -o /dev/null \
      -X POST "https://$AUTH0_DOMAIN/oauth/token" \
      -d '{"grant_type":"password","username":"$EMAIL",...}')
    [ "$HTTP_CODE" != "200" ] && exit 1

- name: Build (15 min)
  run: xcodebuild build
```

## Verify

"Does the workflow validate auth credentials with a lightweight check before any expensive build steps? Will it fail in under 5 seconds if secrets are wrong?"

## Patterns

Bad — discovering auth failure after a full build:

```yaml
- name: Build iOS (15 min)
  run: xcodebuild build -scheme App
- name: Build Android (10 min)
  run: ./gradlew assembleRelease
- name: Run E2E tests
  run: maestro test flows/
  # All 25 minutes wasted — Auth0 token expired yesterday
```

Good — fail-fast auth check as first step:

```yaml
steps:
  - name: Verify auth credentials (fail-fast)
    run: |
      HTTP_CODE=$(curl -sf -w "%{http_code}" -o /dev/null \
        -X POST "https://$AUTH0_DOMAIN/oauth/token" \
        -H "content-type: application/json" \
        -d "{\"grant_type\":\"password\",\"username\":\"${{ secrets.E2E_EMAIL }}\",\"password\":\"${{ secrets.E2E_PASSWORD }}\",\"client_id\":\"${{ secrets.AUTH0_CLIENT_ID }}\",\"client_secret\":\"${{ secrets.AUTH0_CLIENT_SECRET }}\"}")
      if [ "$HTTP_CODE" != "200" ]; then
        echo "::error::Auth check failed with HTTP $HTTP_CODE"
        exit 1
      fi
      echo "Auth credentials valid"

  - name: Build
    run: xcodebuild build
```

## References

- a prior E2E project workflow: ROPC fail-fast step added after wasting multiple 20-min build cycles
