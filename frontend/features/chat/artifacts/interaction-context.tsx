'use client';

/**
 * Context that lets interactive artifact widgets dispatch user submissions
 * back to the chat.
 *
 * @fileoverview The renderers in {@link ./components} are pure UI; the
 * "what happens on click/submit" is owned by whatever installs this
 * provider (today: {@link ../ChatContainer}, which binds the handler to
 * the existing `sendMessage` flow so an interaction becomes a regular
 * follow-up turn). Keeping the dispatch behind a context means the
 * renderer never imports the chat hooks directly — a future in-place
 * mutation mode can swap the handler without touching widget code.
 *
 * Two-layer pattern:
 *  - The outer provider, installed by the chat container, accepts a
 *    handler that takes a fully-shaped {@link ChatArtifactInteractionPayload}.
 *  - {@link ArtifactRenderer} re-wraps its subtree with an inner provider
 *    that injects the current artifact's `id`, so individual widgets only
 *    need to call `submit({ actionId, label, value })`.
 */

import { createContext, type ReactNode, use, useCallback, useMemo } from 'react';
import type {
	ChatArtifactInteractionMode,
	ChatArtifactInteractionPayload,
	ChatArtifactInteractionValue,
} from '@/lib/types';

/** Default submission mode — the renderer never sets `mode` itself. */
const DEFAULT_INTERACTION_MODE: ChatArtifactInteractionMode = 'new_turn';

/**
 * Handler the chat surface installs once and shares with every artifact
 * widget. Receives a fully-shaped payload (artifact id already injected
 * by the inner provider) and returns a Promise so callers can await
 * completion if they want — most renderers ignore the return value.
 */
export type ArtifactInteractionHandler = (
	payload: ChatArtifactInteractionPayload
) => Promise<void> | void;

/** Outer context value supplied by the chat surface. */
interface OuterContextValue {
	handler: ArtifactInteractionHandler;
}

/** Inner context value supplied by {@link ArtifactRenderer}. */
interface InnerContextValue {
	/** Artifact id captured from the surrounding {@link ArtifactRenderer}. */
	artifactId: string;
	/**
	 * Whether an outer {@link ArtifactInteractionProvider} is installed.
	 * Widgets render disabled when this is `false` so a missing dispatcher
	 * is visually communicated instead of silently swallowing clicks.
	 */
	hasHandler: boolean;
	/**
	 * Submit an interaction. Auto-injects `artifactId` + the default mode
	 * so widget code stays focused on the action-id/label/value triple.
	 */
	submit: (input: {
		actionId: string;
		label: string;
		value: ChatArtifactInteractionValue;
	}) => Promise<void> | void;
	/**
	 * Optional callback fired after a successful submit — used by
	 * {@link ArtifactDialog} to close itself when the user has answered.
	 * Renderers should NOT depend on this for behaviour; treat as polish.
	 */
	onSubmitted?: () => void;
}

const OuterContext = createContext<OuterContextValue | null>(null);
const InnerContext = createContext<InnerContextValue | null>(null);

/**
 * Props for the outer interaction provider.
 */
interface ArtifactInteractionProviderProps {
	/** Receives the fully-shaped payload and dispatches it. */
	handler: ArtifactInteractionHandler;
	/** Wrapped subtree — typically the entire chat surface. */
	children: ReactNode;
}

/**
 * Installs the outer handler. Place around every component tree that may
 * render an artifact (today: the chat surface).
 */
export function ArtifactInteractionProvider({
	handler,
	children,
}: ArtifactInteractionProviderProps): ReactNode {
	const value = useMemo<OuterContextValue>(() => ({ handler }), [handler]);
	return <OuterContext.Provider value={value}>{children}</OuterContext.Provider>;
}

/**
 * Props for the inner per-artifact provider used by {@link ArtifactRenderer}.
 */
interface ArtifactInteractionScopeProps {
	/** Artifact id auto-injected into every submission from this subtree. */
	artifactId: string;
	/** Fired after a successful submit; opt-in. */
	onSubmitted?: () => void;
	/** Wrapped subtree — the rendered artifact spec. */
	children: ReactNode;
}

/**
 * Per-artifact inner provider. Reads the outer handler, captures the
 * artifact id, and exposes a tight `submit({ actionId, label, value })`
 * API to descendant widgets.
 *
 * Renders children unwrapped (no extra DOM) so it can sit inside json-render
 * without disturbing the spec's layout.
 */
export function ArtifactInteractionScope({
	artifactId,
	onSubmitted,
	children,
}: ArtifactInteractionScopeProps): ReactNode {
	const outer = use(OuterContext);

	const submit = useCallback(
		async (input: {
			actionId: string;
			label: string;
			value: ChatArtifactInteractionValue;
		}): Promise<void> => {
			if (!outer) return;
			await outer.handler({
				artifactId,
				actionId: input.actionId,
				label: input.label,
				value: input.value,
				mode: DEFAULT_INTERACTION_MODE,
			});
			onSubmitted?.();
		},
		[artifactId, onSubmitted, outer]
	);

	const hasHandler = outer !== null;
	const value = useMemo<InnerContextValue>(
		() => ({ artifactId, hasHandler, submit, onSubmitted }),
		[artifactId, hasHandler, submit, onSubmitted]
	);

	return <InnerContext.Provider value={value}>{children}</InnerContext.Provider>;
}

/**
 * Hook consumed by interactive widget renderers. Returns `null` when no
 * provider is installed — widgets must render a disabled state in that
 * case rather than crashing (read-only previews, tests, etc.).
 */
export function useArtifactInteraction(): InnerContextValue | null {
	return use(InnerContext);
}
