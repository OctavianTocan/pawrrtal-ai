'use client';

import { Search, X } from 'lucide-react';

interface ConversationSearchHeaderProps {
  /** The current search input value. */
  searchQuery: string;
  /** Called with the new value on every keystroke. */
  onSearchChange: (query: string) => void;
  /** Called when the user clicks the "×" clear button. */
  onSearchClose: () => void;
  /** Total number of matching conversations (shown when search is active). */
  resultCount: number;
}

/**
 * Search bar for the conversation sidebar.
 *
 * Uses `rounded-soft` (8px) with the New Session row — between tight
 * `rounded-control` inputs (6px) and card-scale `rounded-surface-lg` (14px).
 *
 * Renders a text input with a search icon, an optional clear button,
 * and a result count badge that appears once the query reaches 2+ chars.
 */
export function ConversationSearchHeader({
  searchQuery,
  onSearchChange,
  onSearchClose,
  resultCount,
}: ConversationSearchHeaderProps): React.JSX.Element {
  const isSearchActive = searchQuery.trim().length >= 2;

  return (
    <div className="shrink-0 border-border/50 border-b px-2 pt-1 pb-1.5">
      <div className="relative rounded-soft bg-muted/50 shadow-minimal has-[:focus-visible]:bg-background">
        <Search className="absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <input
          aria-label="Search conversations"
          className="h-8 w-full rounded-soft border-0 bg-transparent pr-8 pl-8 text-sm outline-none placeholder:text-muted-foreground/50 focus-visible:outline-none focus-visible:ring-0"
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder="Search conversation titles..."
          type="text"
          value={searchQuery}
        />
        {searchQuery ? (
          <button
            aria-label="Clear search"
            className="absolute top-1/2 right-2 -translate-y-1/2 cursor-pointer rounded p-0.5 hover:bg-foreground/10"
            onClick={onSearchClose}
            title="Clear search"
            type="button"
          >
            <X className="size-3.5 text-muted-foreground" />
          </button>
        ) : null}
      </div>

      {isSearchActive ? (
        <div className="flex items-center gap-1.5 px-2 pt-2.5 text-muted-foreground text-xs">
          <span>{resultCount} results</span>
        </div>
      ) : null}
    </div>
  );
}
