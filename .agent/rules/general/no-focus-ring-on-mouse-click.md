---
name: no-focus-ring-on-mouse-click
paths: ["**/*.{css,tsx,ts}"]
---

# Suppress Focus Rings on Mouse Click, Keep Them for Keyboard

Modern browsers paint a focus outline on every focusable element when it
is clicked or tapped — buttons, links, divs with `tabindex`. On touch and
mouse, that outline reads as a stuck selection rectangle the user did not
ask for; on keyboard, the outline is the only signal the user has of
where focus is. Globally killing `outline: none` breaks accessibility;
leaving the default in place looks broken on click.

The fix is the `:focus:not(:focus-visible)` pair. `:focus-visible` only
matches when focus came from the keyboard (Tab, Shift+Tab, arrow keys, or
programmatic focus on a non-pointer event), so the inverted selector
cleanly targets mouse + touch clicks. `frontend/app/globals.css` already
applies this in the `@layer base` block — do not re-add the rule per
component, and never ship `outline: none` on `:focus` directly.

If a component genuinely needs a visible click affordance (e.g. an
active toggle), use a non-focus visual cue (background, border colour,
ring on `aria-pressed`) so keyboard users still get the standard ring.

## Verify

"Did I add `outline: none` (or `focus:outline-none` / `focus:ring-0`) to
any element without a paired `focus-visible:` rule? The global base layer
already suppresses focus on mouse clicks — am I about to re-implement that
locally?"

## Patterns

Bad — strips the ring for everyone, including keyboard users:

```css
button:focus {
	outline: none;
}
```

```tsx
<button className="focus:outline-none focus:ring-0">Submit</button>
```

Good — global base layer already covers mouse click; keyboard users keep
the ring via `:focus-visible`:

```css
/* globals.css — applied once for the whole app */
*:focus:not(:focus-visible) {
	outline: none;
	box-shadow: none;
}
```

```tsx
{/* Component code stays clean — no per-element focus suppression. */}
<button className="focus-visible:ring-2 focus-visible:ring-ring">Submit</button>
```
