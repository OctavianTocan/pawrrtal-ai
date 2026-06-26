'use client';

/**
 * SelectButton — a small DropdownMenu-driven picker that matches the
 * chat composer's model selector styling.
 *
 * Use this instead of a native `<select>` whenever you need a compact
 * "trigger → dropdown of options → pick one" control. The trigger is
 * a `Button` with the project's chat-composer chrome (subtle ghost
 * hover, no border, chevron on the right); the dropdown reuses
 * `chat-composer-dropdown-menu` so the popover skin stays consistent
 * with the model picker.
 *
 * Built on `@octavian-tocan/react-dropdown` (the vendored package). The
 * `asChild` prop lets the consumer's `<Button>` be the actual trigger
 * element so inline-flex layouts and ARIA semantics are preserved.
 */

import { DropdownMenu } from '@octavian-tocan/react-dropdown';
import { CheckIcon, ChevronDownIcon } from 'lucide-react';
import type * as React from 'react';
import { Button } from '@/components/ui/button';
import { usePointerDownCommit } from '@/hooks/use-pointer-down-commit';
import { cn } from '@/lib/utils';

/** A single picker option. `id` is what gets passed to `onSelect`. */
export interface SelectButtonOption {
  id: string;
  label: React.ReactNode;
  /** Optional secondary line under the label (small, muted). */
  description?: React.ReactNode;
  /** Optional left-side leading visual (icon, swatch, avatar). */
  leading?: React.ReactNode;
}

export interface SelectButtonProps {
  /** Accessible name for the trigger button. */
  ariaLabel: string;
  /** Trigger label — usually the active option's name or a placeholder. */
  triggerLabel: React.ReactNode;
  /** Trigger leading visual — small swatch, icon, etc. */
  triggerLeading?: React.ReactNode;
  /** Options listed in the dropdown. */
  options: readonly SelectButtonOption[];
  /** Called with the chosen option's id when the user picks one. */
  onSelect: (id: string) => void;
  /** Currently-active option id (renders a subtle indicator on the row). */
  activeId?: string | null;
  /** Override classes on the trigger button. */
  className?: string;
}

/** Display label fallback used by the keyboard type-ahead. */
function displayFor(option: SelectButtonOption): string {
  return typeof option.label === 'string' ? option.label : option.id;
}

interface SelectButtonRowProps {
  option: SelectButtonOption;
  isActive: boolean;
  onSelect: (option: SelectButtonOption) => void;
}

/** Single selectable option row for {@link SelectButton}. */
function SelectButtonRow({ option, isActive, onSelect }: SelectButtonRowProps): React.JSX.Element {
  const commitSelection = usePointerDownCommit<HTMLButtonElement>(() => onSelect(option));

  return (
    <button
      type="button"
      className={cn(
        // Compact-but-readable Codex rhythm: ~36 px tall rows
        // (py-2 + line-height) with a slightly chunkier corner
        // radius so the hover/active fill reads as its own pill
        // rather than a thin highlight strip.
        'flex w-full cursor-pointer items-center gap-2.5 rounded-[8px] px-3 py-2 text-sm hover:bg-foreground/[0.04]',
        isActive && 'bg-foreground/[0.06]'
      )}
      onClick={commitSelection.onClick}
      onPointerDown={commitSelection.onPointerDown}
    >
      {option.leading ? (
        <span aria-hidden="true" className="flex items-center">
          {option.leading}
        </span>
      ) : null}
      <div className="flex min-w-0 flex-1 flex-col text-left">
        <span className="truncate text-sm text-foreground">{option.label}</span>
        {option.description ? (
          <span className="truncate text-pretty text-xs text-muted-foreground">{option.description}</span>
        ) : null}
      </div>
      {isActive ? <CheckIcon aria-hidden="true" className="size-3.5 shrink-0 text-foreground" /> : null}
    </button>
  );
}

/**
 * DropdownMenu-driven select button.
 *
 * The trigger styling mirrors the model selector in
 * `features/chat/components/ModelSelectorPopover.tsx` (rounded-[7px],
 * ghost variant, chevron). The popover uses `chat-composer-dropdown-menu`
 * so backgrounds, borders, and shadows stay consistent.
 */
export function SelectButton({
  ariaLabel,
  triggerLabel,
  triggerLeading,
  options,
  onSelect,
  activeId,
  className,
}: SelectButtonProps): React.JSX.Element {
  return (
    <DropdownMenu<SelectButtonOption>
      asChild
      usePortal
      align="start"
      placement="bottom"
      items={options}
      getItemKey={(option) => option.id}
      getItemDisplay={displayFor}
      onSelect={(option) => onSelect(option.id)}
      contentClassName="chat-composer-dropdown-menu popover-styled p-1.5 min-w-56"
      trigger={
        <Button
          aria-label={ariaLabel}
          className={cn(
            'h-8 gap-1.5 rounded-[7px] border-0 bg-foreground/[0.04] px-2.5 text-xs font-medium text-foreground',
            'hover:bg-foreground/[0.08] data-[state=open]:bg-foreground/[0.10]',
            'transition-colors duration-150 ease-out',
            className
          )}
          size="xs"
          type="button"
          variant="ghost"
        >
          {triggerLeading ? <span className="flex items-center">{triggerLeading}</span> : null}
          <span className="truncate">{triggerLabel}</span>
          <ChevronDownIcon aria-hidden="true" className="size-3 text-muted-foreground" />
        </Button>
      }
      renderItem={(option, _isSelected, onItemSelect) => {
        const isActive = activeId === option.id;
        return <SelectButtonRow isActive={isActive} onSelect={onItemSelect} option={option} />;
      }}
    />
  );
}
