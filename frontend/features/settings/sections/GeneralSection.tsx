'use client';

import { Skeleton } from 'boneyard-js/react';
import type * as React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { useCurrentUser } from '@/hooks/use-current-user';
import type { PersonalizationProfile } from '@/lib/personalization/storage';
import {
	useGetPersonalization,
	useUpsertPersonalization,
} from '@/lib/personalization/use-personalization';
import { getInitials } from '@/lib/user-utils';
import {
	SettingsCard,
	SettingsPage,
	SettingsRow,
	SettingsSectionHeader,
	Switch,
} from '../primitives';

const SAVE_DEBOUNCE_MS = 1200;

/**
 * General settings section — profile, preferences, and notifications.
 *
 * Pulls the authenticated user's email from `GET /users/me` and display
 * name / role from the personalization profile. Edits are auto-saved to
 * the backend via PUT after a debounce.
 */
export function GeneralSection(): React.JSX.Element {
	const { data: currentUser } = useCurrentUser();
	const { data: personalization, isLoading } = useGetPersonalization();
	const upsert = useUpsertPersonalization();

	const [name, setName] = useState('');
	const [role, setRole] = useState('');
	const [customInstructions, setCustomInstructions] = useState('');

	const hydrated = useRef(false);
	useEffect(() => {
		if (!personalization || hydrated.current) return;
		hydrated.current = true;
		setName(personalization.name ?? '');
		setRole(personalization.role ?? '');
		setCustomInstructions(personalization.customInstructions ?? '');
	}, [personalization]);

	const nickname = name.split(' ')[0] ?? '';
	const initials = getInitials(name || currentUser?.email || '');

	const saveTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
	useEffect(() => {
		return () => {
			if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
		};
	}, []);

	const save = useCallback(
		(patch: Partial<PersonalizationProfile>): void => {
			if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
			saveTimerRef.current = setTimeout(() => {
				const merged: PersonalizationProfile = {
					...personalization,
					...patch,
				};
				upsert.mutate(merged);
				saveTimerRef.current = undefined;
			}, SAVE_DEBOUNCE_MS);
		},
		[personalization, upsert]
	);

	const profileKey = useMemo(
		(): string => `profile-${currentUser?.id ?? 'anon'}`,
		[currentUser?.id]
	);

	return (
		<SettingsPage
			description="Profile, preferences, and notifications for your account."
			title="General"
		>
			<Skeleton loading={isLoading} name="general-settings-profile" animate="pulse">
				<SettingsCard key={profileKey}>
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
						<Input
							className="w-56"
							value={name}
							onChange={(e) => {
								setName(e.target.value);
								save({ name: e.target.value });
							}}
						/>
					</SettingsRow>
					<SettingsRow label="What should we call you?">
						<Input className="w-56" value={nickname} readOnly />
					</SettingsRow>
					<SettingsRow label="What best describes your work?">
						<Input
							className="w-56"
							value={role}
							onChange={(e) => {
								setRole(e.target.value);
								save({ role: e.target.value });
							}}
						/>
					</SettingsRow>
					<SettingsRow
						className="items-start"
						description="Kept in mind across chats."
						label="Instructions for Pawrrtal"
					>
						<Textarea
							className="min-h-24 w-72 resize-none"
							value={customInstructions}
							onChange={(e) => {
								setCustomInstructions(e.target.value);
								save({ customInstructions: e.target.value });
							}}
							placeholder="e.g. keep explanations brief and to the point"
						/>
					</SettingsRow>
				</SettingsCard>
			</Skeleton>

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
