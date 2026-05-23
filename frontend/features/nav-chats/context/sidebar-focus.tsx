/**
 * @file sidebar-focus.tsx
 *
 * Manages keyboard focus across the three major UI regions: sidebar,
 * navigator (conversation list), and chat panel. Without this, Tab/Shift+Tab
 * would walk through every focusable element on the page sequentially. This
 * system lets us treat each region as a "zone" that can be jumped between
 * with a single keystroke, similar to how VS Code handles sidebar/editor/panel
 * focus cycling.
 *
 * Each zone registers itself (with a ref and an optional focusFirst callback)
 * and the provider tracks which zone is currently active. Navigation skips
 * unregistered zones so conditionally-rendered regions don't block the cycle.
 */
'use client';

import type React from 'react';
import {
	createContext,
	use,
	useCallback,
	useEffect,
	useEffectEvent,
	useMemo,
	useRef,
	useState,
} from 'react';

/** Identifies one of the three focusable regions. */
export type FocusZoneId = 'sidebar' | 'navigator' | 'chat';

/**
 * How the focus change was triggered. Keyboard navigation should move DOM focus;
 * click-initiated focus changes should not (the click itself already focused the element).
 */
export type FocusIntent = 'keyboard' | 'click' | 'programmatic';

/** Options passed when requesting focus on a zone. */
export interface FocusZoneOptions {
	intent?: FocusIntent;
	/** If true, actually move DOM focus to the zone root or its first focusable child. */
	moveFocus?: boolean;
}

/** Internal registration record for a mounted focus zone. */
type FocusZoneRegistration = {
	id: FocusZoneId;
	ref: React.RefObject<HTMLElement | null>;
	/** Optional callback to focus the first interactive child instead of the zone root. */
	focusFirst?: () => void;
};

/** Tracks which zone is focused, how it got focused, and whether DOM focus needs to move. */
type FocusState = {
	zone: FocusZoneId | null;
	intent: FocusIntent | null;
	/** True for one microtask after a keyboard/programmatic focus change. */
	shouldMoveDOMFocus: boolean;
};

/** Context value exposing focus-zone state and navigation methods to consumers. */
type FocusContextValue = {
	focusState: FocusState;
	registerZone: (zone: FocusZoneRegistration) => void;
	unregisterZone: (id: FocusZoneId) => void;
	focusZone: (id: FocusZoneId, options?: FocusZoneOptions) => void;
	focusNextZone: () => void;
	focusPreviousZone: () => void;
	isZoneFocused: (id: FocusZoneId) => boolean;
};

/**
 * Defines the Tab-order cycle. Zones are visited in this order for
 * focusNextZone and reversed for focusPreviousZone.
 */
const ZONE_ORDER: FocusZoneId[] = ['sidebar', 'navigator', 'chat'];

const FocusContext = createContext<FocusContextValue | null>(null);

/**
 * Wraps the app layout and provides focus-zone coordination to all children.
 * Mount this once above the sidebar + chat layout.
 */
export function SidebarFocusProvider({
	children,
}: {
	children: React.ReactNode;
}): React.JSX.Element {
	const zonesRef = useRef(new Map<FocusZoneId, FocusZoneRegistration>());
	const [focusState, setFocusState] = useState<FocusState>({
		zone: null,
		intent: null,
		shouldMoveDOMFocus: false,
	});

	const registerZone = useCallback((zone: FocusZoneRegistration) => {
		zonesRef.current.set(zone.id, zone);
	}, []);

	const unregisterZone = useCallback((id: FocusZoneId) => {
		zonesRef.current.delete(id);
	}, []);

	/**
	 * Move logical focus to a zone. If moveFocus is true (default for keyboard),
	 * also moves DOM focus via focusFirst() or the zone root element.
	 */
	const focusZone = useCallback((id: FocusZoneId, options?: FocusZoneOptions) => {
		const zone = zonesRef.current.get(id);
		if (!zone) {
			return;
		}

		const intent = options?.intent ?? 'programmatic';
		// Click-initiated changes don't need to move DOM focus (the click already did).
		const shouldMoveDOMFocus = options?.moveFocus ?? intent !== 'click';

		setFocusState({ zone: id, intent, shouldMoveDOMFocus });

		if (shouldMoveDOMFocus) {
			if (zone.focusFirst) {
				zone.focusFirst();
			} else {
				// Ensure the zone root is focusable before attempting focus.
				// Plain divs without tabindex silently ignore .focus() calls.
				const el = zone.ref.current;
				if (el && !el.hasAttribute('tabindex')) {
					el.setAttribute('tabindex', '-1');
				}
				el?.focus();
			}

			// Clear the flag after one microtask so consumers only see it for one render.
			queueMicrotask(() => {
				setFocusState((current) => ({ ...current, shouldMoveDOMFocus: false }));
			});
		}
	}, []);

	/**
	 * Cycle to the next zone in ZONE_ORDER, skipping any that aren't currently
	 * registered (conditionally rendered or feature-flagged out).
	 */
	const focusNextZone = useCallback(() => {
		const currentIndex = focusState.zone ? ZONE_ORDER.indexOf(focusState.zone) : -1;
		for (let i = 1; i <= ZONE_ORDER.length; i++) {
			const candidate = ZONE_ORDER[(currentIndex + i) % ZONE_ORDER.length] as FocusZoneId;
			if (zonesRef.current.has(candidate)) {
				focusZone(candidate, { intent: 'keyboard', moveFocus: true });
				return;
			}
		}
	}, [focusState.zone, focusZone]);

	/** Cycle to the previous zone, same skip logic as focusNextZone. */
	const focusPreviousZone = useCallback(() => {
		const currentIndex = focusState.zone ? ZONE_ORDER.indexOf(focusState.zone) : 0;
		for (let i = 1; i <= ZONE_ORDER.length; i++) {
			const candidate = ZONE_ORDER[
				(currentIndex - i + ZONE_ORDER.length) % ZONE_ORDER.length
			] as FocusZoneId;
			if (zonesRef.current.has(candidate)) {
				focusZone(candidate, { intent: 'keyboard', moveFocus: true });
				return;
			}
		}
	}, [focusState.zone, focusZone]);

	const value = useMemo<FocusContextValue>(
		() => ({
			focusState,
			registerZone,
			unregisterZone,
			focusZone,
			focusNextZone,
			focusPreviousZone,
			isZoneFocused: (id) => focusState.zone === id,
		}),
		[focusState, registerZone, unregisterZone, focusZone, focusNextZone, focusPreviousZone]
	);

	return <FocusContext.Provider value={value}>{children}</FocusContext.Provider>;
}

/** Access the focus context. Throws if called outside SidebarFocusProvider. */
function useSidebarFocusContext(): FocusContextValue {
	const context = use(FocusContext);
	if (!context) {
		throw new Error('useSidebarFocusContext must be used within SidebarFocusProvider.');
	}
	return context;
}

/**
 * Non-throwing variant of `useSidebarFocusContext`. Returns `null` when called
 * outside `SidebarFocusProvider` instead of throwing. Use in components that
 * may render in trees with or without the focus-zone provider mounted.
 */
export function useOptionalSidebarFocusContext(): FocusContextValue | null {
	return use(FocusContext);
}

/**
 * Hook for a component to participate in the focus zone system.
 * Returns a ref to attach to the zone's root element, plus focus state
 * and a manual focus trigger.
 *
 * @param zoneId - Which zone this component represents.
 * @param enabled - Set false to unregister (e.g. when the panel is hidden).
 * @param onFocus - Called when this zone becomes the active zone.
 * @param onBlur - Called when this zone loses active status.
 * @param focusFirst - Optional: focus the first interactive child instead of the root.
 */
export function useFocusZone({
	zoneId,
	enabled = true,
	onFocus,
	onBlur,
	focusFirst,
}: {
	zoneId: FocusZoneId;
	enabled?: boolean;
	onFocus?: () => void;
	onBlur?: () => void;
	focusFirst?: () => void;
}) {
	const zoneRef = useRef<HTMLDivElement>(null);
	const { focusState, registerZone, unregisterZone, focusZone, isZoneFocused } =
		useSidebarFocusContext();
	const isFocused = enabled && isZoneFocused(zoneId);
	const shouldMoveDOMFocus =
		enabled && focusState.zone === zoneId && focusState.shouldMoveDOMFocus;
	const intent = focusState.zone === zoneId ? focusState.intent : null;
	const previousIsFocused = useRef(isFocused);
	const fireOnFocus = useEffectEvent((): void => {
		onFocus?.();
	});
	const fireOnBlur = useEffectEvent((): void => {
		onBlur?.();
	});

	// Register/unregister this zone as it mounts, unmounts, or toggles enabled.
	useEffect(() => {
		if (!enabled) {
			unregisterZone(zoneId);
			return;
		}

		// Stamp a data attribute for debugging/testing.
		if (zoneRef.current) {
			zoneRef.current.dataset.focusZone = zoneId;
		}

		registerZone({
			id: zoneId,
			ref: zoneRef,
			focusFirst,
		});

		return () => unregisterZone(zoneId);
	}, [enabled, focusFirst, registerZone, unregisterZone, zoneId]);

	// Fire onFocus/onBlur callbacks when the zone's active state changes.
	useEffect(() => {
		if (isFocused && !previousIsFocused.current) {
			fireOnFocus();
		}

		if (!isFocused && previousIsFocused.current) {
			fireOnBlur();
		}

		previousIsFocused.current = isFocused;
	}, [isFocused]);

	return {
		zoneRef,
		isFocused,
		shouldMoveDOMFocus,
		intent,
		/** Manually request focus on this zone. */
		focus: useCallback(
			(options?: FocusZoneOptions) => focusZone(zoneId, options),
			[focusZone, zoneId]
		),
	};
}
