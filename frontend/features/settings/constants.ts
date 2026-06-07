/**
 * Static catalog driving the settings page nav rail.
 *
 * Order here is the order rendered in the rail. `id` is the URL hash and
 * the React key. `path` is the route inside `/settings/[section]` (today
 * everything renders client-side under one route).
 */

import type { LucideIcon } from 'lucide-react';
import {
	Archive,
	BookOpen,
	Boxes,
	Cog,
	FolderGit2,
	GitBranch,
	Globe,
	Layers,
	MessageSquare,
	Plug,
	Puzzle,
	Sliders,
	SparklesIcon,
	Sun,
	TerminalSquare,
} from 'lucide-react';

/** Stable IDs for each settings section — used as the URL hash + React key. */
export const SETTINGS_SECTION_IDS = [
	'general',
	'workspaces',
	'appearance',
	'configuration',
	'personalization',
	'integrations',
	'plugins',
	'channels',
	'mcp-servers',
	'git',
	'environments',
	'worktrees',
	'browser-use',
	'archived-chats',
	'usage',
] as const;

/** Union of valid settings section IDs. */
export type SettingsSectionId = (typeof SETTINGS_SECTION_IDS)[number];

/** Display metadata for one row in the settings nav rail. */
export type SettingsSection = {
	/** Stable hash slug used as the React key + URL hash. */
	id: SettingsSectionId;
	/** Human-readable label rendered in the nav rail. */
	label: string;
	/** Lucide icon shown before the label. */
	Icon: LucideIcon;
};

/**
 * Catalog of every settings section. Co-locates the React-coupled icon
 * components alongside the slug + label so the nav rail renders from a
 * single tuple — adding a section only requires appending here.
 */
export const SETTINGS_SECTIONS = [
	{ id: 'general', label: 'General', Icon: Cog },
	{ id: 'workspaces', label: 'Workspaces', Icon: FolderGit2 },
	{ id: 'appearance', label: 'Appearance', Icon: Sun },
	{ id: 'configuration', label: 'Configuration', Icon: Sliders },
	{ id: 'personalization', label: 'Personalization', Icon: SparklesIcon },
	{ id: 'integrations', label: 'Integrations', Icon: Plug },
	{ id: 'plugins', label: 'Plugins', Icon: Puzzle },
	{ id: 'channels', label: 'Channels', Icon: MessageSquare },
	{ id: 'mcp-servers', label: 'MCP servers', Icon: Layers },
	{ id: 'git', label: 'Git', Icon: GitBranch },
	{ id: 'environments', label: 'Environments', Icon: TerminalSquare },
	{ id: 'worktrees', label: 'Worktrees', Icon: BookOpen },
	{ id: 'browser-use', label: 'Browser use', Icon: Globe },
	{ id: 'archived-chats', label: 'Archived chats', Icon: Archive },
	{ id: 'usage', label: 'Usage', Icon: Boxes },
] as const satisfies ReadonlyArray<SettingsSection>;
