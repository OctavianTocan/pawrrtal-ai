---
name: Radix Tooltip Reopens After Dropdown Close — Fix with setTimeout(150), Not rAF
paths: ["**/*.{ts,tsx}"]
---

# Radix Tooltip Reopens After Dropdown Close — Use setTimeout(150), Not rAF

## The bug

When a Radix `<Tooltip>` wraps a `<DropdownMenuTrigger>`, closing the dropdown
causes the tooltip to reappear immediately — even when the cursor is not hovering.
The user is forced to click elsewhere to dismiss it. This happens because:

1. Radix's `FocusScope` restores focus to the trigger inside a **`useEffect` cleanup**,
   which fires **after browser paint**.
2. When the dropdown closes, `menuOpen` is set to `false` synchronously. The trigger
   regains focus a few milliseconds later, and Radix fires `onOpenChange(true)` on
   the Tooltip (with `data-state="instant-open"` — focus-triggered, no delay).
3. By the time that focus-return fires, `menuOpen` is already `false`, so a naive
   guard (`if (menuOpen) return`) does not catch it.

## The wrong fix

Using `requestAnimationFrame` to clear the closing guard:

```tsx
// BROKEN — rAF fires BEFORE paint, BEFORE Radix's useEffect focus-return
requestAnimationFrame(() => {
  isMenuClosingRef.current = false;
});
```

`rAF` fires before the browser paints, which is **before** Radix's `useEffect`
cleanup runs. The guard is cleared too early and the focus-triggered open slips through.

## The correct fix

Use `setTimeout(150)` instead. 150 ms is well past the ~16 ms it takes for Radix's
`useEffect` cleanup to execute, so the guard is still active when the focus-return
fires `onOpenChange(true)`.

```tsx
const isMenuClosingRef = useRef(false);
// Needed to cancel a pending clear if the dropdown reopens quickly.
const closingTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

// Inside DropdownMenu.onOpenChange:
onOpenChange={(open) => {
  setMenuOpen(open);
  if (!open) {
    isMenuClosingRef.current = true;
    setTooltipOpen(false);
    // 150 ms keeps the guard alive through Radix's useEffect focus-return
    // (~16 ms), absorbing the focus-triggered onOpenChange(true) on the
    // Tooltip before clearing.
    clearTimeout(closingTimerRef.current);
    closingTimerRef.current = setTimeout(() => {
      isMenuClosingRef.current = false;
    }, 150);
  }
}}

// Inside Tooltip.onOpenChange:
onOpenChange={(open) => {
  if (menuOpen || isMenuClosingRef.current) return;
  setTooltipOpen(open);
}}
open={menuOpen ? false : tooltipOpen}
```

## Why 300 ms (not 150 ms)

- Radix's `useEffect` focus restoration for the main Content typically runs within 16-30 ms.
- `requestAnimationFrame` fires at ~16 ms — too soon, the guard is cleared.
- `setTimeout(0)` is similarly unreliable; it may batch before the next paint.
- **If SubContent is rendered inside a `DropdownMenuPrimitive.Portal`**, it has its own
  `animate-dropdown-close` exit animation (150 ms). Radix's `Presence` keeps it mounted
  during that animation, so its `FocusScope` cleanup fires at **~150 ms+** — right as a
  150 ms guard would clear. Use **300 ms** to safely outlast the Portal SubContent restore.
- If there is no Portal SubContent (flat dropdown, no submenus), 150 ms is sufficient.
  Use 300 ms as the safe default whenever submenus are present.

## Where this pattern is used

- `frontend/features/chat/components/ChatComposerControls.tsx` — `AutoReviewSelector`
- `frontend/features/chat/components/ModelSelectorPopover.tsx` — `ModelSelectorPopover`

## Verify

"Does this Tooltip sit next to or inside a DropdownMenuTrigger? Is the closing
guard cleared with `setTimeout(150)` and a `closingTimerRef`? Is `clearTimeout`
called before each new timer to avoid stale clears?"
