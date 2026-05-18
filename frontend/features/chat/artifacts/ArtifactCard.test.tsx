/**
 * Smoke test for the inline artifact preview card.
 *
 * The full json-render pipeline is exercised separately by the dialog tests
 * (and by visual smoke). Here we only assert that the preview surface
 * renders the title and announces an "open artifact" button — the bits
 * that have to be right for the chat row to remain accessible.
 */

import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import type { ChatArtifactPayload } from '../types';
import { ArtifactCard } from './ArtifactCard';

afterEach(cleanup);

const _SAMPLE: ChatArtifactPayload = {
	id: 'art_test_001',
	title: 'A useful comparison',
	tool_use_id: 'tu_1',
	spec: {
		root: 'p',
		elements: {
			p: {
				type: 'Page',
				props: { title: 'demo', accent: 'cat' },
				children: ['h'],
			},
			h: {
				type: 'Heading',
				props: { text: 'Hello', level: 'h2' },
				children: [],
			},
		},
	},
};

describe('ArtifactCard', () => {
	it('renders the title and a button with an accessible name', () => {
		render(<ArtifactCard artifact={_SAMPLE} />);
		expect(screen.getByText('A useful comparison')).toBeInTheDocument();
		expect(screen.getByRole('button', { name: /open artifact/i })).toBeInTheDocument();
	});

	it('opens the dialog on click and shows a Close button', async () => {
		const user = userEvent.setup();
		render(<ArtifactCard artifact={_SAMPLE} />);
		await user.click(screen.getByRole('button', { name: /open artifact/i }));
		// Dialog renders into a portal but still under document.body.
		expect(screen.getByRole('dialog')).toBeInTheDocument();
		expect(screen.getByRole('button', { name: /close artifact/i })).toBeInTheDocument();
	});
});
