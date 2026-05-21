/**
 * Discriminated SSE event shapes and rich message types for the chat feature.
 *
 * @fileoverview The backend `/api/v1/chat` endpoint emits five event kinds
 * over Server-Sent Events: `delta`, `thinking`, `tool_use`, `tool_result`,
 * and `error`. The transport (`useChat`) turns each frame into a
 * {@link ChatStreamEvent}; the container collapses the stream into a
 * {@link import('@/lib/types').ChatMessage} that the UI can render —
 * reasoning panel above the body, chronologically-ordered tool rows, source
 * chips, and a reply-action toolbar.
 *
 * The generic message-shape types (`ChatToolCallBase`, `ChatTimelineEntry`,
 * `AssistantMessageStatus`, `ChatArtifactPayload`, `ChatToolCallStatus`)
 * live in `@/lib/types` so the chat layer doesn't sit above its own data
 * model. Feature code imports them directly from `@/lib/types`.
 */

import type { ChatArtifactPayload, ChatToolCallBase, ToolDisplayPayload } from '@/lib/types';
import type { CalendarEventInfo, MemoryResultInfo, WebSourceInfo } from './tool-result-parsers';

/** Plain text chunk from the assistant's main response. */
export interface ChatDeltaEvent {
	type: 'delta';
	content: string;
}

/** Reasoning / thinking chunk emitted before (or alongside) the answer. */
export interface ChatThinkingEvent {
	type: 'thinking';
	content: string;
}

/** Assistant invoking a tool. */
export interface ChatToolUseEvent {
	type: 'tool_use';
	tool_use_id: string;
	name: string;
	input: Record<string, unknown>;
	display?: ToolDisplayPayload;
}

/** Result returned for a previously emitted tool use. */
export interface ChatToolResultEvent {
	type: 'tool_result';
	tool_use_id: string;
	content: string;
}

/** Backend-surfaced stream-level error (provider failure, rate limit, etc.). */
export interface ChatErrorEvent {
	type: 'error';
	content: string;
}

/**
 * Emitted when the agent safety layer terminates the loop early.
 *
 * Distinct from `error` — this is a controlled stop (hit an iteration cap,
 * wall-clock budget, or consecutive-error threshold) rather than an
 * unexpected failure. The `content` field carries a human-readable
 * explanation of why the agent stopped.
 */
export interface ChatAgentTerminatedEvent {
	type: 'agent_terminated';
	content: string;
}

/** Sibling event emitted whenever the agent calls `render_artifact`. */
export interface ChatArtifactEvent {
	type: 'artifact';
	artifact: ChatArtifactPayload;
}

/** Discriminated union of every event the backend chat stream can emit. */
export type ChatStreamEvent =
	| ChatDeltaEvent
	| ChatThinkingEvent
	| ChatToolUseEvent
	| ChatToolResultEvent
	| ChatArtifactEvent
	| ChatErrorEvent
	| ChatAgentTerminatedEvent;

/**
 * A tool invocation captured during streaming, enriched with pre-parsed
 * source chips so the renderer doesn't reparse `result` on every frame.
 *
 * Extends the transport-level {@link ChatToolCallBase} from `@/lib/types`
 * — assignable into `AgnoMessage.tool_calls` (which uses the base type)
 * while the chat reducer and renderer keep using the richer fields.
 */
export interface ChatToolCall extends ChatToolCallBase {
	/** Web result chips parsed from `result` for `web_search`. */
	webSources?: WebSourceInfo[];
	/** Calendar event chips parsed from `result` for `calendar_search`. */
	calendarEvents?: CalendarEventInfo[];
	/** Memory chips parsed from `result` for memory-flavoured tools. */
	memoryResults?: MemoryResultInfo[];
}
