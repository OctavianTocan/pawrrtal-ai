---
name: clear-caches-when-switching-tool-versions
paths: [".no-match"]
---

# Clear Dependency Caches When Switching Major Tool Versions (Xcode, Node, Gradle) - Stale Artifacts Cause Cryptic Errors

Clear CocoaPods, Gradle, and Metro caches when switching Xcode, Android SDK, or Node versions. Stale caches cause cryptic compilation errors.

## Rule

After changing any of these, clean the corresponding cache:

| Changed | Clean |
| --------- | ------- |
| Xcode version | `pod cache clean --all && rm -rf ios/Pods ios/build` |
| Android SDK | `cd android && ./gradlew clean` |
| Node version | `rm -rf node_modules && pnpm install` |
| React Native version | All of the above |

## Why

Stale fmt 11.0.2 CocoaPods cache caused `fmt consteval` compilation errors after upgrading Xcode. The error message pointed at fmt source code, not the cache, making it look like a library bug. Cleaning the pod cache fixed it instantly.

## Verify

"Have I changed a major tool version (Xcode, Node, Android SDK, React Native)? Did I clean the corresponding dependency caches before building?"

## Patterns

Bad — upgrading tool without clearing caches:

```bash
# Upgrade Xcode, then build immediately
sudo xcode-select -s /Applications/Xcode-16.0.app
cd ios && pod install
# Build fails with cryptic consteval errors in fmt library
# Error points at fmt source code — looks like a library bug
```

Good — clear caches after version switch:

```bash
# Upgrade Xcode, clean caches, then build
sudo xcode-select -s /Applications/Xcode-16.0.app
pod cache clean --all
rm -rf ios/Pods ios/build
cd ios && pod install
# Build succeeds — cached artifacts from old clang are gone
```
