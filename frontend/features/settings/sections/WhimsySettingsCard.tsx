'use client';

/**
 * Settings → Appearance card for the whimsy texture.
 *
 * All controls write to the same localStorage key consumed by
 * {@link useWhimsyTile}, so changes propagate to the chat panel live
 * (and across tabs).  The card itself is a thin orchestrator over
 * three sub-components:
 *
 * - {@link WhimsyPresetModeRows}  — only rendered in `preset` mode.
 * - {@link WhimsyThemeRow}        — only rendered in `generated` mode
 *                                   (presets ignore theme).
 * - {@link WhimsyGeneratedModeRows} — only rendered in `generated` mode.
 *
 * Plus the always-rendered rows: Show texture, Source, Background
 * colour, Tile tint, Opacity.
 */

import { Shuffle } from 'lucide-react';
import type { Dispatch, SetStateAction } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import type { SelectButtonOption } from '@/components/ui/select-button';
import { SelectButton } from '@/components/ui/select-button';
import type { WhimsyColor, WhimsyConfig, WhimsyMode } from '@/features/whimsy/config';
import {
  DEFAULT_WHIMSY_CONFIG,
  isWhimsyThemeName,
  OPACITY_SLIDER_DIVISOR,
  useWhimsyConfig,
  WHIMSY_BOUNDS,
  WHIMSY_THEME_NAMES,
} from '@/features/whimsy/config';
import { cn } from '@/lib/utils';
import { WHIMSY_PRESETS, whimsyPresetUrl } from '@/lib/whimsy-presets';
import type { WhimsyThemeName } from '@/lib/whimsy-tile';
import { WHIMSY_THEMES } from '@/lib/whimsy-tile';
import { SettingsCard, SettingsRow, SettingsSectionHeader, Slider, Switch } from '../primitives';

// ─────────────────────────────────────────────────────────────────────────────
// Module-local labels + options
// ─────────────────────────────────────────────────────────────────────────────

/** Human-readable labels for the dropdown trigger and option list. */
const THEME_LABELS: Record<WhimsyThemeName, string> = {
  kawaii: 'Kawaii (everything)',
  cosmic: 'Cosmic (stars, moons)',
  botanical: 'Botanical (flowers, drops)',
  geometric: 'Geometric (diamonds, plus)',
  cute: 'Cute (hearts, flowers)',
  minimal: 'Minimal (dots, plus)',
  playful: 'Playful (Telegram-style)',
};

/** Static option list for the theme dropdown. */
const THEME_OPTIONS: readonly SelectButtonOption[] = WHIMSY_THEME_NAMES.map((name) => ({
  id: name,
  label: THEME_LABELS[name],
  description: WHIMSY_THEMES[name].join(', '),
}));

/** Human-readable labels for the source-mode segmented toggle. */
const MODE_LABELS: Record<WhimsyMode, string> = {
  generated: 'Generated tile',
  preset: 'Preset pattern',
};

// ─────────────────────────────────────────────────────────────────────────────
// Colour picker
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Default starter colour used when the user clicks the swatch while
 * still on ``"theme"``.  Picked to be a neutral mid-tone so the first
 * picker interaction doesn't blast the panel with a vivid hue.
 */
const COLOR_PICKER_FALLBACK = '#cbd5e1';

interface WhimsyColorPickerProps {
  /** Current persisted value — either ``'theme'`` or a ``#rrggbb`` string. */
  value: WhimsyColor;
  /** Called with the new value when the user picks a colour or resets. */
  onChange: (next: WhimsyColor) => void;
}

/**
 * Compact swatch + native colour picker pair with a "Reset to theme" toggle.
 *
 * Uses the browser's native ``<input type="color">`` to keep the
 * dependency footprint zero — the platform widget is good enough for
 * tints, and we can upgrade to ``react-colorful`` later if/when we
 * want HSL/alpha controls.
 */
function WhimsyColorPicker({ value, onChange }: WhimsyColorPickerProps): React.JSX.Element {
  // Native colour inputs require a hex value at all times — never
  // ``undefined`` or a token string — so we feed the fallback when
  // the persisted value is ``'theme'``.  The user picking a colour
  // transitions the value off ``'theme'``.
  const hexValue = value === 'theme' ? COLOR_PICKER_FALLBACK : value;
  const isThemeDefault = value === 'theme';
  return (
    <div className="flex items-center gap-2">
      <label
        className="relative inline-flex size-7 cursor-pointer items-center justify-center overflow-hidden rounded-[6px] shadow-edge"
        style={{ backgroundColor: hexValue }}
      >
        <input
          aria-label="Pick colour"
          className="absolute inset-0 cursor-pointer opacity-0"
          onChange={(event) => onChange(event.target.value)}
          type="color"
          value={hexValue}
        />
      </label>
      <span className="font-mono text-muted-foreground text-xs tabular-nums">
        {isThemeDefault ? 'theme' : hexValue}
      </span>
      {!isThemeDefault ? (
        <Button className="cursor-pointer" onClick={() => onChange('theme')} size="xs" type="button" variant="ghost">
          Reset
        </Button>
      ) : null}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Mode-specific row groups
// ─────────────────────────────────────────────────────────────────────────────

interface WhimsyRowProps {
  config: WhimsyConfig;
  setConfig: Dispatch<SetStateAction<WhimsyConfig>>;
}

/** Tile-scale + preset-thumbnail grid — only rendered in `preset` mode. */
function WhimsyPresetModeRows({ config, setConfig }: WhimsyRowProps): React.JSX.Element {
  return (
    <>
      <SettingsRow
        description="Tile width in CSS pixels. Smaller = denser, larger = bigger doodles with fewer repeats. Height auto-resolves from the source SVG aspect."
        label="Tile scale"
      >
        <div className="flex w-56 items-center gap-3">
          <Slider
            max={WHIMSY_BOUNDS.presetSize.max}
            min={WHIMSY_BOUNDS.presetSize.min}
            onValueChange={(values) => {
              const next = values[0];
              if (typeof next === 'number') setConfig((c) => ({ ...c, presetSize: next }));
            }}
            step={20}
            value={[config.presetSize]}
          />
          <span className="w-14 text-right text-muted-foreground text-xs tabular-nums">{config.presetSize}px</span>
        </div>
      </SettingsRow>
      <SettingsRow
        className="items-start"
        description="Pick from the bundled SVG patterns. Theme/seed/density are ignored in this mode. Click a thumbnail to apply it instantly."
        label="Preset"
      >
        {/*
         * Thumbnail grid instead of a dropdown.  With 33 unlabelled
         * "Pattern N" options the dropdown was useless even if it
         * worked — patterns differ visually, not by name.  Also
         * sidesteps the SelectButton/dropdown bug tracked in the
         * companion bean.
         */}
        <div className="grid w-72 grid-cols-4 gap-1.5">
          {WHIMSY_PRESETS.map((preset) => {
            const isActive = config.preset === preset.id;
            return (
              <button
                aria-label={preset.label}
                aria-pressed={isActive}
                className={cn(
                  'group relative aspect-square cursor-pointer overflow-hidden rounded-[6px] bg-foreground/[0.04] transition-shadow duration-150',
                  'hover:bg-foreground/[0.08]',
                  isActive && 'shadow-[0_0_0_2px_var(--color-accent)]'
                )}
                key={preset.id}
                onClick={() => setConfig((c) => ({ ...c, preset: preset.id }))}
                type="button"
              >
                <span
                  aria-hidden="true"
                  className="absolute inset-0 text-foreground/40"
                  style={{
                    backgroundColor: 'currentColor',
                    maskImage: `url("${whimsyPresetUrl(preset.id)}")`,
                    WebkitMaskImage: `url("${whimsyPresetUrl(preset.id)}")`,
                    // Each thumbnail shows ~one tile of the
                    // pattern; auto height keeps the source
                    // SVG's portrait aspect, so adjacent
                    // thumbnails read as the same family.
                    maskSize: '64px auto',
                    WebkitMaskSize: '64px auto',
                    maskRepeat: 'repeat',
                    WebkitMaskRepeat: 'repeat',
                  }}
                />
              </button>
            );
          })}
        </div>
      </SettingsRow>
    </>
  );
}

/** Theme picker — only rendered in `generated` mode (presets ignore theme). */
function WhimsyThemeRow({ config, setConfig }: WhimsyRowProps): React.JSX.Element {
  return (
    <SettingsRow description="Restricts which motifs the generator can pick from. Pick a curated combo." label="Theme">
      <SelectButton
        activeId={config.theme}
        ariaLabel="Whimsy theme"
        onSelect={(id) => {
          if (isWhimsyThemeName(id)) setConfig((c) => ({ ...c, theme: id }));
        }}
        options={THEME_OPTIONS}
        triggerLabel={THEME_LABELS[config.theme]}
      />
    </SettingsRow>
  );
}

/** Seed + density + tile-size sliders — only rendered in `generated` mode. */
function WhimsyGeneratedModeRows({ config, setConfig }: WhimsyRowProps): React.JSX.Element {
  // Keep the seed comfortably below 2^31 so it round-trips through any
  // integer arithmetic the generator's PRNG does.
  const randomizeSeed = (): void => setConfig((prev) => ({ ...prev, seed: Math.floor(Math.random() * 1_000_000_000) }));

  return (
    <>
      <SettingsRow
        description="Layout randomness. Same seed always renders the same tile; reroll for a new scatter."
        label="Seed"
      >
        <div className="flex items-center gap-2">
          <Input
            aria-label="Whimsy seed"
            className="w-28 text-right text-sm tabular-nums"
            onChange={(event) => {
              const next = Number.parseInt(event.target.value, 10);
              if (Number.isFinite(next)) setConfig((c) => ({ ...c, seed: next }));
            }}
            type="number"
            value={config.seed}
          />
          <Button
            aria-label="Randomize seed"
            className="cursor-pointer"
            onClick={randomizeSeed}
            size="icon-xs"
            type="button"
            variant="ghost"
          >
            <Shuffle aria-hidden="true" />
          </Button>
        </div>
      </SettingsRow>

      <SettingsRow description="Motifs per row/column inside one tile. Higher = denser pattern." label="Density">
        <div className="flex w-56 items-center gap-3">
          <Slider
            max={WHIMSY_BOUNDS.grid.max}
            min={WHIMSY_BOUNDS.grid.min}
            onValueChange={(values) => {
              const next = values[0];
              if (typeof next === 'number') setConfig((c) => ({ ...c, grid: next }));
            }}
            step={1}
            value={[config.grid]}
          />
          <span className="w-12 text-right text-muted-foreground text-xs tabular-nums">
            {config.grid}×{config.grid}
          </span>
        </div>
      </SettingsRow>

      <SettingsRow
        description="Pixels per repeating tile. Smaller tiles repeat more often, so motifs feel denser without changing the grid."
        label="Tile size"
      >
        <div className="flex w-56 items-center gap-3">
          <Slider
            max={WHIMSY_BOUNDS.size.max}
            min={WHIMSY_BOUNDS.size.min}
            onValueChange={(values) => {
              const next = values[0];
              if (typeof next === 'number') setConfig((c) => ({ ...c, size: next }));
            }}
            step={20}
            value={[config.size]}
          />
          <span className="w-12 text-right text-muted-foreground text-xs tabular-nums">{config.size}px</span>
        </div>
      </SettingsRow>
    </>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main card
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Settings card mounted under Settings → Appearance.  Reads/writes the
 * persisted whimsy config and renders one row per knob, with mode-
 * specific groups branching off the `mode` switch.
 */
export function WhimsySettingsCard(): React.JSX.Element {
  const [config, setConfig] = useWhimsyConfig();

  const reset = (): void => setConfig(DEFAULT_WHIMSY_CONFIG);

  // Slider stores integer 0-200 for fine control while the persisted
  // opacity stays a 0-0.20 decimal — matches how AppearanceSection's
  // contrast slider surfaces a percentage label without changing the
  // persisted scale.
  const opacitySliderValue = Math.round(config.opacity * OPACITY_SLIDER_DIVISOR);

  return (
    <SettingsCard>
      <SettingsSectionHeader
        actions={
          <Button className="cursor-pointer" onClick={reset} size="xs" type="button" variant="ghost">
            Reset
          </Button>
        }
        description="Decorative kawaii texture rendered behind the chat panel. Experimental — every control here is local to this browser."
        title="Whimsy texture"
      />

      <SettingsRow description="Toggle the texture overlay on or off." label="Show texture">
        <Switch
          aria-label="Show texture"
          checked={config.enabled}
          onCheckedChange={(enabled) => setConfig((c) => ({ ...c, enabled }))}
        />
      </SettingsRow>

      <SettingsRow
        description="Generated tiles are procedural and respond to the seed/density knobs below. Presets are hand-laid SVG wallpapers that ignore those knobs."
        label="Source"
      >
        {/*
         * Two-button segmented toggle.  With only two options a
         * dropdown is more friction than the choice merits, and the
         * segmented pattern surfaces the active mode without an
         * extra click — which also sidesteps a regression where the
         * SelectButton's onSelect didn't propagate the mode change
         * reliably under StrictMode + persisted-state validation.
         * Theme/Preset stay SelectButton-driven because they each
         * have many options.
         */}
        <div className="inline-flex rounded-[7px] bg-foreground/[0.04] p-0.5 font-medium text-xs">
          {(['generated', 'preset'] as const).map((mode) => {
            const isActive = config.mode === mode;
            return (
              <button
                aria-pressed={isActive}
                className={cn(
                  'cursor-pointer rounded-[6px] px-3 py-1 transition-colors duration-150 ease-out',
                  isActive ? 'bg-background text-foreground shadow-thin' : 'text-muted-foreground hover:text-foreground'
                )}
                key={mode}
                onClick={() => setConfig((c) => ({ ...c, mode }))}
                type="button"
              >
                {MODE_LABELS[mode]}
              </button>
            );
          })}
        </div>
      </SettingsRow>

      {config.mode === 'preset' ? (
        <WhimsyPresetModeRows config={config} setConfig={setConfig} />
      ) : (
        <WhimsyThemeRow config={config} setConfig={setConfig} />
      )}

      {config.mode === 'generated' ? <WhimsyGeneratedModeRows config={config} setConfig={setConfig} /> : null}

      <SettingsRow
        description="Solid colour painted under the texture. Click the swatch to pick; reset switches back to the theme background."
        label="Background colour"
      >
        <WhimsyColorPicker
          onChange={(next) => setConfig((c) => ({ ...c, backgroundColor: next }))}
          value={config.backgroundColor}
        />
      </SettingsRow>

      <SettingsRow
        description="Tile (mask) colour. Click the swatch to override the theme's foreground colour for the doodles."
        label="Tile tint"
      >
        <WhimsyColorPicker
          onChange={(next) => setConfig((c) => ({ ...c, tintColor: next }))}
          value={config.tintColor}
        />
      </SettingsRow>

      <SettingsRow description="How visible the texture is over the chat panel. The default is 3.5%." label="Opacity">
        <div className="flex w-56 items-center gap-3">
          <Slider
            max={WHIMSY_BOUNDS.opacityScale.max}
            min={WHIMSY_BOUNDS.opacityScale.min}
            onValueChange={(values) => {
              const next = values[0];
              if (typeof next === 'number') {
                setConfig((c) => ({
                  ...c,
                  opacity: next / OPACITY_SLIDER_DIVISOR,
                }));
              }
            }}
            step={5}
            value={[opacitySliderValue]}
          />
          <span className="w-12 text-right text-muted-foreground text-xs tabular-nums">
            {(config.opacity * 100).toFixed(1)}%
          </span>
        </div>
      </SettingsRow>
    </SettingsCard>
  );
}
