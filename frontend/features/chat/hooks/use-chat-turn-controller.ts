'use client';

import { useRouter } from 'next/navigation';
import { useCallback, useMemo, useRef } from 'react';
import type { PromptInputMessage } from '@/components/ai-elements/prompt-input';
import type { ChatMessage } from '@/lib/types';
import type { ChatReasoningLevel } from '../constants';
import { FALLBACK_TITLE_MAX_LENGTH } from '../constants';
import { extractImageInputs } from '../lib/extract-image-inputs';
import type { ChatImageInput } from './use-chat';
import { useChat } from './use-chat';
import { useChatBackgroundRecovery } from './use-chat-background-recovery';
import { useChatTurns } from './use-chat-turns';
import { useCreateConversation } from './use-create-conversation';
import { useGenerateConversationTitle } from './use-generate-conversation-title';

/**
 * Sidebar-safe fallback title before async LLM titling returns: trimmed first line, ellipsized.
 */
function buildInitialConversationTitle(content: string): string {
  const collapsedContent = content.trim().replace(/\s+/g, ' ');

  if (!collapsedContent) {
    return 'New Conversation';
  }

  if (collapsedContent.length <= FALLBACK_TITLE_MAX_LENGTH) {
    return collapsedContent;
  }

  return `${collapsedContent.slice(0, FALLBACK_TITLE_MAX_LENGTH - 3).trimEnd()}...`;
}

/** Inputs to {@link useChatTurnController}. */
export interface ChatTurnControllerArgs {
  /** Conversation UUID this controller operates on. */
  conversationId: string;
  /** Pre-fetched messages used to seed the turn buffer on first render. */
  initialChatHistory?: Array<ChatMessage>;
  /** Currently selected canonical model ID; passed through to the stream call. */
  selectedModelId: string;
  /** Currently selected reasoning level; passed through to the stream call. */
  selectedReasoning: ChatReasoningLevel;
}

/** Return shape from {@link useChatTurnController}. */
export interface ChatTurnControllerResult {
  /** Accumulated chat history including any in-flight assistant turn. */
  chatHistory: Array<ChatMessage>;
  /** ID of the message currently flashing the "copied" affordance, if any. */
  copiedId: string | null;
  /** True while a stream is in flight (send or regenerate). */
  isLoading: boolean;
  /** Index of the message currently being regenerated, or `null`. */
  regeneratingIndex: number | null;
  /** Copies a message body, flashing the in-progress affordance. */
  copyMessage: (id: string, text: string) => void;
  /** Re-streams the assistant turn at `assistantIndex` using the prior user prompt. */
  regenerateMessage: (assistantIndex: number) => Promise<void>;
  /** Sends a new user message, creating the conversation if it doesn't yet exist. */
  sendMessage: (message: PromptInputMessage) => Promise<void>;
}

/**
 * Owns the chat send / regenerate / copy lifecycle for a single conversation.
 *
 * Pulled out of {@link ChatContainer} so the container stays under the
 * per-file line budget. Holds the cross-hook glue between
 * {@link useChat}, {@link useChatTurns},
 * {@link useChatBackgroundRecovery}, and the
 * conversation-creation / titling mutations.
 *
 * Side effects on first send:
 * - Creates the conversation row via {@link useCreateConversation}.
 * - Fires async LLM titling via {@link useGenerateConversationTitle}.
 * - Rewrites the URL to `/c/:id` immediately and routes via Next.js once
 *   the in-flight stream completes (avoids a mid-stream navigation flash).
 */
export function useChatTurnController({
  conversationId,
  initialChatHistory,
  selectedModelId,
  selectedReasoning,
}: ChatTurnControllerArgs): ChatTurnControllerResult {
  const { streamMessage } = useChat();
  const createConversationMutation = useCreateConversation(conversationId);
  const generateConversationTitleMutation = useGenerateConversationTitle(conversationId);
  const { replace } = useRouter();
  const hasNavigated = useRef(false);
  const stream = useCallback(
    (prompt: string, images?: readonly ChatImageInput[]) =>
      streamMessage(prompt, conversationId, selectedModelId, selectedReasoning, images),
    [conversationId, selectedModelId, selectedReasoning, streamMessage]
  );
  const onFirstSend = useCallback(
    async (prompt: string): Promise<void> => {
      await createConversationMutation.mutateAsync({
        title: buildInitialConversationTitle(prompt),
      });
      generateConversationTitleMutation.mutateAsync(prompt).catch(() => undefined);
      window.history.replaceState(null, '', `/c/${conversationId}`);
      hasNavigated.current = true;
    },
    [conversationId, createConversationMutation, generateConversationTitleMutation]
  );
  const initialHistory = useMemo(() => initialChatHistory ?? [], [initialChatHistory]);
  const { chatHistory, isLoading, regeneratingIndex, copiedId, send, regenerate, copy } = useChatTurns({
    initialHistory,
    streamMessage: stream,
    onFirstSend,
  });
  const { beginStream, endStream } = useChatBackgroundRecovery({
    chatHistory,
    conversationId,
    isLoading,
    onRecover: (prompt) => {
      void send(prompt);
    },
  });
  const sendMessage = useCallback(
    async (message: PromptInputMessage): Promise<void> => {
      const prompt = message.content;
      // Decode attachments to base64 BEFORE kicking off the optimistic
      // placeholders so a slow fetch doesn't open a window where the UI
      // looks "sent" but the request hasn't been shaped yet.
      // `extractImageInputs` is non-throwing — failed reads silently drop
      // instead of aborting the whole turn.
      const images = await extractImageInputs(message.files);
      beginStream(prompt);
      try {
        await send(prompt, images.length > 0 ? images : undefined);
      } finally {
        endStream();
        if (hasNavigated.current) replace(`/c/${conversationId}`);
      }
    },
    [beginStream, conversationId, endStream, replace, send]
  );
  const chatHistoryRef = useRef(chatHistory);
  chatHistoryRef.current = chatHistory;
  const regenerateMessage = useCallback(
    async (assistantIndex: number): Promise<void> => {
      const userMessage = chatHistoryRef.current[assistantIndex - 1];
      if (userMessage?.role === 'user') beginStream(userMessage.content);
      try {
        await regenerate(assistantIndex);
      } finally {
        endStream();
      }
    },
    [beginStream, endStream, regenerate]
  );
  const copyMessage = useCallback(
    (id: string, text: string): void => {
      void copy(id, text);
    },
    [copy]
  );
  return {
    chatHistory,
    copiedId,
    isLoading,
    regeneratingIndex,
    copyMessage,
    regenerateMessage,
    sendMessage,
  };
}
