'use client';

import { GitBranchIcon, GitPullRequestIcon, WorkflowIcon, XIcon } from 'lucide-react';
import type * as React from 'react';
import { useState } from 'react';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

/** Suggested empty-state prompts displayed below the chat composer. */
export const CHAT_PROMPT_SUGGESTIONS = [
	{
		id: 'review-commits',
		label: 'Review my recent commits for correctness risks and maintainability concerns',
		icon: GitPullRequestIcon,
	},
	{
		id: 'unblock-pr',
		label: 'Unblock my most recent open PR',
		icon: GitBranchIcon,
	},
	{
		id: 'connect-apps',
		label: 'Connect my favorite apps to Pawrrtal',
		icon: WorkflowIcon,
	},
] as const;

/** Props for the empty-state prompt suggestion list. */
export type ChatPromptSuggestionsProps = {
	/** Callback fired when a suggestion is selected. */
	onSelectSuggestion: (prompt: string) => void;
	/** Additional classes for the root list. */
	className?: string;
};

/**
 * Renders compact Codex-like suggested prompt rows for an empty conversation.
 */
export function ChatPromptSuggestions({
	onSelectSuggestion,
	className,
}: ChatPromptSuggestionsProps): React.JSX.Element {
	const [dismissedIds, setDismissedIds] = useState<ReadonlySet<string>>(() => new Set());

	const visibleSuggestions = CHAT_PROMPT_SUGGESTIONS.filter(
		(suggestion) => !dismissedIds.has(suggestion.id)
	);

	return (
		<div className={cn('w-full max-w-[48.75rem] hidden lg:flex', className)}>
			{visibleSuggestions.map((suggestion) => {
				const Icon = suggestion.icon;

				return (
					<div
						className="group/suggestion flex w-full items-stretch border-foreground/10 border-t first:border-t-0"
						key={suggestion.id}
					>
						<Tooltip>
							<TooltipTrigger asChild>
								<button
									className="flex min-w-0 flex-1 cursor-pointer items-center gap-2 bg-transparent p-3 text-left text-[13px] font-normal transition-colors hover:bg-transparent"
									onClick={() => onSelectSuggestion(suggestion.label)}
									type="button"
								>
									<Icon
										aria-hidden="true"
										className="size-4 shrink-0 text-muted-foreground"
									/>
									<span className="min-w-0 flex-1 truncate text-muted-foreground transition-colors group-hover/suggestion:text-foreground">
										{suggestion.label}
									</span>
								</button>
							</TooltipTrigger>
							<TooltipContent align="start" side="top">
								{suggestion.label}
							</TooltipContent>
						</Tooltip>
						<button
							aria-label={`Dismiss suggestion: ${suggestion.label}`}
							className="flex shrink-0 cursor-pointer items-center justify-center bg-transparent px-3 text-muted-foreground transition-colors hover:bg-transparent hover:text-foreground"
							onClick={() => {
								setDismissedIds((previous) => {
									const next = new Set(previous);
									next.add(suggestion.id);
									return next;
								});
							}}
							type="button"
						>
							<XIcon aria-hidden="true" className="size-4" />
						</button>
					</div>
				);
			})}
		</div>
	);
}
