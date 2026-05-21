/**
 * ComposerActionSelector — generic single-select dropdown for the composer
 * footer.
 *
 * @fileoverview Generalised from pawrrtal's `AutoReviewSelector`. Takes a
 * consumer-supplied item list + selected id, owns the Radix tooltip +
 * dropdown coexistence guard, and delegates presentation to
 * {@link ComposerActionSelectorView}.
 */

'use client';

import { useTooltipDropdown } from '../hooks/useTooltipDropdown';
import {
	ComposerActionSelectorView,
	type ComposerActionSelectorItem,
} from './ComposerActionSelectorView';

/** Props for {@link ComposerActionSelector}. */
export interface ComposerActionSelectorProps<TId extends string = string> {
	/** Items rendered in the dropdown, in display order. */
	items: ComposerActionSelectorItem[];
	/** Currently-selected item id. */
	selectedId: TId;
	/** Fired when the user picks an item. */
	onSelect: (id: TId) => void;
	/** Optional tooltip rendered over the trigger. */
	tooltip?: string;
	/** Optional Tailwind class for the label span inside the trigger button. */
	triggerLabelClassName?: string;
}

/**
 * Generic single-select dropdown for composer footer actions (e.g. an
 * "Auto-review" picker, a tone selector, a tools toggle).
 *
 * @returns The trigger pill paired with its dropdown menu.
 */
export function ComposerActionSelector<TId extends string = string>({
	items,
	selectedId,
	onSelect,
	tooltip,
	triggerLabelClassName,
}: ComposerActionSelectorProps<TId>): React.JSX.Element {
	const { menuOpen, tooltipOpen, handleMenuOpenChange, handleTooltipOpenChange } =
		useTooltipDropdown();
	return (
		<ComposerActionSelectorView
			items={items}
			selectedId={selectedId}
			onSelect={(id) => onSelect(id as TId)}
			tooltip={tooltip}
			menuOpen={menuOpen}
			tooltipOpen={tooltipOpen}
			onMenuOpenChange={handleMenuOpenChange}
			onTooltipOpenChange={handleTooltipOpenChange}
			triggerLabelClassName={triggerLabelClassName}
		/>
	);
}
