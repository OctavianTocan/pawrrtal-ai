/** Rivet registry: the one actor the spike exposes. */
import { setup } from 'rivetkit';
import { conversation } from './conversation-actor.ts';

export const registry = setup({
  use: { conversation },
});

export type Registry = typeof registry;
