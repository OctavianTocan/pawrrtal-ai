'use client';

import { AlertTriangle, Box, CheckCircle2, CircleSlash, Puzzle } from 'lucide-react';
import { SettingsCard, SettingsPage, Switch } from '../primitives';
import type { WorkspacePlugin } from './types';

export interface PluginsSectionViewProps {
	plugins: WorkspacePlugin[];
	isLoading: boolean;
	errorMessage: string | null;
	updatingPluginId: string | null;
	onTogglePlugin: (plugin: WorkspacePlugin, enabled: boolean) => void;
}

function statusLabel(status: string): string {
	if (status === 'active') return 'Active';
	if (status === 'disabled') return 'Disabled';
	if (status === 'misconfigured') return 'Needs setup';
	if (status === 'needs_validation') return 'Needs validation';
	if (status === 'blocked_by_dependency') return 'Blocked';
	return 'Failed';
}

function statusIcon(status: string): React.JSX.Element {
	if (status === 'active') return <CheckCircle2 aria-hidden="true" className="size-3.5" />;
	if (status === 'disabled') return <CircleSlash aria-hidden="true" className="size-3.5" />;
	return <AlertTriangle aria-hidden="true" className="size-3.5" />;
}

function PluginStatusBadge({ status }: { status: string }): React.JSX.Element {
	const tone =
		status === 'active'
			? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200'
			: status === 'disabled'
				? 'border-border bg-foreground/[0.04] text-muted-foreground'
				: 'border-amber-500/30 bg-amber-500/10 text-amber-200';
	return (
		<span
			className={`inline-flex items-center gap-1 rounded-[6px] border px-2 py-0.5 text-xs font-medium ${tone}`}
		>
			{statusIcon(status)}
			{statusLabel(status)}
		</span>
	);
}

function PluginCard({
	plugin,
	isUpdating,
	onTogglePlugin,
}: {
	plugin: WorkspacePlugin;
	isUpdating: boolean;
	onTogglePlugin: (plugin: WorkspacePlugin, enabled: boolean) => void;
}): React.JSX.Element {
	const title = plugin.name ?? plugin.plugin_id;
	const capabilityCount = plugin.capabilities.length;
	return (
		<SettingsCard className="px-0 py-0">
			<div className="flex items-start justify-between gap-4 border-b border-border/40 px-5 py-4">
				<div className="flex min-w-0 items-start gap-3">
					<span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-[8px] border border-border/60 bg-foreground/[0.04] text-foreground">
						<Puzzle aria-hidden="true" className="size-4" />
					</span>
					<div className="min-w-0">
						<div className="flex flex-wrap items-center gap-2">
							<h3 className="text-sm font-semibold text-foreground">{title}</h3>
							<PluginStatusBadge status={plugin.status} />
						</div>
						<p className="mt-1 text-pretty text-sm leading-snug text-muted-foreground">
							{plugin.description ?? plugin.plugin_id}
						</p>
						<div className="mt-2 flex flex-wrap gap-1.5 text-xs text-muted-foreground">
							<span>{plugin.source_type}</span>
							<span aria-hidden="true">/</span>
							<span>{plugin.version ?? 'unversioned'}</span>
							<span aria-hidden="true">/</span>
							<span>{capabilityCount} capabilities</span>
						</div>
					</div>
				</div>
				<Switch
					aria-label={`Enable ${title}`}
					checked={plugin.enabled}
					disabled={isUpdating}
					onCheckedChange={(enabled) => onTogglePlugin(plugin, enabled)}
				/>
			</div>
			<div className="px-5 py-3">
				{plugin.missing_env.length > 0 ? (
					<div className="mb-3 rounded-[8px] border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
						Missing: {plugin.missing_env.join(', ')}
					</div>
				) : null}
				<div className="flex flex-wrap gap-1.5">
					{plugin.capabilities.map((capability) => (
						<span
							className="inline-flex items-center gap-1 rounded-[6px] border border-border/50 bg-foreground/[0.03] px-2 py-1 text-xs text-muted-foreground"
							key={capability.key}
						>
							<Box aria-hidden="true" className="size-3" />
							{capability.title}
							<span className="text-muted-foreground/70">({capability.type})</span>
						</span>
					))}
				</div>
				{plugin.reason ? (
					<p className="mt-3 text-xs text-muted-foreground">{plugin.reason}</p>
				) : null}
			</div>
		</SettingsCard>
	);
}

export function PluginsSectionView({
	plugins,
	isLoading,
	errorMessage,
	updatingPluginId,
	onTogglePlugin,
}: PluginsSectionViewProps): React.JSX.Element {
	return (
		<SettingsPage
			description="Manage optional tools, channels, providers, and workspace capabilities."
			title="Plugins"
		>
			{errorMessage ? (
				<div
					className="rounded-[8px] border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
					role="alert"
				>
					{errorMessage}
				</div>
			) : null}
			{isLoading ? (
				<SettingsCard>
					<div className="py-4 text-sm text-muted-foreground">Loading plugins...</div>
				</SettingsCard>
			) : null}
			{!isLoading && plugins.length === 0 ? (
				<SettingsCard>
					<div className="py-4 text-sm text-muted-foreground">No plugins installed.</div>
				</SettingsCard>
			) : null}
			{!isLoading ? (
				<div className="flex flex-col gap-3">
					{plugins.map((plugin) => (
						<PluginCard
							isUpdating={updatingPluginId === plugin.plugin_id}
							key={plugin.plugin_id}
							onTogglePlugin={onTogglePlugin}
							plugin={plugin}
						/>
					))}
				</div>
			) : null}
		</SettingsPage>
	);
}
