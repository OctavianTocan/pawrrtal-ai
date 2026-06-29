'use client';

import { DropdownMenuShortcut } from '@octavian-tocan/react-dropdown';
import {
  AppWindow,
  Archive,
  CheckCircle2,
  Copy,
  Files,
  FileText,
  Flag,
  FolderOpen,
  MailOpen,
  MoreHorizontal,
  Pencil,
  RefreshCw,
  Tag,
  Trash2,
} from 'lucide-react';
import type { ReactNode } from 'react';
import { useMemo } from 'react';
import { EntityRow } from '@/components/ui/entity-row';
import { useMenuComponents } from '@/components/ui/menu-context';
import { SidebarMenuItem } from '@/components/ui/sidebar';
import { NAV_CHATS_LABELS } from '@/features/nav-chats/constants';
import { CONVERSATION_DRAG_MIME } from '@/lib/conversations/drag';
import { TOAST_IDS, toast } from '@/lib/toast';
import type { ConversationStatus } from '@/lib/types';
import { ConversationStatusGlyph } from './ConversationStatusGlyph';
import { ConversationUnreadGlyph } from './ConversationUnreadGlyph';
import { STATUS_SUBMENU } from './conversation-status-data';

/** Props for the conversation sidebar row presentation component. */
export interface ConversationSidebarItemViewProps {
  /** The conversation title (may include Calligraph or highlight wrapping). */
  title: ReactNode;
  /** Row and conversation status flags. */
  state: ConversationSidebarItemViewState;
  /** Compact relative-time string (e.g. "3h"), or null. */
  age: string | null;
  /** The full URL path for this conversation. */
  href: string;
  /** Absolute URL for clipboard copy. */
  absoluteHref: string;
  /** Current workflow status tag. */
  status: ConversationStatus;
  /** String label IDs currently applied (resolved against NAV_CHATS_LABELS). */
  appliedLabelIds: readonly string[];
  /** Called when the row is clicked. */
  onClick?: () => void;
  /** Called to navigate in a menu item. */
  onNavigate: (href: string) => void;
  /** Opens the rename flow for this conversation. */
  onRename: () => void;
  /** Opens the delete confirmation for this conversation. */
  onDelete: () => void;
  /** Toggles archived state for this conversation. */
  onArchive: () => void;
  /** Toggles flagged state for this conversation. */
  onFlag: () => void;
  /** Sets the status tag for this conversation. */
  onSetStatus: (status: ConversationStatus) => void;
  /** Toggles the unread indicator for this conversation. */
  onMarkUnread: () => void;
  /** Triggers LLM title regeneration for this conversation. */
  onRegenerateTitle: () => void;
  /** Toggles a single label ID on/off for this conversation. */
  onToggleLabel: (labelId: string) => void;
  /** Triggers a Markdown download for this conversation. */
  onExportMarkdown: () => void;
  /** Optional override for the row's left icon (e.g. processing spinner). */
  icon?: ReactNode;
  /** Label badges shown after the title. */
  badges?: ReactNode;
  /** Content shown after the title (e.g. search match count badge). */
  titleTrailing?: ReactNode;
  /** Called on mouse down on the row. */
  onMouseDown?: (e: React.MouseEvent) => void;
  /**
   * The conversation ID dropped onto a project drop target during DnD.
   * Surfaced as a separate prop so the View can populate the
   * dataTransfer payload without needing the full Conversation object.
   */
  conversationId?: string;
  /** Called when a menu item triggers navigation (separate from onClick). */
  onClickMenuItem?: () => void;
  /** Extra button props for the row's interactive element. */
  buttonProps?: React.HTMLAttributes<HTMLDivElement> & { ref?: React.Ref<HTMLDivElement> };
}

export interface ConversationSidebarItemViewState {
  /** Whether the conversation is archived. */
  isArchived: boolean;
  /** Whether the conversation is flagged. */
  isFlagged: boolean;
  /** True when this item is part of an active multi-select. */
  isInMultiSelect?: boolean;
  /** Whether this row is the active route. */
  isSelected: boolean;
  /** Whether the conversation has an unread indicator. */
  isUnread: boolean;
  /** Whether to render a separator above this item. */
  showSeparator: boolean;
}

/** Props for the shared menu-content component. */
interface ConversationMenuContentProps {
  href: string;
  absoluteHref: string;
  isArchived: boolean;
  isFlagged: boolean;
  isUnread: boolean;
  status: ConversationStatus;
  appliedLabelIds: readonly string[];
  onNavigate: () => void;
  onRename: () => void;
  onDelete: () => void;
  onArchive: () => void;
  onFlag: () => void;
  onSetStatus: (status: ConversationStatus) => void;
  onMarkUnread: () => void;
  onRegenerateTitle: () => void;
  onToggleLabel: (labelId: string) => void;
  onExportMarkdown: () => void;
}

/**
 * Two-tier menu content shared by both the dropdown and right-click menu.
 *
 * Tier 1 (top): high-frequency actions — Open, Status, Labels, Flag, Mark
 * Unread, Rename, Archive, then a "More" submenu and Delete.
 *
 * Tier 2 ("More" submenu): Regenerate Title, Open in New Window, Copy Link,
 * Export as Markdown, Duplicate.
 */
function ConversationMenuContent({
  href,
  absoluteHref,
  isArchived,
  isFlagged,
  isUnread,
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
}: ConversationMenuContentProps): React.JSX.Element {
  const { MenuItem, MenuSeparator, MenuSub, MenuSubTrigger, MenuSubContent } = useMenuComponents();

  const handleCopyLink = (): void => {
    if (typeof navigator === 'undefined' || !navigator.clipboard) return;
    void navigator.clipboard.writeText(absoluteHref).then(() => {
      toast.success('Link copied to clipboard', { id: TOAST_IDS.conversationCopyLink });
    });
  };

  const handleOpenNewWindow = (): void => {
    if (typeof window === 'undefined') return;
    window.open(href, '_blank', 'noopener,noreferrer');
  };

  const handleDuplicate = (): void => {
    // Backend clone endpoint is not yet shipped — see follow-up bean. The
    // toast confirms the menu wiring without pretending the feature exists.
    toast.info('Duplicate is coming soon', {
      id: TOAST_IDS.conversationDuplicate,
    });
  };

  return (
    <>
      <MenuItem onSelect={onNavigate}>
        <FolderOpen aria-hidden="true" className="size-3.5" />
        <span className="flex-1">Open</span>
        <DropdownMenuShortcut>↵</DropdownMenuShortcut>
      </MenuItem>

      <MenuSeparator />

      <MenuSub>
        <MenuSubTrigger>
          <ConversationStatusGlyph status={status} />
          <span className="flex-1">Status</span>
        </MenuSubTrigger>
        <MenuSubContent>
          {STATUS_SUBMENU.map((option) => {
            const isActive = status === option.id;
            return (
              <MenuItem key={option.id ?? 'none'} onSelect={() => onSetStatus(option.id)}>
                <option.Icon aria-hidden="true" className={`size-3.5 ${option.className}`} strokeWidth={2} />
                <span className="flex-1">{option.label}</span>
                {isActive ? <CheckCircle2 aria-hidden="true" className="size-3 text-foreground" /> : null}
              </MenuItem>
            );
          })}
        </MenuSubContent>
      </MenuSub>

      <MenuSub>
        <MenuSubTrigger>
          <Tag aria-hidden="true" className="size-3.5" />
          <span className="flex-1">Labels</span>
        </MenuSubTrigger>
        <MenuSubContent>
          {NAV_CHATS_LABELS.map((label) => {
            const isApplied = appliedLabelIds.includes(label.id);
            return (
              <MenuItem key={label.id} onSelect={() => onToggleLabel(label.id)}>
                <span
                  aria-hidden="true"
                  className="inline-block size-2 rounded-full"
                  style={{ backgroundColor: label.color }}
                />
                <span className="flex-1">{label.name}</span>
                {isApplied ? <CheckCircle2 aria-hidden="true" className="size-3 text-foreground" /> : null}
              </MenuItem>
            );
          })}
        </MenuSubContent>
      </MenuSub>

      <MenuItem onSelect={onFlag}>
        <Flag aria-hidden="true" className="size-3.5 text-info" fill={isFlagged ? 'currentColor' : 'none'} />
        <span className="flex-1">{isFlagged ? 'Unflag' : 'Flag'}</span>
        <DropdownMenuShortcut>⇧F</DropdownMenuShortcut>
      </MenuItem>

      <MenuItem onSelect={onMarkUnread}>
        <MailOpen aria-hidden="true" className="size-3.5" />
        <span className="flex-1">{isUnread ? 'Mark as Read' : 'Mark as Unread'}</span>
        <DropdownMenuShortcut>⇧U</DropdownMenuShortcut>
      </MenuItem>

      <MenuSeparator />

      <MenuItem onSelect={onRename}>
        <Pencil aria-hidden="true" className="size-3.5" />
        <span className="flex-1">Rename</span>
        <DropdownMenuShortcut>F2</DropdownMenuShortcut>
      </MenuItem>

      <MenuItem onSelect={onArchive}>
        <Archive aria-hidden="true" className="size-3.5" />
        <span className="flex-1">{isArchived ? 'Unarchive' : 'Archive'}</span>
        <DropdownMenuShortcut>E</DropdownMenuShortcut>
      </MenuItem>

      <MenuSub>
        <MenuSubTrigger>
          <MoreHorizontal aria-hidden="true" className="size-3.5" />
          <span className="flex-1">More</span>
        </MenuSubTrigger>
        <MenuSubContent>
          <MenuItem onSelect={onRegenerateTitle}>
            <RefreshCw aria-hidden="true" className="size-3.5" />
            <span className="flex-1">Regenerate Title</span>
          </MenuItem>
          <MenuItem onSelect={handleOpenNewWindow}>
            <AppWindow aria-hidden="true" className="size-3.5" />
            <span className="flex-1">Open in New Window</span>
          </MenuItem>
          <MenuItem onSelect={handleCopyLink}>
            <Copy aria-hidden="true" className="size-3.5" />
            <span className="flex-1">Copy Link</span>
          </MenuItem>
          <MenuItem onSelect={onExportMarkdown}>
            <FileText aria-hidden="true" className="size-3.5" />
            <span className="flex-1">Export as Markdown</span>
          </MenuItem>
          <MenuItem onSelect={handleDuplicate}>
            <Files aria-hidden="true" className="size-3.5" />
            <span className="flex-1">Duplicate</span>
          </MenuItem>
        </MenuSubContent>
      </MenuSub>

      <MenuSeparator />

      <MenuItem onSelect={onDelete} variant="destructive">
        <Trash2 aria-hidden="true" className="size-3.5" />
        <span className="flex-1">Delete</span>
        <DropdownMenuShortcut>⌫</DropdownMenuShortcut>
      </MenuItem>
    </>
  );
}

/**
 * Pure presentation layer for a single conversation sidebar row.
 *
 * Renders an `EntityRow` with a status glyph (filled, colored when set), the
 * conversation title (bolder when unread), the optional unread chat-bubble
 * glyph + age in the trailing area, and the two-tier dropdown / context menu.
 * All route-derived state (isSelected, href) comes from the container.
 */
export function ConversationSidebarItemView({
  title,
  state,
  age,
  href,
  absoluteHref,
  status,
  appliedLabelIds,
  onClick,
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
  onMouseDown,
  onClickMenuItem,
  buttonProps,
  conversationId,
}: ConversationSidebarItemViewProps): React.JSX.Element {
  const { isArchived, isFlagged, isInMultiSelect, isSelected, isUnread, showSeparator } = state;
  const handleMenuNavigate = (): void => {
    if (onClickMenuItem) {
      onClickMenuItem();
      return;
    }
    onNavigate(href);
  };

  const hasTrailing = Boolean(titleTrailing) || Boolean(badges) || Boolean(age);
  const resolvedTrailing = useMemo(
    () =>
      hasTrailing ? (
        <div className="flex items-center gap-1.5">
          {titleTrailing}
          {badges}
          {age ? <span className="whitespace-nowrap text-foreground/40 text-sm">{age}</span> : null}
        </div>
      ) : undefined,
    [hasTrailing, titleTrailing, badges, age]
  );

  // Unread = bolder title weight. The unread glyph itself is hoisted to the
  // LEFT of the title (see the `title` prop below) instead of the trailing
  // area so it pushes the title rightward — matches the requested Stitch
  // reference. EntityRow only takes a single class for the title, so the
  // weight modifier is merged here rather than added as a separate prop.
  const titleClassName = isUnread ? 'text-[14px] font-semibold text-foreground' : 'text-[14px]';

  const resolvedTitle = isUnread ? (
    <span className="inline-flex min-w-0 items-center gap-1.5">
      <ConversationUnreadGlyph />
      <span className="min-w-0 truncate">{title}</span>
    </span>
  ) : (
    title
  );

  const conversationMenu = (
    <ConversationMenuContent
      absoluteHref={absoluteHref}
      appliedLabelIds={appliedLabelIds}
      href={href}
      isArchived={isArchived}
      isFlagged={isFlagged}
      isUnread={isUnread}
      onArchive={onArchive}
      onDelete={onDelete}
      onExportMarkdown={onExportMarkdown}
      onFlag={onFlag}
      onMarkUnread={onMarkUnread}
      onNavigate={handleMenuNavigate}
      onRegenerateTitle={onRegenerateTitle}
      onRename={onRename}
      onSetStatus={onSetStatus}
      onToggleLabel={onToggleLabel}
      status={status}
    />
  );

  return (
    <SidebarMenuItem>
      <EntityRow
        buttonProps={buttonProps}
        icon={icon ?? <ConversationStatusGlyph status={status} />}
        menuContent={conversationMenu}
        onClick={onClick}
        onDragStart={(event) => {
          if (!conversationId) return;
          event.dataTransfer.effectAllowed = 'move';
          event.dataTransfer.setData(CONVERSATION_DRAG_MIME, conversationId);
        }}
        onMouseDown={onMouseDown}
        state={{
          isDraggable: Boolean(conversationId),
          isInMultiSelect,
          isSelected,
          showSeparator,
        }}
        title={resolvedTitle}
        titleClassName={titleClassName}
        titleTrailing={resolvedTrailing}
      />
    </SidebarMenuItem>
  );
}
