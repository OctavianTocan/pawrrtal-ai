import { cookies } from 'next/headers';
import { notFound, unauthorized } from 'next/navigation';
import ChatContainer from '@/features/chat/ChatContainer';
import { API_ENDPOINTS, serverApiFetch } from '@/lib/server-api';
import type { ChatMessage, Conversation } from '@/lib/types';

/** Route params for `/c/:conversationId`. */
interface ConversationPageProps {
  params: Promise<{ conversationId: string }>;
}

function handleConversationFetchFailure(response: Response, label: string): void {
  if (response.status === 401) {
    unauthorized();
  }
  if (response.status === 404) {
    notFound();
  }
  if (response.status === 500) {
    throw new Error('Internal server error');
  }
  if (!response.ok) {
    throw new Error(`Failed to fetch ${label}: ${response.statusText}`);
  }
}

/**
 * Existing conversation page (`/c/:conversationId`).
 *
 * Server-side fetches the message history for the given conversation and
 * hydrates {@link ChatContainer} with it. Returns 401/404 for unauthorized
 * or missing conversations.
 *
 * TODO: Extract a server-side authed fetch utility to reduce boilerplate.
 * TODO: Handle the case where a conversation was just created but has no messages yet.
 */
export default async function ConversationPage({ params }: ConversationPageProps) {
  // `params` and `cookies()` are independent — resolve in parallel rather
  // than awaiting sequentially. `Promise.all` collapses two ~µs awaits
  // into one but the pattern is the right shape for when either grows
  // (e.g., switching to a database-backed session).
  const [{ conversationId }, cookieStore] = await Promise.all([params, cookies()]);
  const sessionToken = cookieStore.get('session_token');
  const headers = new Headers({ 'content-type': 'application/json' });
  if (sessionToken?.value) {
    headers.set('Cookie', `session_token=${sessionToken.value}`);
  }

  const [conversationResponse, messagesResponse] = await Promise.all([
    serverApiFetch(API_ENDPOINTS.conversations.get(conversationId), {
      cache: 'no-store',
      method: 'GET',
      headers,
    }),
    serverApiFetch(API_ENDPOINTS.conversations.getMessages(conversationId), {
      cache: 'no-store',
      method: 'GET',
      headers,
    }),
  ]);

  handleConversationFetchFailure(conversationResponse, 'conversation metadata');
  handleConversationFetchFailure(messagesResponse, 'conversation messages');

  const [conversation, messages] = await Promise.all([
    conversationResponse.json() as Promise<Conversation | null>,
    messagesResponse.json() as Promise<ChatMessage[]>,
  ]);

  return (
    <ChatContainer
      conversationId={conversationId}
      initialChatHistory={messages}
      initialModelId={conversation?.model_id ?? null}
      key={conversationId}
    />
  );
}
