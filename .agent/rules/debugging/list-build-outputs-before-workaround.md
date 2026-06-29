---
name: list-build-outputs-before-workaround
paths: [".no-match"]
---

# List Actual Build Outputs Before Applying Workarounds for Missing Artifacts

Category: debugging
Tags: [debugging, build-tools, brownfield]

## Rule

Run `ls` on a build tool's output directory before inventing workarounds — the tool may already produce what you need.

## Why

Assuming you know a tool's output layout from docs or training data leads to elaborate workarounds (extracting internals from build intermediates, creating stub module files, patching search paths) when the tool already produced exactly what you need as a standalone file. One project spent 6 CI iterations extracting `.swiftmodule` from CocoaPods build intermediates when `ReactBrownfield.xcframework` was sitting in the same output directory the whole time.

## Verify

Before applying a workaround: have you listed the actual build outputs to see what the tool already produced?

## Patterns

### Pattern (bad)

```bash
# Assume the CLI only produces one file, build elaborate workaround
find build/intermediates -name "*.swiftmodule" -exec cp {} /tmp/modules/ \;
# Create stub modulemap, patch SWIFT_INCLUDE_PATHS...
```

### Pattern (good)

```bash
# First, see what the tool actually produced
ls -la ios/.brownfield/package/build/
# Output: a prior projectDigestBrownfield.xcframework
#         ReactBrownfield.xcframework      ← this was there all along
#         hermesvm.xcframework
```

## References

- systematic-debugging skill: Inspect Build Tool Output section
- brownfield-native-test-hosts skill: The brownfield CLI produces THREE XCFrameworks
