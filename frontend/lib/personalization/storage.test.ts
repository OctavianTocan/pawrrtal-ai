import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
	EMPTY_PROFILE,
	loadPersonalizationProfile,
	MESSAGING_CHANNELS,
	PERSONALITY_OPTIONS,
	PERSONALIZATION_STORAGE_KEY,
	savePersonalizationProfile,
} from './storage';

/**
 * jsdom in this project doesn't ship a usable Storage implementation, so
 * we install a tiny in-memory polyfill via `vi.stubGlobal` for each test.
 * Returning the underlying map lets individual tests pre-seed entries.
 */
function installMemoryStorage(): Map<string, string> {
	const map = new Map<string, string>();
	const fakeStorage: Storage = {
		get length() {
			return map.size;
		},
		clear: () => {
			map.clear();
		},
		getItem: (key: string) => map.get(key) ?? null,
		key: (index: number) => Array.from(map.keys())[index] ?? null,
		removeItem: (key: string) => {
			map.delete(key);
		},
		setItem: (key: string, value: string) => {
			map.set(key, String(value));
		},
	};
	vi.stubGlobal('localStorage', fakeStorage);
	return map;
}

let storageMap: Map<string, string>;

beforeEach(() => {
	storageMap = installMemoryStorage();
});

afterEach(() => {
	vi.unstubAllGlobals();
});

describe('personalization storage', () => {
	it('returns the empty profile when nothing is persisted', () => {
		expect(loadPersonalizationProfile()).toEqual(EMPTY_PROFILE);
	});

	it('round-trips a saved profile via savePersonalizationProfile', () => {
		savePersonalizationProfile({
			name: 'Octavian',
			personality: 'goose',
			goals: ['SEO'],
		});

		const loaded = loadPersonalizationProfile();
		expect(loaded.name).toBe('Octavian');
		expect(loaded.personality).toBe('goose');
		expect(loaded.goals).toEqual(['SEO']);
		expect(loaded.connectedChannels).toEqual([]);
	});

	it('falls back to EMPTY_PROFILE when stored JSON is malformed', () => {
		storageMap.set(PERSONALIZATION_STORAGE_KEY, '{not json');
		expect(loadPersonalizationProfile()).toEqual(EMPTY_PROFILE);
	});

	it('exposes a non-empty personality + messaging channel catalog', () => {
		expect(PERSONALITY_OPTIONS.length).toBeGreaterThan(0);
		expect(PERSONALITY_OPTIONS.every((option) => option.id && option.label)).toBe(true);
		expect(MESSAGING_CHANNELS.length).toBeGreaterThan(0);
		expect(MESSAGING_CHANNELS.every((channel) => channel.id && channel.label)).toBe(true);
	});
});
