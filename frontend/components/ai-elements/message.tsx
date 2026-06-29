/**
 * User and assistant message row with content subcomponents.
 *
 * @fileoverview AI Elements — `message`.
 */

'use client';

import type { UIMessage } from 'ai';
import type { ComponentProps, HTMLAttributes } from 'react';
import { memo } from 'react';
import { Streamdown } from 'streamdown';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

export type MessageProps = HTMLAttributes<HTMLDivElement> & {
  from: UIMessage['role'];
};

export const Message = ({ className, from, ...props }: MessageProps) => (
  <div
    className={cn(
      'group flex w-full flex-col gap-2',
      from === 'user' ? 'is-user ml-auto max-w-[80%] justify-end' : 'is-assistant max-w-full',
      className
    )}
    {...props}
  />
);

export type MessageContentProps = HTMLAttributes<HTMLDivElement>;

export const MessageContent = ({ children, className, ...props }: MessageContentProps) => (
  <div
    className={cn(
      // Base sizing flows from the design system (`--font-size-base` = 16px,
      // surfaced as `text-base`). `leading-relaxed` matches the body rhythm.
      // `gap-[13px]` (13px) keeps inter-block rhythm (thinking header → reasoning →
      // response) at a tighter beat than the previous 16px. Adjacent paragraph
      'is-user:dark flex w-fit min-w-0 max-w-full flex-col gap-[13px] overflow-hidden text-base leading-relaxed',
      // User bubble: asymmetric "tail" radii driven by the design-token
      // pair `--radius-bubble` / `--radius-bubble-tail`. The global
      // `--radius` is 0 so the standard `rounded-*` scale is no-op here —
      // this is the project's bubble token by design.
      // `rounded-br` keeps the bottom-right (outer) corner sharp; a ::before
      // pseudo-element extends a triangular tail pointing right toward the avatar.
      'group-[.is-user]:relative group-[.is-user]:ml-auto group-[.is-user]:rounded-[var(--radius-bubble)] group-[.is-user]:rounded-br-[var(--radius-bubble-tail)]',
      'group-[.is-user]:bg-user-message-bubble group-[.is-user]:px-4 group-[.is-user]:py-3 group-[.is-assistant]:text-assistant-message-text group-[.is-user]:text-user-message-foreground',
      'group-[.is-user]:before:absolute group-[.is-user]:before:right-[calc(100%-18px)] group-[.is-user]:before:bottom-[2px]',
      'group-[.is-user]:before:size-0 group-[.is-user]:before:border-t-[7px] group-[.is-user]:before:border-l-[9px]',
      'group-[.is-user]:before:border-t-transparent group-[.is-user]:before:border-l-user-message-bubble',
      className
    )}
    {...props}
  >
    {children}
  </div>
);

export type MessageActionsProps = ComponentProps<'div'>;

export const MessageActions = ({ className, children, ...props }: MessageActionsProps) => (
  <div className={cn('flex items-center gap-1', className)} {...props}>
    {children}
  </div>
);

export type MessageActionProps = ComponentProps<typeof Button> & {
  tooltip?: string;
  label?: string;
};

export const MessageAction = ({
  tooltip,
  children,
  label,
  variant = 'ghost',
  size = 'icon-sm',
  ...props
}: MessageActionProps) => {
  const button = (
    <Button size={size} type="button" variant={variant} {...props}>
      {children}
      <span className="sr-only">{label || tooltip}</span>
    </Button>
  );

  if (tooltip) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>{button}</TooltipTrigger>
          <TooltipContent>
            <p>{tooltip}</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  return button;
};

export type MessageResponseProps = ComponentProps<typeof Streamdown>;

export const MessageResponse = memo(
  ({ className, ...props }: MessageResponseProps) => (
    <Streamdown
      className={cn(
        // Base flow.
        'chat-message-response size-full text-inherit text-sm leading-relaxed [&_*]:text-inherit',
        // Reset edge margins so the bubble hugs content.
        '[&>*:first-child]:mt-0 [&>*:last-child]:mb-0',
        // Vertical rhythm — `my-4` = 16px under the project's
        // `--font-size-base = 16px`. Adjacent paragraph margins collapse
        // to the larger value, so two consecutive paragraphs render with a
        // 16px gap between them, matching the inter-block rhythm in
        // `MessageContent`. Tailwind spacing scale only, all wired to
        // project tokens in globals.css.
        '[&_p]:my-4 [&_p]:text-sm [&_p]:leading-normal',
        '[&_li]:my-0.5 [&_li]:leading-normal [&_ol]:my-4 [&_ul]:my-4',
        // Pull nested paragraphs (e.g. inside list items) flush so each
        // bullet sits as one tight unit instead of acquiring my-4 again.
        '[&_li_p]:my-0',
        '[&_ol]:list-decimal [&_ol]:pl-6 [&_ul]:list-disc [&_ul]:pl-6',
        // Headings: text-lg / text-base / text-base = 18 / 16 / 16px under
        // the project's `--font-size-base = 16px`. Weight = semibold.
        // Heading margins collapse with adjacent paragraph `my-4` (16px)
        // so heading-to-paragraph gaps land at exactly 16px in either
        // direction.
        '[&_h1]:mt-4 [&_h1]:mb-2 [&_h1]:font-semibold [&_h1]:text-lg',
        '[&_h2]:mt-4 [&_h2]:mb-1.5 [&_h2]:font-semibold [&_h2]:text-base',
        '[&_h3]:mt-3 [&_h3]:mb-1.5 [&_h3]:font-semibold [&_h3]:text-base',
        '[&_strong]:font-semibold',
        '[&_button]:cursor-pointer',
        // Inline code: muted surface + mono font from the design-system stack.
        // Held one notch below body (text-sm = 14px) so monospace doesn't
        // bloom against proportional body type.
        '[&_code]:rounded-sm [&_code]:bg-muted [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-sm',
        className
      )}
      {...props}
    />
  ),
  (prevProps, nextProps) => prevProps.children === nextProps.children
);

MessageResponse.displayName = 'MessageResponse';
