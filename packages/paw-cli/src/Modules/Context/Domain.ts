import { Context as EffectContext } from 'effect';
import type { ActiveContext } from '../../Helpers/Config';

/** Provides the resolved active context to subcommand handlers. */
export class ActiveCliContext extends EffectContext.Service<ActiveCliContext, ActiveContext>()(
  '@pawrrtal/cli/ActiveContext'
) {}
