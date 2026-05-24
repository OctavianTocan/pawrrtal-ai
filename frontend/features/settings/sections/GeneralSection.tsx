'use client';

import type * as React from 'react';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
	SettingsCard,
	SettingsPage,
	SettingsRow,
	SettingsSectionHeader,
	Switch,
} from '../primitives';

/**
 * Visual-only General settings section.
 *
 * Mirrors the Codex-style "Profile / Preferences / Notifications" layout
 * from the reference screenshot. State is local + cosmetic — no real
 * persistence wired this round.
 */
export function GeneralSection(): React.JSX.Element {
	return (
		<SettingsPage
			description="Profile, preferences, and notifications for your account."
			title="General"
		>
			<SettingsCard>
				<SettingsSectionHeader
					description="How you appear inside Pawrrtal and how it should address you."
					title="Profile"
				/>
				<SettingsRow label="Avatar">
					<Avatar className="size-9">
						<AvatarImage alt="Avatar" src="" />
						<AvatarFallback className="text-xs">OT</AvatarFallback>
					</Avatar>
				</SettingsRow>
				<SettingsRow label="Full name">
					<Input className="w-56" defaultValue="Octavian Tocan" />
				</SettingsRow>
				<SettingsRow label="What should we call you?">
					<Input className="w-56" defaultValue="Tavi" />
				</SettingsRow>
				<SettingsRow label="What best describes your work?">
					<Input className="w-56" defaultValue="Engineering" />
				</SettingsRow>
				<SettingsRow
					className="items-start"
					description="Kept in mind across chats."
					label="Instructions for Pawrrtal"
				>
					<Textarea
						className="min-h-24 w-72 resize-none"
						placeholder="e.g. keep explanations brief and to the point"
					/>
				</SettingsRow>
			</SettingsCard>

			{/* The "Preferences" card was removed — it duplicated the live
			    Appearance section (theme mode, chat font, voice) with a
			    visual-only mock that drifted out of sync. The Appearance
			    rail item is the single source of truth for those
			    controls now. */}

			<SettingsCard>
				<SettingsSectionHeader
					description="System-level alerts Pawrrtal can surface to you."
					title="Notifications"
				/>
				<SettingsRow
					description="Get notified when Pawrrtal has finished a response. Useful for long-running tasks."
					label="Response completions"
				>
					<Switch aria-label="Response completions" defaultChecked />
				</SettingsRow>
			</SettingsCard>
		</SettingsPage>
	);
}
