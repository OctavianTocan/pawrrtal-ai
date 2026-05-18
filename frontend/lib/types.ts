/**
 * Shared TypeScript type definitions for conversations, messages, and sidebar items.
 *
 * @fileoverview Types consumed by both the sidebar and the chat view. The
 * message-streaming types below (`ChatToolCallBase`, `ChatTimelineEntry`,
 * `AssistantMessageStatus`, `ChatArtifactPayload`) live here so that
 * `ChatMessage` can describe its streaming-only fields without `lib/`
 * reaching upward into `features/chat/`. Feature-internal extensions —
 * parsed source chips, json-render specs at runtime — stay in
 * `features/chat/types.ts` and extend these base types.
 */

/** The role of a message sender: human user, AI assistant, or a plan artifact. */
export type MessageRole = 'user' | 'assistant' | 'plan';

/** Lifecycle of an assistant turn — drives the failed-state UI. */
export type AssistantMessageStatus = 'streaming' | 'complete' | 'failed';

/** Lifecycle of a single tool invocation as observed from the SSE stream. */
export type ChatToolCallStatus = 'pending' | 'completed' | 'failed';

/** User-facing display metadata for a tool invocation. */
export interface ToolDisplayPayload {
	icon?: string;
	label?: string;
	present?: string;
	compact?: string;
	detail?: string;
}

/**
 * The transport-level shape of a tool invocation, without any parsed-source
 * denormalisations. `features/chat/types.ts` extends this with `webSources`
 * etc. for tool-specific chip rendering.
 */
export interface ChatToolCallBase {
	/** Stable id supplied by the backend (`tool_use.id`) — used to match results. */
	id: string;
	/** Tool name as declared by the assistant. */
	name: string;
	/** Input arguments the assistant passed to the tool. */
	input: Record<string, unknown>;
	/** Optional shared user-facing display metadata from the backend. */
	display?: ToolDisplayPayload;
	/** Tool result text (only present once the tool has finished). */
	result?: string;
	/** Whether the result has arrived yet. */
	status: ChatToolCallStatus;
}

/**
 * One slot in the chain-of-thought timeline.
 *
 * The container records every thinking burst and tool invocation in arrival
 * order so the chain-of-thought view can render them chronologically instead
 * of bucketing all thinking text above all tool steps.
 */
export type ChatTimelineEntry =
	| { kind: 'thinking'; text: string }
	| { kind: 'tool'; toolCallId: string };

/**
 * Submitted value of an interactive widget. String for text fields, an
 * array of selected option keys for multi-choice, and a number for sliders.
 */
export type ChatArtifactInteractionValue = string | readonly string[] | number;

/**
 * Forward-compat dispatch mode for {@link ChatArtifactInteractionPayload}.
 *
 * v1 only implements `new_turn` — the interaction is converted to a regular
 * user message via the existing chat send flow. The enum exists so a future
 * in-place mode (artifact mutates without consuming a turn) can be added
 * without breaking the renderer's call sites.
 */
export type ChatArtifactInteractionMode = 'new_turn';

/**
 * Payload submitted when the user interacts with a widget inside an
 * interactive artifact (button click, choice pick, text submit, slider
 * value). Renderers consume this through `useArtifactInteraction()` and
 * never construct the dispatch themselves.
 */
export interface ChatArtifactInteractionPayload {
	/** Artifact id (matches {@link ChatArtifactPayload.id}). */
	artifactId: string;
	/** Stable widget id chosen by the AI when authoring the artifact. */
	actionId: string;
	/** Human-readable label shown to the user (button text, choice label, etc.). */
	label: string;
	/** Submitted value — string for text, string[] for multi-choice, number for slider. */
	value: ChatArtifactInteractionValue;
	/** Forward-compat hook: v1 only implements `new_turn`. */
	mode: ChatArtifactInteractionMode;
}

/**
 * Structured `render_artifact` payload — emitted as a sibling of the
 * matching `tool_use` so the frontend can render an inline preview card
 * without round-tripping the spec back through the LLM. The catalog of
 * allowed component `type` strings is enforced inside the chat renderer;
 * unknown names render a fallback placeholder rather than the model's free
 * text.
 */
export interface ChatArtifactPayload {
	/** Server-minted id, e.g. `art_3f9b2e1a8c01`. */
	id: string;
	/** Short label shown on the preview card and dialog header. */
	title: string;
	/** json-render flat-spec object — `{ root, elements }`. */
	spec: {
		root: string;
		elements: Record<
			string,
			{
				type: string;
				props?: Record<string, unknown>;
				children?: string[];
			}
		>;
	};
	/** The originating tool_use_id; useful for correlating with chain-of-thought. */
	tool_use_id: string;
}

/** Structured label attached to a conversation (e.g. status tags, categories). */
export type ConversationLabel = {
	/** Machine-readable slug derived from the label name. */
	id?: string;
	/** Human-readable label text. */
	name: string;
	/** Optional hex color for badge rendering. */
	color?: string;
	/** Optional string value associated with the label. */
	value?: string;
	/**
	 * Semantic type hint for the value.
	 * The value itself is always stored as a string regardless of this hint.
	 */
	valueType?: 'string' | 'number' | 'date';
};

/**
 * A label that is either a structured object or a legacy plain string.
 * TODO: Remove the plain-string branch once label migration is complete.
 */
export type ConversationLabelLike = ConversationLabel | string;

/** Status values a conversation can be tagged with. */
export type ConversationStatus = 'todo' | 'in_progress' | 'done' | null;

/** A single conversation record as returned by the backend API. */
export interface Conversation {
	/** Unique conversation identifier. */
	id: string;
	/** ID of the user who owns the conversation. */
	user_id: string;
	/** Display title of the conversation. */
	title: string;
	/** ISO timestamp of creation. */
	created_at: string;
	/** ISO timestamp of last update. */
	updated_at: string;
	/** Whether the conversation has been archived and hidden from the main list. */
	is_archived: boolean;
	/** Whether the conversation has been flagged for follow-up. */
	is_flagged: boolean;
	/** Whether the conversation has an unread indicator. */
	is_unread: boolean;
	/** Workflow status tag: 'todo', 'in_progress', 'done', or null. */
	status: ConversationStatus;
	// Optional sidebar metadata ported from Craft-style session rows.
	/** Whether the conversation is currently generating a response. */
	is_processing?: boolean;
	/** Whether the sidebar should show an unread indicator. */
	has_unread_meta?: boolean;
	/** Role of the most recent message in the conversation. */
	last_message_role?: MessageRole | null;
	/** Number of queued prompts awaiting processing. */
	pending_prompt_count?: number;
	/**
	 * Tags or categories assigned to the conversation.
	 *
	 * Two shapes coexist:
	 * - Server-issued: array of pre-defined label IDs (strings) from
	 *   `NAV_CHATS_LABELS`. The badge renderer resolves each ID to its
	 *   colored display metadata via `getLabelById`.
	 * - Legacy / hand-rolled: structured `ConversationLabel` objects. Kept
	 *   so demo data and hand-built fixtures keep rendering.
	 */
	labels?: ConversationLabelLike[];
	/**
	 * Project this conversation belongs to, or null/undefined when it
	 * lives in the unattached "Chats" list. Set by drag-and-drop in the
	 * sidebar.
	 */
	project_id?: string | null;
}

/** A user-owned sidebar grouping that conversations can be dropped into. */
export interface Project {
	/** Unique project identifier. */
	id: string;
	/** ID of the user who owns the project. */
	user_id: string;
	/** Display name shown in the sidebar. */
	name: string;
	/** ISO timestamp of creation. */
	created_at: string;
	/** ISO timestamp of last update (last rename). */
	updated_at: string;
}

/**
 * Message shape used by the chat API.
 *
 * The streaming-only fields below (`thinking`, `tool_calls`, `timeline`,
 * `thinking_started_at`, `thinking_duration_seconds`, `assistant_status`) are
 * optional so that history fetched from the server (which only persists
 * `role` + `content`) hydrates unchanged; they're populated live during
 * streaming by the chat container in `features/chat/`. `tool_calls` is
 * typed against the transport-level `ChatToolCallBase`; the chat feature
 * extends this with parsed source chips (`webSources`, etc.) that the
 * renderer reads from feature-internal context.
 */
export interface ChatMessage {
	/** Sender of the message. Excludes `'plan'` from {@link MessageRole}. */
	role: Exclude<MessageRole, 'plan'>;
	/** Plain-text message body. */
	content: string;
	/** Accumulated reasoning text from `thinking` SSE events on the assistant turn. */
	thinking?: string;
	/** Tool invocations and their results captured during streaming. */
	tool_calls?: ChatToolCallBase[];
	/** Arrival-ordered timeline of thinking bursts and tool invocations. */
	timeline?: ChatTimelineEntry[];
	/** Wall-clock millis when the first thinking/tool/delta event landed. */
	thinking_started_at?: number;
	/** Total reasoning duration in whole seconds — set when streaming completes. */
	thinking_duration_seconds?: number;
	/** Lifecycle of the assistant turn — drives the failed-state UI. */
	assistant_status?: AssistantMessageStatus;
	/**
	 * Artifacts the agent rendered during this turn (one per `render_artifact`
	 * tool call). v0 lives on the in-memory message only — reload drops them.
	 */
	artifacts?: ChatArtifactPayload[];
}
