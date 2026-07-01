---
name: audit-secrets-across-workflows
paths: [".github/workflows/*.{yml,yaml}", "Dockerfile", "**/*.sh"]
---

# Cross-Reference Secret Usage Across All Workflows to Find Unused or Missing Secrets

Category: ci
Tags: [ci, secrets, github-actions]

## Rule

Cross-reference repo secrets against workflow references after setup — mismatches silently produce empty strings.

## Why

`EXPO_PUBLIC_*` secrets that are set on the repo but not referenced as `env:` vars on the build step are silently absent at build time. Secrets referenced in workflows but not set on the repo resolve to empty strings without error. OpenRouter returns 401, Auth0 returns 403, and Firebase shows degraded states — all with no clear indication that the secret is missing.

## Examples

### Bad

```bash
# Assume all secrets are correctly wired
gh secret list  # Shows 15 secrets — looks good
# But 3 of them aren't referenced in any workflow
```

### Good

```bash
# Cross-reference what's set vs what's referenced
gh secret list --repo owner/repo
grep -rn 'secrets\.' .github/workflows/ | grep -oP 'secrets\.(\w+)' | sort -u
# Diff the two lists — any mismatch is a bug
```

## Verify

"Does every secret in `gh secret list` appear in at least one workflow? Does every `secrets.*` reference in workflows have a corresponding repo secret set?"

## Patterns

Bad — secrets set but never referenced:

```yaml
# Repo has EXPO_PUBLIC_API_KEY set as a secret
# But no workflow step passes it as an env var
env:
  NODE_ENV: production
  # Missing: EXPO_PUBLIC_API_KEY: ${{ secrets.EXPO_PUBLIC_API_KEY }}
```

Bad — secrets referenced but not set on the repo:

```yaml
env:
  OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
  # Secret not configured on the repo → resolves to empty string
  # API returns 401 with no indication the secret is missing
```

Good — cross-reference script:

```bash
# Extract secrets referenced in workflows
used=$(grep -roh 'secrets\.[A-Za-z_][A-Za-z0-9_]*' .github/workflows/ | sort -u | sed 's/secrets\.//')
# Extract secrets configured on the repo
set=$(gh secret list --repo owner/repo --json name --jq '.[].name')
# Find mismatches
comm -23 <(echo "$set") <(echo "$used")  # Unused secrets
comm -13 <(echo "$set") <(echo "$used")  # Missing secrets
```

## References

- Maestro E2E mobile skill: Secrets Audit Pattern
- EXPO_PUBLIC_* must be env: vars on the Metro build step specifically
