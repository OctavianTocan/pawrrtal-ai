/**
 * One conversation = one Rivet actor.
 *
 * The actor owns the live session state (transcript + turn counter) and is the
 * single writer for it. `sendMessage` runs an unforked Pi turn and broadcasts
 * each text delta over the actor's WebSocket so connected clients stream live.
 * This is the M1/M2 substrate probe for the 003 overhaul ADR.
 */

import type { AgentEvent, AgentMessage } from '@earendil-works/pi-agent-core';
import { actor } from 'rivetkit';
import { runPiTurn, userMessage } from './pi-turn.ts';

const SYSTEM_PROMPT = 'You are Pawrrtal, running inside a Rivet actor.';

interface ConversationState {
  systemPrompt: string;
  messages: AgentMessage[];
  turnCount: number;
}

/** Extract the concatenated assistant text from a finished turn's new messages. */
function assistantText(messages: AgentMessage[]): string {
  const assistant = [...messages].reverse().find((m) => m.role === 'assistant');
  if (!assistant || assistant.role !== 'assistant') {
    return '';
  }
  return assistant.content.map((block) => (block.type === 'text' ? block.text : '')).join('');
}

export const conversation = actor({
  createState: (): ConversationState => ({
    systemPrompt: SYSTEM_PROMPT,
    messages: [],
    turnCount: 0,
  }),

  actions: {
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

      return {
        ok: true as const,
        turnCount: c.state.turnCount,
        assistantText: assistantText(newMessages),
        transcriptLength: c.state.messages.length,
      };
    },

    /** Read the persisted transcript (used to prove durability across restart). */
    getTranscript: (c) => ({
      turnCount: c.state.turnCount,
      messageCount: c.state.messages.length,
      messages: c.state.messages,
    }),
  },
});
