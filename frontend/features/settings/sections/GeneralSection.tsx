'use client';

import type * as React from 'react';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { useGetPersonalization } from '@/lib/personalization/use-personalization';
import { useCurrentUser } from '@/hooks/use-current-user';
import { getInitials } from '@/lib/user-utils';
import {
	SettingsCard,
	SettingsPage,
	SettingsRow,
	SettingsSectionHeader,
	Switch,
} from '../primitives';

/**
 * General settings section — profile, preferences, and notifications.
 *
 * Pulls the authenticated user's email from `GET /users/me` and display
 * name / role from the personalization profile. Fields are pre-populated
 * but not yet wired to a save mutation (visual-only persistence).
 */
export function GeneralSection(): React.JSX.Element {
	const { data: currentUser } = useCurrentUser();
	const { data: personalization } = useGetPersonalization();

	const name = personalization?.name ?? currentUser?.email ?? '';
	const nickname = personalization?.name?.split(' ')[0] ?? '';
	const role = personalization?.role ?? '';
	const initials = getInitials(name);

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
						<AvatarFallback className="text-xs">{initials}</AvatarFallback>
					</Avatar>
				</SettingsRow>
				<SettingsRow label="Full name">
					<Input className="w-56" defaultValue={name} />
				</SettingsRow>
				<SettingsRow label="What should we call you?">
					<Input className="w-56" defaultValue={nickname} />
				</SettingsRow>
				<SettingsRow label="What best describes your work?">
					<Input className="w-56" defaultValue={role} />
				</SettingsRow>
				<SettingsRow
					className="items-start"
					description="Kept in mind across chats."
					label="Instructions for Pawrrtal"
				>
					<Textarea
						className="min-h-24 w-72 resize-none"
						defaultValue={personalization?.customInstructions ?? ''}
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
					<Switch defaultChecked />
				</SettingsRow>
			</SettingsCard>
		</SettingsPage>
	);
}
