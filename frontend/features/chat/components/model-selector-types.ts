/**
 * Data model and grouping logic for the model selector.
 *
 * @fileoverview Extracted from `model-selector-host-rows.tsx` so the
 * component file only exports React components (react-doctor
 * `only-export-components`).
 */

import type * as React from 'react';
import type { ChatModelOption } from '../hooks/use-chat-models';

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

/** Render props for the single-vendor host menu row. */
export interface HostMenuRowRenderProps extends HostMenuRowProps, WithRenderModelRow {}

/** Render props for the multi-vendor host menu row. */
export interface MultiVendorHostMenuRowRenderProps
	extends MultiVendorHostMenuRowProps,
		WithRenderModelRow {}

// ---------------------------------------------------------------------------
// Grouping logic
// ---------------------------------------------------------------------------

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
