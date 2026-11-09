/**
 * The unforked-Pi seam.
 *
 * `runPiTurn` drives the real `@earendil-works/pi-agent-core` loop with a keyless
 * faux provider so the spike can prove "Pi runs inside a Rivet actor" without any
 * API keys or network. Nothing here patches Pi; it only wires Pi's public
 * `runAgentLoop` + `createFauxCore` together and forwards events to a sink.
 */
import type { AgentContext, AgentEvent, AgentLoopConfig, AgentMessage, StreamFn } from '@earendil-works/pi-agent-core';
import { runAgentLoop } from '@earendil-works/pi-agent-core';
import type { Message } from '@earendil-works/pi-ai';
import { createFauxCore, fauxAssistantMessage } from '@earendil-works/pi-ai/providers/faux';

/** A plain text user message in Pi's `AgentMessage` shape. */
export function userMessage(text: string): AgentMessage {
  return {
    role: 'user',
    content: [{ type: 'text', text }],
    timestamp: Date.now(),
  };
}

/** Pull the most recent user text out of a prompt list, for the canned reply. */
function lastUserText(prompts: AgentMessage[]): string {
  for (let i = prompts.length - 1; i >= 0; i--) {
    const message = prompts[i];
    if (message.role !== 'user') {
      continue;
    }
    const { content } = message;
    if (typeof content === 'string') {
      return content;
    }
    return content.map((block) => (block.type === 'text' ? block.text : '')).join('');
  }
  return '';
}

/** Scripted reply the faux provider streams back, so deltas are visibly chunked. */
function defaultReply(prompts: AgentMessage[]): string {
  const said = lastUserText(prompts).trim();
  return [
    "I'm the Pi agent loop, running unmodified inside a Rivet actor.",
    said ? `You said: "${said}".` : '',
    'Every token in this sentence is a faux-provider delta the actor is',
    'broadcasting over its WebSocket to prove the substrate streams end to end.',
  ]
    .filter(Boolean)
    .join(' ');
}

export interface RunPiTurnArgs {
  /** Prior transcript visible to the model (does not include the new prompt). */
  readonly context: AgentContext;
  /** New prompt messages to start this turn. */
  readonly prompts: AgentMessage[];
  /** Sink for every Pi agent event (used to broadcast deltas from the actor). */
  readonly onEvent: (event: AgentEvent) => void | Promise<void>;
  /** Optional override for the streamed reply text. */
  readonly reply?: string;
  /** Tokens-per-second pacing for the faux stream. */
  readonly tokensPerSecond?: number;
  readonly signal?: AbortSignal;
}

/**
 * Run one Pi turn against a keyless faux provider and return the new messages
 * (prompt + assistant response) the loop produced.
 */
export async function runPiTurn(args: RunPiTurnArgs): Promise<AgentMessage[]> {
  const faux = createFauxCore({
    tokensPerSecond: args.tokensPerSecond ?? 40,
    tokenSize: { min: 2, max: 4 },
  });
  faux.setResponses([fauxAssistantMessage(args.reply ?? defaultReply(args.prompts))]);

  const config: AgentLoopConfig = {
    model: faux.getModel(),
    convertToLlm: (messages: AgentMessage[]): Message[] => messages as Message[],
  };

  return runAgentLoop(
    args.prompts,
    args.context,
    config,
    (event) => args.onEvent(event),
    args.signal,
    faux.stream as unknown as StreamFn
  );
}
