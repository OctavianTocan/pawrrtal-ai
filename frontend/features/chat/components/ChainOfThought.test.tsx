import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { ToolResultChips } from '../tool-result-parsers';
import type { ChatToolCall } from '../types';
import { ChainOfThought } from './ChainOfThought';

const EMPTY_CHIPS = new Map<string, ToolResultChips>();

describe('ChainOfThought', () => {
	it('renders backend display metadata for tool steps', () => {
		const call: ChatToolCall = {
			id: 'tool-1',
			name: 'read_file',
			input: { path: 'AGENTS.md' },
			display: {
				icon: '📖',
				present: '📖 Reading AGENTS.md',
				compact: 'Read file -> AGENTS.md',
			},
			status: 'pending',
		};

		render(
			<ChainOfThought
				chipsByToolId={EMPTY_CHIPS}
				timeline={[{ kind: 'tool', toolCallId: 'tool-1' }]}
				toolCallsById={new Map([['tool-1', call]])}
			/>
		);

		expect(screen.getByText('Reading AGENTS.md')).toBeInTheDocument();
		expect(screen.getByText('📖')).toBeInTheDocument();
	});
});
