'use client';

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { OPEN_ONBOARDING_SERVER_STEP_EVENT } from './OnboardingFlow';
import { StepServer } from './step-server';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Minimal profile stub — most tests only care about remoteServerUrl. */
const blankProfile = {};

function renderStep(overrides: Partial<Parameters<typeof StepServer>[0]> = {}) {
	const onContinue = vi.fn();
	const onPatch = vi.fn();
	const { unmount } = render(
		<StepServer
			onContinue={onContinue}
			onPatch={onPatch}
			profile={blankProfile}
			{...overrides}
		/>
	);
	return { onContinue, onPatch, unmount };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('StepServer', () => {
	beforeEach(() => {
		window.localStorage.clear();
	});

	describe('initial render', () => {
		it('defaults to hosted mode when profile has no remoteServerUrl', () => {
			renderStep();
			// The "Hosted by Pawrrtal" option should be visually active — easy to
			// detect by checking the URL input is NOT visible.
			expect(screen.queryByLabelText('Server URL')).toBeNull();
		});

		it('defaults to self-hosted mode when profile already has a remoteServerUrl', () => {
			renderStep({ profile: { remoteServerUrl: 'https://pawrrtal.mycompany.com' } });
			expect(screen.getByLabelText('Server URL')).toBeTruthy();
			expect((screen.getByLabelText('Server URL') as HTMLInputElement).value).toBe(
				'https://pawrrtal.mycompany.com'
			);
		});

		it('renders the title via OnboardingShell', () => {
			renderStep();
			expect(screen.getByRole('heading', { name: /Where is your Pawrrtal\?/i })).toBeTruthy();
		});
	});

	describe('mode toggle', () => {
		it('shows URL input after clicking "Self-hosted"', () => {
			renderStep();
			fireEvent.click(screen.getByText('Self-hosted'));
			expect(screen.getByLabelText('Server URL')).toBeTruthy();
		});

		it('hides URL input after switching back to hosted', () => {
			renderStep();
			fireEvent.click(screen.getByText('Self-hosted'));
			expect(screen.getByLabelText('Server URL')).toBeTruthy();
			fireEvent.click(screen.getByText('Hosted by Pawrrtal'));
			expect(screen.queryByLabelText('Server URL')).toBeNull();
		});
	});

	describe('Continue button', () => {
		it('calls onPatch with remoteServerUrl="" and then onContinue in hosted mode', () => {
			const { onContinue, onPatch } = renderStep();
			fireEvent.click(screen.getByRole('button', { name: /Continue/i }));
			expect(onPatch).toHaveBeenCalledWith({ remoteServerUrl: '' });
			expect(onContinue).toHaveBeenCalled();
			expect(window.localStorage.getItem('pawrrtal:backend-config')).toBeTruthy();
		});

		it('is disabled when self-hosted mode has an empty URL', () => {
			renderStep();
			fireEvent.click(screen.getByText('Self-hosted'));
			const btn = screen.getByRole('button', { name: /Continue/i });
			expect((btn as HTMLButtonElement).disabled).toBe(true);
		});

		it('is enabled when a non-empty URL is typed in self-hosted mode', () => {
			renderStep();
			fireEvent.click(screen.getByText('Self-hosted'));
			fireEvent.change(screen.getByLabelText('Server URL'), {
				target: { value: 'https://pawrrtal.example.com' },
			});
			const btn = screen.getByRole('button', { name: /Continue/i });
			expect((btn as HTMLButtonElement).disabled).toBe(false);
		});

		it('calls onPatch with the typed URL and onContinue in self-hosted mode', () => {
			const { onContinue, onPatch } = renderStep();
			fireEvent.click(screen.getByText('Self-hosted'));
			fireEvent.change(screen.getByLabelText('Server URL'), {
				target: { value: 'https://pawrrtal.example.com' },
			});
			fireEvent.click(screen.getByRole('button', { name: /Continue/i }));
			expect(onPatch).toHaveBeenCalledWith({
				remoteServerUrl: 'https://pawrrtal.example.com',
			});
			expect(onContinue).toHaveBeenCalled();
		});

		it('shows an error and does not call onContinue when URL is invalid on Continue', () => {
			const { onContinue } = renderStep();
			fireEvent.click(screen.getByText('Self-hosted'));
			fireEvent.change(screen.getByLabelText('Server URL'), {
				target: { value: 'not-a-url' },
			});
			fireEvent.click(screen.getByRole('button', { name: /Continue/i }));
			expect(screen.getByText(/valid URL/i)).toBeTruthy();
			expect(onContinue).not.toHaveBeenCalled();
		});
	});

	describe('Skip button', () => {
		it('does not render a skip control in the mandatory path', () => {
			renderStep();
			expect(screen.queryByText('Skip for now')).toBeNull();
		});
	});

	describe('URL validation (validateServerUrl)', () => {
		it('Verify button is disabled when the URL field is empty', () => {
			// The button should be disabled — clicking it would be a no-op in a
			// real browser.  This guards against accidentally enabling it for
			// empty input.
			renderStep();
			fireEvent.click(screen.getByText('Self-hosted'));
			const verifyBtn = screen.getByRole('button', { name: /Verify/i });
			expect((verifyBtn as HTMLButtonElement).disabled).toBe(true);
		});

		it('shows an error for a non-http scheme', () => {
			renderStep();
			fireEvent.click(screen.getByText('Self-hosted'));
			fireEvent.change(screen.getByLabelText('Server URL'), {
				target: { value: 'ftp://example.com' },
			});
			fireEvent.click(screen.getByRole('button', { name: /Verify/i }));
			expect(screen.getByText(/http:\/\/ or https:\/\//i)).toBeTruthy();
		});

		it('shows an error for a syntactically invalid URL on Continue', () => {
			// We can trigger the "not a valid URL" path via Continue because
			// canContinue only requires url.trim().length > 0 (no scheme check).
			const { onContinue } = renderStep();
			fireEvent.click(screen.getByText('Self-hosted'));
			fireEvent.change(screen.getByLabelText('Server URL'), {
				target: { value: 'not-a-url' },
			});
			fireEvent.click(screen.getByRole('button', { name: /Continue/i }));
			expect(screen.getByText(/valid URL/i)).toBeTruthy();
			expect(onContinue).not.toHaveBeenCalled();
		});
	});

	describe('Verify button', () => {
		beforeEach(() => {
			// jsdom's AbortSignal.timeout may be missing; stub it if needed.
			if (!('timeout' in AbortSignal)) {
				(AbortSignal as unknown as { timeout: (ms: number) => AbortSignal }).timeout = () =>
					new AbortController().signal;
			}
		});

		it('shows "Server reachable" on a 2xx response', async () => {
			vi.stubGlobal(
				'fetch',
				vi.fn().mockResolvedValue({ ok: true, status: 200 } as Response)
			);

			renderStep();
			fireEvent.click(screen.getByText('Self-hosted'));
			fireEvent.change(screen.getByLabelText('Server URL'), {
				target: { value: 'https://pawrrtal.example.com' },
			});
			fireEvent.click(screen.getByRole('button', { name: /Verify/i }));

			await waitFor(() => expect(screen.getByText(/Server reachable/i)).toBeTruthy());

			vi.unstubAllGlobals();
		});

		it('shows an error on a 5xx response', async () => {
			vi.stubGlobal(
				'fetch',
				vi.fn().mockResolvedValue({ ok: false, status: 503 } as Response)
			);

			renderStep();
			fireEvent.click(screen.getByText('Self-hosted'));
			fireEvent.change(screen.getByLabelText('Server URL'), {
				target: { value: 'https://pawrrtal.example.com' },
			});
			fireEvent.click(screen.getByRole('button', { name: /Verify/i }));

			await waitFor(() => expect(screen.getByText(/HTTP 503/i)).toBeTruthy());

			vi.unstubAllGlobals();
		});

		it('shows a network error when fetch rejects', async () => {
			vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));

			renderStep();
			fireEvent.click(screen.getByText('Self-hosted'));
			fireEvent.change(screen.getByLabelText('Server URL'), {
				target: { value: 'https://pawrrtal.example.com' },
			});
			fireEvent.click(screen.getByRole('button', { name: /Verify/i }));

			await waitFor(() => expect(screen.getByText(/Could not reach/i)).toBeTruthy());

			vi.unstubAllGlobals();
		});

		it('shows "Re-check" label after a successful verify', async () => {
			vi.stubGlobal(
				'fetch',
				vi.fn().mockResolvedValue({ ok: true, status: 200 } as Response)
			);

			renderStep();
			fireEvent.click(screen.getByText('Self-hosted'));
			fireEvent.change(screen.getByLabelText('Server URL'), {
				target: { value: 'https://pawrrtal.example.com' },
			});
			fireEvent.click(screen.getByRole('button', { name: /Verify/i }));

			await waitFor(() => expect(screen.getByText('Re-check')).toBeTruthy());

			vi.unstubAllGlobals();
		});
	});

	describe('OPEN_ONBOARDING_SERVER_STEP_EVENT export', () => {
		it('exports the correct event name constant', () => {
			expect(OPEN_ONBOARDING_SERVER_STEP_EVENT).toBe('pawrrtal:open-onboarding-server-step');
		});
	});
});
