/**
 * Domain model for the chat app, defined with Effect v4 `Schema`.
 *
 * Every entity that crosses a service boundary (conversations, messages,
 * model tiers) is a `Schema.Struct`, and the static TypeScript types are
 * derived from the schema with `Schema.Schema.Type` so the runtime decoder
 * and the compile-time type can never drift apart.
 */
import * as Schema from 'effect/Schema';

/**
 * The four reasoning tiers offered in the model selector popover. `auto`
 * delegates to fast/expert; the others map to a fixed tier.
 */
export const ModelTier = Schema.Literals(['heavy', 'expert', 'fast', 'auto']);
/** Static union of the model-tier ids. */
export type ModelTier = Schema.Schema.Type<typeof ModelTier>;

/** A selectable model in the tier popover. */
export const Model = Schema.Struct({
  id: ModelTier,
  /** Display name shown in the popover row and the composer pill. */
  name: Schema.String,
  /** Secondary line under the name (e.g. "Chooses Fast or Expert"). */
  subtitle: Schema.String,
  /**
   * Icon key resolved by the icon registry. Constrained to the tier-icon
   * names so it is assignable to `AppIcon`'s `IconName` without a cast.
   */
  icon: Schema.Literals(['heavy', 'expert', 'fast', 'auto']),
});
/** Static shape of a selectable model. */
export type Model = Schema.Schema.Type<typeof Model>;

/** Who authored a message. */
export const MessageRole = Schema.Literals(['user', 'assistant']);
/** Static union of message roles. */
export type MessageRole = Schema.Schema.Type<typeof MessageRole>;

/** A single chat message inside a conversation thread. */
export const Message = Schema.Struct({
  id: Schema.String,
  role: MessageRole,
  text: Schema.String,
  /** Epoch milliseconds the message was created. */
  createdAt: Schema.Number,
});
/** Static shape of a chat message. */
export type Message = Schema.Schema.Type<typeof Message>;

/** A conversation as listed in the history drawer. */
export const Conversation = Schema.Struct({
  id: Schema.String,
  /** Title shown in the history row. */
  title: Schema.String,
  /** Pre-formatted relative time label (e.g. "Sunday", "May 31", "7:45 PM"). */
  timeLabel: Schema.String,
  /** Messages in the thread (empty for seed history rows). */
  messages: Schema.Array(Message),
});
/** Static shape of a conversation. */
export type Conversation = Schema.Schema.Type<typeof Conversation>;

/** The two top-level home modes ("Ask" / "Imagine"). */
export const HomeMode = Schema.Literals(['ask', 'imagine']);
/** Static union of home modes. */
export type HomeMode = Schema.Schema.Type<typeof HomeMode>;
