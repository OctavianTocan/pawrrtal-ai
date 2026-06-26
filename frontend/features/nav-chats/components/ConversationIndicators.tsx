import { Circle, LoaderCircle, ShieldAlert } from 'lucide-react';
import type * as React from 'react';
import type { Conversation } from '@/lib/types';
import { cn } from '@/lib/utils';

/**
 * Renders status indicators for a conversation row: a base circle icon plus
 * contextual badges for loading, unread messages, pending plans, and
 * queued prompts. Secondary indicators animate in/out via width + opacity
 * transitions.
 */
export function ConversationIndicators({
  conversation,
  isProcessing,
}: {
  conversation: Conversation;
  isProcessing: boolean;
}): React.JSX.Element {
  const hasUnreadMeta = Boolean(conversation.has_unread_meta);
  const hasPlan = conversation.last_message_role === 'plan';
  const hasPendingPrompt = (conversation.pending_prompt_count ?? 0) > 0;

  return (
    <>
      <div className="flex items-center justify-center text-muted-foreground/75">
        <Circle aria-hidden="true" className="size-3.5" strokeWidth={1.5} />
      </div>
      <div
        className={cn(
          'flex items-center justify-center gap-1 overflow-hidden transition-[margin,opacity] duration-150 ease-out',
          isProcessing || hasUnreadMeta || hasPlan || hasPendingPrompt
            ? 'ml-0 opacity-100'
            : '!w-0 -ml-[10px] opacity-0'
        )}
      >
        {isProcessing ? <LoaderCircle aria-hidden="true" className="size-3.5 animate-spin text-[10px]" /> : null}
        {hasUnreadMeta ? <UnreadMetaGlyph /> : null}
        {hasPlan ? <PlanGlyph /> : null}
        {hasPendingPrompt ? <ShieldAlert aria-hidden="true" className="size-3.5 text-sky-500" /> : null}
      </div>
    </>
  );
}

/** Filled chat-bubble glyph used to mark a row with unread server-side meta. */
function UnreadMetaGlyph(): React.JSX.Element {
  return (
    <svg aria-hidden="true" className="size-3.5 text-accent" fill="currentColor" viewBox="0 0 25 24">
      <title>Unread</title>
      <g transform="translate(1.75, 0.78)">
        <path
          d="M11,22 C8,22 7.01,21.54 5.35,20.63 C4.86,21.05 4.29,21.39 3.65,21.63 C3.01,21.88 2.37,22 1.71,22 C1,22 1.34,21.95 1.23,21.84 C1.11,21.73 1.06,21 1.06,21.45 C1.06,21.29 1.14,21.13 1.28,20.98 C1.57,20.66 1.78,20.34 1,20.02 C2.03,19.69 2.09,19.31 2.09,18.87 C2.09,18.46 2.02,18.06 1.88,17.69 C1.74,17.33 1.57,16.94 1.36,16.53 C1.15,16.13 0.94,15.67 0.73,15.17 C0.52,14.66 0.35,14.07 0.21,13.39 C0.07,12.71 0,11.91 0,11 C0,9.41 0.27,7.94 0.81,6 C1.36,5.26 2.12,4.09 3.11,3 C4.09,2.12 5.26,1.35 6,0.81 C7.94,0.27 9,0 11,0 C12.59,0 14.05,0.27 15.39,0.81 C16.74,1.35 17,2.12 18.89,3 C19.88,4.09 20.64,5.26 21.19,6 C21.73,7.94 22,9.41 22,11 C22,12.59 21.73,14.06 21.19,15 C20.64,16.74 19.88,17.91 18.89,18 C17.91,19.88 16.74,20.65 15,21.19 C14.06,21.73 12.59,22 11,22 Z"
          fillRule="nonzero"
        />
      </g>
    </svg>
  );
}

/** Filled paper-airplane / compass glyph used when the latest message is a plan artifact. */
function PlanGlyph(): React.JSX.Element {
  return (
    <svg aria-hidden="true" className="size-3.5 text-success" fill="currentColor" viewBox="0 0 25 24">
      <title>Plan</title>
      <path
        d="M13.72,22.65 C13.26,22.65 12.94,22.49 12.73,22.16 C12.53,21.84 12.36,21.43 12.22,20.94 L10.66,15.79 C10.57,15.46 10.54,15 10.57,15 C10.59,14 10,14 10.89,14 L20.86,3.65 C20.92,3.59 20.95,3.52 20.95,3.45 C20.95,3.38 20.92,3.32 20.87,3.28 C20.82,3.23 20.76,3.21 20.69,3 C20.62,3 20.56,3.23 20,3.29 L9.79,13 C9.57,13.49 9.36,13 9.16,13.62 C8.96,13.65 8,13.61 8.39,13.51 L3.12,11.91 C2.65,11.77 2.26,11 1.95,11 C1.65,11 1.49,10.88 1.49,10.43 C1.49,10.07 1.63,9.77 1.91,9.52 C2.19,9.26 2.54,9.06 2.95,8 L19.75,2.47 C19.97,2.38 20.19,2.32 20.39,2.27 C20.58,2.22 20.76,2.19 20.93,2.19 C21.25,2.19 21,2.28 21.68,2.47 C21.86,2.65 21.95,2 21.95,3.22 C21.95,3.39 21.93,3.57 21.88,3.77 C21.83,3.96 21.76,4.17 21.68,4 L15.28,21.11 C15,21.58 14.88,21.95 14.63,22.23 C14.38,22.51 14.07,22.65 13.72,22.65 Z"
        fillRule="nonzero"
      />
    </svg>
  );
}
