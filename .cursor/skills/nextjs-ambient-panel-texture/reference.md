# Reference: source map and port checklist

## Canonical implementation (Pawrrtal)

Use these paths when aligning behavior; rename public APIs to **ambient panel texture** in the host app.

| Concern | Path in pawrrtal |
|--------|-------------------|
| Feature barrel + integration notes | `frontend/features/whimsy/index.tsx` |
| Config schema, bounds, optional persistence hook | `frontend/features/whimsy/config.ts` |
| Mask URL hook | `frontend/features/whimsy/use-whimsy-tile.ts` |
| Settings UI (port to design-system primitives) | `frontend/features/whimsy/WhimsySettingsCard.tsx` |
| Procedural generator + themes | `frontend/lib/whimsy-tile.ts` |
| Preset IDs + URL helper | `frontend/lib/whimsy-presets.ts` |
| Example overlay mount | `frontend/features/chat/ChatView.tsx` |
| Mirrored shell texture (optional) | `frontend/features/settings/SettingsLayout.tsx` |
| Dev preview page (optional) | `frontend/app/dev/whimsy-tile/page.tsx` |

## Suggested rename table (public names in host repo)

| Source symbol / path | Target |
|---------------------|--------|
| `whimsy` feature folder | `frontend/features/ambient-panel-texture/` |
| `WhimsyConfig`, `useWhimsyConfig` | `AmbientPanelTextureConfig`, `useAmbientPanelTextureConfig` |
| `useWhimsyTile` | `useAmbientPanelTexture` |
| `WhimsySettingsCard` | `AmbientPanelTextureSettingsCard` |
| `whimsy:config` storage key | `ambient-texture:config` (only if you add persistence) |
| `/whimsy-patterns/` URL prefix | `/ambient-texture-patterns/` (or host-chosen; keep code and `public/` in sync) |

## Bundled presets (this skill)

- **Location:** `bundled-patterns/pattern-{1..33}.svg` (33 files).
- **Default install:** copy the entire directory to `public/ambient-texture-patterns/` so URLs are `/ambient-texture-patterns/pattern-N.svg`.
- **Idempotent copy:** if `public/ambient-texture-patterns/` already contains 33 files matching `pattern-*.svg`, skip copying.

Example (run from the **Next.js app root**; adjust the source path if the skill lives under `~/.cursor/skills/` instead of the repo’s `.cursor/skills/`):

```bash
mkdir -p public/ambient-texture-patterns
SKILL_ROOT=".cursor/skills/nextjs-ambient-panel-texture"   # or ~/.cursor/skills/nextjs-ambient-panel-texture
cp -n "$SKILL_ROOT/bundled-patterns/"*.svg public/ambient-texture-patterns/
```

(`cp -n` does not overwrite; omit `-n` if you intentionally refresh assets.)

## Overlay stacking rules

- Parent of the overlay must be `position: relative` (or other positioned ancestor).
- Texture layers: `pointer-events-none`, absolute inset, below interactive children (often first child in the panel).
- Use CSS `mask-image` / `-webkit-mask-image` with `backgroundColor: currentColor` (or host foreground token) so light/dark tracks the theme.

## Procedural mode

No extra assets: SVG string is generated client-side from seed, grid, size, and theme motif list (`whimsy-tile.ts` logic).
