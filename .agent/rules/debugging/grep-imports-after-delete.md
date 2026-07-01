---
name: grep-imports-after-delete
paths: ["**/*.{ts,tsx,js,jsx}"]
---
# Grep for Imports After Deleting or Renaming Files

After deleting or renaming a file, `git rebase` will succeed because git only cares about file-level conflicts. But downstream branches that import the old path will fail at typecheck — and if you're rebasing a stack, this failure might not surface until CI runs 20 minutes later.

Before pushing a rebase that includes file deletions or renames, grep the entire project for imports of the old path. This catches dangling imports immediately rather than waiting for CI. It's especially critical in monorepos where a file might be imported from another package.

This also applies to renamed exports: if you rename a function from `getUserById` to `findUser`, grep for all usages of the old name.

## Verify

"After renaming or deleting a file, have I searched the entire project for imports referencing the old path or name?"

## Patterns

Bad — delete file, rebase succeeds, CI fails later:

```bash
git rm src/utils/formatDate.ts
git commit -m "refactor: remove formatDate utility"
git rebase main  # ✅ succeeds (no file conflicts)
git push --force origin feature
# ❌ CI fails: Cannot find module './utils/formatDate'
# in src/components/DatePicker.tsx (a file you didn't touch)
```

Good — grep before pushing:

```bash
git rm src/utils/formatDate.ts
git commit -m "refactor: remove formatDate utility"

# Search for all references to the deleted file
grep -r "formatDate" --include="*.ts" --include="*.tsx" src/
# src/components/DatePicker.tsx:import { formatDate } from '../utils/formatDate'
# Found it — fix the import before pushing

# Also check re-exports and dynamic imports
grep -r "utils/formatDate" --include="*.ts" --include="*.tsx" .
```

Good — automate with a pre-push check:

```bash
# In a helper script or git hook
DELETED_FILES=$(git diff --name-only --diff-filter=D HEAD~1)
for file in $DELETED_FILES; do
 basename=$(basename "$file" | sed 's/\.[^.]*$//')
 if grep -r "$basename" --include="*.ts" --include="*.tsx" src/ | grep -v "^Binary"; then
  echo "⚠️  Deleted '$file' is still referenced"
  exit 1
 fi
done
```
