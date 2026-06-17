/**
 * Typed domain errors, defined as Effect v4 schema-backed tagged errors so
 * they are serializable and exhaustively matchable in `Effect.catchTag`.
 */
import * as Schema from 'effect/Schema';

/** Raised when a conversation id is requested but not present in the store. */
export class ConversationNotFound extends Schema.TaggedErrorClass<ConversationNotFound>()(
  'ConversationNotFound',
  { conversationId: Schema.String },
) {
  /** Human-readable summary for logs and error surfaces. */
  override get message(): string {
    return `Conversation "${this.conversationId}" was not found`;
  }
}

/** Raised when a requested model tier is not in the registry. */
export class ModelNotFound extends Schema.TaggedErrorClass<ModelNotFound>()('ModelNotFound', {
  tier: Schema.String,
}) {
  /** Human-readable summary for logs and error surfaces. */
  override get message(): string {
    return `Model tier "${this.tier}" was not found`;
  }
}
