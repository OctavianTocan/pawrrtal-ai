import { renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { fetcherMock, toastSuccess, toastLoading, toastError } = vi.hoisted(() => ({
  fetcherMock: vi.fn(),
  toastSuccess: vi.fn(),
  toastLoading: vi.fn(),
  toastError: vi.fn(),
}));

vi.mock('@/hooks/use-authed-fetch', () => ({
  useAuthedFetch: () => fetcherMock,
}));

vi.mock('@/lib/toast', () => ({
  toast: { success: toastSuccess, loading: toastLoading, error: toastError, info: vi.fn() },
  TOAST_IDS: { conversationExport: 'conversation:export' },
}));

import type { Conversation } from '@/lib/types';
import { useExportConversation } from './use-export-conversation';

const baseConversation: Conversation = {
  id: 'conv-1',
  user_id: 'user-1',
  title: 'My great chat',
  created_at: '2026-05-04T12:00:00.000Z',
  updated_at: '2026-05-04T12:00:00.000Z',
  is_archived: false,
  is_flagged: false,
  is_unread: false,
  status: null,
};

beforeEach(() => {
  fetcherMock.mockReset();
  toastSuccess.mockReset();
  toastLoading.mockReset();
  toastError.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('useExportConversation', () => {
  it('fetches messages, builds a markdown blob, and toasts success', async () => {
    fetcherMock.mockResolvedValueOnce({
      json: async () => [
        { role: 'user', content: 'Hi' },
        { role: 'assistant', content: 'Hello!' },
      ],
    });

    const { result } = renderHook(() => useExportConversation());

    // Stub the anchor.click() so jsdom doesn't try to actually navigate.
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);

    await result.current.exportAsMarkdown(baseConversation);

    expect(fetcherMock).toHaveBeenCalled();
    expect(clickSpy).toHaveBeenCalled();
    expect(toastLoading).toHaveBeenCalledWith(
      'Preparing export...',
      expect.objectContaining({ id: 'conversation:export' })
    );
    expect(toastSuccess).toHaveBeenCalledWith(
      'Exported as Markdown',
      expect.objectContaining({ id: 'conversation:export' })
    );
    clickSpy.mockRestore();
  });

  it('emits an error toast when the fetch throws', async () => {
    fetcherMock.mockRejectedValueOnce(new Error('boom'));

    const { result } = renderHook(() => useExportConversation());
    await result.current.exportAsMarkdown(baseConversation);

    expect(toastError).toHaveBeenCalledWith(
      'Could not export conversation',
      expect.objectContaining({ id: 'conversation:export' })
    );
  });
});
