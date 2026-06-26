'use client';

/**
 * Whimsy texture — CSS mask URL hook.
 *
 * Generates a tileable mask URL from the persisted whimsy config and
 * memoizes it on every input that affects the rendered SVG.  Cheap to
 * call from any component; regenerates only when the user changes a
 * relevant setting.
 */

import { useMemo } from 'react';
import { whimsyPresetUrl } from '@/lib/whimsy-presets';
import { generateWhimsyTile, svgToDataUri, WHIMSY_THEMES } from '@/lib/whimsy-tile';
import { useWhimsyConfig } from './config';

/** Result of {@link useWhimsyTile} — the inputs a consumer needs to render the overlay. */
export interface UseWhimsyTileResult {
  /**
   * CSS `url("data:image/svg+xml,...")` value ready to drop into
   * `mask-image`.  `null` when the user has disabled the texture —
   * consumers should skip rendering the overlay entirely in that case.
   */
  cssUrl: string | null;
  /**
   * Ready-to-drop ``mask-size`` value.  In ``generated`` mode the
   * source SVG is square so this is ``"<size>px <size>px"``.  In
   * ``preset`` mode the source SVGs are portrait (~1125×2436); we
   * set the width and let the height resolve from the SVG's
   * intrinsic aspect via ``auto`` so adjacent tiles meet
   * edge-to-edge instead of leaving empty bands between repeats.
   */
  maskSize: string;
  /**
   * Custom background colour to paint under the masked tile.
   * ``null`` means "use the parent's existing background"; a CSS
   * colour string overrides.
   */
  backgroundColor: string | null;
  /**
   * CSS colour to use for the masked-tile fill.  Either a hex
   * string the user picked or ``"currentColor"`` when the config is
   * ``"theme"`` — consumers can drop this directly into
   * ``backgroundColor`` on the overlay element.
   */
  tintColor: string;
  /** Stored opacity (0..1) — apply via CSS `opacity` on the overlay element. */
  opacity: number;
}

/**
 * Generate the CSS mask URL + ancillary render inputs for the whimsy
 * texture overlay.
 *
 * In ``preset`` mode the URL is a static asset under
 * ``/whimsy-patterns/`` and the returned mask size is fixed at the
 * persisted ``presetSize`` — the user's ``size`` slider is ignored,
 * since it's only meaningful for the procedural generator.  In
 * ``generated`` mode we build a tile in-memory and inline it as a
 * data URI (cheaper round-trip and lets the seed/density knobs drive
 * the SVG live).
 */
export function useWhimsyTile(): UseWhimsyTileResult {
  const [config] = useWhimsyConfig();
  const cssUrl = useMemo(() => {
    if (!config.enabled) return null;
    if (config.mode === 'preset') {
      return `url("${whimsyPresetUrl(config.preset)}")`;
    }
    const svg = generateWhimsyTile({
      size: config.size,
      seed: config.seed,
      grid: config.grid,
      motifs: WHIMSY_THEMES[config.theme],
    });
    return `url("${svgToDataUri(svg)}")`;
  }, [config.enabled, config.mode, config.preset, config.size, config.seed, config.grid, config.theme]);
  const maskSize = config.mode === 'preset' ? `${config.presetSize}px auto` : `${config.size}px ${config.size}px`;
  const backgroundColor = config.backgroundColor === 'theme' ? null : config.backgroundColor;
  const tintColor = config.tintColor === 'theme' ? 'currentColor' : config.tintColor;
  return { cssUrl, maskSize, backgroundColor, tintColor, opacity: config.opacity };
}
