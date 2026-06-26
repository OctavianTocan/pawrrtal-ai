import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ChatStreamEvent } from '../types';
import { useChatTurns } from './use-chat-turns';

/**
 * Build an async generator that yields the supplied events in order.
 * Mirrors the shape of `useChat().streamMessage` so the hook can drive
 * a fake transport without touching `fetch`.
 */
function makeStream(events: ChatStreamEvent[]): (prompt: string) => AsyncGenerator<ChatStreamEvent> {
  return async function* gen(_prompt: string): AsyncGenerator<ChatStreamEvent> {
    for (const e of events) yield e;
  };
}

function streamThatThrows(message: string): (prompt: string) => AsyncGenerator<ChatStreamEvent> {
  return async function* gen(_prompt: string): AsyncGenerator<ChatStreamEvent> {
    yield { type: 'delta', content: 'partial' };
    throw new Error(message);
  };
}

describe('useChatTurns', () => {
  describe('send (first turn, empty history)', () => {
    it('appends user + assistant rows and streams deltas into the assistant slot', async () => {
      const { result } = renderHook(() =>
        useChatTurns({
          initialHistory: [],
          streamMessage: makeStream([
            { type: 'delta', content: 'Hel' },
            { type: 'delta', content: 'lo' },
          ]),
        })
      );

      await act(async () => {
        await result.current.send('hi');
      });

      expect(result.current.chatHistory).toEqual([
        { role: 'user', content: 'hi' },
        expect.objectContaining({
          role: 'assistant',
          content: 'Hello',
          assistant_status: 'complete',
        }),
      ]);
    });

    it('calls onFirstSend exactly once when history starts empty', async () => {
      const onFirstSend = vi.fn().mockResolvedValue(undefined);
      const { result } = renderHook(() =>
        useChatTurns({
          initialHistory: [],
          streamMessage: makeStream([{ type: 'delta', content: 'ok' }]),
          onFirstSend,
        })
      );

      await act(async () => {
        await result.current.send('first');
      });
      await act(async () => {
        await result.current.send('second');
      });

      expect(onFirstSend).toHaveBeenCalledExactlyOnceWith('first');
    });

    it('skips onFirstSend when initialHistory already has messages', async () => {
      const onFirstSend = vi.fn().mockResolvedValue(undefined);
      const { result } = renderHook(() =>
        useChatTurns({
          initialHistory: [
            { role: 'user', content: 'old' },
            { role: 'assistant', content: 'reply' },
          ],
          streamMessage: makeStream([{ type: 'delta', content: 'new reply' }]),
          onFirstSend,
        })
      );

      await act(async () => {
        await result.current.send('new');
      });

      expect(onFirstSend).not.toHaveBeenCalled();
    });

    it('toggles isLoading around the stream', async () => {
      let resolveStream: () => void = () => {};
      const streamMessage = (_prompt: string): AsyncGenerator<ChatStreamEvent> => {
        return (async function* gen() {
          await new Promise<void>((resolve) => {
            resolveStream = resolve;
          });
          yield { type: 'delta', content: 'done' };
        })();
      };

      const { result } = renderHook(() => useChatTurns({ initialHistory: [], streamMessage }));

      act(() => {
        void result.current.send('q');
      });
      await waitFor(() => expect(result.current.isLoading).toBe(true));
      await act(async () => {
        resolveStream();
      });
      await waitFor(() => expect(result.current.isLoading).toBe(false));
    });
  });

  describe('send (error path)', () => {
    it('collapses thrown errors into a failed assistant message', async () => {
      const { result } = renderHook(() =>
        useChatTurns({
          initialHistory: [],
          streamMessage: streamThatThrows('upstream 500'),
        })
      );

      await act(async () => {
        await result.current.send('hi');
      });

      const last = result.current.chatHistory.at(-1);
      expect(last).toEqual(
        expect.objectContaining({
          role: 'assistant',
          content: 'Error: upstream 500',
          assistant_status: 'failed',
        })
      );
    });

    it('uses a generic message when the rejection is not an Error instance', async () => {
      const streamMessage = (_prompt: string): AsyncGenerator<ChatStreamEvent> => {
        return (async function* gen() {
          yield { type: 'delta', content: 'x' };
          throw 'just a string';
        })();
      };

      const { result } = renderHook(() => useChatTurns({ initialHistory: [], streamMessage }));

      await act(async () => {
        await result.current.send('hi');
      });

      expect(result.current.chatHistory.at(-1)).toEqual(
        expect.objectContaining({
          content: 'Error: Chat stream failed.',
          assistant_status: 'failed',
        })
      );
    });
  });

  describe('regenerate', () => {
    it('replaces the assistant slot in place and re-streams the user prompt', async () => {
      const streamMessage = vi
        .fn<typeof makeStream extends (...args: never) => infer R ? R : never>()
        .mockImplementation(makeStream([{ type: 'delta', content: 'fresh' }]));

      const { result } = renderHook(() =>
        useChatTurns({
          initialHistory: [
            { role: 'user', content: 'what is 2+2' },
            { role: 'assistant', content: 'stale answer' },
          ],
          streamMessage,
        })
      );

      await act(async () => {
        await result.current.regenerate(1);
      });

      // `streamMessage` is invoked with `(prompt, images)` — `regenerate`
      // intentionally passes `undefined` for images so the re-stream is text-only.
      expect(streamMessage).toHaveBeenCalledExactlyOnceWith('what is 2+2', undefined);
      expect(result.current.chatHistory).toEqual([
        { role: 'user', content: 'what is 2+2' },
        expect.objectContaining({
          role: 'assistant',
          content: 'fresh',
          assistant_status: 'complete',
        }),
      ]);
    });

    it('is a no-op when the index does not point at a user→assistant pair', async () => {
      const streamMessage = vi
        .fn<typeof makeStream extends (...args: never) => infer R ? R : never>()
        .mockImplementation(makeStream([{ type: 'delta', content: 'x' }]));

      const { result } = renderHook(() =>
        useChatTurns({
          initialHistory: [{ role: 'user', content: 'only-user' }],
          streamMessage,
        })
      );

      // Index 0 isn't an assistant, and there is no message at index 1.
      await act(async () => {
        await result.current.regenerate(0);
      });
      await act(async () => {
        await result.current.regenerate(1);
      });

      expect(streamMessage).not.toHaveBeenCalled();
    });
  });
});
