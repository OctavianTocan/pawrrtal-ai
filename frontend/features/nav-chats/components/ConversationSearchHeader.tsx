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
		<div className="shrink-0 px-2 pt-1 pb-1.5 border-b border-border/50">
			<div className="relative rounded-soft shadow-minimal bg-muted/50 has-[:focus-visible]:bg-background">
				<Search className="absolute left-2.5 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground" />
				<input
					aria-label="Search conversations"
					type="text"
					value={searchQuery}
					onChange={(event) => onSearchChange(event.target.value)}
					placeholder="Search conversation titles..."
					className="w-full h-8 pl-8 pr-8 text-sm bg-transparent border-0 rounded-soft outline-none focus-visible:ring-0 focus-visible:outline-none placeholder:text-muted-foreground/50"
				/>
				{searchQuery ? (
					<button
						type="button"
						onClick={onSearchClose}
						className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 hover:bg-foreground/10 rounded cursor-pointer"
						title="Clear search"
						aria-label="Clear search"
					>
						<X className="size-3.5 text-muted-foreground" />
					</button>
				) : null}
			</div>

			{isSearchActive ? (
				<div className="px-2 pt-2.5 flex items-center gap-1.5 text-xs text-muted-foreground">
					<span>{resultCount} results</span>
				</div>
			) : null}
		</div>
	);
}
