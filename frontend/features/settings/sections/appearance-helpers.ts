/**
 * Static mock data + label maps for the Settings → Appearance visual-mock
 * section.
 *
 * Lives next to `AppearanceSection.tsx` so the section file stays small.
 * Anything that doesn't render JSX or hold component state belongs here.
 *
 * As of 2026-05-06 this file no longer references the deleted
 * `@/features/appearance` module — the types and defaults are inlined as
 * mock data and have a `Mock` prefix so any future re-import doesn't
 * silently re-bind to a system that's gone. See
 * `frontend/content/docs/handbook/decisions/2026-05-06-rip-theming-system.md`.
 */

import { LaptopMinimal, Moon, Sun } from 'lucide-react';

/** Tuple of the six semantic color slots the visual mock displays. */
export const COLOR_SLOTS = [
	'background',
	'foreground',
	'accent',
	'info',
	'success',
	'destructive',
] as const;

/** Single color slot key (`'background' | 'foreground' | ...`). */
export type ColorSlot = (typeof COLOR_SLOTS)[number];

/** Tuple of the three font family slots the visual mock displays. */
export const FONT_SLOTS = ['display', 'sans', 'mono'] as const;

/** Single font slot key. */
export type FontSlot = (typeof FONT_SLOTS)[number];

/** Theme-mode options shown in the top-of-card switcher. */
export const THEME_MODE_OPTIONS = [
	{ id: 'light', label: 'Light', Icon: Sun },
	{ id: 'dark', label: 'Dark', Icon: Moon },
	{ id: 'system', label: 'System', Icon: LaptopMinimal },
] as const;

/** Theme-mode the user can pick in the Appearance panel. */
export type ThemeMode = (typeof THEME_MODE_OPTIONS)[number]['id'];

/** Per-mode color overrides — partial record so unset slots fall back to defaults. */
export type MockThemeColors = {
	[K in ColorSlot]?: string | null;
};

/** Font family overrides applied to the mock. */
export type MockAppearanceFonts = {
	[K in FontSlot]?: string | null;
};

/** Behavior + numeric options exposed by the visual mock. */
export interface MockAppearanceOptions {
	theme_mode?: ThemeMode | null;
	translucent_sidebar?: boolean | null;
	contrast?: number | null;
	pointer_cursors?: boolean | null;
	ui_font_size?: number | null;
}

/** Preset shape consumed by the per-mode preset picker. Font values are
	non-nullable so the preview can pass `fonts.display` directly to a
	`style.fontFamily` prop without coercion. */
export interface MockThemePreset {
	id: string;
	name: string;
	description: string;
	light: MockThemeColors;
	dark: MockThemeColors;
	fonts: Record<FontSlot, string>;
}

/** Light-mode color defaults — mirrors the values in `globals.css`. */
export const DEFAULT_LIGHT_COLORS: Record<ColorSlot, string> = {
	background: 'oklch(0.973 0.014 90)',
	foreground: 'oklch(0.21 0.005 285)',
	accent: 'oklch(0.704 0.102 285)',
	info: 'oklch(0.783 0.119 255)',
	success: 'oklch(0.50 0.12 165)',
	destructive: 'oklch(0.55 0.20 355)',
};

/** Dark-mode color defaults — mirrors the values in `globals.css`. */
export const DEFAULT_DARK_COLORS: Record<ColorSlot, string> = {
	background: 'oklch(0.145 0.005 285)',
	foreground: 'oklch(0.9158314607 0 0)',
	accent: 'oklch(0.704 0.102 285)',
	info: 'oklch(0.783 0.119 255)',
	success: 'oklch(0.50 0.09 165)',
	destructive: 'oklch(0.55 0.20 355)',
};

/** Default font stacks — mirrors `globals.css` font tokens. */
export const DEFAULT_FONTS: Record<FontSlot, string> = {
	display:
		'var(--font-display-loaded, "Newsreader"), "Iowan Old Style", "Charter", Georgia, "Times New Roman", serif',
	sans: 'var(--font-google-sans-flex-loaded, "Google Sans Flex"), var(--font-google-sans-loaded, "Google Sans"), "Helvetica Neue", sans-serif',
	mono: '"JetBrains Mono", ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace',
};

/** Default behavioral toggles. */
export const DEFAULT_OPTIONS: Required<MockAppearanceOptions> = {
	theme_mode: 'system',
	translucent_sidebar: false,
	contrast: 60,
	pointer_cursors: true,
	ui_font_size: 16,
};

/** Mock preset list — unified Pawrrtal default plus Cursor for warm-grey lovers. */
export const THEME_PRESETS: ReadonlyArray<MockThemePreset> = [
	{
		id: 'pawrrtal',
		name: 'Pawrrtal',
		description:
			'Warm off-white canvas, soft purple accent, soft blue info, forest green success.',
		light: DEFAULT_LIGHT_COLORS,
		dark: DEFAULT_DARK_COLORS,
		fonts: DEFAULT_FONTS,
	},
	{
		id: 'cursor',
		name: 'Cursor',
		description: 'Cool warm-grey canvas, orange CTAs, Geist sans typography.',
		light: {
			background: '#f7f7f4',
			foreground: '#26251e',
			accent: '#f54e00',
			info: '#a06a3a',
			success: '#2f7d51',
			destructive: '#d04200',
		},
		dark: {
			background: '#0d0d0c',
			foreground: '#ededea',
			accent: '#ff7a3a',
			info: '#d6a468',
			success: '#5fbb84',
			destructive: '#ff5b30',
		},
		fonts: {
			display: '"Geist", "Inter", system-ui, -apple-system, BlinkMacSystemFont, sans-serif',
			sans: '"Geist", "Inter", system-ui, -apple-system, BlinkMacSystemFont, sans-serif',
			mono: '"Geist Mono", "JetBrains Mono", ui-monospace, "SF Mono", Menlo, monospace',
		},
	},
];

/** Human-readable labels for each color slot. */
export const COLOR_LABELS: Record<ColorSlot, string> = {
	background: 'Background',
	foreground: 'Foreground',
	accent: 'Accent',
	info: 'Info',
	success: 'Success',
	destructive: 'Destructive',
};

/** Human-readable labels for each font slot. */
export const FONT_LABELS: Record<FontSlot, string> = {
	display: 'Display font',
	sans: 'UI font',
	mono: 'Code font',
};

/**
 * Resolve any CSS color string (hex, rgb, oklch, named) into a `#rrggbb`
 * literal that `<input type="color">` accepts. Used by the color-pill
 * picker; falls back to `#888888` on SSR or unparseable input.
 */
export function toHex(value: string | undefined | null): string {
	if (!value) return '#888888';
	const trimmed = value.trim();
	if (/^#[0-9a-f]{6}$/i.test(trimmed)) return trimmed.toLowerCase();
	if (typeof document === 'undefined') return '#888888';
	const ctx = document.createElement('canvas').getContext('2d');
	if (!ctx) return '#888888';
	try {
		ctx.fillStyle = '#000';
		ctx.fillStyle = trimmed;
		const computed = ctx.fillStyle;
		if (typeof computed === 'string' && /^#[0-9a-f]{6}$/i.test(computed)) {
			return computed.toLowerCase();
		}
	} catch {
		/* fall through to fallback */
	}
	return '#888888';
}

/** Debounce window (ms) for the color hex / font family text inputs. */
export const TEXT_INPUT_DEBOUNCE_MS = 250;
