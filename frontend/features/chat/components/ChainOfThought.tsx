'use client';

import { ChevronRightIcon } from 'lucide-react';
import { memo, type ReactNode, useMemo } from 'react';
import { Streamdown } from 'streamdown';
import { Shimmer } from '@/components/ai-elements/shimmer';
import { cn } from '@/lib/utils';
import { getCompletedToolLabel, getToolIcon, getToolLabel } from '../thinking-constants';
import { parseThinkingSections } from '../thinking-parser';
import type { ToolResultChips } from '../tool-result-parsers';
import type { ChatTimelineEntry, ChatToolCall } from '../types';
import { ToolResultChipsRow } from './ToolResultChipsRow';

/**
 * Hoverable row for a single tool invocation.
 *
 * Matches the Perplexity-style chain-of-thought aesthetic: leading tool
 * icon, compact label, trailing chevron — wrapped in a subtle hover
 * background. Active steps shimmer; completed steps render the same
 * row plus optional source chips below.
 */
function ToolStep({ call, chips }: { call: ChatToolCall; chips: ToolResultChips }): ReactNode {
	const Icon = getToolIcon(call.name);
	const isComplete = call.status === 'completed';
	const label = isComplete ? getCompletedToolLabel(call.name) : getToolLabel(call.name);

	return (
		<div className="flex flex-col">
			<div
				className={cn(
					'group flex items-center gap-2 rounded-md px-1.5 py-1 text-sm',
					'text-muted-foreground transition-colors hover:bg-muted/50'
				)}
			>
				<Icon aria-hidden="true" className="size-3.5 shrink-0 text-muted-foreground/80" />
				<span className="min-w-0 flex-1 truncate">
					{isComplete ? (
						<span className="text-foreground/85">{label}</span>
					) : (
						<Shimmer duration={1.2}>{label}</Shimmer>
					)}
				</span>
				<ChevronRightIcon
					aria-hidden="true"
					className={cn(
						'size-3.5 shrink-0 text-muted-foreground/60',
						'opacity-0 transition-opacity group-hover:opacity-100'
					)}
				/>
			</div>
			<ToolResultChipsRow chips={chips} />
		</div>
	);
}

/**
 * A single rendered thinking section: optional title, then markdown body.
 *
 * Sits flush with tool rows (no rail, no connector) — the muted typography
 * is what ties it to the surrounding chain. Headings are raised to
 * `text-foreground/85` so a Gemini-style `## Title` reads as a step
 * boundary without an extra divider.
 */
function ThinkingStep({ title, content }: { title: string; content: string }): ReactNode {
	return (
		<div className="flex flex-col gap-1 px-1.5 py-1 text-base leading-snug text-muted-foreground">
			{title ? <div className="font-medium text-foreground/85">{title}</div> : null}
			{content ? (
				// Streamdown renders each thinking line as its own <p>; default
				// prose margins (~1em top + 1em bottom) made the chain of
				// thought feel airy and disconnected. Collapse paragraph and
				// list margins to a tight 0.25rem so consecutive lines read
				// as one continuous reasoning block.
				<Streamdown
					className={cn(
						'text-base text-muted-foreground',
						'[&>*:first-child]:mt-0 [&>*:last-child]:mb-0',
						'[&_p]:my-1 [&_ul]:my-1 [&_ol]:my-1 [&_li]:my-0',
						'[&_p]:leading-snug'
					)}
				>
					{content}
				</Streamdown>
			) : null}
		</div>
	);
}

/**
 * Props for {@link ChainOfThought}.
 */
interface ChainOfThoughtProps {
	/** Arrival-ordered timeline of thinking bursts and tool invocations. */
	timeline: ChatTimelineEntry[];
	/** Tool calls indexed by id so the timeline can dereference each tool slot. */
	toolCallsById: Map<string, ChatToolCall>;
	/** Pre-parsed source chips per tool call id (web/calendar/memory). */
	chipsByToolId: Map<string, ToolResultChips>;
}

const EMPTY_CHIPS: ToolResultChips = {
	webSources: [],
	calendarEvents: [],
	memoryResults: [],
};

/**
 * Chronologically-ordered chain-of-thought renderer.
 *
 * Walks the message's `timeline` (arrival order of thinking bursts and tool
 * calls) so the user sees reasoning and tool steps interleaved exactly as
 * they happened. Each `thinking` slot is split into sub-sections by
 * {@link parseThinkingSections} so Gemini-style `## Title` headings turn
 * into individual rows.
 *
 * Layout follows Perplexity's chain-of-thought pattern: flat hoverable
 * rows, no vertical rail, tool icon + label + trailing chevron — keeps
 * the panel scannable without competing with the assistant's reply.
 */
export const ChainOfThought = memo(function ChainOfThought({
	timeline,
	toolCallsById,
	chipsByToolId,
}: ChainOfThoughtProps) {
	const items = useMemo(() => {
		type Item =
			| { kind: 'thinking'; title: string; content: string }
			| { kind: 'tool'; call: ChatToolCall; chips: ToolResultChips };
		const flat: Item[] = [];
		for (const entry of timeline) {
			if (entry.kind === 'thinking') {
				const sections = parseThinkingSections(entry.text);
				for (const section of sections) {
					flat.push({ kind: 'thinking', title: section.title, content: section.content });
				}
				continue;
			}
			const call = toolCallsById.get(entry.toolCallId);
			if (!call) continue;
			flat.push({
				kind: 'tool',
				call,
				chips: chipsByToolId.get(entry.toolCallId) ?? EMPTY_CHIPS,
			});
		}
		return flat;
	}, [timeline, toolCallsById, chipsByToolId]);

	if (items.length === 0) {
		return (
			<div
				className={cn('flex items-center gap-2 px-1.5 py-1 text-sm text-muted-foreground')}
			>
				<ChevronRightIcon aria-hidden="true" className="size-3.5" />
				<Shimmer duration={1.2}>Thinking&hellip;</Shimmer>
			</div>
		);
	}

	return (
		<div className="flex flex-col gap-0.5">
			{items.map((item) => {
				if (item.kind === 'tool') {
					return (
						<ToolStep
							call={item.call}
							chips={item.chips}
							key={`tool-${item.call.id}`}
						/>
					);
				}
				return (
					<ThinkingStep
						content={item.content}
						key={`thinking-${item.title}-${item.content.slice(0, 80)}`}
						title={item.title}
					/>
				);
			})}
		</div>
	);
});
