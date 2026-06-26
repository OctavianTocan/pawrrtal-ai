import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useAuthedFetch } from './use-authed-fetch';

const replaceMock = vi.fn();

async function expectRejectedMessage(promise: Promise<unknown>, expectedMessage: string): Promise<void> {
  try {
    await promise;
  } catch (error) {
    expect(error).toBeInstanceOf(Error);
    expect((error as Error).message).toBe(expectedMessage);
    return;
  }

  throw new Error(`Expected promise to reject with: ${expectedMessage}`);
}

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    replace: replaceMock,
  }),
}));

describe('useAuthedFetch', (): void => {
  beforeEach((): void => {
    replaceMock.mockClear();
    vi.stubGlobal('fetch', vi.fn());
  });

  it('uses same-origin API paths and includes credentials', async (): Promise<void> => {
    vi.mocked(fetch).mockResolvedValue(new Response('ok'));

    const { result } = renderHook(() => useAuthedFetch());

    await result.current('/api/v1/conversations', {
      method: 'GET',
    });

    expect(fetch).toHaveBeenCalledWith('/api/v1/conversations', {
      method: 'GET',
      credentials: 'include',
      cache: 'no-store',
    });
  });

  it('redirects to /login with ?redirect= and throws on 401 responses', async (): Promise<void> => {
    // On a 401 the hook must preserve where the user was so the login
    // page can return them after re-authenticating — same contract the
    // Next.js proxy (``frontend/proxy.ts``) uses when no cookie is
    // present in the first place.
    vi.mocked(fetch).mockResolvedValue(new Response('nope', { status: 401 }));

    const { result } = renderHook(() => useAuthedFetch());

    await expectRejectedMessage(result.current('/me'), 'User is not authenticated');
    expect(replaceMock).toHaveBeenCalledOnce();
    // Must point at /login and round-trip the original path through ?redirect=.
    expect(replaceMock).toHaveBeenCalledWith(expect.stringMatching(/^\/login\?redirect=/));
  });

  it('includes response bodies in non-auth API errors', async (): Promise<void> => {
    vi.mocked(fetch).mockResolvedValue(new Response('broken database', { status: 500 }));

    const { result } = renderHook(() => useAuthedFetch());

    await expectRejectedMessage(result.current('/api/v1/conversations'), 'API Error: 500 . Body: broken database');
  });
});
