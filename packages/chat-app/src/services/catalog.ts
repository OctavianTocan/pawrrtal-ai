/**
 * `Catalog` — read-only access to the static domain data (model tiers and
 * conversation history). Backed by in-memory seed fixtures for this UI-only
 * build; the Effect surface means a real data source can be swapped in behind
 * the same key without touching call sites.
 */
import * as Context from 'effect/Context';
import * as Effect from 'effect/Effect';
import * as Layer from 'effect/Layer';
import { SEED_CONVERSATIONS, SEED_MODELS } from '@/data/seed';
import { type Conversation, type Model, ModelNotFound, type ModelTier } from '@/domain';

/** Public surface of the catalog service. */
export interface CatalogShape {
  /** All selectable model tiers, in display order. */
  readonly models: readonly Model[];
  /** Resolve a single model by tier, failing if absent. */
  readonly modelByTier: (tier: ModelTier) => Effect.Effect<Model, ModelNotFound>;
  /** The conversation history list. */
  readonly conversations: readonly Conversation[];
}

/** Service key for the catalog. */
export class Catalog extends Context.Service<Catalog, CatalogShape>()('ChatApp/Catalog') {}

/** Live layer over the in-memory seed fixtures. */
export const CatalogLive: Layer.Layer<Catalog> = Layer.succeed(
  Catalog,
  Catalog.of({
    models: SEED_MODELS,
    conversations: SEED_CONVERSATIONS,
    modelByTier: (tier) => {
      const found = SEED_MODELS.find((model) => model.id === tier);
      return found ? Effect.succeed(found) : Effect.fail(new ModelNotFound({ tier }));
    },
  }),
);
