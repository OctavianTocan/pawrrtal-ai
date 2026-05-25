'use client';

import type * as React from 'react';
import { useCallback, useEffect, useReducer, useRef } from 'react';
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

/** Local form state for the profile editor fields. */
interface ProfileFormState {
	name: string;
	role: string;
	customInstructions: string;
}

const INITIAL_FORM: ProfileFormState = { name: '', role: '', customInstructions: '' };

/**
 * General settings section — profile, preferences, and notifications.
 *
 * Pulls the authenticated user's email from `GET /users/me` and display
 * name / role from the personalization profile. Edits are auto-saved to
 * the backend via PUT after a debounce.
 */
export function GeneralSection(): React.JSX.Element {
	const { data: currentUser } = useCurrentUser();
	const { data: personalization } = useGetPersonalization();
	const upsert = useUpsertPersonalization();

	const hydrated = useRef(false);
	const [form, updateForm] = useReducer(
		(prev: ProfileFormState, patch: Partial<ProfileFormState>): ProfileFormState => ({
			...prev,
			...patch,
		}),
		INITIAL_FORM
	);
	useEffect(() => {
		if (!personalization || hydrated.current) return;
		hydrated.current = true;
		updateForm({
			name: personalization.name ?? '',
			role: personalization.role ?? '',
			customInstructions: personalization.customInstructions ?? '',
		});
	}, [personalization]);

	const { name, role, customInstructions } = form;

	const nickname = name.split(' ')[0] ?? '';
	const initials = getInitials(name || currentUser?.email || '');

	const saveTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
	useEffect(() => {
		const ref = saveTimerRef;
		return () => {
			if (ref.current) clearTimeout(ref.current);
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

	const profileKey = `profile-${currentUser?.id ?? 'anon'}`;

	return (
		<SettingsPage
			description="Profile, preferences, and notifications for your account."
			title="General"
		>
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
						aria-label="Full name"
						className="w-56"
						value={name}
						onChange={(e) => {
							updateForm({ name: e.target.value });
							save({ name: e.target.value });
						}}
					/>
				</SettingsRow>
				<SettingsRow label="What should we call you?">
					<Input aria-label="Nickname" className="w-56" value={nickname} readOnly />
				</SettingsRow>
				<SettingsRow label="What best describes your work?">
					<Input
						aria-label="Work description"
						className="w-56"
						value={role}
						onChange={(e) => {
							updateForm({ role: e.target.value });
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
							updateForm({ customInstructions: e.target.value });
							save({ customInstructions: e.target.value });
						}}
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
