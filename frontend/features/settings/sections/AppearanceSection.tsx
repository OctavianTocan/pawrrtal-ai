'use client';

/**
 * Settings → Appearance — visual mock.
 *
 * As of the 2026-05-06 theming rip
 * (`frontend/content/docs/handbook/decisions/2026-05-06-rip-theming-system.md`) this section is a
 * presentation-only shell. The pickers, sliders, and preset buttons
 * render and accept input, but **none of it persists or affects the
 * runtime UI**. There is no provider, no API call, no CSS variable
 * mutation. Local state lives just long enough to make the controls
 * feel responsive while the rebuild is being designed.
 *
 * Once a new theming system lands, the controls here should be re-wired
 * (or the entire section deleted, depending on what the rebuild
 * decides). All references to the deleted `@/features/appearance`
 * module have been inlined here as static mock data.
 */

import type { ReactNode } from 'react';
import { useCallback, useMemo, useState } from 'react';
import { Input } from '@/components/ui/input';
import type { SelectButtonOption } from '@/components/ui/select-button';
import { SelectButton } from '@/components/ui/select-button';
import { cn } from '@/lib/utils';
import { SettingsCard, SettingsPage, SettingsRow, SettingsSectionHeader, Slider, Switch } from '../primitives';
import { ColorRow, FontRow } from './AppearanceRows';
import type {
  ColorSlot,
  FontSlot,
  MockAppearanceFonts,
  MockAppearanceOptions,
  MockThemeColors,
  MockThemePreset,
  ThemeMode,
} from './appearance-helpers';
import {
  COLOR_LABELS,
  COLOR_SLOTS,
  DEFAULT_DARK_COLORS,
  DEFAULT_FONTS,
  DEFAULT_LIGHT_COLORS,
  DEFAULT_OPTIONS,
  FONT_LABELS,
  FONT_SLOTS,
  THEME_MODE_OPTIONS,
  THEME_PRESETS,
} from './appearance-helpers';
import { WhimsySettingsCard } from './WhimsySettingsCard';

/** Top-of-card theme-mode switcher (visual-only). */
function ThemeModeToggle({
  value,
  onChange,
}: {
  value: ThemeMode;
  onChange: (mode: ThemeMode) => void;
}): React.JSX.Element {
  return (
    <div
      aria-label="Theme mode"
      className="flex items-center gap-1 rounded-[8px] border border-border/50 bg-foreground/[0.03] p-0.5"
      role="toolbar"
    >
      {THEME_MODE_OPTIONS.map((option) => {
        const isActive = value === option.id;
        return (
          <button
            aria-pressed={isActive}
            className={cn(
              'flex cursor-pointer items-center gap-1.5 rounded-[6px] px-2.5 py-1 font-medium text-xs',
              'transition-colors duration-150 ease-out',
              isActive
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:bg-foreground/[0.05] hover:text-foreground'
            )}
            key={option.id}
            onClick={() => onChange(option.id)}
            type="button"
          >
            <option.Icon aria-hidden="true" className="size-3.5" />
            <span>{option.label}</span>
          </button>
        );
      })}
    </div>
  );
}

/** Props for the per-mode theme card. */
interface ThemeColorCardProps {
  heading: string;
  description: string;
  overrides: MockThemeColors;
  resolvedColors: Record<ColorSlot, string>;
  defaults: Record<ColorSlot, string>;
  mode: 'light' | 'dark';
  onSlotCommit: (slot: ColorSlot, next: string | null) => void;
  onPresetApply: (preset: MockThemePreset) => void;
  footer?: ReactNode;
}

/** Per-mode theme card — visual-only preview of slot colors + preset picker. */
function ThemeColorCard({
  heading,
  description,
  overrides,
  resolvedColors,
  defaults,
  mode: _mode,
  onSlotCommit,
  onPresetApply,
  footer,
}: ThemeColorCardProps): React.JSX.Element {
  const options = useMemo<SelectButtonOption[]>(
    () =>
      THEME_PRESETS.map((preset) => ({
        id: preset.id,
        label: preset.name,
        description: preset.description,
        leading: (
          <span
            aria-hidden="true"
            className="flex size-5 items-center justify-center rounded-[5px] border border-border/40 bg-background font-medium text-[11px] text-foreground leading-none"
            style={{ fontFamily: preset.fonts.display }}
          >
            Aa
          </span>
        ),
      })),
    []
  );
  const handleSelect = useCallback(
    (presetId: string) => {
      const preset = THEME_PRESETS.find((entry) => entry.id === presetId);
      if (preset) onPresetApply(preset);
    },
    [onPresetApply]
  );

  return (
    <SettingsCard>
      <SettingsSectionHeader
        actions={
          <SelectButton
            ariaLabel={`${heading} preset`}
            onSelect={handleSelect}
            options={options}
            triggerLabel="Apply preset"
          />
        }
        description={description}
        title={heading}
      />
      {COLOR_SLOTS.map((slot) => (
        <ColorRow
          defaultValue={defaults[slot]}
          key={slot}
          label={COLOR_LABELS[slot]}
          onCommit={(next) => onSlotCommit(slot, next)}
          overrideValue={overrides[slot]}
          resolvedValue={resolvedColors[slot]}
        />
      ))}
      {footer}
    </SettingsCard>
  );
}

/** Props for the {@link TypographyCard}. */
interface TypographyCardProps {
  overrides: MockAppearanceFonts;
  uiFontSize: number;
  onFontCommit: (slot: FontSlot, next: string | null) => void;
  onUiFontSize: (next: number) => void;
}

/** Typography card — font-family rows + UI base font-size input (visual-only). */
function TypographyCard({ overrides, uiFontSize, onFontCommit, onUiFontSize }: TypographyCardProps): React.JSX.Element {
  return (
    <SettingsCard>
      <SettingsSectionHeader
        description="Font families and base size that drive the type system across the app."
        title="Typography"
      />
      {FONT_SLOTS.map((slot) => (
        <FontRow
          defaultValue={DEFAULT_FONTS[slot]}
          key={slot}
          label={FONT_LABELS[slot]}
          onCommit={(next) => onFontCommit(slot, next)}
          overrideValue={overrides[slot]}
        />
      ))}
      <SettingsRow description="Drives every rem-denominated value across the app." label="UI font size">
        <div className="flex items-center gap-2">
          <Input
            aria-label="UI font size in pixels"
            className="w-16 text-right text-sm tabular-nums"
            max={32}
            min={10}
            onChange={(event) => {
              const next = Number.parseInt(event.target.value, 10);
              if (Number.isFinite(next)) onUiFontSize(next);
            }}
            type="number"
            value={uiFontSize}
          />
          <span className="text-muted-foreground text-xs">px</span>
        </div>
      </SettingsRow>
    </SettingsCard>
  );
}

/** Props for the {@link BehaviorCard}. */
interface BehaviorCardProps {
  pointerCursors: boolean;
  translucentSidebar: boolean;
  contrast: number;
  onOptionChange: <K extends keyof MockAppearanceOptions>(key: K, next: MockAppearanceOptions[K]) => void;
}

/** Behavior card — interaction toggles + global contrast slider (visual-only). */
function BehaviorCard({
  pointerCursors,
  translucentSidebar,
  contrast,
  onOptionChange,
}: BehaviorCardProps): React.JSX.Element {
  return (
    <SettingsCard>
      <SettingsSectionHeader
        description="Interaction defaults that aren't tied to a specific palette or font."
        title="Behavior"
      />
      <SettingsRow
        description="Change the cursor to a pointer when hovering over interactive elements."
        label="Use pointer cursors"
      >
        <Switch
          aria-label="Use pointer cursors"
          checked={pointerCursors}
          onCheckedChange={(checked) => onOptionChange('pointer_cursors', checked)}
        />
      </SettingsRow>
      <SettingsRow
        description="Use a glass-style backdrop on the sidebar when scenic mode is enabled."
        label="Translucent sidebar"
      >
        <Switch
          aria-label="Translucent sidebar"
          checked={translucentSidebar}
          onCheckedChange={(checked) => onOptionChange('translucent_sidebar', checked)}
        />
      </SettingsRow>
      <SettingsRow
        description="Boosts mid-tone separation across the entire UI. Higher values render bolder borders and stronger contrast on hover states."
        label="Contrast"
      >
        <div className="flex w-56 items-center gap-3">
          <Slider
            max={100}
            min={0}
            onValueChange={(values) => {
              const next = values[0];
              if (typeof next === 'number') onOptionChange('contrast', next);
            }}
            step={1}
            value={[contrast]}
          />
          <span className="w-8 text-right text-muted-foreground text-xs tabular-nums">{contrast}</span>
        </div>
      </SettingsRow>
    </SettingsCard>
  );
}

/** Theme-mode card — owns just the toggle so the orchestrator stays small. */
function ThemeModeCard({
  themeMode,
  onChange,
}: {
  themeMode: ThemeMode;
  onChange: (mode: ThemeMode) => void;
}): React.JSX.Element {
  return (
    <SettingsCard>
      <SettingsSectionHeader
        actions={<ThemeModeToggle onChange={onChange} value={themeMode} />}
        description="Use light, dark, or match your system. Light and dark themes can be picked from different presets independently."
        noDivider
        title="Theme"
      />
    </SettingsCard>
  );
}

/**
 * Visual-mock Appearance settings section.
 *
 * Holds purely local state — there is no provider, no API call, no
 * CSS-variable mutation, no real preset application beyond updating
 * the local preview state. See
 * `frontend/content/docs/handbook/decisions/2026-05-06-rip-theming-system.md` for context.
 */
export function AppearanceSection(): React.JSX.Element {
  const [light, setLight] = useState<MockThemeColors>({});
  const [dark, setDark] = useState<MockThemeColors>({});
  const [fonts, setFonts] = useState<MockAppearanceFonts>({});
  const [options, setOptions] = useState<MockAppearanceOptions>(DEFAULT_OPTIONS);

  const resolvedLight = useMemo<Record<ColorSlot, string>>(() => {
    return { ...DEFAULT_LIGHT_COLORS, ...stripNulls(light) };
  }, [light]);

  const resolvedDark = useMemo<Record<ColorSlot, string>>(() => {
    return { ...DEFAULT_DARK_COLORS, ...stripNulls(dark) };
  }, [dark]);

  const setLightSlot = useCallback((slot: ColorSlot, next: string | null) => {
    setLight((prev) => ({ ...prev, [slot]: next }));
  }, []);

  const setDarkSlot = useCallback((slot: ColorSlot, next: string | null) => {
    setDark((prev) => ({ ...prev, [slot]: next }));
  }, []);

  const setFontSlot = useCallback((slot: FontSlot, next: string | null) => {
    setFonts((prev) => ({ ...prev, [slot]: next }));
  }, []);

  const setOption = useCallback(<K extends keyof MockAppearanceOptions>(key: K, next: MockAppearanceOptions[K]) => {
    setOptions((prev) => ({ ...prev, [key]: next }));
  }, []);

  const applyLightPreset = useCallback((preset: MockThemePreset) => {
    setLight({ ...preset.light });
  }, []);

  const applyDarkPreset = useCallback((preset: MockThemePreset) => {
    setDark({ ...preset.dark });
  }, []);

  return (
    <SettingsPage
      description="Customize colors, typography, and behavior. (Currently a visual mock — controls do not persist or change the runtime UI; see /docs/handbook/decisions/2026-05-06-rip-theming-system.)"
      title="Appearance"
    >
      <ThemeModeCard onChange={(mode) => setOption('theme_mode', mode)} themeMode={options.theme_mode ?? 'system'} />

      <ThemeColorCard
        defaults={DEFAULT_LIGHT_COLORS}
        description="Palette applied when the active theme is light. Pick a preset or fine-tune any of the six semantic slots."
        heading="Light theme"
        mode="light"
        onPresetApply={applyLightPreset}
        onSlotCommit={setLightSlot}
        overrides={light}
        resolvedColors={resolvedLight}
      />
      <ThemeColorCard
        defaults={DEFAULT_DARK_COLORS}
        description="Palette applied when the active theme is dark. Pick a preset or fine-tune any of the six semantic slots."
        heading="Dark theme"
        mode="dark"
        onPresetApply={applyDarkPreset}
        onSlotCommit={setDarkSlot}
        overrides={dark}
        resolvedColors={resolvedDark}
      />

      <TypographyCard
        onFontCommit={setFontSlot}
        onUiFontSize={(next) => setOption('ui_font_size', next)}
        overrides={fonts}
        uiFontSize={options.ui_font_size ?? 16}
      />

      <BehaviorCard
        contrast={options.contrast ?? 60}
        onOptionChange={setOption}
        pointerCursors={options.pointer_cursors ?? true}
        translucentSidebar={options.translucent_sidebar ?? false}
      />

      {/*
       * Whimsy texture customization. Lives in `@/features/whimsy` as a
       * single self-contained module (hook + storage + settings card).
       * Unlike the rest of this section, this card *does* persist and
       * affect the runtime UI (chat panel background) — it intentionally
       * sits at the bottom so its live behavior doesn't get confused
       * with the visual-mock controls above. Remove the import + this
       * line (and the matching call in `ChatView`) to rip it out.
       */}
      <WhimsySettingsCard />
    </SettingsPage>
  );
}

/**
 * Drop nullish entries from a partial record so spreading it on top of
 * the defaults doesn't blast a real default value back to null. The
 * returned type unboxes nullable members to their non-nullable form so
 * the spread result resolves to the defaults' non-nullable shape.
 */
function stripNulls<T extends Record<string, unknown>>(record: T): { [K in keyof T]?: NonNullable<T[K]> } {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(record)) {
    if (value !== null && value !== undefined) {
      out[key] = value;
    }
  }
  return out as { [K in keyof T]?: NonNullable<T[K]> };
}
