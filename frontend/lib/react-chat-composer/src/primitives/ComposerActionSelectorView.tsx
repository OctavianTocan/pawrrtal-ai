/**
 * Pure presentational shell for the generic composer action selector.
 *
 * @fileoverview Renders a labelled trigger pill that opens a dropdown of
 * action items. Each item carries an optional icon + color/background class
 * pair and an optional `advanced` flag that adds a divider above it.
 */

'use client';

import { DropdownMenu } from '@octavian-tocan/react-dropdown';
import { CheckIcon, ChevronDownIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import { Button } from '../ui/Button';
import {
	Tooltip,
	TooltipContent,
	TooltipProvider,
	TooltipTrigger,
} from '../ui/Tooltip';
import { usePointerDownCommit } from '../hooks/usePointerDownCommit';
import { cn } from '../utils/cn';

/** Item entry rendered inside the selector. */
export interface ComposerActionSelectorItem {
	/** Stable identifier surfaced via `onSelect`. */
	id: string;
	/** Human-readable label shown in the row and trigger. */
	label: string;
	/** Optional leading glyph rendered next to the label. */
	icon?: ReactNode;
	/** Optional Tailwind text-color class for the icon + trigger label. */
	colorClass?: string;
	/** Optional Tailwind background class for the icon badge. */
	bgClass?: string;
	/** When true, a divider is rendered above this item. */
	advanced?: boolean;
}

/** Props for the pure presentational shell of the selector. */
export interface ComposerActionSelectorViewProps {
	/** Items rendered in the dropdown, in display order. */
	items: ComposerActionSelectorItem[];
	/** Currently-selected item id. */
	selectedId: string;
	/** Fired when the user picks an item. */
	onSelect: (id: string) => void;
	/** Tooltip text rendered over the trigger. Optional. */
	tooltip?: string;
	/** Whether the dropdown is currently open. */
	menuOpen: boolean;
	/** Whether the tooltip should be open. */
	tooltipOpen: boolean;
	/** Fired by Radix when the dropdown opens or closes. */
	onMenuOpenChange: (open: boolean) => void;
	/** Fired by Radix when the tooltip opens or closes. */
	onTooltipOpenChange: (open: boolean) => void;
	/** Optional Tailwind class for the label span inside the trigger button. */
	triggerLabelClassName?: string;
}

interface ComposerActionSelectorRowProps {
	item: ComposerActionSelectorItem;
	selectedId: string;
	onSelect: (item: ComposerActionSelectorItem) => void;
}

/** Single selectable row for {@link ComposerActionSelectorView}. */
function ComposerActionSelectorRow({
	item,
	selectedId,
	onSelect,
}: ComposerActionSelectorRowProps): React.JSX.Element {
	const commitSelection = usePointerDownCommit<HTMLButtonElement>(() => onSelect(item));

	return (
		<button
			type="button"
			className="flex w-full cursor-pointer items-center justify-between rounded-md px-2 py-1.5 text-sm hover:bg-[color:color-mix(in_oklch,var(--color-chat-foreground)_4%,transparent)]"
			onClick={commitSelection.onClick}
			onPointerDown={commitSelection.onPointerDown}
		>
			<span className="flex items-center gap-2">
				{item.icon ? (
					<span
						aria-hidden="true"
						className={cn(
							'inline-flex size-5 items-center justify-center rounded-[var(--radius-chat-sm)]',
							item.bgClass,
							item.colorClass
						)}
					>
						{item.icon}
					</span>
				) : null}
				{item.label}
			</span>
			{item.id === selectedId ? (
				<CheckIcon
					aria-hidden="true"
					className="size-3.5 text-[var(--color-chat-foreground)]"
				/>
			) : null}
		</button>
	);
}

/**
 * Renders the trigger and dropdown items for the generic action selector.
 *
 * @returns The trigger button paired with its dropdown menu.
 */
export function ComposerActionSelectorView({
	items,
	selectedId,
	onSelect,
	tooltip,
	menuOpen,
	tooltipOpen,
	onMenuOpenChange,
	onTooltipOpenChange,
	triggerLabelClassName,
}: ComposerActionSelectorViewProps): React.JSX.Element {
	const activeItem = items.find((item) => item.id === selectedId) ?? items[0];
	const triggerLabel = activeItem?.label ?? '';
	const triggerColor = activeItem?.colorClass;

	const triggerButton = (
		<Button
			className={cn(
				'h-7 gap-1 rounded-[var(--radius-chat-sm)] bg-transparent px-1.5 text-[12px] font-normal hover:bg-[color:color-mix(in_oklch,var(--color-chat-foreground)_4%,transparent)]',
				menuOpen &&
					'bg-[color:color-mix(in_oklch,var(--color-chat-foreground)_4%,transparent)]',
				triggerColor,
			)}
			type="button"
			variant="ghost"
		>
			{activeItem?.icon ?? null}
			<span className={cn('truncate sm:contents', triggerLabelClassName)}>
				{triggerLabel}
			</span>
			<ChevronDownIcon aria-hidden="true" className="size-3" />
		</Button>
	);

	const dropdown = (
		<DropdownMenu<ComposerActionSelectorItem>
			align="start"
			closeOnSelect
			usePortal
			placement="top"
			contentClassName="p-1 min-w-[208px] rounded-[var(--radius-chat-lg)] bg-[var(--color-chat-bg-elevated)] border border-[color:color-mix(in_oklch,var(--color-chat-border)_50%,transparent)] shadow-[var(--shadow-chat-minimal)]"
			getItemDisplay={(item) => item.label}
			getItemKey={(item) => item.id}
			getItemSeparator={(item) => Boolean(item.advanced)}
			items={items}
			onOpenChange={onMenuOpenChange}
			onSelect={(item) => onSelect(item.id)}
			renderItem={(item, _isSelected, handleSelect) => (
				<ComposerActionSelectorRow
					item={item}
					onSelect={handleSelect}
					selectedId={selectedId}
				/>
			)}
			trigger={triggerButton}
		/>
	);

	if (!tooltip) {
		return <span className="inline-flex">{dropdown}</span>;
	}

	return (
		<TooltipProvider disableHoverableContent>
			<Tooltip onOpenChange={onTooltipOpenChange} open={tooltipOpen}>
				<TooltipTrigger asChild>
					<span className="inline-flex">{dropdown}</span>
				</TooltipTrigger>
				<TooltipContent side="top">{tooltip}</TooltipContent>
			</Tooltip>
		</TooltipProvider>
	);
}
