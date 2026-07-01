---
name: verbose-builds
paths: [".github/workflows/*.{yml,yaml}"]
---
# Always Use Verbose Flags in CI Builds

Build tools that produce no progress output by default make CI debugging
impossible. Without `--verbose`, builds appear to hang for 30+ minutes
with no way to tell if they're working or stuck.

## Verify

"Will this CI build command produce progress output? Can I tell if it's
stuck or working?"

## Patterns

Bad — no output, appears to hang:

```yaml
- run: npx react-native-brownfield build-android
  timeout-minutes: 90
```

Good — progress visible in CI logs:

```yaml
- run: npx react-native-brownfield build-android --verbose
  timeout-minutes: 90
```

Apply the same principle to: Metro (`--verbose`), Gradle (`--info`),
xcodebuild (`-verbose`), pod install (`--verbose`).
