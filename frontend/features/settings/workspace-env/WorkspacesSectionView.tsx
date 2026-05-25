/**
 * @fileoverview Pure presentation for Settings → Workspaces.
 *
 * No hooks except `useId` for accessibility. All data and handlers are
 * supplied by the container (`WorkspacesSection`). This split keeps the
 * presentation testable in isolation — a vitest can render the view with
 * a fixed prop set and assert on the DOM without mocking fetch or React
 * Query.
 */

'use client';

import { Eye, EyeOff, RotateCcw, Save } from 'lucide-react';
import type * as React from 'react';
import { Button } from '@/components/ui/button';
import { SettingsCard, SettingsPage, SettingsSectionHeader } from '@/features/settings/primitives';
import type { WorkspaceEnvKey } from './use-workspace-env';

/**
 * Display metadata for one overridable workspace env key. The `key` field
 * matches the backend `OVERRIDABLE_KEYS` allowlist; the rest is purely
 * UI-facing (label, help text, link to obtain a key, placeholder).
 */
export interface WorkspaceEnvKeyMeta {
	/** Backend key name. Must be one of `WORKSPACE_ENV_KEY_IDS`. */
	key: WorkspaceEnvKey;
	/** User-facing label for the input row. */
	label: string;
	/** Sub-line shown under the input describing what the key powers. */
	description: string;
	/** Placeholder text for the input. */
	placeholder: string;
	/** External docs/console link where the user can obtain the key. */
	url?: string;
}

/** Props for the pure-presentation Workspaces section. */
export interface WorkspacesSectionViewProps {
	/** Display metadata for each key, in render order. */
	keyMetas: readonly WorkspaceEnvKeyMeta[];
	/** Current form values (working copy that handles edits). */
	values: Record<WorkspaceEnvKey, string>;
	/** UI state for the workspace env form. */
	state: WorkspacesSectionViewState;
	/** Localised error message to surface above the action buttons; null when none. */
	errorMessage: string | null;
	/** Called whenever a single field's value changes. */
	onValueChange: (key: WorkspaceEnvKey, value: string) => void;
	/** Toggle the password mask for one key. */
	onToggleVisibility: (key: WorkspaceEnvKey) => void;
	/** Submit the working copy to the backend. */
	onSave: () => void;
	/** Discard local edits and revert to the last saved value. */
	onDiscard: () => void;
}

export interface WorkspacesSectionViewState {
	/** True when the form has unsaved changes. */
	isDirty: boolean;
	/** True while the initial query is in flight. */
	isLoading: boolean;
	/** True while the save mutation is in flight. */
	isSaving: boolean;
	/** Per-key visibility toggle: `true` shows plaintext, `false` masks. */
	showTokens: Partial<Record<WorkspaceEnvKey, boolean>>;
}

/**
 * Settings → Workspaces presentation surface. Renders every key in
 * `keyMetas` as a masked input row plus Save/Discard controls. Has no
 * data-fetch or mutation logic of its own.
 *
 * @returns The settings page tree.
 */
export function WorkspacesSectionView({
	keyMetas,
	values,
	state,
	errorMessage,
	onValueChange,
	onToggleVisibility,
	onSave,
	onDiscard,
}: WorkspacesSectionViewProps): React.JSX.Element {
	const { isDirty, isLoading, isSaving, showTokens } = state;
	return (
		<SettingsPage
			description="Override gateway environment variables for your workspace. Leave a field blank to use the gateway default."
			title="Workspaces"
		>
			<SettingsCard
				description="Per-workspace environment variables override gateway defaults."
				title="Environment Variables"
			>
				<SettingsSectionHeader
					description="Values are encrypted at rest on the server."
					noDivider
					title="API Keys"
				/>
				<div
					aria-busy={isLoading}
					className="flex flex-col gap-4 py-2"
					data-testid="workspaces-section-fields"
				>
					{keyMetas.map(({ key, label, description, placeholder, url }) => (
						<div className="flex flex-col gap-1.5" key={key}>
							<div className="flex items-center justify-between">
								<label
									className="font-medium text-foreground text-sm"
									htmlFor={`env-${key}`}
								>
									{label}
								</label>
								{url && (
									<a
										className="text-muted-foreground text-xs underline"
										href={url}
										rel="noopener noreferrer"
										target="_blank"
									>
										Get key
									</a>
								)}
							</div>
							<div className="relative flex items-center">
								<input
									aria-label={label}
									className="flex h-9 w-full rounded-md border border-border bg-background px-3 pr-10 text-foreground text-sm placeholder:text-muted-foreground"
									id={`env-${key}`}
									onChange={(e) => {
										onValueChange(key, e.target.value);
									}}
									placeholder={placeholder}
									type={showTokens[key] ? 'text' : 'password'}
									value={values[key] ?? ''}
								/>
								<button
									aria-label={
										showTokens[key]
											? `Hide ${label} value`
											: `Show ${label} value`
									}
									className="absolute right-2 flex size-5 cursor-pointer items-center justify-center text-muted-foreground hover:text-foreground"
									onClick={() => {
										onToggleVisibility(key);
									}}
									type="button"
								>
									{showTokens[key] ? (
										<EyeOff className="size-3.5" />
									) : (
										<Eye className="size-3.5" />
									)}
								</button>
							</div>
							<span className="text-muted-foreground text-xs">{description}</span>
						</div>
					))}
				</div>
			</SettingsCard>

			{errorMessage !== null && (
				<div
					className="rounded-[12px] border border-destructive/40 bg-destructive/10 px-4 py-3 text-destructive text-sm"
					role="alert"
				>
					{errorMessage}
				</div>
			)}

			<div className="flex items-center gap-3">
				<Button
					className="gap-1.5"
					disabled={!isDirty || isSaving}
					onClick={onSave}
					type="button"
				>
					<Save className="size-4" />
					{isSaving ? 'Saving...' : 'Save'}
				</Button>
				<Button
					className="gap-1.5"
					disabled={!isDirty || isSaving}
					onClick={onDiscard}
					type="button"
					variant="outline"
				>
					<RotateCcw className="size-4" />
					Discard
				</Button>
			</div>
		</SettingsPage>
	);
}
