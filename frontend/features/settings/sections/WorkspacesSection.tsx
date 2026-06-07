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
import { useRef, useState } from 'react';
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
		description: 'Speech-to-text plus Grok chat models routed via LiteLLM. Get a key from xAI.',
		placeholder: 'Your xAI API key',
		url: 'https://x.ai',
	},
	{
		key: 'OPENAI_API_KEY',
		label: 'OpenAI API Key',
		description: 'GPT-4o and o-series chat models routed via LiteLLM. Get a key from OpenAI.',
		placeholder: 'sk-...',
		url: 'https://platform.openai.com/api-keys',
	},
	{
		key: 'OPENAI_CODEX_OAUTH_TOKEN',
		label: 'OpenAI Codex OAuth Token',
		description: 'Enables Codex-backed image generation and other Codex plugin capabilities.',
		placeholder: 'Your Codex OAuth token',
		url: 'https://chatgpt.com/codex',
	},
	{
		key: 'NOTION_API_KEY',
		label: 'Notion API Key',
		description:
			'Unlocks the Notion plugin (search, read, write, sync). Create an Internal Integration and share the pages you want it to see.',
		placeholder: 'ntn_...',
		url: 'https://www.notion.so/profile/integrations',
	},
	{
		key: 'OPENCODE_API_KEY',
		label: 'OpenCode API Key',
		description:
			'OpenCode Go gateway — open-weight coding models (GLM, Kimi). Get a key from opencode.ai.',
		placeholder: 'Your OpenCode API key',
		url: 'https://opencode.ai/docs/zen',
	},
	{
		key: 'GITHUB_TOKEN',
		label: 'GitHub Token',
		description: 'Unlocks the GitHub Issues plugin so the agent can report actionable issues.',
		placeholder: 'github_pat_...',
		url: 'https://github.com/settings/tokens',
	},
	{
		key: 'GITHUB_ISSUES_REPO',
		label: 'GitHub Issues Repo',
		description:
			'Optional target repository for agent-reported issues. Leave empty to use the gateway default.',
		placeholder: 'owner/repo',
		url: 'https://docs.github.com/en/issues',
	},
	{
		key: 'ACTIVE_RECALL_ENABLED',
		label: 'Active Recall Enabled',
		description:
			'Master switch for the pre-turn memory lookup agent. If false, the recall agent is skipped entirely.',
		placeholder: 'true',
	},
	{
		key: 'ACTIVE_RECALL_MODEL',
		label: 'Active Recall Model',
		description:
			'Cheap, fast model used to query conversation history (LCM) and workspace files for context.',
		placeholder: 'google-ai:google/gemini-3.1-flash-lite',
	},
	{
		key: 'ACTIVE_RECALL_SEARCH_WORKSPACE',
		label: 'Active Recall Search Workspace',
		description:
			'Allow Active Recall to read local workspace files (e.g. TASKS.md) to gather context.',
		placeholder: 'true',
	},
	{
		key: 'ACTIVE_RECALL_TIMEOUT_S',
		label: 'Active Recall Timeout',
		description: 'Maximum seconds the Active Recall plugin may spend searching before a turn.',
		placeholder: '10',
	},
	{
		key: 'ACTIVE_RECALL_SYSTEM_PROMPT',
		label: 'Active Recall System Prompt',
		description:
			'Optional system prompt override for the Active Recall agent. If empty, falls back to the default prompt.',
		placeholder: 'Enter custom system prompt',
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
	// Track the last query data we synced so we can detect when the server
	// response changes and sync it inline during render instead of via effect.
	const lastSyncedDataRef = useRef(query.data);

	// Sync server data into the working copy when it arrives or refreshes,
	// but only while the form is clean. Without the `isDirty` guard, a
	// background refetch (e.g. on window focus) would clobber unsaved edits.
	if (query.data && query.data !== lastSyncedDataRef.current && !isDirty) {
		lastSyncedDataRef.current = query.data;
		setValues({ ...emptyEnvRecord(), ...query.data.vars });
	}

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
