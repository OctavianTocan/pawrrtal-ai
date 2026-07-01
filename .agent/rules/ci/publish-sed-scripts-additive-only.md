---
name: publish-sed-scripts-additive-only
paths: [".github/workflows/*.{yml,yaml}", "Dockerfile", "**/*.sh"]
---

# Publish sed Scripts Must ADD Dependencies, Never Replace Existing Declarations

## Rule

When CI sed scripts modify dependency declarations in build.gradle files during publish, ADD new lines alongside existing ones. Never REPLACE existing dependency declarations.

## Why

Replacing `api()` with `embed()` (or any variant swap) silently removes the original declaration from the generated POM. The build succeeds but consumers lose transitive dependency resolution.

## Bad

```bash
# Replaces api() with embed() — POM loses transitive deps
sed -i 's/api(/embed(/g' build.gradle.kts
```

## Good

```bash
# Adds embed() lines AFTER existing api() lines — both end up in the build
sed -i '/api("com.facebook.react:react-android/a\    embed("com.facebook.react:react-android:0.83.6")' build.gradle.kts
```

## Verify

After the sed step, `grep -c 'api(' build.gradle.kts` should return AT LEAST as many matches as before the sed. If the count dropped, the sed deleted lines instead of adding.

## Patterns

Bad — sed replaces dependency declarations:

```bash
# Replaces api() with embed() — loses transitive deps in POM
sed -i 's/api(/embed(/g' build.gradle.kts
# Build succeeds but consumers get ClassNotFoundException
```

Good — sed adds new declarations alongside existing ones:

```bash
# Adds embed() after api() — both exist in build file
sed -i '/api("com.facebook.react:react-android/a\    embed("com.facebook.react:react-android:0.83.6")' build.gradle.kts
# After: both api() and embed() exist, POM includes transitive deps
```

## Origin

a prior project brownfield publish workflow — sed replaced api→embed, broke POM, caused ClassNotFoundException for 9 Facebook deps in consumer apps.
