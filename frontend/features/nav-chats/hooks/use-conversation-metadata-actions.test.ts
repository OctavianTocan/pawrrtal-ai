import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mutateAsyncMetadata, mutateAsyncRegen, toastSuccess, toastLoading, toastError } = vi.hoisted(() => ({
  mutateAsyncMetadata: vi.fn(),
  mutateAsyncRegen: vi.fn(),
  toastSuccess: vi.fn(),
  toastLoading: vi.fn(),
  toastError: vi.fn(),
}));

vi.mock('./use-conversation-mutations', () => ({
  useUpdateConversationMetadata: () => ({ mutateAsync: mutateAsyncMetadata }),
  useRegenerateTitle: () => ({ mutateAsync: mutateAsyncRegen }),
}));

vi.mock('@/lib/toast', () => ({
  toast: { success: toastSuccess, loading: toastLoading, error: toastError, info: vi.fn() },
  TOAST_IDS: {
    conversationFlag: 'conversation:flag',
    conversationArchive: 'conversation:archive',
    conversationUnread: 'conversation:unread',
    conversationStatus: 'conversation:status',
    conversationLabel: 'conversation:label',
    conversationRegenerateTitle: 'conversation:regenerate-title',
  },
}));

import type { Conversation } from '@/lib/types';
import { useConversationMetadataActions } from './use-conversation-metadata-actions';

function makeConversation(overrides: Partial<Conversation> = {}): Conversation {
  return {
    id: overrides.id ?? 'conv-1',
    user_id: 'user-1',
    title: 'Untitled',
    created_at: '2026-05-04T12:00:00.000Z',
    updated_at: '2026-05-04T12:00:00.000Z',
    is_archived: overrides.is_archived ?? false,
    is_flagged: overrides.is_flagged ?? false,
    is_unread: overrides.is_unread ?? false,
    status: overrides.status ?? null,
    labels: overrides.labels,
  };
}

beforeEach(() => {
  mutateAsyncMetadata.mockReset();
  mutateAsyncMetadata.mockResolvedValue(undefined);
  mutateAsyncRegen.mockReset();
  mutateAsyncRegen.mockResolvedValue('Renamed Title');
  toastSuccess.mockClear();
  toastLoading.mockClear();
  toastError.mockClear();
});

describe('useConversationMetadataActions', () => {
  it('toggles archive and emits the matching toast', () => {
    const conv = makeConversation({ is_archived: false });
    const { result } = renderHook(() => useConversationMetadataActions([conv]));
    result.current.handleArchive(conv.id);
    expect(mutateAsyncMetadata).toHaveBeenCalledWith({
      conversationId: conv.id,
      is_archived: true,
    });
    expect(toastSuccess).toHaveBeenCalledWith(
      'Moved to Archive',
      expect.objectContaining({ id: 'conversation:archive' })
    );
  });

  it('toggles flag and emits the "Added to your flagged items" toast', () => {
    const conv = makeConversation({ is_flagged: false });
    const { result } = renderHook(() => useConversationMetadataActions([conv]));
    result.current.handleFlag(conv.id);
    expect(toastSuccess).toHaveBeenCalledWith(
      'Added to your flagged items',
      expect.objectContaining({ id: 'conversation:flag' })
    );
  });

  it('toggles unread state and emits "Marked as unread"', () => {
    const conv = makeConversation({ is_unread: false });
    const { result } = renderHook(() => useConversationMetadataActions([conv]));
    result.current.handleMarkUnread(conv.id);
    expect(mutateAsyncMetadata).toHaveBeenCalledWith({
      conversationId: conv.id,
      is_unread: true,
    });
    expect(toastSuccess).toHaveBeenCalledWith(
      'Marked as unread',
      expect.objectContaining({ id: 'conversation:unread' })
    );
  });

  it('sets status and emits the formatted toast', () => {
    const conv = makeConversation();
    const { result } = renderHook(() => useConversationMetadataActions([conv]));
    result.current.handleSetStatus(conv.id, 'in_progress');
    expect(mutateAsyncMetadata).toHaveBeenCalledWith({
      conversationId: conv.id,
      status: 'in_progress',
    });
    expect(toastSuccess).toHaveBeenCalledWith(
      'Status set to In Progress',
      expect.objectContaining({ id: 'conversation:status' })
    );
  });

  it('toggles a label by appending the ID and PATCHing the new array', () => {
    const conv = makeConversation({ labels: [] });
    const { result } = renderHook(() => useConversationMetadataActions([conv]));
    result.current.handleToggleLabel(conv.id, 'bug');
    expect(mutateAsyncMetadata).toHaveBeenCalledWith({
      conversationId: conv.id,
      labels: ['bug'],
    });
    expect(toastSuccess).toHaveBeenCalledWith(
      'Added label "Bug"',
      expect.objectContaining({ id: 'conversation:label' })
    );
  });

  it('removes an already-applied label on second toggle', () => {
    const conv = makeConversation({ labels: ['bug'] });
    const { result } = renderHook(() => useConversationMetadataActions([conv]));
    result.current.handleToggleLabel(conv.id, 'bug');
    expect(mutateAsyncMetadata).toHaveBeenCalledWith({
      conversationId: conv.id,
      labels: [],
    });
  });

  it('no-ops when the conversation id is unknown', () => {
    const { result } = renderHook(() => useConversationMetadataActions([]));
    result.current.handleArchive('missing');
    result.current.handleFlag('missing');
    result.current.handleMarkUnread('missing');
    result.current.handleToggleLabel('missing', 'bug');
    expect(mutateAsyncMetadata).not.toHaveBeenCalled();
  });
});
