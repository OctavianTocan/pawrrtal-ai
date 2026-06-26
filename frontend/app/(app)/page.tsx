import ChatContainer from '@/features/chat/ChatContainer';

/**
 * Root conversation page (`/`).
 *
 * Generates a fresh UUID on each render so the {@link ChatContainer} starts
 * with a blank slate. The `key` prop ensures React fully remounts the
 * component when navigating back here from an existing conversation.
 *
 * The onboarding modal is mounted once at the app-layout level and only
 * opens in response to `OPEN_ONBOARDING_EVENT` (dispatched by the
 * "Add Workspace" item in the workspace selector). It's no longer
 * mounted here so it doesn't auto-open every time the user returns to home.
 */
export default async function ConversationPage() {
  const uuid: string = crypto.randomUUID();

  return <ChatContainer key={uuid} conversationId={uuid} />;
}
