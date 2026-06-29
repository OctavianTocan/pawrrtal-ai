import type { WorkspaceEnvKey, WorkspaceEnvResponse } from './use-workspace-env';
import { WORKSPACE_ENV_KEY_IDS } from './use-workspace-env';
import type { WorkspaceEnvKeyMeta } from './WorkspacesSectionView';

/**
 * UI-facing metadata for each overridable key. Pure presentation concern
 * (label, help text, where to get the key) — kept on the frontend so adding a
 * copy tweak does not require a backend deploy. The `key` field is the contract
 * with the backend allowlist.
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
    description: 'OpenCode Go gateway — open-weight coding models (GLM, Kimi). Get a key from opencode.ai.',
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
    description: 'Optional target repository for agent-reported issues. Leave empty to use the gateway default.',
    placeholder: 'owner/repo',
    url: 'https://docs.github.com/en/issues',
  },
  {
    key: 'ACTIVE_RECALL_ENABLED',
    label: 'Active Recall Enabled',
    description: 'Master switch for the pre-turn memory lookup agent. If false, the recall agent is skipped entirely.',
    placeholder: 'true',
  },
  {
    key: 'ACTIVE_RECALL_MODEL',
    label: 'Active Recall Model',
    description: 'Cheap, fast model used to query conversation history (LCM) and workspace files for context.',
    placeholder: 'google-ai:google/gemini-3.1-flash-lite',
  },
  {
    key: 'ACTIVE_RECALL_SEARCH_WORKSPACE',
    label: 'Active Recall Search Workspace',
    description: 'Allow Active Recall to read local workspace files (e.g. TASKS.md) to gather context.',
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

const STATIC_KEY_METAS = new Map(KEY_METAS.map((meta) => [meta.key, meta]));

function titleFromEnvKey(key: string): string {
  return key
    .split('_')
    .filter(Boolean)
    .map((part) => part.slice(0, 1) + part.slice(1).toLowerCase())
    .join(' ');
}

function metaFromApiKey(key: string, response: WorkspaceEnvResponse | undefined): WorkspaceEnvKeyMeta {
  const apiMeta = response?.keys.find((entry) => entry.key === key);
  return {
    key,
    label: apiMeta?.label ?? titleFromEnvKey(key),
    description: apiMeta?.description ?? 'Plugin-provided workspace setting.',
    placeholder: apiMeta?.secret === false ? 'Enter value' : `Your ${titleFromEnvKey(key)}`,
    url: apiMeta?.help_url ?? undefined,
  };
}

export function workspaceEnvKeyMetasForResponse(
  response: WorkspaceEnvResponse | undefined
): readonly WorkspaceEnvKeyMeta[] {
  const responseKeys = response?.keys.map((entry) => entry.key) ?? Object.keys(response?.vars ?? {});
  const orderedKeys = [...WORKSPACE_ENV_KEY_IDS, ...responseKeys.filter((key) => !STATIC_KEY_METAS.has(key))];
  return orderedKeys.map((key) => STATIC_KEY_METAS.get(key) ?? metaFromApiKey(key, response));
}

/** Empty record with every overridable key seeded to the empty string. */
export function emptyEnvRecord(): Record<WorkspaceEnvKey, string> {
  const result: Record<WorkspaceEnvKey, string> = {};
  for (const key of WORKSPACE_ENV_KEY_IDS) {
    result[key] = '';
  }
  return result;
}
