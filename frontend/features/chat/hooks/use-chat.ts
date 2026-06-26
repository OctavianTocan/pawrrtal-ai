/**
 * Streaming chat transport: POST to the chat endpoint and parse SSE frames into typed events.
 *
 * @fileoverview Consumes the `/api/v1/chat` Server-Sent Events stream and yields a
 * {@link ChatStreamEvent} for every well-formed `data: {...}` frame until `[DONE]`.
 * The container collapses the event sequence into the displayed chat history.
 */

import { useAuthedFetch } from '@/hooks/use-authed-fetch';
import { API_ENDPOINTS } from '@/lib/api';
import type { ChatReasoningLevel } from '../constants';
import type { ChatStreamEvent } from '../types';

/** Sentinel returned by {@link parseSseFrame} when the stream signals completion. */
const STREAM_DONE = Symbol('STREAM_DONE');

/**
 * Wire shape for one multimodal image attached to a chat request.
 *
 * Mirrors the backend's `ChatImageInput` schema: a base64-encoded blob
 * with no `data:` URL prefix plus an explicit MIME type the provider
 * bridge translates into a multimodal content block.
 */
export type ChatImageInput = {
  /** Base64-encoded image bytes, with the `data:<mime>;base64,` prefix stripped. */
  data: string;
  /** Allowed image MIME types — must match the backend `ChatImageInput.media_type` literal union. */
  media_type: 'image/png' | 'image/jpeg' | 'image/gif' | 'image/webp';
};

/** Allowed `type` field values for chat SSE events. */
const CHAT_EVENT_TYPES = [
  'delta',
  'thinking',
  'tool_use',
  'tool_progress',
  'tool_result',
  'artifact',
  'error',
  'agent_terminated',
] as const;

/**
 * Narrow an unknown JSON payload to a {@link ChatStreamEvent}.
 *
 * Returns the event if `type` is one of the known kinds; otherwise returns
 * `null` so the caller can ignore the frame instead of crashing on unexpected
 * payloads. Field-level validation is intentionally light — frames already
 * passed JSON.parse and originate from our own backend contract.
 */
function asChatStreamEvent(value: unknown): ChatStreamEvent | null {
  if (!value || typeof value !== 'object') return null;
  const candidate = value as { type?: unknown };
  if (typeof candidate.type !== 'string') return null;
  if (!(CHAT_EVENT_TYPES as readonly string[]).includes(candidate.type)) return null;
  return value as ChatStreamEvent;
}

/**
 * Parse a single SSE frame.
 *
 * @returns the parsed event, the done sentinel, or `null` for non-data /
 *   unparseable frames (e.g., comment lines, partial frames).
 */
function parseSseFrame(raw: string): ChatStreamEvent | typeof STREAM_DONE | null {
  if (!raw.startsWith('data: ')) return null;

  const data = raw.slice(6);

  if (data.includes('[DONE]')) return STREAM_DONE;

  try {
    return asChatStreamEvent(JSON.parse(data));
  } catch {
    // Ignore parse errors from incomplete SSE frames.
    return null;
  }
}

/**
 * Generator yielding events from a single buffered batch of SSE frames.
 *
 * Returns `'done'` when a `[DONE]` sentinel was seen so the caller can break
 * out of the read loop, otherwise `'continue'`. Throws on stream-level
 * `error` events so the outer transport can fail the request.
 */
function* parseFrameBatch(frames: string[]): Generator<ChatStreamEvent, 'done' | 'continue'> {
  for (const frame of frames) {
    const parsed = parseSseFrame(frame);
    if (parsed === null) continue;
    if (parsed === STREAM_DONE) return 'done';
    if (parsed.type === 'error') {
      throw new Error(parsed.content || 'Chat stream failed.');
    }
    // agent_terminated is a controlled stop, not an exception — yield it
    // to the reducer so the UI can display a distinct notice rather than
    // a generic error banner.
    yield parsed;
  }
  return 'continue';
}

/**
 * Release a stream reader lock without crashing on an already-errored stream.
 *
 * `releaseLock` throws if the underlying stream entered an error state, but
 * that's expected during exception unwind — swallow it so the original error
 * keeps propagating.
 */
function safeReleaseLock(reader: { releaseLock: () => void }): void {
  try {
    reader.releaseLock();
  } catch {
    // Stream already errored — nothing to release.
  }
}

/**
 * Hook that exposes a streaming chat API as an async generator of typed events.
 *
 * @returns An object with `streamMessage` — call it to send a user message and
 *   yield {@link ChatStreamEvent} frames as they arrive. Throws if the backend
 *   emits a stream-level `error` event so the container can surface it as a
 *   failed assistant message.
 */
export function useChat(): {
  streamMessage: (
    message: string,
    conversationId: string,
    modelId: string,
    reasoningEffort: ChatReasoningLevel,
    images?: readonly ChatImageInput[]
  ) => AsyncGenerator<ChatStreamEvent>;
} {
  const fetcher = useAuthedFetch();

  async function* streamMessage(
    message: string,
    conversationId: string,
    modelId: string,
    reasoningEffort: ChatReasoningLevel,
    images?: readonly ChatImageInput[]
  ): AsyncGenerator<ChatStreamEvent> {
    const response = await fetcher(API_ENDPOINTS.chat.messages, {
      method: 'POST',
      body: JSON.stringify({
        question: message,
        conversation_id: conversationId,
        model_id: modelId,
        reasoning_effort: reasoningEffort,
        // Only include `images` when the user actually attached one — keeps
        // the wire payload identical to the pre-multimodal contract for
        // the common text-only path.
        ...(images && images.length > 0 ? { images } : {}),
      }),
      headers: {
        'Content-Type': 'application/json',
        Accept: 'text/event-stream',
      },
    });

    if (!response.body) throw new Error('Failed to get response body from chat API');

    // Pipe raw bytes through a text decoder so we can read string chunks.
    const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();

    // SSE frames can arrive split across chunks — buffer partial frames here.
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += value;

        // SSE events are delimited by double newlines.
        const frames = buffer.split('\n\n');

        // The last element is either empty or a partial frame — keep it buffered.
        buffer = frames.pop() ?? '';

        const status = yield* parseFrameBatch(frames);
        if (status === 'done') return;
      }
    } finally {
      safeReleaseLock(reader);
    }
  }

  return { streamMessage };
}
