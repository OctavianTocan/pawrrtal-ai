/**
 * One conversation = one Rivet actor.
 *
 * The actor owns the live session state (transcript + turn counter) and is the
 * single writer for it. `sendMessage` runs an unforked Pi turn and broadcasts
 * each text delta over the actor's WebSocket so connected clients stream live
 * (M1/M2). When an identity is bound via `setIdentity`, each finished turn also
 * projects a conversation-summary row to Postgres through the API seam — the
 * actor never touches PG directly (M3 single-writer path).
 */

import type { AgentEvent, AgentMessage } from '@earendil-works/pi-agent-core';
import { actor } from 'rivetkit';
import { upsertConversationSummary } from './api.ts';
import { runPiTurn, userMessage } from './pi-turn.ts';

const SYSTEM_PROMPT = 'You are Pawrrtal, running inside a Rivet actor.';
const TITLE_MAX_LENGTH = 60;

interface ConversationState {
  systemPrompt: string;
  /** Postgres conversation id; null until `setIdentity` binds one (no projection). */
  id: string | null;
  owner: string;
  messages: AgentMessage[];
  turnCount: number;
  /** Times the actor's own scheduler fired a per-session wake (M9 durability). */
  wakeCount: number;
  /** Label of the most recent fired wake; proves the right schedule ran. */
  lastWakeLabel: string | null;
}

/** Extract the concatenated assistant text from a finished turn's new messages. */
function assistantText(messages: AgentMessage[]): string {
  const assistant = [...messages].reverse().find((m) => m.role === 'assistant');
  if (!assistant || assistant.role !== 'assistant') {
    return '';
  }
  return assistant.content.map((block) => (block.type === 'text' ? block.text : '')).join('');
}

/** Derive a conversation title from the first user message. */
function conversationTitle(messages: AgentMessage[]): string {
  const firstUser = messages.find((m) => m.role === 'user');
  let text = '';
  if (firstUser?.role === 'user') {
    const { content } = firstUser;
    text =
      typeof content === 'string'
        ? content
        : content.map((block) => (block.type === 'text' ? block.text : '')).join('');
  }
  const title = text.trim().length > 0 ? text.trim() : 'New conversation';
  return title.length > TITLE_MAX_LENGTH ? `${title.slice(0, TITLE_MAX_LENGTH - 1)}…` : title;
}

export const conversation = actor({
  createState: (): ConversationState => ({
    systemPrompt: SYSTEM_PROMPT,
    id: null,
    owner: 'spike-user',
    messages: [],
    turnCount: 0,
    wakeCount: 0,
    lastWakeLabel: null,
  }),

  actions: {
    /**
     * Bind this actor to a Postgres conversation id (and owner) so finished
     * turns project a summary row through the API. Without it, the actor stays
     * PG-free (M1/M2 behavior).
     */
    setIdentity: (c, identity: { id: string; owner?: string }) => {
      c.state.id = identity.id;
      if (identity.owner) {
        c.state.owner = identity.owner;
      }
      return { id: c.state.id, owner: c.state.owner };
    },

    /** Run one Pi turn for `text`, streaming deltas out as broadcasts. */
    sendMessage: async (c, text: string) => {
      const priorHistory = c.state.messages;
      const prompt = userMessage(text);

      const onEvent = (event: AgentEvent): void => {
        if (event.type === 'message_update' && event.assistantMessageEvent.type === 'text_delta') {
          c.broadcast('delta', { text: event.assistantMessageEvent.delta });
          return;
        }
        if (event.type === 'turn_end') {
          c.broadcast('turn_done', {
            stopReason: event.message.role === 'assistant' ? event.message.stopReason : 'stop',
          });
        }
      };

      const newMessages = await runPiTurn({
        context: {
          systemPrompt: c.state.systemPrompt,
          messages: priorHistory,
          tools: [],
        },
        prompts: [prompt],
        onEvent,
        signal: c.abortSignal,
      });

      c.state.messages = [...priorHistory, ...newMessages];
      c.state.turnCount += 1;
      const reply = assistantText(newMessages);

      // Single-writer projection: the actor reaches Postgres only via the API.
      if (c.state.id) {
        await upsertConversationSummary({
          id: c.state.id,
          owner: c.state.owner,
          title: conversationTitle(c.state.messages),
          lastMessage: reply,
          turnCount: c.state.turnCount,
        });
      }

      return {
        ok: true as const,
        turnCount: c.state.turnCount,
        assistantText: reply,
        transcriptLength: c.state.messages.length,
      };
    },

    /** Read the persisted transcript (used to prove durability across restart). */
    getTranscript: (c) => ({
      turnCount: c.state.turnCount,
      messageCount: c.state.messages.length,
      messages: c.state.messages,
    }),

    /**
     * Register a per-session wake `delayMs` from now via the actor's OWN
     * scheduler. The wake invokes `fireWake` even if the actor hibernates or the
     * engine restarts in the meantime — this is the session-scoped durable timer
     * the ADR puts on the actor (not Hatchet). Returns when the wake will fire.
     */
    scheduleWake: async (c, args: { delayMs: number; label: string }) => {
      await c.schedule.after(args.delayMs, 'fireWake', args.label);
      return { scheduledFor: Date.now() + args.delayMs, label: args.label };
    },

    /** Scheduler-invoked callback (never called by clients). Mutates state. */
    fireWake: (c, label: string) => {
      c.state.wakeCount += 1;
      c.state.lastWakeLabel = label;
    },

    /** Read the wake counters (used to prove the schedule fired post-restart). */
    getWakes: (c) => ({
      wakeCount: c.state.wakeCount,
      lastWakeLabel: c.state.lastWakeLabel,
    }),
  },
});
