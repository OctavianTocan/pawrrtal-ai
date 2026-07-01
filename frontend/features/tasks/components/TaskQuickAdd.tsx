'use client';

/**
 * Inline "add a task" composer rendered above the section list.
 *
 * Mock-only — pressing Enter or clicking the plus does nothing more than
 * clear the input and surface a tiny success ping. The container will
 * eventually wire `onAdd` to a real mutation.
 */

import { PlusIcon } from 'lucide-react';
import type { FormEvent, ReactNode } from 'react';
import { useState } from 'react';
import { cn } from '@/lib/utils';

export interface TaskQuickAddProps {
  /** Mock add handler — receives the trimmed title only. */
  onAdd: (title: string) => void;
}

/**
 * Single input with a leading plus glyph. Stays decoupled from anything
 * upstream — the container can swap it for a richer modal without
 * touching the rest of the page.
 */
export function TaskQuickAdd({ onAdd }: TaskQuickAddProps): ReactNode {
  const [value, setValue] = useState('');
  const trimmed = value.trim();

  const handleSubmit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (!trimmed) return;
    onAdd(trimmed);
    setValue('');
  };

  return (
    <form
      className={cn(
        'group/quick-add flex items-center gap-2 rounded-md border border-foreground/[0.08] bg-background px-3 py-2.5 transition-colors duration-150 ease-out',
        'focus-within:border-foreground/30 hover:border-foreground/15'
      )}
      onSubmit={handleSubmit}
    >
      <span
        className={cn(
          'flex size-5 items-center justify-center rounded-full border border-foreground/30 border-dashed text-muted-foreground transition-colors duration-150 ease-out',
          trimmed && 'border-accent border-solid text-accent'
        )}
      >
        <PlusIcon aria-hidden="true" className="size-3" strokeWidth={2.5} />
      </span>
      <input
        aria-label="Add a task"
        className="h-6 min-w-0 flex-1 bg-transparent text-[13px] text-foreground outline-none placeholder:text-muted-foreground"
        onChange={(event) => setValue(event.target.value)}
        placeholder="Add a task to today..."
        type="text"
        value={value}
      />
      <span className="hidden font-medium text-[11px] text-muted-foreground/70 tracking-tight sm:inline">
        Press Enter to add
      </span>
    </form>
  );
}
