'use client';

import {
	DropdownMenu,
	DropdownSubmenu,
	DropdownSubmenuContent,
	DropdownSubmenuTrigger,
	useDropdownContext,
} from '@octavian-tocan/react-dropdown';
import { ChevronDownIcon } from 'lucide-react';
import type * as React from 'react';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { usePointerDownCommit } from '@/hooks/use-pointer-down-commit';
import { useTooltipDropdown } from '@/hooks/use-tooltip-dropdown';
import { cn } from '@/lib/utils';
import type { ChatReasoningLevel } from '../constants';
import type { ChatModelOption } from '../hooks/use-chat-models';
import { hostLabel } from './model-picker-labels';
import { MultiVendorHostMenuRow, SingleVendorHostMenuRow } from './model-selector-host-rows';
import { groupModelsByHost, type ModelRowSlotProps } from './model-selector-types';

type ReasoningOption = {
	/** Stable reasoning value. */
	id: ChatReasoningLevel;
	/** Human-facing label. */
	label: string;
};

const REASONING_OPTIONS: ReasoningOption[] = [
	{ id: 'low', label: 'Low' },
	{ id: 'medium', label: 'Medium' },
	{ id: 'high', label: 'High' },
	{ id: 'extra-high', label: 'Extra High' },
];

/** Discriminated union of root-menu rows. */
type RootRow = { kind: 'host'; host: string } | { kind: 'thinking' };

/** Stable React key for each root row. */
function rootRowKey(row: RootRow): string {
	return row.kind === 'host' ? `host:${row.host}` : 'thinking';
}

/** Type-ahead display string for each root row — uses the host label or a fixed literal. */
function rootRowDisplay(row: RootRow): string {
	return row.kind === 'host' ? hostLabel(row.host) : 'Thinking';
}

/**
 * Render a model row; passed as a slot to host-row components.
 *
 * Pure function — depends only on its arguments, not on component state.
 * Lifted to module scope so React does not re-create it on every render.
 */
function renderModelRow({ model, isSelected, onSelect }: ModelRowSlotProps): React.JSX.Element {
	return <ModelRow key={model.id} model={model} isSelected={isSelected} onSelect={onSelect} />;
}

/**
 * Props for the compact model and reasoning selector used in the chat composer.
 */
export interface ModelSelectorPopoverProps {
	/** Catalog entries from `useChatModels()` — the full set of selectable models. */
	models: readonly ChatModelOption[];
	/** Currently selected canonical model ID. */
	selectedModelId: string;
	/** Currently selected reasoning level. */
	selectedReasoning: ChatReasoningLevel;
	/** Callback fired when the user chooses a model. */
	onSelectModel: (modelId: string) => void;
	/** Callback fired when the user chooses a reasoning level. */
	onSelectReasoning: (reasoning: ChatReasoningLevel) => void;
	/** When `true`, the trigger renders a neutral placeholder while the catalog loads. */
	isLoading?: boolean;
	/** When `true`, the trigger renders a catalog failure state. */
	isError?: boolean;
}

/** Placeholder label rendered while the catalog is still in flight. */
const LOADING_MODEL_LABEL = 'Loading…';
const MODEL_ERROR_LABEL = 'Models unavailable';
const NO_MODELS_LABEL = 'No models';
const SELECT_MODEL_LABEL = 'Select model';

function findModel(models: readonly ChatModelOption[], modelId: string): ChatModelOption | null {
	return models.find((model) => model.id === modelId) ?? null;
}

function getReasoningLabel(reasoning: ChatReasoningLevel): string {
	return REASONING_OPTIONS.find((option) => option.id === reasoning)?.label ?? 'Medium';
}

function getTriggerLabel({
	isError,
	isLoading,
	modelCount,
	selectedModel,
}: {
	isError: boolean;
	isLoading: boolean;
	modelCount: number;
	selectedModel: ChatModelOption | null;
}): string {
	if (isLoading) return LOADING_MODEL_LABEL;
	if (isError) return MODEL_ERROR_LABEL;
	if (modelCount === 0) return NO_MODELS_LABEL;
	return selectedModel?.short_name ?? SELECT_MODEL_LABEL;
}

/**
 * Submenu row that selects a model and closes the root dropdown.
 *
 * Lives inside the root `DropdownMenu`'s React tree, so `useDropdownContext`
 * resolves to the root's context — closing it on selection collapses the
 * entire submenu chain along with the root panel.
 */
function ModelRow({
	model,
	isSelected,
	onSelect,
}: {
	model: ChatModelOption;
	isSelected: boolean;
	onSelect: (modelId: string) => void;
}): React.JSX.Element {
	const { closeDropdown } = useDropdownContext();
	const commitSelection = usePointerDownCommit<HTMLButtonElement>(() => {
		onSelect(model.id);
		closeDropdown();
	});

	return (
		<button
			type="button"
			className={cn(
				'flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-foreground/[0.04]',
				isSelected && 'bg-foreground/[0.07] font-medium'
			)}
			onClick={commitSelection.onClick}
			onPointerDown={commitSelection.onPointerDown}
		>
			<div className="flex min-w-0 flex-1 flex-col text-left">
				<span className="truncate text-foreground">{model.short_name}</span>
				<span className="truncate text-[11px] text-muted-foreground">
					{model.description}
				</span>
			</div>
			{isSelected ? (
				<span className="ml-1 size-1.5 shrink-0 rounded-full bg-foreground" />
			) : null}
		</button>
	);
}

/**
 * Submenu row that selects a reasoning level and closes the root dropdown.
 */
function ReasoningRow({
	option,
	isSelected,
	onSelect,
}: {
	option: ReasoningOption;
	isSelected: boolean;
	onSelect: (reasoning: ChatReasoningLevel) => void;
}): React.JSX.Element {
	const { closeDropdown } = useDropdownContext();
	const commitSelection = usePointerDownCommit<HTMLButtonElement>(() => {
		onSelect(option.id);
		closeDropdown();
	});

	return (
		<button
			type="button"
			className={cn(
				'flex w-full cursor-pointer items-center justify-between rounded-md px-2 py-1.5 text-sm hover:bg-foreground/[0.04]',
				isSelected && 'bg-foreground/[0.07]'
			)}
			onClick={commitSelection.onClick}
			onPointerDown={commitSelection.onPointerDown}
		>
			<span>{option.label}</span>
		</button>
	);
}

/**
 * Renders the chat composer's model selector. Top-level rows group models by
 * host — single-vendor hosts skip the intermediate vendor screen and surface
 * their model list directly, while multi-vendor hosts add a vendor flyout level
 * between the host and model rows. The `Thinking` row at the bottom is a peer
 * submenu with the four reasoning levels and a descriptive secondary line,
 * mirroring the layout used by the Craft Agents reference design.
 *
 * Catalog data is supplied via the `models` prop — the source of truth is
 * the server-owned `GET /api/v1/models` endpoint surfaced through
 * `useChatModels()`. The picker is otherwise stateless.
 *
 * Built on `@octavian-tocan/react-dropdown` (the vendored package) to stay
 * consistent with `AutoReviewSelector` and `NavUser`. The package's
 * `DropdownSubmenu` family provides Radix-equivalent flyout submenus with
 * hover-open + ArrowRight-open keyboard semantics.
 */
export function ModelSelectorPopover({
	models,
	selectedModelId,
	selectedReasoning,
	onSelectModel,
	onSelectReasoning,
	isLoading = false,
	isError = false,
}: ModelSelectorPopoverProps): React.JSX.Element {
	const selectedModel = findModel(models, selectedModelId);
	const reasoningLabel = getReasoningLabel(selectedReasoning);
	const { menuOpen, tooltipOpen, handleMenuOpenChange, handleTooltipOpenChange } =
		useTooltipDropdown();
	const groupedHosts = groupModelsByHost(models);

	// Discriminated union of every root-level row currently in the menu.
	const rootRows: RootRow[] = [
		...groupedHosts.map((group) => ({ kind: 'host', host: group.host }) satisfies RootRow),
		{ kind: 'thinking' },
	];

	/** Select and render the correct host submenu variant based on vendor count. */
	function renderHostRow(hostSlug: string): React.JSX.Element | null {
		const group = groupedHosts.find((entry) => entry.host === hostSlug);
		if (!group || group.vendors.length === 0) return null;
		const isActiveHost = selectedModel?.host === hostSlug;

		if (group.vendors.length === 1) {
			// Single-vendor host: skip the intermediate vendor screen.
			return (
				<SingleVendorHostMenuRow
					group={group}
					isActiveHost={isActiveHost}
					selectedModelId={selectedModelId}
					onSelectModel={onSelectModel}
					renderModelRow={renderModelRow}
				/>
			);
		}

		// Multi-vendor host: host → vendor → model.
		return (
			<MultiVendorHostMenuRow
				group={group}
				isActiveHost={isActiveHost}
				selectedModel={selectedModel}
				selectedModelId={selectedModelId}
				onSelectModel={onSelectModel}
				renderModelRow={renderModelRow}
			/>
		);
	}

	const triggerLabel = getTriggerLabel({
		isError,
		isLoading,
		modelCount: models.length,
		selectedModel,
	});

	return (
		<TooltipProvider disableHoverableContent>
			<Tooltip onOpenChange={handleTooltipOpenChange} open={tooltipOpen}>
				<TooltipTrigger asChild>
					<span className="inline-flex">
						<DropdownMenu<RootRow>
							asChild
							usePortal
							placement="top"
							align="start"
							// Submenu rows handle their own selection + closeDropdown,
							// so the root menu's onSelect is unused but required.
							closeOnSelect={false}
							contentClassName="chat-composer-dropdown-menu popover-styled p-1 min-w-56"
							getItemDisplay={rootRowDisplay}
							getItemKey={rootRowKey}
							// Render a separator above the Thinking row to break the
							// host section from the reasoning section.
							getItemSeparator={(row) => row.kind === 'thinking'}
							items={rootRows}
							onOpenChange={handleMenuOpenChange}
							onSelect={() => {
								// no-op — submenu rows handle their own selection
							}}
							trigger={
								<Button
									aria-label="Select model and reasoning"
									className={cn(
										'h-7 max-w-[8.75rem] gap-1 rounded-[7px] border-0 bg-transparent px-2 text-[12px] font-normal text-muted-foreground hover:bg-foreground/[0.1] hover:text-foreground sm:max-w-none',
										menuOpen && 'bg-foreground/[0.08]'
									)}
									size="xs"
									type="button"
									variant="ghost"
								>
									<span className="truncate text-foreground">{triggerLabel}</span>
									<span className="hidden sm:inline">{reasoningLabel}</span>
									<ChevronDownIcon aria-hidden="true" className="size-3" />
								</Button>
							}
							renderItem={(row) => {
								if (row.kind === 'host') {
									return renderHostRow(row.host);
								}
								// 'thinking' row
								return (
									<DropdownSubmenu>
										<DropdownSubmenuTrigger className="flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-foreground/[0.04]">
											<div className="flex min-w-0 flex-1 flex-col text-left">
												<span className="truncate text-foreground">
													Thinking: {reasoningLabel}
												</span>
												<span className="truncate text-[11px] text-muted-foreground">
													Extended reasoning depth
												</span>
											</div>
										</DropdownSubmenuTrigger>
										<DropdownSubmenuContent className="chat-composer-dropdown-menu popover-styled p-1 min-w-32">
											{REASONING_OPTIONS.map((option) => (
												<ReasoningRow
													key={option.id}
													option={option}
													isSelected={selectedReasoning === option.id}
													onSelect={onSelectReasoning}
												/>
											))}
										</DropdownSubmenuContent>
									</DropdownSubmenu>
								);
							}}
						/>
					</span>
				</TooltipTrigger>
				<TooltipContent side="top">Choose model and reasoning level</TooltipContent>
			</Tooltip>
		</TooltipProvider>
	);
}
