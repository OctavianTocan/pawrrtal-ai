'use client';

import type * as React from 'react';
import { useMemo, useState, useSyncExternalStore } from 'react';
import { Button } from '@/components/ui/button';
import { SelectButton, type SelectButtonOption } from '@/components/ui/select-button';
import { Textarea } from '@/components/ui/textarea';
import {
	EMPTY_PROFILE,
	loadPersonalizationProfile,
	PERSONALITY_OPTIONS,
	PERSONALIZATION_STORAGE_KEY,
	type PersonalityId,
	type PersonalizationProfile,
	savePersonalizationProfile,
} from '@/lib/personalization/storage';
import {
	SettingsCard,
	SettingsPage,
	SettingsRow,
	SettingsSectionHeader,
	Switch,
} from '../primitives';

const PERSONALIZATION_PROFILE_EVENT = 'pawrrtal:personalization-profile';

let cachedProfileRaw: string | null | undefined;
let cachedProfileSnapshot: PersonalizationProfile = EMPTY_PROFILE;

const getServerProfileSnapshot = (): PersonalizationProfile => EMPTY_PROFILE;

const getClientProfileSnapshot = (): PersonalizationProfile => {
	const raw = window.localStorage.getItem(PERSONALIZATION_STORAGE_KEY);
	if (raw === cachedProfileRaw) {
		return cachedProfileSnapshot;
	}
	cachedProfileRaw = raw;
	cachedProfileSnapshot = loadPersonalizationProfile();
	return cachedProfileSnapshot;
};

const subscribeToProfile = (onStoreChange: () => void): (() => void) => {
	const handleStorageChange = (event: StorageEvent): void => {
		if (event.key === PERSONALIZATION_STORAGE_KEY) {
			onStoreChange();
		}
	};

	window.addEventListener('storage', handleStorageChange);
	window.addEventListener(PERSONALIZATION_PROFILE_EVENT, onStoreChange);

	return () => {
		window.removeEventListener('storage', handleStorageChange);
		window.removeEventListener(PERSONALIZATION_PROFILE_EVENT, onStoreChange);
	};
};

const dispatchProfileChange = (): void => {
	window.dispatchEvent(new Event(PERSONALIZATION_PROFILE_EVENT));
};

/**
 * Personalization settings section.
 *
 * Reads + writes the same `pawrrtal:personalization` localStorage profile
 * that the v2 onboarding flow collects, so a personality picked in
 * onboarding shows up here pre-selected (and edits here flow back to
 * the profile).
 */
export function PersonalizationSection(): React.JSX.Element {
	const profile = useSyncExternalStore(
		subscribeToProfile,
		getClientProfileSnapshot,
		getServerProfileSnapshot
	);
	const [enableMemories, setEnableMemories] = useState(true);
	const [skipToolChats, setSkipToolChats] = useState(false);

	const patchProfile = (patch: Partial<PersonalizationProfile>): void => {
		const next = { ...profile, ...patch };
		savePersonalizationProfile(next);
		dispatchProfileChange();
	};

	const personality: PersonalityId = profile.personality ?? PERSONALITY_OPTIONS[0].id;

	// Map the storage `PERSONALITY_OPTIONS` tuple to the SelectButton's
	// `SelectButtonOption[]` shape once per render. Each personality's
	// one-line `summary` becomes the muted sub-line in the dropdown row,
	// mirroring the Codex pattern of "label + secondary explanation"
	// for picker entries.
	const personalityOptions = useMemo<SelectButtonOption[]>(
		() =>
			PERSONALITY_OPTIONS.map((option) => ({
				id: option.id,
				label: option.label,
				description: option.summary,
			})),
		[]
	);
	const activePersonality = PERSONALITY_OPTIONS.find((option) => option.id === personality);

	return (
		<SettingsPage
			description="Tune how Pawrrtal addresses you, what context it carries between chats, and how it builds memory."
			title="Personalization"
		>
			<SettingsCard>
				<SettingsSectionHeader
					description="Default tone applied to every response."
					title="Personality"
				/>
				<SettingsRow
					description="Choose a default tone for your agent's responses."
					label="Personality"
				>
					<SelectButton
						activeId={personality}
						ariaLabel="Personality"
						onSelect={(id) => patchProfile({ personality: id as PersonalityId })}
						options={personalityOptions}
						triggerLabel={activePersonality?.label ?? 'Choose'}
					/>
				</SettingsRow>
			</SettingsCard>

			<SettingsCard>
				<SettingsSectionHeader
					description="Give your agent extra instructions and context for your project."
					title="Custom instructions"
				/>
				<Textarea
					className="min-h-32 resize-y border-0 bg-transparent px-0 text-sm focus-visible:ring-0"
					onChange={(event) => patchProfile({ customInstructions: event.target.value })}
					placeholder="Add your custom instructions..."
					value={profile.customInstructions ?? ''}
				/>
				<div className="flex justify-end pt-2">
					<Button size="sm" type="button" variant="secondary">
						Saved
					</Button>
				</div>
			</SettingsCard>

			<SettingsCard>
				<SettingsSectionHeader
					description="Configure how the agent collects, retains, and consolidates memories."
					title="Memory (experimental)"
				/>
				<SettingsRow
					description="Generate new memories from chats and bring them into new chats."
					label="Enable memories"
				>
					<Switch
						aria-label="Enable memories"
						checked={enableMemories}
						onCheckedChange={setEnableMemories}
					/>
				</SettingsRow>
				<SettingsRow
					description="Do not generate memories from chats that used MCP tools or web search."
					label="Skip tool-assisted chats"
				>
					<Switch
						aria-label="Skip tool-assisted chats"
						checked={skipToolChats}
						onCheckedChange={setSkipToolChats}
					/>
				</SettingsRow>
				<SettingsRow description="Delete all stored memories." label="Reset memories">
					<Button
						className="text-destructive hover:text-destructive"
						size="sm"
						type="button"
						variant="ghost"
					>
						Reset
					</Button>
				</SettingsRow>
			</SettingsCard>
		</SettingsPage>
	);
}
