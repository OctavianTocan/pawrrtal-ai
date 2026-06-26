/**
 * Pure helpers that fold a single SSE event into the in-flight assistant message.
 *
 * @fileoverview Lifted out of `ChatContainer.tsx` so the reducer can be unit
 * tested without rendering a component, and so the container body stays focused
 * on lifecycle/routing wiring instead of state-shape mechanics.
 */

import type { ChatMessage } from '@/lib/types';
import type { ChatStreamEvent, ChatToolCall } from './types';

/**
 * Apply an updater to the last assistant message in `messages`, returning a
 * new array. Each SSE event produces exactly one immutable message-list update
 * via this helper so React can short-circuit unrelated rows.
 */
export function updateLastAssistantMessage(
  messages: Array<ChatMessage>,
  update: (current: ChatMessage) => ChatMessage
): Array<ChatMessage> {
  const lastIndex = messages.length - 1;
  const last = messages[lastIndex];
  if (last?.role !== 'assistant') return messages;

  const updated = [...messages];
  updated[lastIndex] = update(last);
  return updated;
}

/**
 * Stamp `thinking_started_at` the first time we see a delta/thinking/tool
 * event. The reducer uses the wall clock so the UI can show a live "thinking
 * for Xs" affordance even across separate SSE bursts.
 */
function markStartedAt(message: ChatMessage): ChatMessage {
  if (message.thinking_started_at !== undefined) return message;
  return { ...message, thinking_started_at: Date.now() };
}

/**
 * Append a `thinking` slot to the timeline, merging into a trailing one.
 *
 * Consecutive `thinking` chunks all belong to the same logical reasoning
 * burst, so we coalesce them rather than creating a new bullet for every
 * SSE frame. A tool invocation inserted between two thinking bursts breaks
 * the merge: the trailing thinking is no longer the last entry.
 */
function pushThinkingTimelineEntry(message: ChatMessage, text: string): ChatMessage {
  const timeline = message.timeline ?? [];
  const last = timeline[timeline.length - 1];
  if (last?.kind === 'thinking') {
    const merged: ChatMessage['timeline'] = [...timeline.slice(0, -1), { kind: 'thinking', text: last.text + text }];
    return { ...message, timeline: merged };
  }
  return { ...message, timeline: [...timeline, { kind: 'thinking', text }] };
}

/**
 * Reduce a single {@link ChatStreamEvent} into the in-flight assistant message.
 *
 * Pure function so it stays trivially testable and composes inside a setState
 * updater. `error` events never reach here — the transport throws on those and
 * the catch block in `runAssistantTurn` writes the error into `content`.
 */
export function applyChatEvent(message: ChatMessage, event: ChatStreamEvent): ChatMessage {
  switch (event.type) {
    case 'delta':
      return markStartedAt({
        ...message,
        content: message.content + event.content,
        assistant_status: 'streaming',
      });
    case 'thinking': {
      const stamped = markStartedAt(message);
      const withText: ChatMessage = {
        ...stamped,
        thinking: (stamped.thinking ?? '') + event.content,
        assistant_status: 'streaming',
      };
      return pushThinkingTimelineEntry(withText, event.content);
    }
    case 'tool_use': {
      const stamped = markStartedAt(message);
      const newCall: ChatToolCall = {
        id: event.tool_use_id,
        name: event.name,
        input: event.input,
        display: event.display,
        status: 'pending',
      };
      return {
        ...stamped,
        assistant_status: 'streaming',
        tool_calls: [...(stamped.tool_calls ?? []), newCall],
        timeline: [...(stamped.timeline ?? []), { kind: 'tool', toolCallId: event.tool_use_id }],
      };
    }
    case 'tool_result': {
      const calls = message.tool_calls ?? [];
      const updated = calls.map((call) =>
        call.id === event.tool_use_id ? { ...call, result: event.content, status: 'completed' as const } : call
      );
      return { ...message, tool_calls: updated };
    }
    case 'tool_progress': {
      const calls = message.tool_calls ?? [];
      const updated = calls.map((call) => (call.id === event.tool_use_id ? { ...call, result: event.content } : call));
      return { ...message, tool_calls: updated };
    }
    case 'artifact': {
      // The matching `tool_use` for `render_artifact` arrives just
      // before this event and is already in `tool_calls` — we keep
      // the artifact as a separate first-class field rather than
      // stuffing it into the tool-call slot, so the renderer can
      // treat artifacts as their own surface (preview card +
      // expandable dialog) without picking apart tool metadata.
      const stamped = markStartedAt(message);
      return {
        ...stamped,
        artifacts: [...(stamped.artifacts ?? []), event.artifact],
      };
    }
    case 'error':
      // Should be unreachable — the transport surfaces errors by throwing.
      return { ...message, content: `Error: ${event.content}`, assistant_status: 'failed' };
    case 'agent_terminated':
      // Safety layer fired a controlled stop (iteration cap, wall-clock
      // budget, or consecutive-error threshold).  Append the explanation
      // to whatever content the model produced before stopping, and mark
      // the message complete so it doesn’t linger in a streaming state.
      return {
        ...message,
        content: `${message.content ? `${message.content}\n\n` : ''}⚠️ ${event.content}`,
        assistant_status: 'complete',
      };
    default:
      return message;
  }
}

/**
 * Compute the elapsed reasoning duration in whole seconds from the first
 * thinking/tool/delta to the call completion. Returns 0 when no events ever
 * arrived (e.g. the stream errored before producing anything).
 */
export function computeThinkingDuration(message: ChatMessage): number {
  if (message.thinking_started_at === undefined) return 0;
  const elapsedMs = Date.now() - message.thinking_started_at;
  return Math.max(0, Math.round(elapsedMs / 1000));
}
