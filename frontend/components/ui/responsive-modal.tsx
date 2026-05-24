/**
 * Responsive overlay primitive built on `@octavian-tocan/react-overlay`.
 *
 * Renders a centered {@link Modal} on desktop and a draggable
 * {@link BottomSheet} on mobile. This is the project standard for any new
 * modal/sheet UI — see `.claude/rules/react/use-octavian-overlay-for-modals.md`.
 *
 * Prefer **`header`** and **`footer`** so {@link BottomSheet} uses sticky
 * header/footer regions (snap/scroll math) and desktop {@link Modal} keeps
 * titles/actions out of the scrollable body — compose with {@link ModalHeader},
 * {@link ModalDescription}, etc. from the package.
 *
 * Feature code should prefer **`AppDialog`** (`app-dialog.tsx`), which wraps this
 * component with the Pawrrtal application shell contract — see DESIGN.md.
 *
 * @fileoverview Responsive Modal/BottomSheet implementation layer (use AppDialog in features).
 */

'use client';

import { BottomSheet, Modal, type ModalSize } from '@octavian-tocan/react-overlay';
import type * as React from 'react';
import { useSyncExternalStore } from 'react';
import { createPortal } from 'react-dom';
import { useIsMobile } from '@/hooks/use-mobile';

const unsubscribeFromHydration = (): void => undefined;
const subscribeToHydration = (): (() => void) => unsubscribeFromHydration;
const getClientHydrationSnapshot = (): boolean => true;
const getServerHydrationSnapshot = (): boolean => false;

/**
 * Props accepted by {@link ResponsiveModal}.
 */
export interface ResponsiveModalProps {
	/** Whether the overlay is open. */
	open: boolean;
	/** Called when the overlay should close (overlay click, escape key, drag-down on mobile). */
	onDismiss: () => void;
	/**
	 * Main body (form fields, descriptions — typically everything between
	 * {@link ModalHeader} and action buttons). When **`header`** or **`footer`**
	 * is set, keep chrome out of `children` so mobile gets correct sheet regions.
	 */
	children: React.ReactNode;
	/**
	 * Header row (e.g. {@link ModalHeader} from `@octavian-tocan/react-overlay`).
	 * Passed to {@link BottomSheet} `header` on mobile and rendered above `children` on desktop.
	 */
	header?: React.ReactNode;
	/**
	 * Footer row (primary actions). Passed to {@link BottomSheet} `footer` on mobile
	 * and rendered below `children` on desktop.
	 */
	footer?: React.ReactNode;
	/**
	 * Short title forwarded to {@link BottomSheet} `title` for handle/backdrop
	 * `aria-label` text when a string title is not otherwise supplied.
	 */
	sheetTitle?: string;
	/** Modal size preset (desktop only). Default `md`. */
	size?: ModalSize;
	/** Whether clicking the overlay backdrop dismisses. Default `true`. */
	closeOnOverlayClick?: boolean;
	/** Whether pressing Escape dismisses. Default `true`. */
	closeOnEscape?: boolean;
	/** Whether to render the built-in dismiss (X) button on desktop. Default `false`. */
	showDismissButton?: boolean;
	/** Accessible label for screen readers when no visible heading is wired via `aria-labelledby`. */
	ariaLabel?: string;
	/** ID of the element labelling the modal (e.g. a `<DialogTitle>` analogue). */
	ariaLabelledBy?: string;
	/** ID of the element describing the modal. */
	ariaDescribedBy?: string;
	/** Test ID forwarded to the overlay root. */
	testId?: string;
}

/**
 * Pick `Modal` (desktop) or `BottomSheet` (mobile) based on viewport.
 *
 * Falls back to {@link Modal} during SSR / before hydration ({@link useIsMobile}
 * returns `false` until mounted), which matches the desktop-first chrome of
 * the rest of the app.
 *
 * @returns The active overlay rendering the supplied children.
 */
export function ResponsiveModal({
	open,
	onDismiss,
	children,
	header,
	footer,
	sheetTitle,
	size = 'md',
	closeOnOverlayClick = true,
	closeOnEscape = true,
	showDismissButton = false,
	ariaLabel,
	ariaLabelledBy,
	ariaDescribedBy,
	testId,
}: ResponsiveModalProps): React.JSX.Element {
	const isMobile = useIsMobile();
	const usesChromeSlots = header !== undefined || footer !== undefined;
	// Mounting flag so we don't try to portal during SSR — `document` is
	// undefined on the server and the first render has to match.
	const isMounted = useSyncExternalStore(
		subscribeToHydration,
		getClientHydrationSnapshot,
		getServerHydrationSnapshot
	);

	if (isMobile) {
		const sheetDismiss = showDismissButton
			? { show: true as const, position: 'right' as const }
			: undefined;
		const sheetBody = usesChromeSlots ? (
			children
		) : (
			// BottomSheet has no aria* props of its own — wrap body in a labelled
			// dialog region when we are not using explicit header/footer slots.
			// Uses <dialog> with `open` for semantic markup without the built-in
			// modal overlay (the BottomSheet itself handles that).
			<dialog
				open
				aria-modal="true"
				aria-label={ariaLabel}
				aria-labelledby={ariaLabelledBy}
				aria-describedby={ariaDescribedBy}
				style={{ display: 'contents' }}
			>
				{children}
			</dialog>
		);
		return (
			<BottomSheet
				open={open}
				onDismiss={onDismiss}
				header={header}
				footer={footer}
				testId={testId}
				dismissButton={sheetDismiss}
			>
				{sheetBody}
			</BottomSheet>
		);
	}

	const desktopModal = (
		<Modal
			open={open}
			onDismiss={onDismiss}
			size={size}
			closeOnOverlayClick={closeOnOverlayClick}
			closeOnEscape={closeOnEscape}
			showDismissButton={showDismissButton}
			ariaLabel={ariaLabel}
			ariaLabelledBy={ariaLabelledBy}
			ariaDescribedBy={ariaDescribedBy}
			testId={testId}
		>
			{usesChromeSlots ? (
				<div className="flex flex-col gap-5 text-foreground">
					{header}
					<div className="min-h-0">{children}</div>
					{footer}
				</div>
			) : (
				children
			)}
		</Modal>
	);

	// Portal to document.body so the modal escapes any ancestor stacking
	// context — without this the sidebar's `overflow:hidden` + flex
	// transforms clip the modal and the user sees the rename form
	// rendered inline as a sidebar row instead of as a centered overlay.
	if (!isMounted) {
		return desktopModal;
	}
	return createPortal(desktopModal, document.body);
}
