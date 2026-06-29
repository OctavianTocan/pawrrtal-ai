---
name: use-semver-regex-for-tags
paths: [".github/workflows/*.{yml,yaml}", "Dockerfile", "**/*.sh"]
---

# Use Proper Semver Regex When Parsing Git Tags for Version Extraction

Category: ci
Tags: [ci, git, versioning, shell]

## Rule

Use strict semver regex when parsing version tags — glob patterns like `v*` match non-semver tags that corrupt version arithmetic.

## Why

The glob `v*` matches auto-generated tags like `vauto-20260428-0744-7883073` which corrupt `IFS='.' read -r MAJ MIN PAT` parsing, producing invalid tag names (e.g., `vauto-20260428-0744-7883073..1`). Always filter with `grep -E '^[0-9]+\\.[0-9]+\\.[0-9]+$'` after stripping the tag prefix.

## Examples

### Bad

```bash
# Matches non-semver tags, corrupts version parsing
LATEST=$(git tag -l 'v*' | sort -V | tail -1)
```

### Good

```bash
# Only matches strict semver (N.N.N)
LATEST_STABLE=$(git tag -l 'twinmind-digest/v*' | \
  sed 's|twinmind-digest/v||' | \
  grep -E '^[0-9]+\.[0-9]+\.[0-9]+$' | \
  sort -V | tail -1)
```

## References

- rn-twinmind-brownfield-ci skill: Semver tag parsing
- brownfield-native-test-hosts skill: Publish version detection

## Verify

"After stripping the tag prefix, does the version string pass `grep -E '^[0-9]+\\.[0-9]+\\.[0-9]+$'`? Could any auto-generated tag corrupt version arithmetic?"

## Patterns

Bad — loose glob matches non-semver tags:

```bash
LATEST=$(git tag -l 'v*' | sort -V | tail -1)
# Matches: vauto-20260428-0744-7883073
# IFS='.' read -r MAJ MIN PAT <<< "$LATEST" → garbage
# Version arithmetic produces: vauto-20260428-0744-7883073..1
```

Good — strict semver filter after glob:

```bash
LATEST=$(git tag -l 'v*' | \
  sed 's/^v//' | \
  grep -E '^[0-9]+\.[0-9]+\.[0-9]+$' | \
  sort -V | tail -1)
# Only matches: 1.2.3, 0.76.0, etc.
# Version arithmetic works correctly: 0.76.0 → 0.76.1
```
