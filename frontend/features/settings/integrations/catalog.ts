/**
 * Static catalog of integrations the Settings → Integrations section can
 * surface.
 *
 * No real integrations are implemented in the backend yet — this module
 * exists so the UI shape is in place and ready to wire up. Both lists
 * are intentionally empty; populate them as real integrations land.
 *
 * @fileoverview Integrations catalog types + empty defaults.
 */

import type { LucideIcon } from 'lucide-react';

/** Status badge shown next to an integration / account name. */
export type IntegrationBadge = 'beta' | 'connected' | 'expired' | null;

/** Integration row metadata shown in the "Your Integrations" list. */
export interface IntegrationDef {
  /** Stable id used as React key + storage key. */
  id: string;
  /** Display name (e.g. "Apple Calendar", "Gmail"). */
  name: string;
  /** Short subtitle ("See your events in Apple Calendar"). */
  description: string;
  /** Optional badge rendered to the right of the name. */
  badge?: IntegrationBadge;
  /** Lucide icon used as the integration's avatar tile. */
  Icon: LucideIcon;
  /** Tailwind background class for the avatar tile. */
  tileBgClass: string;
  /** Tailwind text class for the avatar tile icon. */
  tileTextClass: string;
  /** Per-account rows (Gmail / Google Calendar can have multiple accounts). */
  accounts?: IntegrationAccount[];
}

/** A single account attached to an integration (Gmail address, etc). */
export interface IntegrationAccount {
  id: string;
  email: string;
  subtitle?: string;
  status: 'connected' | 'expired';
  label?: string;
}

/**
 * Master list rendered in "Your Integrations".
 *
 * Empty by default — there are no real integrations implemented in the
 * backend yet. Add a row here once the corresponding backend endpoint
 * + OAuth flow is live so the UI faithfully reflects what works.
 */
export const YOUR_INTEGRATIONS: IntegrationDef[] = [];

/** Catalog rendered inside the "Add integration" modal grid. */
export interface CatalogIntegration extends IntegrationDef {
  /** "connect" → CTA button shown; otherwise pre-installed (gear). */
  state: 'installed' | 'connectable';
}

/**
 * Catalog of integrations the user can browse + connect from the
 * "Add integration" modal.
 *
 * Empty by default — same reason as `YOUR_INTEGRATIONS`. When a real
 * integration is implemented, add it here as `state: 'connectable'`
 * (or `'installed'` if it's auto-enabled).
 */
export const INTEGRATION_CATALOG: CatalogIntegration[] = [];
