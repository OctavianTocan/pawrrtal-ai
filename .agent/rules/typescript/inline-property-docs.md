---
name: inline-property-docs
paths: ["**/*.{ts,tsx}"]
---
# Inline Per-Property JSDoc

IDE hover tooltips don't surface `@property` block tags on individual
properties. Place `/** ... */` comments directly above each property on
interfaces and types so documentation appears in autocomplete and hover.

## Verify

"Are property descriptions in a @property block tag? Will they show up when
someone hovers over this property in their IDE?"

## Patterns

Bad — block-level @property tags are invisible on hover:

```typescript
/**
 * User settings.
 * @property name - Display name
 * @property email - Contact email
 */
interface UserSettings {
  name: string;
  email: string;
}
```

Good — docs appear on hover for each property:

```typescript
interface UserSettings {
  /** Display name shown in the UI header and comments */
  name: string;
  /** Primary contact email, used for notifications */
  email: string;
}
```
