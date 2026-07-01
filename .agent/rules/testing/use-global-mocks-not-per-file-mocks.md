---
name: use-global-mocks-not-per-file-mocks
paths: ["**/*.test.ts", "**/*.test.tsx", "**/*.spec.ts", "**/*.spec.tsx", "**/vitest.config.*"]
---

# Set Up Global Mocks in Setup Files, Not Per-Test-File - Shared Mocks Prevent Drift Between Tests

Category: testing
Tags: [ios, accessibility, maestro, swiftui]

## Rule

Never use `.accessibilityElement(children: .contain)` on SwiftUI containers used in E2E tests. It makes child elements invisible to Maestro's hierarchy inspection.

## Why

SwiftUI's `.accessibilityElement(children: .contain)` merges children into the parent's accessibility representation. The parent becomes visible to Maestro, but individual children (buttons, labels) disappear from the hierarchy dump. Maestro can see the List but can't tap its items.

## Examples

### Bad

```swift
List {
    ForEach(surfaces) { surface in
        Button(surface.label) { ... }
    }
}
.accessibilityElement(children: .contain)  // Hides buttons from Maestro
```

### Good

```swift
List {
    ForEach(surfaces) { surface in
        Button(surface.label) { ... }
            .accessibilityIdentifier("btn_\(surface.id)")
    }
}
// No .accessibilityElement — children remain individually accessible
```

## References

- a prior E2E project: Maestro found surface_list but couldn't tap buttons until .accessibilityElement was removed

## Verify

- Run Maestro E2E tests against SwiftUI lists: confirm child elements (buttons, labels) are tappable
- Inspect Maestro hierarchy dump: verify children appear under their parent containers, not merged
- Test on iOS: manually verify VoiceOver can still navigate to individual children

## Patterns

- **Use `.accessibilityIdentifier()` on interactive children:** Set unique IDs on buttons and controls inside SwiftUI containers so Maestro can target them directly
- **Avoid `.accessibilityElement(children: .contain)` on scrollable containers:** Lists, ScrollViews, and LazyVStacks used in E2E flows should not merge children
- **Test accessibility hierarchy in CI:** Add a step that dumps the view hierarchy and asserts children are present
