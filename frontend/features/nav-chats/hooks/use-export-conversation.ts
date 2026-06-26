'use client';

import { useCallback } from 'react';
import { useAuthedFetch } from '@/hooks/use-authed-fetch';
import { API_ENDPOINTS } from '@/lib/api';
import { TOAST_IDS, toast } from '@/lib/toast';
import type { Conversation } from '@/lib/types';

/** Minimal message shape consumed by the markdown serializer. */
interface ExportableMessage {
  role: string;
  content: string;
}

/**
 * Serializes a conversation + its messages to a Markdown string.
 *
 * Keeps the layout deliberately simple — H1 title, ISO timestamp meta line,
 * then `**You**` / `**Assistant**` labelled blocks. No attempt is made to
 * render thinking blocks or tool calls; this is the "save as text" path,
 * not a full transcript export.
 */
function serializeConversationToMarkdown(conversation: Conversation, messages: ExportableMessage[]): string {
  const lines: string[] = [];
  lines.push(`# ${conversation.title}`);
  lines.push('');
  lines.push(`*Exported ${new Date().toISOString()}*`);
  lines.push('');
  lines.push('---');
  lines.push('');

  for (const message of messages) {
    const speaker = message.role === 'user' ? '**You**' : '**Assistant**';
    lines.push(speaker);
    lines.push('');
    lines.push(message.content.trim() || '_(empty)_');
    lines.push('');
  }

  return lines.join('\n');
}

/**
 * Slugifies a conversation title into a filesystem-friendly file name stem.
 * Falls back to `conversation-${id}` when the title yields an empty slug.
 */
function buildExportFilename(conversation: Conversation): string {
  const stem = conversation.title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60);
  const safeStem = stem.length > 0 ? stem : `conversation-${conversation.id.slice(0, 8)}`;
  return `${safeStem}.md`;
}

/**
 * Triggers a browser download of the given Markdown content.
 *
 * Uses a detached `<a>` (never inserted into the live DOM) so the click
 * doesn't mutate document.body — appending + removing during the click
 * was triggering a chat re-render that briefly blanked the visible
 * message stream while the download finalised. The blob URL is revoked
 * on the next macrotask so the browser has time to finish issuing the
 * download before the URL is torn down.
 */
function downloadMarkdown(filename: string, body: string): void {
  if (typeof window === 'undefined') return;
  const blob = new Blob([body], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = 'noopener';
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

/** Result type for {@link useExportConversation}. */
export interface UseExportConversationResult {
  /**
   * Fetch the conversation's messages and trigger a markdown download.
   *
   * Toasts "Preparing export..." up-front and either "Exported as Markdown"
   * or "Could not export conversation" on completion. Failure keeps the
   * row state untouched — no destructive side effect.
   */
  exportAsMarkdown: (conversation: Conversation) => Promise<void>;
}

/**
 * Hook that builds + delivers a markdown file for a single conversation.
 *
 * Pure-frontend: re-fetches messages via the existing
 * `GET /api/v1/conversations/{id}/messages` endpoint and writes a Blob via
 * an `<a download>`. No backend additions required.
 */
export function useExportConversation(): UseExportConversationResult {
  const fetcher = useAuthedFetch();

  const exportAsMarkdown = useCallback(
    async (conversation: Conversation): Promise<void> => {
      toast.loading('Preparing export...', { id: TOAST_IDS.conversationExport });
      try {
        const response = await fetcher(API_ENDPOINTS.conversations.getMessages(conversation.id));
        const messages = (await response.json()) as ExportableMessage[];
        const body = serializeConversationToMarkdown(conversation, messages);
        downloadMarkdown(buildExportFilename(conversation), body);
        toast.success('Exported as Markdown', { id: TOAST_IDS.conversationExport });
      } catch {
        toast.error('Could not export conversation', { id: TOAST_IDS.conversationExport });
      }
    },
    [fetcher]
  );

  return { exportAsMarkdown };
}
