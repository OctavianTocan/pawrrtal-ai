'use client';

/**
 * @fileoverview Host-row submenu components and grouping logic for
 * `ModelSelectorPopover`. Extracted to keep the popover file under the
 * 500-line budget while preserving the three-level walk:
 * host → (optional vendor) → model.
 */

import {
	DropdownSubmenu,
	DropdownSubmenuContent,
	DropdownSubmenuTrigger,
} from '@octavian-tocan/react-dropdown';
import type * as React from 'react';
import { cn } from '@/lib/utils';
import type { ChatModelOption } from '../hooks/use-chat-models';
import { hostLabel, vendorLabel } from './model-picker-labels';
import { vendorLogo } from './VendorLogos';

// ---------------------------------------------------------------------------
// Data model
// ---------------------------------------------------------------------------

/** One vendor bucket inside a host group. */
export interface VendorGroup {
	/** Vendor wire slug. */
	vendor: string;
	/** Models authored by this vendor, in catalog order. */
	entries: readonly ChatModelOption[];
}

/** One host group: a provider + the vendors it serves. */
export interface HostGroup {
	/** Host wire slug. */
	host: string;
	/** Vendors served by this host, in catalog order. */
	vendors: readonly VendorGroup[];
}

/**
 * Group models by host, then by vendor inside each host.
 *
 * Preserves the catalog's declaration order for both hosts and vendors.
 * Entries with missing or empty `host`/`vendor` slugs are silently skipped.
 *
 * @param models - The full catalog from `useChatModels()`.
 * @returns Read-only array of host groups, each with their vendor sub-groups.
 */
export function groupModelsByHost(models: readonly ChatModelOption[]): readonly HostGroup[] {
	const hostOrder: string[] = [];
	const hostBuckets = new Map<
		string,
		{ vendorOrder: string[]; byVendor: Map<string, ChatModelOption[]> }
	>();

	for (const model of models) {
		if (typeof model.host !== 'string' || model.host.length === 0) continue;
		if (typeof model.vendor !== 'string' || model.vendor.length === 0) continue;

		let host = hostBuckets.get(model.host);
		if (!host) {
			host = { vendorOrder: [], byVendor: new Map() };
			hostBuckets.set(model.host, host);
			hostOrder.push(model.host);
		}
		let vendor = host.byVendor.get(model.vendor);
		if (!vendor) {
			vendor = [];
			host.byVendor.set(model.vendor, vendor);
			host.vendorOrder.push(model.vendor);
		}
		vendor.push(model);
	}

	return hostOrder.map((host) => {
		const bucket = hostBuckets.get(host);
		if (!bucket) return { host, vendors: [] };
		return {
			host,
			vendors: bucket.vendorOrder.map((vendor) => ({
				vendor,
				entries: bucket.byVendor.get(vendor) ?? [],
			})),
		};
	});
}

// ---------------------------------------------------------------------------
// Internal sub-components
// ---------------------------------------------------------------------------

/** Render-only wrapper that resolves the vendor logo from the canonical map. */
function VendorLogo({
	vendor,
	className,
}: {
	vendor: string;
	className?: string;
}): React.JSX.Element {
	const Logo = vendorLogo(vendor);
	return <Logo className={cn('size-3', className)} />;
}

// ---------------------------------------------------------------------------
// Host-row components
// ---------------------------------------------------------------------------

/** Props shared by both host-row variants. */
interface HostMenuRowProps {
	/** The host group being rendered. */
	group: HostGroup;
	/** True when a model from this host is currently selected. */
	isActiveHost: boolean;
	/** Currently selected model ID — used to mark the selected model row. */
	selectedModelId: string;
	/** Callback fired when the user selects a model. */
	onSelectModel: (modelId: string) => void;
}

/** Props exclusive to the multi-vendor variant. */
interface MultiVendorHostMenuRowProps extends HostMenuRowProps {
	/** Currently selected model, or `null` when none is selected yet. */
	selectedModel: ChatModelOption | null;
}

/** Props for a single model row rendered inside a host submenu. */
export interface ModelRowSlotProps {
	/** The model to render. */
	model: ChatModelOption;
	/** True when this model is the currently selected one. */
	isSelected: boolean;
	/** Callback fired when the user selects this model. */
	onSelect: (modelId: string) => void;
}

/** Mixin that adds the `renderModelRow` slot to a host-row props interface. */
interface WithRenderModelRow {
	/** Render a single model row. Called once per model entry. */
	renderModelRow: (props: ModelRowSlotProps) => React.JSX.Element;
}

/**
 * A thin wrapper so host-row files can render model rows without importing
 * the heavyweight `ModelRow` (which calls `useDropdownContext` and
 * `usePointerDownCommit`). Callers render via the `renderModelRow` slot.
 *
 * This indirection keeps `model-selector-host-rows.tsx` a pure layout
 * module with no hook calls, which simplifies testing.
 */
export interface HostMenuRowRenderProps extends HostMenuRowProps, WithRenderModelRow {}

/** Multi-vendor variant render props. */
export interface MultiVendorHostMenuRowRenderProps
	extends MultiVendorHostMenuRowProps,
		WithRenderModelRow {}

/**
 * Flyout submenu for a single host that has only one vendor.
 *
 * The intermediate vendor screen is skipped — models render directly inside
 * the host's submenu panel, with the single vendor's logo shown in the trigger.
 */
export function SingleVendorHostMenuRow({
	group,
	isActiveHost,
	selectedModelId,
	onSelectModel,
	renderModelRow,
}: HostMenuRowRenderProps): React.JSX.Element | null {
	const onlyVendor = group.vendors[0];
	if (!onlyVendor) return null;

	return (
		<DropdownSubmenu>
			{/* `DropdownSubmenuTrigger` bakes in its own flyout chevron — rendering an
			    explicit ChevronRightIcon here used to produce two arrows side-by-side. We
			    only emit the "active host" check now; the library's chevron handles the
			    "expand" affordance for every row. */}
			<DropdownSubmenuTrigger
				className={cn(
					'flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-foreground/[0.04]',
					isActiveHost && 'bg-foreground/[0.07]'
				)}
			>
				<VendorLogo vendor={onlyVendor.vendor} />
				<span className="min-w-0 flex-1 truncate text-left">{hostLabel(group.host)}</span>
			</DropdownSubmenuTrigger>
			<DropdownSubmenuContent className="chat-composer-dropdown-menu popover-styled p-1 min-w-64">
				{onlyVendor.entries.map((model) =>
					renderModelRow({
						model,
						isSelected: selectedModelId === model.id,
						onSelect: onSelectModel,
					})
				)}
			</DropdownSubmenuContent>
		</DropdownSubmenu>
	);
}

/**
 * Flyout submenu for a host that carries multiple vendors.
 *
 * Root trigger opens the vendor list; each vendor entry opens its own model list.
 */
export function MultiVendorHostMenuRow({
	group,
	isActiveHost,
	selectedModel,
	selectedModelId,
	onSelectModel,
	renderModelRow,
}: MultiVendorHostMenuRowRenderProps): React.JSX.Element {
	return (
		<DropdownSubmenu>
			<DropdownSubmenuTrigger
				className={cn(
					'flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-foreground/[0.04]',
					isActiveHost && 'bg-foreground/[0.07]'
				)}
			>
				<span className="min-w-0 flex-1 truncate text-left">{hostLabel(group.host)}</span>
			</DropdownSubmenuTrigger>
			<DropdownSubmenuContent className="chat-composer-dropdown-menu popover-styled p-1 min-w-56">
				{group.vendors.map((vendorGroup) => {
					const isActiveVendor =
						selectedModel?.host === group.host &&
						selectedModel?.vendor === vendorGroup.vendor;
					return (
						<DropdownSubmenu key={vendorGroup.vendor}>
							<DropdownSubmenuTrigger
								className={cn(
									'flex w-full cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-foreground/[0.04]',
									isActiveVendor && 'bg-foreground/[0.07]'
								)}
							>
								<VendorLogo vendor={vendorGroup.vendor} />
								<span className="min-w-0 flex-1 truncate text-left">
									{vendorLabel(vendorGroup.vendor)}
								</span>
							</DropdownSubmenuTrigger>
							<DropdownSubmenuContent className="chat-composer-dropdown-menu popover-styled p-1 min-w-64">
								{vendorGroup.entries.map((model) =>
									renderModelRow({
										model,
										isSelected: selectedModelId === model.id,
										onSelect: onSelectModel,
									})
								)}
							</DropdownSubmenuContent>
						</DropdownSubmenu>
					);
				})}
			</DropdownSubmenuContent>
		</DropdownSubmenu>
	);
}
