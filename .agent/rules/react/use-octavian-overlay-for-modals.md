---
name: use-octavian-overlay-for-modals
paths: ["**/*.{ts,tsx}"]
---

# Use @octavian-tocan/react-overlay for Modals and Bottom Sheets

All new modal, dialog, and bottom-sheet UI in pawrrtal must be built on
`@octavian-tocan/react-overlay` — not raw Radix `Dialog`, shadcn
`<Dialog>` / `<AlertDialog>`, or hand-rolled overlays. The package gives
us a single responsive primitive (`Modal` on desktop, `BottomSheet` on
mobile) with consistent dismiss/escape/backdrop semantics; mixing it
with Radix dialogs creates two parallel focus-trap and scroll-lock
mechanisms that fight each other when both are open and produce
inconsistent mobile affordances (modal slides from center vs. drags
from bottom).

Compose through `@/components/ui/app-dialog` (`AppDialog`), which switches
between `Modal` and `BottomSheet` based on `useIsMobile`. `AppDialog` wraps
`ResponsiveModal` — use `ResponsiveModal` only inside shared UI plumbing or
when extending the shell; feature code should import `AppDialog`.

Reach for the raw `Modal` / `BottomSheet` / `ModalWrapper` exports only when you
need a viewport-specific overlay (e.g. an explicitly mobile-only sheet) or a
fully custom container.

`shadcn` `<Dialog>`, `<AlertDialog>`, and `<Sheet>` (in
`components/ui/{dialog,alert-dialog,sheet}.tsx`) are kept only as low-level
primitives that other shadcn components depend on — do not import them
directly into feature code.

## Verify

"Am I about to import `Dialog`, `AlertDialog`, or `Sheet` from
`@/components/ui/...` in a feature file? Could I use `AppDialog`
(or a direct `Modal` / `BottomSheet` from `@octavian-tocan/react-overlay`)
instead?"

## Patterns

Bad — feature code reaches into shadcn `Dialog`:

```tsx
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';

export function ConfirmRename({ open, onOpenChange }: Props) {
	return (
		<Dialog open={open} onOpenChange={onOpenChange}>
			<DialogContent>
				<DialogTitle>Rename</DialogTitle>
				{/* ...form... */}
			</DialogContent>
		</Dialog>
	);
}
```

Good — feature code uses the project responsive overlay primitive:

```tsx
import { AppDialog } from '@/components/ui/app-dialog';

export function ConfirmRename({ open, onDismiss }: Props) {
	const headingId = useId();
	return (
		<AppDialog
			open={open}
			onDismiss={onDismiss}
			ariaLabelledBy={headingId}
			size="md"
			showDismissButton
		>
			<div className="p-6">
				<h2 id={headingId}>Rename</h2>
				{/* ...form... */}
			</div>
		</AppDialog>
	);
}
```

Good — explicit mobile-only sheet uses `BottomSheet` directly:

```tsx
import { BottomSheet } from '@octavian-tocan/react-overlay';

export function MobileFilterSheet({ open, onDismiss, children }: Props) {
	return (
		<BottomSheet
			open={open}
			onDismiss={onDismiss}
			snapPoints={({ maxHeight }) => maxHeight * 0.85}
		>
			{children}
		</BottomSheet>
	);
}
```
