/**
 * @fileoverview Tests for the pure-presentation `WorkspacesSectionView`.
 *
 * The container (`WorkspacesSection`) is intentionally not tested here —
 * its job is to thread TanStack Query state into props, which is best
 * exercised at the integration / Playwright level. The view is the part
 * that needs unit coverage: it has every branch in its rendering logic
 * and no I/O of its own.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { type WorkspaceEnvKeyMeta, WorkspacesSectionView } from './WorkspacesSectionView';

const KEY_METAS: readonly WorkspaceEnvKeyMeta[] = [
	{
		key: 'GEMINI_API_KEY',
		label: 'Gemini API Key',
		description: 'Google Gemini.',
		placeholder: 'AIza...',
		url: 'https://aistudio.google.com/apikey',
	},
	{
		key: 'EXA_API_KEY',
		label: 'Exa API Key',
		description: 'Exa search.',
		placeholder: 'exa-...',
		url: 'https://exa.ai',
	},
];

const EMPTY_VALUES = {
	GEMINI_API_KEY: '',
	CLAUDE_CODE_OAUTH_TOKEN: '',
	EXA_API_KEY: '',
	XAI_API_KEY: '',
	NOTION_API_KEY: '',
} as const;

describe('WorkspacesSectionView', () => {
	const baseProps = {
		keyMetas: KEY_METAS,
		values: EMPTY_VALUES,
		state: {
			showTokens: {},
			isLoading: false,
			isDirty: false,
			isSaving: false,
		},
		errorMessage: null,
		onValueChange: vi.fn(),
		onToggleVisibility: vi.fn(),
		onSave: vi.fn(),
		onDiscard: vi.fn(),
	};

	it('renders one input per overridable key with a Get key link', () => {
		render(<WorkspacesSectionView {...baseProps} />);
		expect(screen.getByLabelText('Gemini API Key')).toBeTruthy();
		expect(screen.getByLabelText('Exa API Key')).toBeTruthy();
		const links = screen.getAllByRole('link', { name: 'Get key' });
		expect(links).toHaveLength(2);
	});

	it('disables Save and Discard when the form is clean', () => {
		render(<WorkspacesSectionView {...baseProps} />);
		expect((screen.getByRole('button', { name: 'Save' }) as HTMLButtonElement).disabled).toBe(
			true
		);
		expect(
			(screen.getByRole('button', { name: 'Discard' }) as HTMLButtonElement).disabled
		).toBe(true);
	});

	it('enables Save when isDirty is true and fires onSave on click', () => {
		const onSave = vi.fn();
		render(
			<WorkspacesSectionView
				{...baseProps}
				onSave={onSave}
				state={{ ...baseProps.state, isDirty: true }}
			/>
		);
		const saveButton = screen.getByRole('button', { name: 'Save' });
		fireEvent.click(saveButton);
		expect(onSave).toHaveBeenCalledTimes(1);
	});

	it('shows "Saving..." label while the mutation is pending', () => {
		render(
			<WorkspacesSectionView
				{...baseProps}
				state={{ ...baseProps.state, isDirty: true, isSaving: true }}
			/>
		);
		expect(screen.getByRole('button', { name: 'Saving...' })).toBeTruthy();
	});

	it('renders the error region as alert when errorMessage is provided', () => {
		render(
			<WorkspacesSectionView
				{...baseProps}
				errorMessage="Value for GEMINI_API_KEY exceeds 512 characters."
			/>
		);
		const alert = screen.getByRole('alert');
		expect(alert.textContent).toContain('exceeds 512 characters');
	});

	it('fires onValueChange with the typed key + new value on input', () => {
		const onValueChange = vi.fn();
		render(<WorkspacesSectionView {...baseProps} onValueChange={onValueChange} />);
		const gemini = screen.getByLabelText('Gemini API Key');
		fireEvent.change(gemini, { target: { value: 'new-gemini-value' } });
		expect(onValueChange).toHaveBeenCalledWith('GEMINI_API_KEY', 'new-gemini-value');
	});

	it('shows the eye toggle as a focusable button with an aria label', () => {
		const onToggleVisibility = vi.fn();
		render(<WorkspacesSectionView {...baseProps} onToggleVisibility={onToggleVisibility} />);
		const toggle = screen.getByRole('button', { name: /show gemini api key value/i });
		fireEvent.click(toggle);
		expect(onToggleVisibility).toHaveBeenCalledWith('GEMINI_API_KEY');
	});

	it('renders the input as type="text" when the key is in showTokens', () => {
		render(
			<WorkspacesSectionView
				{...baseProps}
				state={{ ...baseProps.state, showTokens: { GEMINI_API_KEY: true } }}
			/>
		);
		const gemini = screen.getByLabelText('Gemini API Key') as HTMLInputElement;
		expect(gemini.type).toBe('text');
	});

	it('renders the input as type="password" by default', () => {
		render(<WorkspacesSectionView {...baseProps} />);
		const gemini = screen.getByLabelText('Gemini API Key') as HTMLInputElement;
		expect(gemini.type).toBe('password');
	});
});
