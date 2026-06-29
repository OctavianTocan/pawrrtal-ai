'use client';

/**
 * Local primitives used only by the settings surface.
 *
 * Lives in-feature rather than `components/ui` because today these are not
 * shared anywhere else — promote them out if a second feature needs them.
 *
 * Visual rhythm derived from the Codex settings reference:
 * - Page heading: text-3xl, tight tracking, balanced wrap
 * - Section heading inside a card: text-base, semibold, paired with a
 *   muted text-pretty description
 * - Row vertical padding: py-4 (default) — descriptions wrap on the left,
 *   control sits hard-right with tabular-nums for hex/value alignment
 * - Surfaces use `border-border` + `bg-card` (theme tokens) rather than
 *   raw `foreground/[0.0X]` so a switch to the dark theme inherits the
 *   right tint instead of stamping a black-on-black wash
 *
 * @fileoverview Switch, Slider, ColorPill, and labelled-row helpers
 *               for the settings UI.
 */

import { Slider as SliderPrimitive, Switch as SwitchPrimitive } from 'radix-ui';
import type { ChangeEvent, ReactNode } from 'react';
import { useCallback, useEffect, useMemo, useRef } from 'react';
import { cn } from '@/lib/utils';

/**
 * Pick a near-black or near-white foreground that contrasts against
 * `background`.
 *
 * Why luminance over `mix-blend-mode: difference`: difference inverts
 * each channel (255 - bg), so a mid-tone pill (e.g. `#3fa760` —
 * Success green) maps to roughly `(192, 88, 159)` against white-with-
 * difference, which lands as a muddy mid-tone instead of a readable
 * label. Real luminance (BT.709) tells us whether the surface is
 * "light" or "dark" and we pick a strong contrasting flat color
 * instead — predictable on every preset, including warm greens and
 * oranges.
 *
 * Falls back to `#fafafa` when the canvas can't parse `background`
 * (SSR, exotic color spaces) so the pill still has a legible label.
 *
 * @param background - Any CSS color string the pill is filled with.
 * @returns `#0b0b0b` for light backgrounds, `#fafafa` for dark.
 */
function pickContrastForeground(background: string): string {
  if (typeof document === 'undefined') return '#fafafa';
  const ctx = document.createElement('canvas').getContext('2d');
  if (!ctx) return '#fafafa';
  try {
    ctx.fillStyle = '#000';
    ctx.fillStyle = background;
    const computed = ctx.fillStyle;
    // Canvas normalises every parseable CSS color to `#rrggbb` (or
    // `rgba(...)`). Hex is the common case for our pills.
    const hex = typeof computed === 'string' ? computed : '';
    const match = /^#([0-9a-f]{6})$/i.exec(hex);
    const channels = match?.[1];
    if (!channels) return '#fafafa';
    const value = Number.parseInt(channels, 16);
    const r = (value >> 16) & 0xff;
    const g = (value >> 8) & 0xff;
    const b = value & 0xff;
    // BT.709 relative luminance against the 0-255 channel range.
    // We don't bother sRGB-linearising for this binary decision —
    // the threshold is well-clear of any preset slot.
    const luminance = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
    return luminance > 0.6 ? '#0b0b0b' : '#fafafa';
  } catch {
    return '#fafafa';
  }
}

/**
 * Compact accent-tinted toggle.
 *
 * Renders a Radix Switch with the project's accent + border tokens so it
 * visually matches the toggle in the reference screenshots without a full
 * shadcn-style component file. Sized at h-6 w-11 / thumb size-5 — Fitts-
 * compliant for trackpad use without crowding the row.
 */
export function Switch({ className, ...props }: React.ComponentProps<typeof SwitchPrimitive.Root>): React.JSX.Element {
  return (
    <SwitchPrimitive.Root
      className={cn(
        'peer inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full',
        'border border-border bg-foreground/10 transition-colors duration-150',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40',
        'data-[state=checked]:border-accent data-[state=checked]:bg-accent',
        'disabled:cursor-not-allowed disabled:opacity-50',
        className
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        className={cn(
          'pointer-events-none block size-5 rounded-full bg-background shadow-sm ring-0',
          'transition-transform duration-150 ease-out',
          'data-[state=checked]:translate-x-5 data-[state=unchecked]:translate-x-0.5'
        )}
      />
    </SwitchPrimitive.Root>
  );
}

/**
 * Single-thumb slider with the project's accent fill on the active track.
 *
 * Matches the contrast slider in the Appearance section — value + range
 * accepted as numbers so consumers can hold local state without coercing.
 */
export function Slider({ className, ...props }: React.ComponentProps<typeof SliderPrimitive.Root>): React.JSX.Element {
  return (
    <SliderPrimitive.Root
      className={cn('relative flex w-full cursor-pointer touch-none select-none items-center', className)}
      {...props}
    >
      <SliderPrimitive.Track className="relative h-1 w-full grow overflow-hidden rounded-full bg-foreground/10">
        <SliderPrimitive.Range className="absolute h-full bg-accent" />
      </SliderPrimitive.Track>
      <SliderPrimitive.Thumb
        aria-label="Slider value"
        className="block size-4 rounded-full border-2 border-accent bg-background shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40"
      />
    </SliderPrimitive.Root>
  );
}

/** Props for the labelled row used throughout the settings sections. */
export type SettingsRowProps = {
  /** Bold label rendered on the left. */
  label: ReactNode;
  /** Optional secondary helper text under the label. */
  description?: ReactNode;
  /** The control / value rendered on the right. */
  children: ReactNode;
  /** Override classes on the outer row. */
  className?: string;
};

/**
 * Two-column row used by every settings section (label/description on the
 * left, control on the right).
 *
 * Mirrors the Codex settings layout — label/description column on the
 * left (capped at 60% so descriptions wrap before crowding the control),
 * control column right-aligned. Hairline divider uses `--border` so it
 * inherits the active theme rather than a hard-coded foreground tint.
 *
 * Override with `className` (e.g. `items-start`) when stacking taller
 * controls like textareas.
 */
export function SettingsRow({ label, description, children, className }: SettingsRowProps): React.JSX.Element {
  return (
    <div
      className={cn(
        'flex items-center justify-between gap-6 border-border/40 border-b py-4 first:pt-2 last:border-0 last:pb-2',
        className
      )}
    >
      <div className="flex min-w-0 max-w-[60%] flex-col gap-1">
        <span className="text-pretty font-medium text-foreground text-sm tabular-nums">{label}</span>
        {description ? (
          <span className="text-pretty text-muted-foreground text-sm tabular-nums leading-snug">{description}</span>
        ) : null}
      </div>
      <div className="flex shrink-0 items-center justify-end gap-2 text-right">{children}</div>
    </div>
  );
}

/** Props for the section card wrapper. */
export type SettingsCardProps = {
  /** Section heading rendered above the card body. */
  title?: ReactNode;
  /** Optional helper line under the title. */
  description?: ReactNode;
  /** Card body — typically a stack of `SettingsRow`s. */
  children: ReactNode;
  /** Override classes on the card root. */
  className?: string;
};

/**
 * Card surface used to group related rows in a settings section.
 *
 * Uses theme-aware tokens (`bg-card`) plus the project's `shadow-edge`
 * utility (1 px white inset highlight + 1 px black 4 % outer shadow) so
 * the card reads as a sharp, dimensional surface rather than a flat
 * gray-bordered panel. See DESIGN.md → Elevation & Depth → Edges for
 * why we stopped using bare 1 px borders here.
 */
export function SettingsCard({ title, description, children, className }: SettingsCardProps): React.JSX.Element {
  return (
    <section className={cn('rounded-[14px] bg-card px-6 pt-3 pb-3 shadow-edge', className)}>
      {title || description ? (
        <header className="mb-1 flex flex-col gap-1 pt-2">
          {title ? <h3 className="font-semibold text-base text-foreground tracking-tight">{title}</h3> : null}
          {description ? <p className="text-pretty text-muted-foreground text-sm leading-snug">{description}</p> : null}
        </header>
      ) : null}
      <div className="flex flex-col">{children}</div>
    </section>
  );
}

/** Props for the page-level shell wrapping every Settings section. */
export type SettingsPageProps = {
  /** Page title rendered as `<h1>` at the top. */
  title: ReactNode;
  /** Optional sub-line beneath the title (text-pretty, muted). */
  description?: ReactNode;
  /** Page body — typically a stack of `SettingsCard`s. */
  children: ReactNode;
  /** Override classes on the page root. */
  className?: string;
};

/**
 * Page-level shell EVERY Settings section MUST wrap itself in.
 *
 * Standardises the outer rhythm — same `<h1>` size, same gap below the
 * title, same gap between sections, same `text-pretty` description.
 * Bespoke `<header><h1>` blocks per section are a consistency bug; use
 * this instead. Documented in `DESIGN.md` →
 * `Components` → `settings-page-shell`.
 *
 * Heading bumped to `text-3xl` to match the Codex page-level title
 * (was `text-2xl`); kerning stays `tracking-tight` so long words like
 * "Personalization" don't drift.
 */
export function SettingsPage({ title, description, children, className }: SettingsPageProps): React.JSX.Element {
  return (
    <div className={cn('flex flex-col gap-8', className)}>
      <header className="flex flex-col gap-2">
        <h1 className="text-balance font-semibold text-3xl text-foreground tracking-tight">{title}</h1>
        {description ? (
          <p className="max-w-[60ch] text-pretty text-muted-foreground text-sm leading-relaxed">{description}</p>
        ) : null}
      </header>
      <div className="flex flex-col gap-6">{children}</div>
    </div>
  );
}

/** Props for the consistent settings-section header. */
export type SettingsSectionHeaderProps = {
  /** Section heading rendered on the left. */
  title: ReactNode;
  /** Sub-line under the title (small, muted, `text-pretty`). */
  description?: ReactNode;
  /** Right-aligned actions / pickers (e.g. preset selector, mode toggle). */
  actions?: ReactNode;
  /**
   * Drop the bottom hairline. Use for cards where the header is the only
   * content — without this, the divider reads as a stray separator at the
   * bottom of the card.
   */
  noDivider?: boolean;
};

/**
 * Standard top-of-card header used by every section / sub-section
 * across Settings — title (`text-base font-semibold tracking-tight`),
 * description (`text-sm text-muted-foreground text-pretty`), and an
 * optional right-aligned actions slot. Centralised so every section
 * shares the exact same vertical rhythm and type rules — no more
 * bespoke one-off headers.
 *
 * Use INSIDE a `SettingsCard` (not as a replacement for it). The
 * `SettingsCard` handles the rounded surface; this primitive renders
 * the header row with its bottom hairline.
 */
export function SettingsSectionHeader({
  title,
  description,
  actions,
  noDivider,
}: SettingsSectionHeaderProps): React.JSX.Element {
  return (
    <header
      className={cn('flex items-start justify-between gap-3 pt-1 pb-3', !noDivider && 'border-border/40 border-b')}
    >
      <div className="flex min-w-0 flex-col gap-1">
        {/* Semantic `<h3>` so this matches `SettingsCard`'s standalone
				   title path (also `<h3>`). Using a `<span>` previously meant
				   the two header surfaces shared classes but rendered as
				   different elements, which subtly nudged user-agent line-
				   heights and broke the assumption that both render
				   identically. */}
        <h3 className="font-semibold text-base text-foreground tracking-tight">{title}</h3>
        {description ? <p className="text-pretty text-muted-foreground text-sm leading-snug">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </header>
  );
}

/** Props for the {@link ColorPill} primitive. */
export interface ColorPillProps {
  /** Accessible label for the picker (e.g. "Accent color picker"). */
  ariaLabel: string;
  /** The fully-resolved color the pill should render. Any CSS color works. */
  resolvedColor: string;
  /** The hex literal used to seed `<input type="color">`. */
  pickerSeed: string;
  /** Display value (typically the typed override; falls back to defaultValue). */
  displayValue: string;
  /** Placeholder when {@link displayValue} is empty (e.g. the slot's default hex). */
  placeholder: string;
  /** Fired when the user types into the value field. */
  onValueChange: (value: string) => void;
  /** Fired when the native color picker emits a new value (RAF-batched upstream). */
  onPickerChange: (value: string) => void;
}

/**
 * Codex-style filled color pill.
 *
 * The entire pill background renders as the resolved color; the hex /
 * literal value floats on top in tabular-nums with a contrast-adaptive
 * foreground. Clicking anywhere on the pill opens the OS color picker
 * via an invisible `<input type="color">` overlay — same trick the
 * Appearance section used before, but the swatch is now the *whole*
 * affordance rather than a 20px circle next to a bare text input.
 *
 * The native picker is left UNCONTROLLED (`defaultValue` + `key`) so
 * that mid-drag re-renders triggered by upstream state updates don't
 * snap the OS picker back to a stale value (the "lurping" bug). The
 * commit handler should RAF-batch upstream updates so a 60fps drag
 * produces ≤60 PUTs/s instead of hundreds.
 */
export function ColorPill({
  ariaLabel,
  resolvedColor,
  pickerSeed,
  displayValue,
  placeholder,
  onValueChange,
  onPickerChange,
}: ColorPillProps): React.JSX.Element {
  const handleValueChange = useCallback(
    (event: ChangeEvent<HTMLInputElement>) => onValueChange(event.target.value),
    [onValueChange]
  );
  const handlePickerChange = useCallback(
    (event: ChangeEvent<HTMLInputElement>) => onPickerChange(event.target.value),
    [onPickerChange]
  );

  const inputRef = useRef<HTMLInputElement | null>(null);
  useEffect(() => {
    // Re-seed the uncontrolled picker on external resets (preset apply,
    // server refetch). Using `defaultValue + key` would re-mount the
    // node mid-drag and steal focus; setting `value` here only fires
    // when the seed changes outside the picker's own onChange loop.
    if (inputRef.current && inputRef.current.value !== pickerSeed) {
      inputRef.current.value = pickerSeed;
    }
  }, [pickerSeed]);

  // Compute a flat contrast color so mid-tone pills (warm greens,
  // oranges, browns) get a readable label. `mix-blend-mode: difference`
  // fails on those — it folds (255 - bg) per channel and a green like
  // `#3fa760` ends up rendering the label as a muddy mid-tone instead
  // of crisp on/off-white. See `pickContrastForeground` above.
  const foregroundColor = useMemo(() => pickContrastForeground(resolvedColor), [resolvedColor]);

  return (
    <label
      aria-label={ariaLabel}
      className="group relative flex h-7 min-w-36 cursor-pointer items-center justify-center overflow-hidden rounded-full border border-border/50 px-3 transition-shadow duration-150 focus-within:ring-2 focus-within:ring-ring/40 hover:shadow-sm"
      style={{ backgroundColor: resolvedColor }}
    >
      <input
        aria-label={`${ariaLabel} value`}
        className="w-full bg-transparent text-center font-mono text-xs tabular-nums outline-none placeholder:text-current/60"
        onChange={handleValueChange}
        placeholder={placeholder}
        style={{ color: foregroundColor }}
        type="text"
        value={displayValue}
      />
      {/* Native color picker — clicking the pill opens the OS dialog.
			    Uncontrolled via `defaultValue` + ref-driven re-seed, see
			    the `pickerSeed` effect above for why this is NOT
			    controlled. */}
      <input
        aria-label={`${ariaLabel} color picker`}
        className="absolute inset-0 size-full cursor-pointer opacity-0"
        defaultValue={pickerSeed}
        onChange={handlePickerChange}
        ref={inputRef}
        type="color"
      />
    </label>
  );
}
