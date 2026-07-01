import { Context as EffectContext, Schema } from 'effect';

export const AuthStateSchema = Schema.Literals([
  'not_applicable',
  'unresolved',
  'authenticated',
  'unauthenticated',
]).pipe(
  Schema.annotate({
    identifier: 'AuthState',
    title: 'Auth State',
    description: 'Resolved authentication state for the active CLI context.',
  })
);

export type AuthState = typeof AuthStateSchema.Type;

export class ConfigSourceSummary extends Schema.Class<ConfigSourceSummary>('ConfigSourceSummary')(
  {
    key: Schema.NonEmptyString,
    source: Schema.NonEmptyString,
    value: Schema.NullOr(Schema.String),
  },
  {
    identifier: 'ConfigSourceSummary',
    title: 'Config Source Summary',
    description: 'Public source label and value summary for one resolved config key.',
  }
) {}

export class ActiveContext extends Schema.Class<ActiveContext>('ActiveContext')(
  {
    profile: Schema.NonEmptyString,
    configRoot: Schema.NonEmptyString,
    cacheRoot: Schema.NonEmptyString,
    backendTarget: Schema.NullOr(Schema.String),
    backendTargetSource: Schema.NullOr(Schema.String),
    backendTargetUnsetReason: Schema.NullOr(Schema.String),
    authState: AuthStateSchema,
    configSources: Schema.Array(ConfigSourceSummary),
  },
  {
    identifier: 'ActiveContext',
    title: 'Active Context',
    description: 'Secret-safe active context resolved for one Paw CLI invocation.',
  }
) {}

export type ConfigSource = typeof ConfigSourceSummary.Type;

/** Provides the resolved active context to subcommand handlers. */
export class ActiveCliContext extends EffectContext.Service<ActiveCliContext, ActiveContext>()(
  '@pawrrtal/cli/ActiveContext'
) {}
