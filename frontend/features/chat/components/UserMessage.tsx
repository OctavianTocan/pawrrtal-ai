'use client';

import { CheckIcon, CopyIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import { Message, MessageContent, MessageResponse } from '@/components/ai-elements/message';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

/**
 * Props for {@link UserMessage}.
 */
export interface UserMessageProps {
  /** Plain-text user prompt — rendered through Streamdown for inline markdown. */
  content: string;
  /** Whether this row's copy button should currently render its "Copied!" state. */
  isCopied?: boolean;
  /** Copy the user message body to the clipboard. */
  onCopy?: () => void;
}

/**
 * User-side chat row with a hover-only copy button.
 *
 * The copy slot below the bubble is always mounted and always occupies its
 * 28px row of vertical space, so the surrounding layout never shifts when
 * the user moves their cursor over the message. Visibility is driven by an
 * opacity transition on the parent's `:hover` / `:focus-within` state — the
 * button is also keyboard-reachable via Tab.
 *
 * @returns The user message bubble plus its hover-revealed action row.
 */
export function UserMessage({ content, isCopied, onCopy }: UserMessageProps): ReactNode {
  return (
    <div className="group flex flex-col items-end">
      <Message from="user">
        <MessageContent>
          <MessageResponse>{content}</MessageResponse>
        </MessageContent>
      </Message>
      {onCopy ? (
        <div
          className={cn(
            // Always-mounted row so the next message's position never
            // shifts when the user hovers — only opacity transitions.
            'mt-1 flex h-8 items-center justify-end',
            'opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100'
          )}
        >
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                aria-label={isCopied ? 'Copied' : 'Copy message'}
                className="size-8 p-0 text-muted-foreground hover:bg-muted hover:text-foreground"
                onClick={onCopy}
                size="sm"
                type="button"
                variant="ghost"
              >
                {isCopied ? <CheckIcon className="size-4" /> : <CopyIcon className="size-4" />}
              </Button>
            </TooltipTrigger>
            <TooltipContent>{isCopied ? 'Copied' : 'Copy'}</TooltipContent>
          </Tooltip>
        </div>
      ) : null}
    </div>
  );
}
