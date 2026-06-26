import { renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ChatMessage } from '@/lib/types';
import { useChatBackgroundRecovery } from './use-chat-background-recovery';

const CONVERSATION_ID = 'conv-7';
const KEY = `chat:in-flight:${CONVERSATION_ID}`;

function lastAssistant(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    role: 'assistant',
    content: 'A reply',
    assistant_status: 'complete',
    ...overrides,
  };
}

describe('useChatBackgroundRecovery', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('beginStream / endStream', () => {
    it('beginStream writes the prompt under the per-conversation key', () => {
      const onRecover = vi.fn();
      const { result } = renderHook(() =>
        useChatBackgroundRecovery({
          conversationId: CONVERSATION_ID,
          chatHistory: [lastAssistant()],
          isLoading: false,
          onRecover,
        })
      );

      result.current.beginStream('please continue');

      expect(window.sessionStorage.getItem(KEY)).toBe('please continue');
    });

    it('endStream clears the breadcrumb', () => {
      window.sessionStorage.setItem(KEY, 'leftover');
      const { result } = renderHook(() =>
        useChatBackgroundRecovery({
          conversationId: CONVERSATION_ID,
          chatHistory: [lastAssistant()],
          isLoading: false,
          onRecover: vi.fn(),
        })
      );

      result.current.endStream();

      expect(window.sessionStorage.getItem(KEY)).toBeNull();
    });

    it('beginStream survives sessionStorage throwing (private mode)', () => {
      vi.spyOn(window.sessionStorage, 'setItem').mockImplementation(() => {
        throw new Error('QuotaExceededError');
      });
      const { result } = renderHook(() =>
        useChatBackgroundRecovery({
          conversationId: CONVERSATION_ID,
          chatHistory: [lastAssistant()],
          isLoading: false,
          onRecover: vi.fn(),
        })
      );

      // Should not throw; recovery is best-effort.
      expect(() => result.current.beginStream('whatever')).not.toThrow();
    });
  });

  describe('mount-time recovery', () => {
    it('calls onRecover when a breadcrumb exists and the last reply is missing', () => {
      window.sessionStorage.setItem(KEY, 'resume me');
      const onRecover = vi.fn();

      renderHook(() =>
        useChatBackgroundRecovery({
          conversationId: CONVERSATION_ID,
          chatHistory: [],
          isLoading: false,
          onRecover,
        })
      );

      expect(onRecover).toHaveBeenCalledExactlyOnceWith('resume me');
    });

    it('calls onRecover when a breadcrumb exists and the last reply failed', () => {
      window.sessionStorage.setItem(KEY, 'try again');
      const onRecover = vi.fn();

      renderHook(() =>
        useChatBackgroundRecovery({
          conversationId: CONVERSATION_ID,
          chatHistory: [lastAssistant({ assistant_status: 'failed' })],
          isLoading: false,
          onRecover,
        })
      );

      expect(onRecover).toHaveBeenCalledExactlyOnceWith('try again');
    });

    it('does NOT call onRecover when the last reply is complete', () => {
      window.sessionStorage.setItem(KEY, 'do not run');
      const onRecover = vi.fn();

      renderHook(() =>
        useChatBackgroundRecovery({
          conversationId: CONVERSATION_ID,
          chatHistory: [lastAssistant({ content: 'finished reply' })],
          isLoading: false,
          onRecover,
        })
      );

      expect(onRecover).not.toHaveBeenCalled();
    });

    it('does NOT call onRecover when a turn is already streaming', () => {
      window.sessionStorage.setItem(KEY, 'do not run');
      const onRecover = vi.fn();

      renderHook(() =>
        useChatBackgroundRecovery({
          conversationId: CONVERSATION_ID,
          chatHistory: [lastAssistant({ content: '' })],
          // A turn is already in flight — recovery would double-fire.
          isLoading: true,
          onRecover,
        })
      );

      expect(onRecover).not.toHaveBeenCalled();
    });

    it('does NOT call onRecover when no breadcrumb exists', () => {
      const onRecover = vi.fn();

      renderHook(() =>
        useChatBackgroundRecovery({
          conversationId: CONVERSATION_ID,
          chatHistory: [],
          isLoading: false,
          onRecover,
        })
      );

      expect(onRecover).not.toHaveBeenCalled();
    });

    it('fires onRecover at most once per mount even if deps change', () => {
      window.sessionStorage.setItem(KEY, 'only-once');
      const onRecover = vi.fn();

      const { rerender } = renderHook(
        ({ history }: { history: Array<ChatMessage> }) =>
          useChatBackgroundRecovery({
            conversationId: CONVERSATION_ID,
            chatHistory: history,
            isLoading: false,
            onRecover,
          }),
        { initialProps: { history: [] as Array<ChatMessage> } }
      );

      // Simulate the container responding to onRecover by appending a
      // pending assistant message — the hook must not re-fire.
      rerender({ history: [lastAssistant({ content: '', assistant_status: 'streaming' })] });
      rerender({
        history: [lastAssistant({ content: 'partial', assistant_status: 'streaming' })],
      });

      expect(onRecover).toHaveBeenCalledTimes(1);
    });
  });
});
