---
name: biome-2-migration-gotchas
paths: ["**/*"]
---

# Biome 2.x Breaking Changes: Nursery Rules Renamed, Config Format Changed

Category: general
Tags: [biome, linting, migration]

## Rule

Run `npx biome migrate --write` after Biome version bumps — v2.x removed `files.ignore`, deprecated `--fix`, and requires matching schema version.

## Why

Biome 2.x has breaking config changes: `files.ignore` was removed (use `files.includes` with negation), `--fix` was deprecated (use `--write`), and the schema version in the config must match the installed version or features fail silently. The migrate command auto-fixes all of these, but manual config edits miss the changes.

## Examples

### Bad

```json
{
  "$schema": "https://biomejs.dev/schemas/1.9.0/schema.json",
  "files": {
    "ignore": ["node_modules", "dist"]
  }
}
```

### Good

```bash
npx biome migrate --write
```

```json
{
  "$schema": "https://biomejs.dev/schemas/2.4.13/schema.json",
  "files": {
    "includes": ["**", "!**/node_modules", "!**/dist"]
  }
}
```

## References

- rn-component-architecture skill: Biome 2.x Gotchas

## Verify

"Did I run `npx biome migrate --write` after bumping Biome? Does the schema version match the installed version?"

## Patterns

Bad — manual config edit misses breaking changes:

```bash
# Just bump the version and hope for the best
pnpm add -D @biomejs/biome@latest
# Config still has "files.ignore", schema is 1.9.0
# Rules fail silently or give cryptic "unknown rule" errors
```

Good — migrate command auto-fixes everything:

```bash
pnpm add -D @biomejs/biome@latest
npx biome migrate --write
# Schema updated, files.ignore → files.includes, deprecated flags fixed
```
