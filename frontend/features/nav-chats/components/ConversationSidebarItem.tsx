'use client';

import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';
import { formatConversationAge } from '@/lib/format-conversation-age';
import type { ConversationStatus } from '@/lib/types';
import { ConversationSidebarItemView } from './ConversationSidebarItemView';

/** Props for the ConversationSidebarItem container component. */
interface ConversationSidebarItemProps {
  /** The conversation ID. */
  id: string;
  /** The conversation title (may include Calligraph or highlight wrapping). */
  title: ReactNode;
  /** ISO 8601 timestamp of the conversation's last update. */
  updatedAt: string;
  /** Row and conversation status flags. */
  state: ConversationSidebarItemState;
  /** Current workflow status tag. */
  status: ConversationStatus;
  /** String label IDs currently applied (resolved against NAV_CHATS_LABELS). */
  appliedLabelIds: readonly string[];
  /** Called to navigate to a conversation. */
  onNavigate: (href: string) => void;
  /** Called to open the rename dialog for this conversation. */
  onRename: (conversationId: string) => void;
  /** Called to open the delete confirmation for this conversation. */
  onDelete: (conversationId: string) => void;
  /** Toggles archived state for this conversation. */
  onArchive: (conversationId: string) => void;
  /** Toggles flagged state for this conversation. */
  onFlag: (conversationId: string) => void;
  /** Sets the status tag on this conversation. */
  onSetStatus: (conversationId: string, status: ConversationStatus) => void;
  /** Toggles the unread indicator on this conversation. */
  onMarkUnread: (conversationId: string) => void;
  /** Triggers LLM title regeneration for this conversation. */
  onRegenerateTitle: (conversationId: string) => void;
  /** Toggles a single label ID on/off for this conversation. */
  onToggleLabel: (conversationId: string, labelId: string) => void;
  /** Triggers a Markdown download for this conversation. */
  onExportMarkdown: (conversationId: string) => void;
  /** Icon shown before the title (e.g. processing spinner, unread dot). */
  icon?: ReactNode;
  /** Label badges shown after the title. */
  badges?: ReactNode;
  /** Content shown after the title (e.g. search match count badge). */
  titleTrailing?: ReactNode;
  /** Called when the row is clicked. */
  onClick?: () => void;
  /** Called on mouse down on the row. */
  onMouseDown?: (e: React.MouseEvent) => void;
  /** Extra button props for the row's interactive element. */
  buttonProps?: React.HTMLAttributes<HTMLDivElement> & { ref?: React.Ref<HTMLDivElement> };
}

interface ConversationSidebarItemState {
  /** Whether the conversation is archived. */
  isArchived: boolean;
  /** Whether the conversation is flagged. */
  isFlagged: boolean;
  /** True when this item is part of an active multi-select. */
  isInMultiSelect?: boolean;
  /** Whether the conversation has an unread indicator. */
  isUnread: boolean;
  /** Whether to render a separator above this item. */
  showSeparator: boolean;
}

/**
 * Container for a single conversation sidebar row.
 *
 * Resolves route-derived state (isSelected, href, absoluteHref) and
 * formats the conversation age. Delegates rendering to
 * `ConversationSidebarItemView`.
 */
/**
 * Container for a single conversation sidebar row.
 *
 * Resolves route-derived state (isSelected, href, absoluteHref), formats the
 * conversation age, and binds all action handlers to the current conversation ID
 * before delegating rendering to `ConversationSidebarItemView`.
 */
export function ConversationSidebarItem({
  id,
  title,
  updatedAt,
  state,
  status,
  appliedLabelIds,
  onNavigate,
  onRename,
  onDelete,
  onArchive,
  onFlag,
  onSetStatus,
  onMarkUnread,
  onRegenerateTitle,
  onToggleLabel,
  onExportMarkdown,
  icon,
  badges,
  titleTrailing,
  onClick,
  onMouseDown,
  buttonProps,
}: ConversationSidebarItemProps): React.JSX.Element {
  const pathname = usePathname();
  const href = `/c/${id}`;
  const isSelected = pathname === href;
  const age = formatConversationAge(updatedAt);
  const { isArchived, isFlagged, isInMultiSelect, isUnread, showSeparator } = state;

  // Compute absolute URL for clipboard operations. No memoization needed —
  // the computation is trivial and href is already stable (derived from id).
  const absoluteHref = typeof window === 'undefined' ? href : new URL(href, window.location.origin).toString();

  return (
    <ConversationSidebarItemView
      absoluteHref={absoluteHref}
      age={age}
      appliedLabelIds={appliedLabelIds}
      badges={badges}
      buttonProps={buttonProps}
      conversationId={id}
      href={href}
      icon={icon}
      onArchive={() => onArchive(id)}
      onClick={onClick}
      onClickMenuItem={() => onNavigate(href)}
      onDelete={() => onDelete(id)}
      onExportMarkdown={() => onExportMarkdown(id)}
      onFlag={() => onFlag(id)}
      onMarkUnread={() => onMarkUnread(id)}
      onMouseDown={onMouseDown}
      onNavigate={onNavigate}
      onRegenerateTitle={() => onRegenerateTitle(id)}
      onRename={() => onRename(id)}
      onSetStatus={(s) => onSetStatus(id, s)}
      onToggleLabel={(labelId) => onToggleLabel(id, labelId)}
      state={{
        isArchived,
        isFlagged,
        isInMultiSelect,
        isSelected,
        isUnread,
        showSeparator,
      }}
      status={status}
      title={title}
      titleTrailing={titleTrailing}
    />
  );
}
