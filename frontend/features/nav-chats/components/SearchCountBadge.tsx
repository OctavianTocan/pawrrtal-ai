import type * as React from 'react';
import { cn } from '@/lib/utils';

/** Small pill showing the number of search matches found in a conversation's history. */
export function SearchCountBadge({ count, isSelected }: { count: number; isSelected: boolean }): React.JSX.Element {
  return (
    <span
      className={cn(
        'inline-flex min-w-[24px] items-center justify-center whitespace-nowrap rounded-[6px] px-1 py-0.5 text-[10px] font-medium leading-tight tabular-nums shadow-tinted',
        isSelected
          ? 'border border-yellow-500 bg-yellow-300/50 text-yellow-900'
          : 'border border-yellow-600/20 bg-yellow-300/10 text-yellow-800'
      )}
      style={{
        ['--shadow-color' as string]: isSelected ? '234, 179, 8' : '133, 77, 14',
      }}
      title="Matches found"
    >
      {count}
    </span>
  );
}
