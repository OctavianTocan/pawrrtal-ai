---
name: workspace-protocol-for-internal-deps
paths: ["**/package.json", "pnpm-workspace.yaml"]
---
# Use workspace: Protocol for Internal Dependencies

In pnpm/yarn workspaces, internal packages should be referenced with the `workspace:*` protocol, not hardcoded version numbers. A hardcoded version like `"@myorg/utils": "^1.0.0"` can resolve to the **published registry version** instead of the local workspace package, causing mysterious behavior where your local changes aren't reflected.

This happens because the package manager's resolution algorithm checks the registry first if the version range matches a published version. With `workspace:*`, the package manager is forced to resolve to the local workspace package — and it errors immediately if the package doesn't exist locally, rather than silently falling back to a potentially outdated registry version.

At publish time, `workspace:*` is automatically replaced with the actual version number, so published packages get correct dependency ranges.

## Verify

"Are internal workspace dependencies using `workspace:*` protocol? Could any resolve to the npm registry instead of the local package?"

## Patterns

Bad — hardcoded version resolves to registry:

```json
{
 "name": "@myorg/web-app",
 "dependencies": {
  "@myorg/shared-utils": "^1.2.0",
  "@myorg/ui-components": "^2.0.0"
 }
}
```

```bash
pnpm install
# @myorg/shared-utils@1.2.0 resolved from npm registry
# NOT your local packages/shared-utils with latest changes
# Your local edits to shared-utils are invisible
```

Good — workspace protocol forces local resolution:

```json
{
 "name": "@myorg/web-app",
 "dependencies": {
  "@myorg/shared-utils": "workspace:*",
  "@myorg/ui-components": "workspace:*"
 }
}
```

```bash
pnpm install
# ✅ Always resolves to local workspace package
# If the package doesn't exist locally, install fails immediately
```

Good — workspace protocol variants:

```json
{
 "dependencies": {
  "@myorg/utils": "workspace:*",     // Any local version
  "@myorg/config": "workspace:^",    // Compatible local version
  "@myorg/types": "workspace:~"      // Patch-compatible local version
 }
}
```

```bash
# At publish time, pnpm replaces these automatically:
# "workspace:*" → "1.2.3" (exact version at publish time)
# "workspace:^" → "^1.2.3"
# "workspace:~" → "~1.2.3"
```
