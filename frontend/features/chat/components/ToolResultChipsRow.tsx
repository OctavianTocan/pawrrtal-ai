'use client';

import { CalendarIcon, FileTextIcon } from 'lucide-react';
import Image from 'next/image';
import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { MAX_VISIBLE_RESULTS } from '../thinking-constants';
import type { CalendarEventInfo, MemoryResultInfo, ToolResultChips, WebSourceInfo } from '../tool-result-parsers';

/** Common visual treatment shared by every chip flavour. */
const CHIP_CLASS = cn(
  'inline-flex max-w-[180px] items-center gap-1.5 truncate rounded-full',
  'border border-border bg-background px-2 py-0.5 text-foreground/80 text-xs',
  'transition-colors hover:bg-muted/60'
);

/** A single web result chip (favicon + hostname). */
function WebChip({ source }: { source: WebSourceInfo }): ReactNode {
  const label = source.title ?? source.siteName;
  return (
    <a className={CHIP_CLASS} href={source.url} rel="noopener noreferrer" target="_blank" title={label}>
      {source.faviconUrl ? (
        <Image
          alt=""
          className="size-3.5 shrink-0 rounded-sm"
          height={14}
          loading="lazy"
          src={source.faviconUrl}
          unoptimized
          width={14}
        />
      ) : null}
      <span className="truncate">{label}</span>
    </a>
  );
}

/** A single calendar event chip. */
function CalendarChip({ event }: { event: CalendarEventInfo }): ReactNode {
  const child = (
    <>
      <CalendarIcon className="size-3.5 shrink-0 text-muted-foreground" />
      <span className="truncate">{event.summary}</span>
    </>
  );
  if (event.htmlLink) {
    return (
      <a className={CHIP_CLASS} href={event.htmlLink} rel="noopener noreferrer" target="_blank" title={event.summary}>
        {child}
      </a>
    );
  }
  return (
    <span className={CHIP_CLASS} title={event.summary}>
      {child}
    </span>
  );
}

/** A single memory / chat-history chip. */
function MemoryChip({ memory }: { memory: MemoryResultInfo }): ReactNode {
  return (
    <span className={CHIP_CLASS} title={memory.title}>
      <FileTextIcon className="size-3.5 shrink-0 text-muted-foreground" />
      <span className="truncate">{memory.title}</span>
    </span>
  );
}

/**
 * Compact row of source chips shown beneath a completed tool step.
 *
 * Caps the visible chip count at {@link MAX_VISIBLE_RESULTS} and adds a
 * `+N more` overflow chip so a noisy web search doesn't push the chat layout
 * around. Returns `null` when no chips exist so callers can render the row
 * unconditionally.
 */
export function ToolResultChipsRow({ chips }: { chips: ToolResultChips }): ReactNode {
  const total = chips.webSources.length + chips.calendarEvents.length + chips.memoryResults.length;
  if (total === 0) return null;

  const visibleWeb = chips.webSources.slice(0, MAX_VISIBLE_RESULTS);
  const remainingBudget = Math.max(0, MAX_VISIBLE_RESULTS - visibleWeb.length);
  const visibleCalendar = chips.calendarEvents.slice(0, remainingBudget);
  const remainingAfterCalendar = Math.max(0, remainingBudget - visibleCalendar.length);
  const visibleMemory = chips.memoryResults.slice(0, remainingAfterCalendar);
  const overflow = total - (visibleWeb.length + visibleCalendar.length + visibleMemory.length);

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {visibleWeb.map((source) => (
        <WebChip key={source.id} source={source} />
      ))}
      {visibleCalendar.map((event) => (
        <CalendarChip event={event} key={event.eventId} />
      ))}
      {visibleMemory.map((memory) => (
        <MemoryChip key={memory.meetingId} memory={memory} />
      ))}
      {overflow > 0 ? <span className={cn(CHIP_CLASS, 'text-muted-foreground')}>+{overflow} more</span> : null}
    </div>
  );
}
