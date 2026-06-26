'use client';

/**
 * Vertical list of memory category cards rendered inside the Memory
 * sub-view's middle column.
 *
 * Each card is a tap target with a 40px tinted circular icon on the left,
 * a bold title, and a one-line description below. Tones map to the
 * project's semantic tokens (info / success / accent / destructive /
 * neutral foreground) so we never introduce literal palette colors.
 */

import {
  BookOpenIcon,
  BrainIcon,
  HistoryIcon,
  type LucideIcon,
  ShieldIcon,
  SparklesIcon,
  UserIcon,
  UsersIcon,
  WrenchIcon,
} from 'lucide-react';
import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';
import type { MemoryCardData, MemoryCardTone } from '../types';

const TONE_CLASSNAMES: Record<MemoryCardTone, string> = {
  info: 'bg-info/15 text-info-text',
  success: 'bg-success/15 text-success-text',
  accent: 'bg-accent/15 text-accent',
  destructive: 'bg-destructive/15 text-destructive-text',
  foreground: 'bg-foreground-10 text-muted-foreground',
};

/**
 * Lookup from card id to the icon used inside its tinted chip.
 *
 * Kept as a dictionary rather than baking the icon into `mock-data.ts` so
 * the data file stays free of React/Lucide imports — easier to migrate to
 * a server-fetched payload later.
 */
const ICON_BY_ID: Record<string, LucideIcon> = {
  preferences: SparklesIcon,
  rules: ShieldIcon,
  profile: UserIcon,
  tools: WrenchIcon,
  identity: BrainIcon,
  relationships: UsersIcon,
  activity: HistoryIcon,
};

interface MemoryCardListProps {
  cards: readonly MemoryCardData[];
}

/**
 * Pure presentation. Cards are not currently interactive — they'll wire
 * up to detail routes once a real Memory backend lands. Keeping them as
 * `<button>` so the eventual interaction is one prop swap away.
 */
export function MemoryCardList({ cards }: MemoryCardListProps): ReactNode {
  return (
    <ul className="flex flex-col gap-2 py-2">
      {cards.map((card) => {
        const Icon = ICON_BY_ID[card.id] ?? BookOpenIcon;
        return (
          <li key={card.id}>
            <button
              type="button"
              className="flex w-full cursor-pointer items-start gap-3 rounded-[10px] border border-border/60 bg-background p-3 text-left transition-colors duration-150 ease-out hover:bg-foreground-5"
            >
              <span
                className={cn(
                  'flex size-9 shrink-0 items-center justify-center rounded-full',
                  TONE_CLASSNAMES[card.tone]
                )}
              >
                <Icon aria-hidden="true" className="size-4" />
              </span>
              <span className="flex min-w-0 flex-1 flex-col gap-0.5 pt-0.5">
                <span className="truncate text-[13px] font-semibold text-foreground">{card.title}</span>
                <span className="line-clamp-2 text-[12px] leading-snug text-muted-foreground">{card.description}</span>
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
