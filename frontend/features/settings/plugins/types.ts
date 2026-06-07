/** Shared types for the Settings → Plugins surface. */

export interface WorkspacePluginCapability {
	plugin_id: string;
	capability_id: string;
	key: string;
	type: string;
	title: string;
	description: string;
	tags: string[];
	intents: string[];
	slots: string[];
	state: string;
	preferred: boolean;
	priority: number;
	exposure: string;
	permissions: string[];
	requires_confirmation: boolean;
	input_schema: Record<string, unknown>;
	examples: Record<string, unknown>[];
	invokable: boolean;
}

export interface WorkspacePlugin {
	plugin_id: string;
	name: string | null;
	description: string | null;
	version: string | null;
	source_type: string;
	status: string;
	reason: string | null;
	enabled: boolean;
	manageable: boolean;
	manage_reason: string | null;
	missing_env: string[];
	fingerprint: string | null;
	manifest_path: string;
	capabilities: WorkspacePluginCapability[];
}

export interface WorkspacePluginsResponse {
	workspace_id: string;
	fingerprint: string;
	plugins: WorkspacePlugin[];
}
