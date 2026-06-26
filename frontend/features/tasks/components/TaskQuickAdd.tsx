'use client';

/**
 * Inline "add a task" composer rendered above the section list.
 *
 * Mock-only — pressing Enter or clicking the plus does nothing more than
 * clear the input and surface a tiny success ping. The container will
 * eventually wire `onAdd` to a real mutation.
 */

import { PlusIcon } from 'lucide-react';
import { type FormEvent, type ReactNode, useState } from 'react';
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
      onSubmit={handleSubmit}
      className={cn(
        'group/quick-add flex items-center gap-2 rounded-md border border-foreground/[0.08] bg-background px-3 py-2.5 transition-colors duration-150 ease-out',
        'focus-within:border-foreground/30 hover:border-foreground/15'
      )}
    >
      <span
        className={cn(
          'flex size-5 items-center justify-center rounded-full border border-dashed border-foreground/30 text-muted-foreground transition-colors duration-150 ease-out',
          trimmed && 'border-solid border-accent text-accent'
        )}
      >
        <PlusIcon aria-hidden="true" className="size-3" strokeWidth={2.5} />
      </span>
      <input
        aria-label="Add a task"
        type="text"
        value={value}
        onChange={(event) => setValue(event.target.value)}
        placeholder="Add a task to today..."
        className="h-6 min-w-0 flex-1 bg-transparent text-[13px] text-foreground outline-none placeholder:text-muted-foreground"
      />
      <span className="hidden text-[11px] font-medium tracking-tight text-muted-foreground/70 sm:inline">
        Press Enter to add
      </span>
    </form>
  );
}
