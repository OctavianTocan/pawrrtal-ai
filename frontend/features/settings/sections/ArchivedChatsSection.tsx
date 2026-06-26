'use client';

import { Archive } from 'lucide-react';
import type * as React from 'react';
import { AppEmptyState } from '@/components/ui/app-empty-state';
import { Button } from '@/components/ui/button';
import { useUpdateConversationMetadata } from '@/features/nav-chats/hooks/use-conversation-mutations';
import useGetConversations from '@/hooks/get-conversations';
import { toast } from '@/lib/toast';
import type { Conversation } from '@/lib/types';
import { SettingsPage } from '../primitives';

const ARCHIVED_ROW_DATE_FORMATTER = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
});

/**
 * Settings → Archived chats. Lists every conversation with `is_archived=true`
 * (newest-first) and exposes an Unarchive action per row that flips the
 * flag back to `false` via the existing PATCH mutation.
 *
 * Mirrors the Codex reference layout (Image #37): row title, "Mar 27,
 * 2026, 6:30 PM · pawrrtal" metadata line, Unarchive button on the right.
 */
export function ArchivedChatsSection(): React.JSX.Element {
  const { data: conversations, isLoading } = useGetConversations();
  const updateMetadata = useUpdateConversationMetadata();

  const archived = (conversations ?? [])
    .filter((conversation) => conversation.is_archived)
    .toSorted((left, right) => new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime());

  const handleUnarchive = (conversationId: string): void => {
    updateMetadata.mutate(
      { conversationId, is_archived: false },
      {
        onSuccess: () => toast.success('Chat unarchived'),
        onError: () => toast.error('Could not unarchive chat'),
      }
    );
  };

  return (
    <SettingsPage
      description="Conversations you've archived. Unarchive any to bring it back into your active chat list."
      title="Archived chats"
    >
      {isLoading ? <p className="text-sm text-muted-foreground">Loading archived chats&hellip;</p> : null}

      {!isLoading && archived.length === 0 ? <ArchivedEmptyState /> : null}

      {archived.length > 0 ? (
        <section className="flex flex-col rounded-[12px] border border-border/60 bg-foreground/[0.02]">
          {archived.map((conversation, index) => (
            <ArchivedChatRow
              conversation={conversation}
              isFirst={index === 0}
              isLast={index === archived.length - 1}
              isPending={updateMetadata.isPending}
              key={conversation.id}
              onUnarchive={() => handleUnarchive(conversation.id)}
            />
          ))}
        </section>
      ) : null}
    </SettingsPage>
  );
}

interface ArchivedChatRowProps {
  conversation: Conversation;
  isFirst: boolean;
  isLast: boolean;
  isPending: boolean;
  onUnarchive: () => void;
}

/**
 * Single archived-chat row. Title + metadata line on the left, Unarchive
 * pill on the right. Internal dividers between rows; first/last suppress
 * their corresponding border so the rounded card edges look clean.
 */
function ArchivedChatRow({
  conversation,
  isFirst: _isFirst,
  isLast,
  isPending,
  onUnarchive,
}: ArchivedChatRowProps): React.JSX.Element {
  const updatedAt = new Date(conversation.updated_at);
  const formatted = formatRowDate(updatedAt);

  return (
    <div
      className={
        isLast
          ? 'flex items-center justify-between gap-6 px-5 py-4'
          : 'flex items-center justify-between gap-6 border-b border-border/40 px-5 py-4'
      }
    >
      <div className="flex min-w-0 flex-col gap-1">
        <span className="truncate text-sm font-medium text-foreground">{conversation.title || 'Untitled chat'}</span>
        <span className="truncate text-sm text-muted-foreground">{formatted} · pawrrtal</span>
      </div>
      <Button
        className="cursor-pointer"
        disabled={isPending}
        onClick={onUnarchive}
        size="sm"
        type="button"
        variant="outline"
      >
        Unarchive
      </Button>
    </div>
  );
}

/** Friendly `Mar 27, 2026, 6:30 PM`-style date formatter. */
function formatRowDate(date: Date): string {
  return ARCHIVED_ROW_DATE_FORMATTER.format(date);
}

/** Empty state shown when the user has no archived conversations. */
function ArchivedEmptyState(): React.JSX.Element {
  return (
    <AppEmptyState
      description="Chats you archive from the sidebar appear here. They stay searchable but stay out of the active list."
      icon={<Archive aria-hidden="true" className="size-5" />}
      title="No archived chats"
      tone="panel"
    />
  );
}
