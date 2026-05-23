import type { Metadata } from 'next';
import Image from 'next/image';
import type React from 'react';
import { WHIMSY_PRESETS, whimsyPresetUrl } from '@/lib/whimsy-presets';
import {
	generateWhimsyTile,
	svgToDataUri,
	WHIMSY_THEMES,
	type WhimsyThemeName,
} from '@/lib/whimsy-tile';

export const metadata: Metadata = {
	title: 'Whimsy Tile Dev',
	description: 'Dev-only preview page for generated whimsy tile variants.',
};

/**
 * Tile dimension in pixels. Same value is used for the SVG `viewBox`, the CSS
 * `mask-size`, and the single-tile preview image so all three line up.
 */
const TILE_SIZE = 240;

/**
 * Preview tile size for preset patterns — matches the ``PRESET_RENDER_SIZE``
 * constant in ``frontend/features/whimsy/index.tsx`` so this page renders the
 * same way the chat panel will.
 */
const PRESET_TILE_SIZE = 600;

/**
 * Theme presets to display, paired with the seed used in their preview tile.
 * Different seeds make each theme's character easier to read at a glance.
 */
const THEME_VARIANTS: readonly { theme: WhimsyThemeName; seed: number; grid: number }[] = [
	{ theme: 'kawaii', seed: 42, grid: 6 },
	{ theme: 'cosmic', seed: 7, grid: 6 },
	{ theme: 'botanical', seed: 19, grid: 6 },
	{ theme: 'geometric', seed: 31, grid: 6 },
	{ theme: 'cute', seed: 88, grid: 6 },
	{ theme: 'minimal', seed: 4, grid: 6 },
	{ theme: 'playful', seed: 56, grid: 6 },
];

/**
 * Density / seed variants on the default kawaii theme, to demonstrate that
 * seed and grid are independent axes of variation from theme.
 */
const DENSITY_VARIANTS = [
	{ label: 'sparse (seed 13 · grid 4)', seed: 13, grid: 4 },
	{ label: 'default (seed 42 · grid 6)', seed: 42, grid: 6 },
	{ label: 'dense (seed 99 · grid 7)', seed: 99, grid: 7 },
] as const;

interface SampleProps {
	/** Encoded SVG data URI used as the CSS mask. */
	uri: string;
	/** Label rendered in the bottom-left corner of the swatch. */
	caption: string;
	/** Tailwind classes controlling background and `currentColor` (mask color). */
	className: string;
	/** Tailwind class controlling height. Defaults to `h-64`. */
	heightClass?: string;
	/**
	 * CSS ``mask-size``. Defaults to a square based on {@link TILE_SIZE}; preset
	 * previews override with ``"<size>px auto"`` so portrait viewBoxes preserve
	 * their aspect when tiled.
	 */
	maskSize?: string;
}

/**
 * A swatch that fills its area with the tiled pattern. The pattern's color
 * comes from `currentColor` (set via `text-*` utilities), with the SVG acting
 * purely as an alpha mask.
 */
function Sample({
	uri,
	caption,
	className,
	heightClass = 'h-64',
	maskSize = `${TILE_SIZE}px ${TILE_SIZE}px`,
}: SampleProps): React.JSX.Element {
	const cssUri = `url("${uri}")`;
	return (
		<div
			className={`relative ${heightClass} overflow-hidden rounded-lg border border-border ${className}`}
		>
			<div
				className="absolute inset-0"
				style={{
					backgroundColor: 'currentColor',
					maskImage: cssUri,
					WebkitMaskImage: cssUri,
					maskSize,
					WebkitMaskSize: maskSize,
					maskRepeat: 'repeat',
					WebkitMaskRepeat: 'repeat',
				}}
			/>
			<div className="absolute bottom-2 left-2 font-mono text-xs opacity-60">{caption}</div>
		</div>
	);
}

/**
 * Dev-only preview page for the whimsy-tile generator. Demonstrates the three
 * axes of variation — theme (motif set), seed (layout), and grid (density) —
 * over both light and dark surfaces so themed coloring can be eyeballed.
 */
export default function WhimsyTilePage(): React.JSX.Element {
	return (
		<main className="min-h-screen bg-background p-8 text-foreground">
			<div className="mx-auto max-w-5xl space-y-12">
				<header className="space-y-2">
					<h1 className="text-3xl font-semibold tracking-tight">Whimsy tile test</h1>
					<p className="text-muted-foreground">
						Toroidally-tiled motifs rendered as a CSS mask. The mask carries shape only;
						color comes from theme tokens, so light and dark mode adapt automatically.
						Three knobs control the output: <code>theme</code> (motif set),{' '}
						<code>seed</code> (layout), and <code>grid</code> (density).
					</p>
				</header>

				<section className="space-y-4">
					<header className="space-y-1">
						<h2 className="text-xl font-semibold">Theme presets</h2>
						<p className="text-sm text-muted-foreground">
							Each preset restricts the generator to a curated subset of motifs. Pass{' '}
							<code>motifs: WHIMSY_THEMES.cosmic</code> (etc.) to use one.
						</p>
					</header>

					<div className="grid grid-cols-1 gap-4 md:grid-cols-2">
						{THEME_VARIANTS.map(({ theme, seed, grid }) => {
							const motifs = WHIMSY_THEMES[theme];
							const svg = generateWhimsyTile({
								size: TILE_SIZE,
								seed,
								grid,
								motifs,
							});
							const uri = svgToDataUri(svg);
							const caption = `${theme} · ${motifs.join(', ')}`;
							return (
								<Sample
									key={theme}
									uri={uri}
									caption={caption}
									className="bg-background text-foreground/10"
									heightClass="h-56"
								/>
							);
						})}
					</div>
				</section>

				<section className="space-y-4">
					<header className="space-y-1">
						<h2 className="text-xl font-semibold">Density &amp; seed variants</h2>
						<p className="text-sm text-muted-foreground">
							All three use the default <code>kawaii</code> theme. Only{' '}
							<code>seed</code> and <code>grid</code> change. Same surface (light +
							dark) for each.
						</p>
					</header>

					{DENSITY_VARIANTS.map(({ label, seed, grid }) => {
						const svg = generateWhimsyTile({ size: TILE_SIZE, seed, grid });
						const uri = svgToDataUri(svg);
						return (
							<div key={label} className="space-y-3">
								<h3 className="font-mono text-xs uppercase tracking-wider text-muted-foreground">
									{label}
								</h3>

								<div className="grid grid-cols-1 gap-4 md:grid-cols-2">
									<Sample
										uri={uri}
										caption="bg-background · text-foreground/10"
										className="bg-background text-foreground/10"
									/>
									<Sample
										uri={uri}
										caption="bg-foreground · text-background/15"
										className="bg-foreground text-background/15"
									/>
								</div>

								<details className="text-xs text-muted-foreground">
									<summary className="cursor-pointer">Single tile (raw)</summary>
									<Image
										alt={`Single ${label} tile`}
										className="mt-2 inline-block rounded border border-border bg-background p-2 text-foreground"
										height={TILE_SIZE}
										src={uri}
										unoptimized
										width={TILE_SIZE}
									/>
								</details>
							</div>
						);
					})}
				</section>

				<section className="space-y-4">
					<header className="space-y-1">
						<h2 className="text-xl font-semibold">Preset patterns</h2>
						<p className="text-sm text-muted-foreground">
							Hand-laid SVG wallpapers under <code>/whimsy-patterns/</code>. They
							ignore <code>seed</code>/<code>grid</code>/<code>theme</code>. Tile size
							here is fixed at 600 px to match the runtime hook.
						</p>
					</header>

					<div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
						{WHIMSY_PRESETS.map((preset) => (
							<Sample
								key={preset.id}
								uri={whimsyPresetUrl(preset.id)}
								caption={preset.label}
								className="bg-background text-foreground/15"
								heightClass="h-72"
								maskSize={`${PRESET_TILE_SIZE}px auto`}
							/>
						))}
					</div>
				</section>

				<section className="space-y-3 rounded-lg border border-border bg-muted/30 p-5 text-sm">
					<h2 className="text-base font-semibold">How to use</h2>
					<pre className="overflow-x-auto text-xs leading-relaxed">
						{`import { generateWhimsyTile, svgToDataUri, WHIMSY_THEMES } from '@/lib/whimsy-tile';

// Default kawaii mix:
const url = \`url("\${svgToDataUri(generateWhimsyTile())}")\`;

// Pick a theme:
const cosmic = generateWhimsyTile({
  seed: 7,
  motifs: WHIMSY_THEMES.cosmic,
});

// Custom subset:
const heartfield = generateWhimsyTile({
  seed: 99,
  grid: 7,
  motifs: ['heart', 'dot'],
});

// Apply via CSS mask + theme color:
<div
  className="text-foreground/[0.035]"  // controls intensity
  style={{
    backgroundColor: 'currentColor',
    maskImage: url,
    maskSize: '240px 240px',
    maskRepeat: 'repeat',
  }}
/>`}
					</pre>
				</section>

				<footer className="border-t border-border pt-6 text-xs text-muted-foreground">
					To remove this test: delete{' '}
					<code className="rounded bg-muted px-1">frontend/app/dev/whimsy-tile/</code> and{' '}
					<code className="rounded bg-muted px-1">frontend/lib/whimsy-tile.ts</code>.
				</footer>
			</div>
		</main>
	);
}
