---
name: no-bash-associative-arrays-on-macos
paths: [".github/workflows/*.{yml,yaml}", "Dockerfile", "**/*.sh"]
---

# macOS bash 3.2 Does Not Support Associative Arrays - Use POSIX Alternatives

Category: ci
Tags: [ci, shell, macos, self-hosted]

## Rule

Never use `declare -A` (bash associative arrays) in CI scripts targeting macOS — Apple ships bash 3.x which doesn't support them.

## Why

macOS ships bash 3.2 as `/bin/bash` due to GPL licensing. GitHub Actions `run:` steps use this shell by default on self-hosted macOS runners. `declare -A` fails with "invalid option" at runtime. Also avoid `${!array[@]}` iteration, `|&` pipe stderr, and `&>>` append redirect — all are bash 4+ features.

## Examples

### Bad

```bash
# Fails on macOS: "declare: -A: invalid option"
declare -A MY_MAP
MY_MAP[key]="value"
```

### Good

```bash
# Works on bash 3.x and 4+
FW_NAMES=""
for fw in "$FW_DIR"/*.framework; do
  FWNAME=$(basename "$fw" .framework)
  FW_NAMES="$FW_NAMES $FWNAME"
done
```

## References

- Maestro E2E mobile skill: macOS bash 3.x pitfall
- brownfield-native-test-hosts skill: bash 3.x on macOS CI runners

## Verify

"Does this bash script avoid `declare -A`, `${!array[@]}`, `|&`, and `&>>`? Would it run on bash 3.2?"

## Patterns

Bad — bash 4+ features that fail on macOS:

```bash
declare -A PLATFORM_MAP
PLATFORM_MAP[ios]="iPhone 15"
PLATFORM_MAP[android]="pixel_7"

for key in "${!PLATFORM_MAP[@]}"; do
  echo "$key: ${PLATFORM_MAP[$key]}"
done
```

Good — bash 3.x compatible alternatives:

```bash
# Use parallel arrays or string concatenation
PLATFORMS="ios android"
for p in $PLATFORMS; do
  case "$p" in
    ios) device="iPhone 15" ;;
    android) device="pixel_7" ;;
  esac
  echo "$p: $device"
done
```
