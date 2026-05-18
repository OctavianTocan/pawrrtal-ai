import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

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

import { PersonalizationSection } from './PersonalizationSection';

beforeEach(() => {
	installMemoryStorage();
});

afterEach(() => {
	vi.unstubAllGlobals();
});

describe('PersonalizationSection', () => {
	it('renders the Personalization heading + Custom instructions section', () => {
		const { getByRole, getByText } = render(<PersonalizationSection />);
		expect(getByRole('heading', { name: 'Personalization' })).toBeTruthy();
		expect(getByText('Custom instructions')).toBeTruthy();
		expect(getByText(/Memory \(experimental\)/)).toBeTruthy();
	});

	it('renders the personality picker with a default value', () => {
		const { getAllByText, getByRole } = render(<PersonalizationSection />);
		// "Personality" appears twice: once as the section header and
		// once as the row label. Both should be present.
		expect(getAllByText('Personality').length).toBeGreaterThanOrEqual(2);
		// The picker is now a `SelectButton` (Radix DropdownMenu trigger)
		// — assert on the button labeled "Personality" rather than a
		// native `<select>` so we test the semantic affordance the
		// user actually sees + tabs to.
		const trigger = getByRole('button', { name: 'Personality' });
		expect(trigger).toBeTruthy();
	});

	it('renders the memory toggles + reset button', () => {
		const { getByText } = render(<PersonalizationSection />);
		expect(getByText('Enable memories')).toBeTruthy();
		expect(getByText('Skip tool-assisted chats')).toBeTruthy();
		expect(getByText('Reset memories')).toBeTruthy();
	});

	it('updates the custom instructions textarea when typed into', async () => {
		const user = userEvent.setup();
		const { getByPlaceholderText } = render(<PersonalizationSection />);
		const textarea = getByPlaceholderText('Add your custom instructions...');
		await user.type(textarea, 'be terse');
		expect((textarea as HTMLTextAreaElement).value).toBe('be terse');
	});
});
