/**
 * @file chat-activity-context.tsx
 *
 * Provides a shared context for tracking which conversation is currently active
 * in the chat panel. The sidebar needs to know this so it can show activity
 * indicators (loading spinners, unread badges) on the correct row without
 * prop-drilling through the entire component tree.
 *
 * Without this context, the sidebar and the chat panel would need a common
 * parent to hoist the "active conversation" state into, which doesn't exist
 * cleanly in the current layout (sidebar and chat are siblings under different
 * layout regions).
 */
'use client';

import type React from 'react';
import { createContext, use, useMemo, useState } from 'react';
import type { ChatMessage } from '@/lib/types';

/** Snapshot of the conversation currently open in the chat panel. */
type ActiveConversationState = {
  conversationId: string | null;
  chatHistory: ChatMessage[];
  isLoading: boolean;
};

/** Context value exposed to consumers: current state + mutation helpers. */
type ChatActivityContextValue = ActiveConversationState & {
  /** Publish the latest active conversation snapshot for sidebar consumers. */
  publishActiveConversation: (state: ActiveConversationState) => void;
  /**
   * Clear the active conversation, but only if the given ID matches.
   * Guards against race conditions where a slow close callback fires
   * after a new conversation was already opened.
   */
  clearActiveConversation: (conversationId: string) => void;
};

const ChatActivityContext = createContext<ChatActivityContextValue | null>(null);

/**
 * Provides chat activity state to the sidebar and any other component
 * that needs to know which conversation is currently open.
 */
export function ChatActivityProvider({ children }: { children: React.ReactNode }): React.JSX.Element {
  const [state, setState] = useState<ActiveConversationState>({
    conversationId: null,
    chatHistory: [],
    isLoading: false,
  });

  const value = useMemo<ChatActivityContextValue>(
    () => ({
      ...state,
      publishActiveConversation: setState,
      clearActiveConversation: (conversationId) => {
        setState((current) =>
          current.conversationId === conversationId
            ? { conversationId: null, chatHistory: [], isLoading: false }
            : current
        );
      },
    }),
    [state]
  );

  return <ChatActivityContext.Provider value={value}>{children}</ChatActivityContext.Provider>;
}

/**
 * Access the chat activity context. Must be called inside a ChatActivityProvider.
 * @throws If called outside the provider tree.
 */
export function useChatActivity(): ChatActivityContextValue {
  const context = use(ChatActivityContext);
  if (!context) {
    throw new Error('useChatActivity must be used within ChatActivityProvider.');
  }
  return context;
}
