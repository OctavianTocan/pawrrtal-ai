---
name: no-jsdoc-property-block-tags
paths: ["**/*.ts", "**/*.tsx"]
---

# JSDoc @property Block Tags Are Invisible in IDE Hover - Use Inline Property Docs Instead

## Rule

Use inline `/** */` comments directly above each interface property. Do NOT use `@property` block tags on the interface-level JSDoc.

## Why

TypeScript language servers (VS Code, WebStorm) don't surface `@property` block tags in hover tooltips. Developers never see those docs. Inline comments above each property appear in hover, autocomplete, and go-to-definition.

## Bad

```typescript
/**
 * User configuration.
 * @property name - Display name
 * @property email - Contact email
 */
interface UserConfig {
  name: string;
  email: string;
}
```

## Good

```typescript
/** User configuration. */
interface UserConfig {
  /** Display name shown in the UI header. */
  name: string;
  /** Contact email for account recovery. */
  email: string;
}
```

## Origin

pawrrtal PR #80 — Copilot and Codex both flagged @property tags as invisible to IDEs. Converted to inline docs across all interfaces.

## Verify

- Hover over interface property in VS Code/WebStorm — inline doc should appear in tooltip
- Autocomplete on property should show the inline comment
- Go-to-definition should land on the property with doc visible
- Verify no `@property` block tags remain in any interface JSDoc comments

## Patterns

- **Inline `/** */` above each property:** Each property gets its own documentation comment
- **Interface-level doc for context:** Keep a brief `/** InterfaceName description. */` above the interface
- **Be descriptive but concise:** Focus on what the property *is* or *does*, not just its type
