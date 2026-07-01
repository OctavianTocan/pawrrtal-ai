#!/usr/bin/env bash
# lint/filenames.sh — enforce kebab-case filenames for all rule .md files
# Excludes top-level docs (README, CHANGELOG, AGENTS, CLAUDE.md)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
errors=0

while IFS= read -r file; do
  basename=$(basename "$file")

  # Skip top-level docs
  case "$basename" in
    README.md|CHANGELOG.md|AGENTS.md|CLAUDE.md) continue ;;
  esac

  # Check kebab-case: lowercase letters, digits, hyphens only, must not start with hyphen
  if ! echo "$basename" | grep -qE '^[a-z][a-z0-9-]*\.md$'; then
    echo "FAIL: $file — filename must be kebab-case (lowercase, digits, hyphens)"
    errors=$((errors + 1))
  fi
done < <(find "$REPO_ROOT" -name '*.md' -not -path '*/node_modules/*' -not -path '*/.git/*')

if [ "$errors" -gt 0 ]; then
  echo ""
  echo "Found $errors filename violation(s)."
  exit 1
fi

echo "All filenames are kebab-case."
exit 0
