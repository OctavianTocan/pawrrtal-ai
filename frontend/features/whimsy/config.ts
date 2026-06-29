'use client';

/**
 * Whimsy texture — config schema, validation, and persistence hook.
 *
 * Owns:
 * - {@link WhimsyConfig} type + sub-types ({@link WhimsyMode},
 *   {@link WhimsyColor}).
 * - Default values, slider bounds, and the localStorage key.
 * - {@link useWhimsyConfig} read/write hook with validation against the
 *   on-disk shape.
 *
 * Kept in its own module so consumers that only need types or the
 * config hook (settings UI, Stagehand fixtures, etc.) don't pull in
 * the SVG generator or the heavy settings card.
 */

import type { Dispatch, SetStateAction } from 'react';
import { usePersistedState } from '@/hooks/use-persisted-state';
import type { WhimsyPresetId } from '@/lib/whimsy-presets';
import { isWhimsyPresetId } from '@/lib/whimsy-presets';
import type { WhimsyThemeName } from '@/lib/whimsy-tile';
import { WHIMSY_THEMES } from '@/lib/whimsy-tile';

/** localStorage key under which the whimsy customization is persisted. */
const WHIMSY_STORAGE_KEY = 'whimsy:config';

/**
 * Numeric bounds for sliders and validation. Centralizing keeps the
 * slider min/max in lockstep with the storage validator so a malicious
 * or stale value can't slip through one and fail the other.
 */
export const WHIMSY_BOUNDS = {
  grid: { min: 3, max: 10 },
  size: { min: 120, max: 360 },
  /** Slider integer scale — internal 0-200 maps to opacity 0-0.20 (0%-20%). */
  opacityScale: { min: 0, max: 200 },
  /** Preset tile width in CSS pixels. Height auto-resolves from the SVG aspect. */
  presetSize: { min: 200, max: 1200 },
} as const;

/** Multiplier applied to the slider integer value to get the stored decimal opacity. */
export const OPACITY_SLIDER_DIVISOR = 1000;

/**
 * Source of the texture — procedural (`generated`) or one of the
 * bundled SVG presets (`preset`). The mode flips which sub-fields the
 * settings UI exposes and which the renderer reads.
 */
export type WhimsyMode = 'generated' | 'preset';

/**
 * Tile / background colour override.
 *
 * - ``'theme'`` — derive from theme tokens (current behaviour). Tile
 *   uses ``currentColor`` (text-foreground); background stays the chat
 *   panel's underlying ``bg-background``.
 * - A ``'#rrggbb'`` string — apply that exact colour. Lets users dial
 *   in tints without waiting on a full gradient picker.
 */
export type WhimsyColor = 'theme' | string;

/** Validate a stored ``WhimsyColor`` value. */
function isWhimsyColor(value: unknown): value is WhimsyColor {
  if (value === 'theme') return true;
  return typeof value === 'string' && /^#[0-9a-fA-F]{6}$/.test(value);
}

/** User-tunable parameters for the whimsy texture overlay. */
export interface WhimsyConfig {
  /** When false, the texture overlay is not rendered at all. */
  enabled: boolean;
  /** Source of the texture — procedurally generated tile or a static preset. */
  mode: WhimsyMode;
  /**
   * Custom background colour painted under the texture. ``'theme'``
   * keeps the chat panel's underlying ``bg-background`` showing
   * through; a hex string overrides it with a solid fill before the
   * masked tile renders.
   */
  backgroundColor: WhimsyColor;
  /**
   * Custom tile tint. ``'theme'`` uses the foreground theme token
   * (current behaviour); a hex string overrides the masked-tile
   * colour.
   */
  tintColor: WhimsyColor;
  /** Curated motif set name; one of {@link WHIMSY_THEMES}'s keys. Used in ``generated`` mode. */
  theme: WhimsyThemeName;
  /** Identifier of the active preset under ``/whimsy-patterns/``. Used in ``preset`` mode. */
  preset: WhimsyPresetId;
  /**
   * Tile width in CSS pixels for ``preset`` mode. Height resolves
   * from the SVG's intrinsic aspect via ``mask-size: <width>px auto``.
   * Smaller = tighter repeats with smaller doodles; larger = bigger
   * drawings, fewer repeats. Procedural ``size`` doesn't translate
   * (different SVG aspect), so we keep this as its own field.
   */
  presetSize: number;
  /** Deterministic placement seed. Any 32-bit integer; reroll for fresh layout. */
  seed: number;
  /** Motifs per row/column in the placement grid. Higher = denser pattern. */
  grid: number;
  /** Repeating tile dimension in CSS pixels. */
  size: number;
  /** Texture intensity. Stored as a 0..1 fraction; rendered via CSS `opacity`. */
  opacity: number;
}

/** Default config — matches the values originally hardcoded in `ChatView`. */
export const DEFAULT_WHIMSY_CONFIG: WhimsyConfig = {
  enabled: true,
  mode: 'generated',
  backgroundColor: 'theme',
  tintColor: 'theme',
  theme: 'kawaii',
  preset: 'pattern-1',
  presetSize: 600,
  seed: 42,
  grid: 6,
  size: 240,
  opacity: 0.035,
};

/** Theme-name allowlist derived from the registered themes. */
const THEME_NAMES = Object.keys(WHIMSY_THEMES) as readonly WhimsyThemeName[];

/** Type guard for a string being one of the registered theme names. */
export function isWhimsyThemeName(value: unknown): value is WhimsyThemeName {
  return typeof value === 'string' && THEME_NAMES.includes(value as WhimsyThemeName);
}

/** Public list of registered theme names — consumed by the settings UI. */
export const WHIMSY_THEME_NAMES = THEME_NAMES;

/**
 * Validates the on-disk shape. Rejects anything outside the slider
 * bounds so a stale persisted value (e.g. after we tighten a range)
 * silently falls back to the default instead of leaving the UI stuck
 * on an invalid state.  Pre-mode persisted blobs (no ``mode`` /
 * ``preset``) fail this guard; the ``usePersistedState`` hook then
 * replaces them with ``DEFAULT_WHIMSY_CONFIG``, which is the safest
 * one-shot migration since neither field had a meaningful prior
 * value.
 */
function validateWhimsyConfig(value: unknown): value is WhimsyConfig {
  if (!value || typeof value !== 'object') return false;
  const v = value as Partial<Record<keyof WhimsyConfig, unknown>>;
  return (
    typeof v.enabled === 'boolean' &&
    (v.mode === 'generated' || v.mode === 'preset') &&
    isWhimsyColor(v.backgroundColor) &&
    isWhimsyColor(v.tintColor) &&
    isWhimsyThemeName(v.theme) &&
    isWhimsyPresetId(v.preset) &&
    typeof v.presetSize === 'number' &&
    v.presetSize >= WHIMSY_BOUNDS.presetSize.min &&
    v.presetSize <= WHIMSY_BOUNDS.presetSize.max &&
    typeof v.seed === 'number' &&
    Number.isFinite(v.seed) &&
    typeof v.grid === 'number' &&
    v.grid >= WHIMSY_BOUNDS.grid.min &&
    v.grid <= WHIMSY_BOUNDS.grid.max &&
    typeof v.size === 'number' &&
    v.size >= WHIMSY_BOUNDS.size.min &&
    v.size <= WHIMSY_BOUNDS.size.max &&
    typeof v.opacity === 'number' &&
    v.opacity >= 0 &&
    v.opacity <= 1
  );
}

/**
 * Read/write hook for the whimsy customization. Backed by
 * localStorage with cross-tab sync via the shared
 * {@link usePersistedState} primitive.
 *
 * @returns A `[config, setConfig]` tuple matching React's `useState` signature.
 */
export function useWhimsyConfig(): [WhimsyConfig, Dispatch<SetStateAction<WhimsyConfig>>] {
  return usePersistedState<WhimsyConfig>({
    storageKey: WHIMSY_STORAGE_KEY,
    defaultValue: DEFAULT_WHIMSY_CONFIG,
    validate: validateWhimsyConfig,
  });
}
