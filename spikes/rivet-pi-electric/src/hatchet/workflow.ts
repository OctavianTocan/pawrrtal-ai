/**
 * The Hatchet client + the one durable task the spike registers (M8).
 *
 * The task projects a conversation summary into the app Postgres through the
 * SAME single-writer seam the actor uses (`upsertConversationSummary`). It is
 * shared by the worker (which executes it) and m8 (which triggers it), so both
 * sides agree on the task name and input shape.
 */
import { HatchetClient } from '@hatchet-dev/typescript-sdk/v1';
import { upsertConversationSummary } from '../api.ts';

export const TASK_NAME = 'project-conversation-summary';

// `type` (not `interface`) so these satisfy Hatchet's `JsonObject` constraint:
// object-literal type aliases get an implicit string index signature, interfaces don't.
export type ProjectSummaryInput = {
  readonly id: string;
  readonly owner: string;
  readonly title: string;
  readonly lastMessage: string;
  readonly turnCount: number;
};

export type ProjectSummaryOutput = {
  readonly projected: boolean;
  readonly id: string;
};

// 7079, not the default 7077: this host already runs a separate persistent
// Hatchet on 7077. Must match the compose SERVER_GRPC_BROADCAST_ADDRESS.
const HOST_PORT = process.env.HATCHET_HOST_PORT ?? '127.0.0.1:7079';

/** Build a Hatchet client from the env token (insecure local gRPC). */
export function makeHatchet(): HatchetClient {
  const token = process.env.HATCHET_CLIENT_TOKEN;
  if (!token) {
    throw new Error('HATCHET_CLIENT_TOKEN is required (see infra/hatchet-creds/api-token)');
  }
  return HatchetClient.init({
    token,
    host_port: HOST_PORT,
    tls_config: { tls_strategy: 'none' },
  });
}

/** Define the durable projection task; pass to a worker to register + execute it. */
export function defineProjectSummary(hatchet: HatchetClient) {
  return hatchet.task({
    name: TASK_NAME,
    fn: async (input: ProjectSummaryInput): Promise<ProjectSummaryOutput> => {
      await upsertConversationSummary({
        id: input.id,
        owner: input.owner,
        title: input.title,
        lastMessage: input.lastMessage,
        turnCount: input.turnCount,
      });
      return { projected: true, id: input.id };
    },
  });
}
