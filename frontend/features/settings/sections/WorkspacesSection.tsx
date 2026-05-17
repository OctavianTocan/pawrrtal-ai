/**
 * @fileoverview Settings → Workspaces — per-workspace environment variable
 * overrides.
 *
 * Container that wires:
 *   - `useWorkspaceEnv()` — TanStack Query GET of the user's overrides.
 *   - `useUpsertWorkspaceEnv()` — TanStack mutation that PATCHes new
 *     values onto the encrypted .env file.
 *   - `WorkspacesSectionView` — pure presentation; receives the working
 *     copy + handlers as props.
 *
 * The container owns the working-copy state (form edits before Save) and
 * the per-key visibility toggle. The query/mutation handle abort-on-unmount,
 * caching, and dedup automatically.
 */

'use client';

import type * as React from 'react';
import { useEffect, useState } from 'react';
import {
	extractApiErrorMessage,
	useUpsertWorkspaceEnv,
	useWorkspaceEnv,
	WORKSPACE_ENV_KEY_IDS,
	type WorkspaceEnvKey,
} from '@/features/settings/workspace-env/use-workspace-env';
import {
	type WorkspaceEnvKeyMeta,
	WorkspacesSectionView,
} from '@/features/settings/workspace-env/WorkspacesSectionView';

/**
 * UI-facing metadata for each overridable key. Pure presentation concern
 * (label, help text, where to get the key) — kept on the frontend so
 * adding a new copy tweak doesn't require a backend deploy. The `key`
 * field is the contract with the backend allowlist.
 */
const KEY_METAS: readonly WorkspaceEnvKeyMeta[] = [
	{
		key: 'GEMINI_API_KEY',
		label: 'Gemini API Key',
		description: 'Google Gemini. Get a key from Google AI Studio.',
		placeholder: 'AIza...',
		url: 'https://aistudio.google.com/apikey',
	},
	{
		key: 'CLAUDE_CODE_OAUTH_TOKEN',
		label: 'Claude OAuth Token',
		description: 'Run `claude setup-token` while logged in to Claude Code to get this.',
		placeholder: 'sk-ant-...',
		url: 'https://docs.anthropic.com/en/docs/claude-code',
	},
	{
		key: 'EXA_API_KEY',
		label: 'Exa API Key',
		description: 'Powers web search. Get a key from exa.ai.',
		placeholder: 'Your Exa API key',
		url: 'https://exa.ai',
	},
	{
		key: 'XAI_API_KEY',
		label: 'xAI API Key',
		description: 'Speech-to-text. Get a key from xAI.',
		placeholder: 'Your xAI API key',
		url: 'https://x.ai',
	},
	{
		key: 'NOTION_API_KEY',
		label: 'Notion API Key',
		description:
			'Unlocks the Notion plugin (search, read, write, sync). Create an Internal Integration and share the pages you want it to see.',
		placeholder: 'ntn_...',
		url: 'https://www.notion.so/profile/integrations',
	},
];

/** Empty record with every overridable key seeded to the empty string. */
function emptyEnvRecord(): Record<WorkspaceEnvKey, string> {
	const result = {} as Record<WorkspaceEnvKey, string>;
	for (const key of WORKSPACE_ENV_KEY_IDS) {
		result[key] = '';
	}
	return result;
}

/**
 * Settings → Workspaces container component.
 *
 * Manages local form state, kicks off the GET on mount via TanStack
 * Query, and submits edits via the upsert mutation. Renders nothing of
 * its own — delegates all presentation to {@link WorkspacesSectionView}.
 */
export function WorkspacesSection(): React.JSX.Element {
	const query = useWorkspaceEnv();
	const mutation = useUpsertWorkspaceEnv();

	// Working copy: starts empty and is replaced once the query lands.
	// Edits are tracked locally so Discard can revert to the last
	// server-known state (`query.data`) without an extra fetch.
	const [values, setValues] = useState<Record<WorkspaceEnvKey, string>>(emptyEnvRecord);
	const [showTokens, setShowTokens] = useState<Partial<Record<WorkspaceEnvKey, boolean>>>({});
	const [isDirty, setIsDirty] = useState(false);

	// Sync server data into the working copy when it arrives or refreshes,
	// but only while the form is clean. Without the `isDirty` guard, a
	// background refetch (e.g. on window focus) would clobber unsaved edits.
	useEffect(() => {
		if (!query.data || isDirty) return;
		setValues({ ...emptyEnvRecord(), ...query.data.vars });
	}, [query.data, isDirty]);

	const handleValueChange = (key: WorkspaceEnvKey, value: string): void => {
		setValues((current) => ({ ...current, [key]: value }));
		setIsDirty(true);
	};

	const handleToggleVisibility = (key: WorkspaceEnvKey): void => {
		setShowTokens((current) => ({ ...current, [key]: !current[key] }));
	};

	const handleSave = (): void => {
		mutation.mutate(values, {
			onSuccess: () => {
				setIsDirty(false);
			},
		});
	};

	const handleDiscard = (): void => {
		setValues({ ...emptyEnvRecord(), ...(query.data?.vars ?? {}) });
		setIsDirty(false);
		mutation.reset();
	};

	// Surface the most relevant error: mutation errors override query
	// errors because the user just attempted an action and expects
	// feedback on it. `extractApiErrorMessage` parses the FastAPI
	// `detail` body out of the fetch wrapper's "API Error: ..." string.
	let errorMessage: string | null = null;
	if (mutation.error !== null) {
		errorMessage = extractApiErrorMessage(
			mutation.error,
			'Failed to save workspace environment.'
		);
	} else if (query.error !== null) {
		errorMessage = extractApiErrorMessage(query.error, 'Failed to load workspace environment.');
	}

	return (
		<WorkspacesSectionView
			errorMessage={errorMessage}
			keyMetas={KEY_METAS}
			onDiscard={handleDiscard}
			onSave={handleSave}
			onToggleVisibility={handleToggleVisibility}
			onValueChange={handleValueChange}
			state={{
				isDirty,
				isLoading: query.isLoading,
				isSaving: mutation.isPending,
				showTokens,
			}}
			values={values}
		/>
	);
}
