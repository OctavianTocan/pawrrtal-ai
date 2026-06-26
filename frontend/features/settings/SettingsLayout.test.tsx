import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type * as React from 'react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn() }),
}));

// AppearanceSection (mounted in the right pane on the Appearance tab)
// fetches `/api/v1/appearance` via useAuthedFetch — stub it so the
// SettingsLayout-level tests don't need a real backend.
const { mockAuthedFetch } = vi.hoisted(() => ({
  mockAuthedFetch: vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ light: {}, dark: {}, fonts: {}, options: {} }),
    text: async () => '{}',
  }),
}));
vi.mock('@/hooks/use-authed-fetch', () => ({
  useAuthedFetch: () => mockAuthedFetch,
}));

import { SettingsLayout } from './SettingsLayout';

vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(
  () =>
    ({
      fillStyle: '#000000',
    }) as CanvasRenderingContext2D
);

/** Wrap each render in a fresh QueryClient so cache state never leaks. */
function renderWithQuery(ui: React.ReactElement): ReturnType<typeof render> {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const Wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return render(ui, { wrapper: Wrapper });
}

describe('SettingsLayout', () => {
  it('renders the rail with Back to app + every section button', () => {
    const { getByRole } = renderWithQuery(<SettingsLayout />);
    expect(getByRole('button', { name: /Back to app/ })).toBeTruthy();
    expect(getByRole('button', { name: 'General' })).toBeTruthy();
    expect(getByRole('button', { name: 'Appearance' })).toBeTruthy();
    expect(getByRole('button', { name: 'Personalization' })).toBeTruthy();
    expect(getByRole('button', { name: 'Integrations' })).toBeTruthy();
    expect(getByRole('button', { name: 'Plugins' })).toBeTruthy();
    expect(getByRole('button', { name: 'Usage' })).toBeTruthy();
  });

  it('defaults to the General section', () => {
    const { getByRole } = renderWithQuery(<SettingsLayout />);
    expect(getByRole('heading', { name: 'General' })).toBeTruthy();
  });

  it('switches the right pane to Appearance when the rail item is clicked', async () => {
    const user = userEvent.setup();
    const { getByRole, getAllByText } = renderWithQuery(<SettingsLayout />);
    await user.click(getByRole('button', { name: 'Appearance' }));
    // Multiple "Theme" labels render once the Appearance section mounts
    // (section header + theme-mode toggle aria-label). Asserting at
    // least one is present is enough to confirm the right pane swapped
    // — the previous `getByText` blew up on multiple matches.
    expect(getAllByText('Theme').length).toBeGreaterThan(0);
  });

  it('switches the right pane to Usage when the rail item is clicked', async () => {
    const user = userEvent.setup();
    const { getByRole } = renderWithQuery(<SettingsLayout />);
    await user.click(getByRole('button', { name: 'Usage' }));
    expect(getByRole('heading', { name: 'Usage' })).toBeTruthy();
  });
});
