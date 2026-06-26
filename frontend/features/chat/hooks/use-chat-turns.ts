'use client';

import { useCallback, useRef, useState } from 'react';
import type { ChatMessage } from '@/lib/types';
import { applyChatEvent, computeThinkingDuration, updateLastAssistantMessage } from '../chat-reducer';
import type { ChatStreamEvent } from '../types';
import type { ChatImageInput } from './use-chat';
import { useCopyToClipboard } from './use-copy-to-clipboard';

/** Hook input. */
interface UseChatTurnsConfig {
  /** Initial chat history hydrated from the server. */
  initialHistory: Array<ChatMessage>;
  /**
   * Async generator that yields {@link ChatStreamEvent}s for one user prompt.
   * Provided by the caller so this hook stays decoupled from
   * `useChat`/`useAuthedFetch`. Accepts an optional list of multimodal
   * image inputs that ride alongside the prompt on the first turn —
   * regenerate intentionally re-runs with text only because images
   * aren't persisted on the assistant placeholder yet.
   */
  streamMessage: (prompt: string, images?: readonly ChatImageInput[]) => AsyncGenerator<ChatStreamEvent>;
  /**
   * Optional side-effect fired the first time a turn is sent. Returns a
   * promise the caller awaits before the SSE stream starts so any
   * conversation-creation work can finish first.
   */
  onFirstSend?: (prompt: string) => Promise<void>;
}

/** Hook output — passed straight through to {@link import('../ChatView').default}. */
export interface UseChatTurnsReturn {
  chatHistory: Array<ChatMessage>;
  isLoading: boolean;
  regeneratingIndex: number | null;
  copiedId: string | null;
  send: (prompt: string, images?: readonly ChatImageInput[]) => Promise<void>;
  regenerate: (assistantIndex: number) => Promise<void>;
  copy: (id: string, text: string) => Promise<{ ok: boolean }>;
}

/**
 * Owns the chat-history lifecycle: streaming state, optimistic placeholders,
 * regenerate, and clipboard feedback.
 *
 * Extracted out of `ChatContainer` so the container can stay focused on
 * routing/title/sidebar wiring. The transport function is injected so this
 * hook is independently testable with a fake generator.
 */
export function useChatTurns({ initialHistory, streamMessage, onFirstSend }: UseChatTurnsConfig): UseChatTurnsReturn {
  const [chatHistory, setChatHistory] = useState<Array<ChatMessage>>(initialHistory);
  const [isLoading, setIsLoading] = useState(false);
  const [regeneratingIndex, setRegeneratingIndex] = useState<number | null>(null);
  const isSendingRef = useRef(false);
  // Seed from initialHistory so existing conversations (loaded via
  // /c/[uuid] with hydrated messages) don't re-fire onFirstSend on the
  // next user message — that fires conversation-creation and title
  // generation, both of which would re-run on every reply otherwise.
  const hasSentRef = useRef(initialHistory.length > 0);
  const { copy, copiedId } = useCopyToClipboard();

  /**
   * Stream a single assistant turn into the trailing assistant placeholder
   * and finalize status + duration. Any thrown error is collapsed into a
   * `failed` status with the error message in `content`.
   */
  const runAssistantTurn = useCallback(
    async (prompt: string, images?: readonly ChatImageInput[]): Promise<void> => {
      try {
        for await (const event of streamMessage(prompt, images)) {
          setChatHistory((prev) => updateLastAssistantMessage(prev, (msg) => applyChatEvent(msg, event)));
        }
        setChatHistory((prev) =>
          updateLastAssistantMessage(prev, (msg) => ({
            ...msg,
            assistant_status: 'complete',
            thinking_duration_seconds: computeThinkingDuration(msg),
          }))
        );
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Chat stream failed.';
        setChatHistory((prev) =>
          updateLastAssistantMessage(prev, (msg) => ({
            ...msg,
            content: `Error: ${errorMessage}`,
            assistant_status: 'failed',
            thinking_duration_seconds: computeThinkingDuration(msg),
          }))
        );
      }
    },
    [streamMessage]
  );

  const send = useCallback(
    async (prompt: string, images?: readonly ChatImageInput[]): Promise<void> => {
      if (isSendingRef.current || isLoading) return;
      isSendingRef.current = true;
      setIsLoading(true);
      setChatHistory((prev) => [
        ...prev,
        { role: 'user', content: prompt } as ChatMessage,
        { role: 'assistant', content: '' } as ChatMessage,
      ]);

      try {
        if (!hasSentRef.current && onFirstSend) {
          await onFirstSend(prompt);
        }
        hasSentRef.current = true;
        await runAssistantTurn(prompt, images);
      } finally {
        setIsLoading(false);
        isSendingRef.current = false;
      }
    },
    [isLoading, onFirstSend, runAssistantTurn]
  );

  const regenerate = useCallback(
    async (assistantIndex: number): Promise<void> => {
      if (isSendingRef.current || isLoading) return;
      const userMessage = chatHistory[assistantIndex - 1];
      const targetAssistant = chatHistory[assistantIndex];
      if (!(userMessage?.role === 'user' && targetAssistant?.role === 'assistant')) return;

      isSendingRef.current = true;
      setRegeneratingIndex(assistantIndex);
      setIsLoading(true);

      // Reset the assistant slot in place so the row keeps its position.
      setChatHistory((prev) =>
        prev.map((msg, i) => (i === assistantIndex ? ({ role: 'assistant', content: '' } as ChatMessage) : msg))
      );

      try {
        await runAssistantTurn(userMessage.content);
      } finally {
        setIsLoading(false);
        isSendingRef.current = false;
        setRegeneratingIndex(null);
      }
    },
    [chatHistory, isLoading, runAssistantTurn]
  );

  return { chatHistory, isLoading, regeneratingIndex, copiedId, send, regenerate, copy };
}
