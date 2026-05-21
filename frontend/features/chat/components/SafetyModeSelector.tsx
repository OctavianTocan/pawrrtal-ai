'use client';

import {
	ComposerActionSelector,
	type ComposerActionSelectorItem,
} from '@octavian-tocan/react-chat-composer/primitives';
import { HandIcon, ShieldAlertIcon, ShieldCheckIcon, SlidersHorizontalIcon } from 'lucide-react';
import type * as React from 'react';
import { useMemo } from 'react';
import { usePersistedState } from '@/hooks/use-persisted-state';
import {
	CHAT_STORAGE_KEYS,
	DEFAULT_SAFETY_MODE,
	SAFETY_MODES,
	type SafetyMode,
} from '../constants';

/**
 * Runtime guard so an older persisted value from a renamed mode doesn't
 * crash the picker — falls back to {@link DEFAULT_SAFETY_MODE}.
 */
function isSafetyMode(value: unknown): value is SafetyMode {
	return typeof value === 'string' && (SAFETY_MODES as readonly string[]).includes(value);
}

/**
 * Static metadata for the pawrrtal safety modes. Lives here (not in the
 * shared constants module) because the Lucide icon components are React
 * render concerns, and the items are consumed by the generic
 * {@link ComposerActionSelector} primitive from the package.
 */
const SAFETY_MODE_ITEMS: ReadonlyArray<ComposerActionSelectorItem> = [
	{
		id: 'default-permissions',
		label: 'Default permissions',
		icon: <HandIcon aria-hidden="true" className="size-3.5" />,
		colorClass: 'text-info',
		bgClass: 'bg-info/15',
	},
	{
		id: 'auto-review',
		label: 'Auto-review',
		icon: <ShieldCheckIcon aria-hidden="true" className="size-3.5" />,
		colorClass: 'text-warning',
		bgClass: 'bg-warning/15',
	},
	{
		id: 'full-access',
		label: 'Full access',
		icon: <ShieldAlertIcon aria-hidden="true" className="size-3.5" />,
		colorClass: 'text-destructive',
		bgClass: 'bg-destructive/15',
	},
	{
		id: 'custom',
		label: 'Custom (config.toml)',
		icon: <SlidersHorizontalIcon aria-hidden="true" className="size-3.5" />,
		colorClass: 'text-muted-foreground',
		bgClass: 'bg-foreground/10',
		// Renders below a divider in the package's dropdown.
		advanced: true,
	},
];

/**
 * Host-local SafetyMode picker rendered in the composer's `footerActions`
 * slot. Replaces the previous in-tree `AutoReviewSelector` which combined
 * its own dropdown + persisted state implementation; this version delegates
 * dropdown chrome to the package's generic {@link ComposerActionSelector}
 * primitive and only owns pawrrtal-specific concerns (persistence key,
 * default mode, item metadata).
 *
 * @returns The safety-mode trigger paired with its dropdown menu.
 */
export function SafetyModeSelector(): React.JSX.Element {
	const [safetyMode, setSafetyMode] = usePersistedState<SafetyMode>({
		storageKey: CHAT_STORAGE_KEYS.safetyMode,
		defaultValue: DEFAULT_SAFETY_MODE,
		validate: isSafetyMode,
	});
	const items = useMemo(() => [...SAFETY_MODE_ITEMS], []);

	return (
		<ComposerActionSelector<SafetyMode>
			items={items}
			onSelect={setSafetyMode}
			selectedId={safetyMode}
			tooltip="Safety mode"
			triggerLabelClassName="hidden sm:contents"
		/>
	);
}
