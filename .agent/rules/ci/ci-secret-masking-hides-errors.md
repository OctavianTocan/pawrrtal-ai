---
name: ci-secret-masking-hides-errors
paths: [".github/workflows/*.{yml,yaml}", "Dockerfile", "**/*.sh"]
---

# CI Secret Masking Can Hide Real Error Messages - Check Unmasked Logs

Category: ci
Tags: [ci, secrets, debugging, github-actions]

## Rule

When debugging CI secret injection, read raw file bytes with hex dump. CI log masking AND local tool output masking both replace secret-like patterns with `***`, making it impossible to distinguish "value is literal asterisks" from "value is correct but masked."

## Why

GitHub Actions masks secret values in logs. Some dev tools (Hermes, terminal wrappers) also mask patterns matching known secrets. When a file contains `$AUTH0_DOMAIN`, both systems display `***`. When a file contains literal `***`, both systems also display `***`. The only reliable check is reading raw bytes: `0x24 0x41 0x55...` ($AU...) vs `0x2a 0x2a 0x2a` (***).

## Examples

### Bad

```bash
# Both show *** regardless of actual content
cat workflow.yml | grep AUTH0_DOMAIN
# Output: AUTH0_DOMAIN="***"  — is that real or masked?
```

### Good

```python
with open('workflow.yml', 'rb') as f:
    content = f.read()
idx = content.find(b'AUTH0_DOMAIN=***\n')
chunk = content[idx:idx+40]
# 0x24 = $ (correct), 0x2a = * (broken)
print([hex(b) for b in chunk])
```

## Verify

"When you see `***` in CI output, did you check raw bytes to determine whether the value is actually masked vs literally asterisks?"

## Patterns

Bad — trusting masked output:

```bash
# Both of these produce identical output: ***
echo "$AUTH0_DOMAIN"          # Real value, masked by CI
echo "***"                     # Literal asterisks
# Cannot tell which is which from log output alone
cat .env | grep DOMAIN
# DOMAIN=*** — correct or broken? No way to know
```

Good — use hex dump to see raw bytes:

```bash
# Check raw bytes around the secret reference
xxd .env | grep -A1 DOMAIN
# Correct value:  444f 4d41 494e 3d24 4155 5448  → DOMAIN=$AUTH...
# Broken value:   444f 4d41 494e 3d2a 2a2a 0a    → DOMAIN=***\n

# Or in a CI step, write to a file and inspect
- name: Debug secret injection
  run: |
    printf '%s' "$AUTH0_DOMAIN" | xxd | head -1
    # 24 41 55 54 48 30 = correct ($AUTH0)
    # 2a 2a 2a 2a 2a 2a = broken (******)
```

## References

- a prior E2E project: 3 debugging rounds wasted because both CI logs and local tools showed *** for correct values
