/**
 * Pawrrtal application dialog shell — the standard entry point for modal UI.
 *
 * This component delegates to {@link ResponsiveModal}: a centered {@link Modal}
 * on desktop and a draggable {@link BottomSheet} on narrow viewports (same
 * breakpoint as {@link useIsMobile}). Feature code should compose **variants**
 * (project flows, nav dialogs, settings sheets, etc.) on top of this primitive
 * rather than wiring {@link ResponsiveModal} or raw overlay exports from scratch.
 *
 * **Modal → bottom sheet:** When you implement dialogs with **`header`**,
 * **`footer`**, and scrollable **`children`** as the body, the same structure
 * maps correctly on mobile: sticky header/footer regions on the sheet with a
 * scrollable middle. Omitting header/footer keeps everything in `children`
 * (single scroll region); that works but loses sticky chrome on small screens.
 *
 * Compose chrome with **`ModalHeader`**, **`ModalDescription`**, and related
 * exports from **`@octavian-tocan/react-overlay`**. Pass **`sheetTitle`** for a
 * short label used by the sheet for handle/backdrop accessibility when you do not
 * rely solely on **`ariaLabelledBy`**.
 *
 * @see DESIGN.md — Components — Modal / sheet overlays (application shell)
 * @see `.claude/rules/react/use-octavian-overlay-for-modals.md`
 *
 * @fileoverview Application-level responsive dialog primitive for Pawrrtal.
 */

'use client';

import type * as React from 'react';
import { ResponsiveModal, type ResponsiveModalProps } from './responsive-modal';

/** Props for {@link AppDialog}; identical to {@link ResponsiveModalProps}. */
export type AppDialogProps = ResponsiveModalProps;

/**
 * Responsive dialog: centered modal on wide viewports, bottom sheet on narrow ones.
 *
 * @returns The active overlay for the current breakpoint.
 */
export function AppDialog(props: AppDialogProps): React.JSX.Element {
	return <ResponsiveModal {...props} />;
}
