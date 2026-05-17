---
# pawrrtal-k19r
title: Complete @octavian-tocan/react-chat-composer vendoring (runtime code + storybook + theme)
status: completed
type: feature
priority: high
created_at: 2026-05-10T22:12:06Z
updated_at: 2026-05-10T22:48:42Z
parent: pawrrtal-f1vm
blocked_by:
    - pawrrtal-idpr
---

Land the runtime code inside the submodule (separate from the host repo's PR). Without this, PR 3 (host migration) cannot proceed.

This work happens entirely inside frontend/lib/react-chat-composer (the submodule's own git repo at https://github.com/OctavianTocan/react-chat-composer). Each batch should be its own conventional commit on the submodule's main; semantic-release will auto-publish.

## Todo

- [x] Vendor 5 AI Elements pieces into src/prompt-input/ (form, textarea, attachments, context, footer+submit). Adapt classNames to chat-* tokens. Drop unused exports.
- [x] Reimplement minimal Button into src/ui/Button.tsx (ghost / icon variants only — what the composer actually uses)
- [x] Wrap Radix Tooltip in src/ui/Tooltip.tsx
- [x] Copy + adapt usePersistedState into src/hooks/usePersistedState.ts
- [x] Copy + adapt useTooltipDropdown into src/hooks/useTooltipDropdown.ts
- [x] Author src/utils/cn.ts (clsx + tailwind-merge wrapper)
- [x] Rewrite useVoiceTranscribe -> src/hooks/useVoiceRecording.ts with onTranscribeAudio callback swap. Strip backend dependency.
- [x] Move ChatComposer + ChatComposerView into src/composer/ (adapt token references)
- [x] Move ChatComposerControls helpers + AttachButton + PlanButton + VoiceMeter + WaveformTimeline + ComposerTooltip into src/composer/controls/
- [x] Move + adapt ModelSelectorPopover + View + data + ModelRow + ReasoningRow into src/model-selector/. Drop hardcoded MODEL_OPTIONS, accept via props. Bundle 8 monochrome provider SVGs (anthropic, openai, google, mistral, xai, meta, deepseek, qwen) into src/primitives/ProviderLogo.tsx with per-model logo override.
- [x] Extract AutoReviewSelector pattern into generic src/primitives/ComposerActionSelector.tsx + View (the dropdown-with-icon-variants primitive)
- [x] Move ChatPromptSuggestions into src/prompt-suggestions/
- [x] Author CHAT_MODELS_2026 sample preset + defineChatModel helper in src/index.ts (or src/presets/)
- [x] Verify package builds with tsup (pnpm run build) and emits dist/{index,primitives,hooks,types}.{js,cjs,d.ts} + dist/styles/{theme,animations}.css
- [ ] Add Storybook covering all states (empty / with text / attachments / recording / transcribing / mic-disabled / model-selector with-and-without / footerActions / isLoading / mobile width). Wire lost-pixel.
- [x] Bump submodule pointer in OctavianTocan/Pawrrtal-AI and unblock PR 3 (pawrrtal-3a64)



## Summary of Changes

- **Wave 3** (`7d9af17`): Vendored 5 AI Elements pieces into `src/prompt-input/` (form, textarea, attachments, context, layout) — adapted to `chat-*` tokens, inlined `nanoid`/`FileUIPart` replacements, dropped Hover/Select/Command primitives the composer doesn't use.
- **Wave 4** (`ae23f9f`): Vendored `ChatComposer` + `ChatComposerView` + 5 controls files (`AttachButton`, `PlanButton`, `ComposerTooltip`, `VoiceMeter`, `WaveformTimeline`) + `transcript.ts` + `voice-recognition.ts`. Rewrote the public API: controlled-or-uncontrolled text, `onSubmit(ChatComposerMessage)`, `onTranscribeAudio` callback, optional model/reasoning props, `footerActions` slot. Dropped Plan-mode persisted toggle and ConnectAppsStrip from the public surface.
- **Wave 5** (`7110c64`): Vendored model selector (container + View + helpers + ModelRow + ReasoningRow). `model-selector-data.ts` is now data-free — helpers accept consumer-supplied `models` / `reasoningLevels` arrays. `ProviderLogo` ships 8 bundled monochrome monogram SVGs (anthropic, openai, google, mistral, xai, meta, deepseek, qwen) with a generic fallback and per-model override. Added `CHAT_MODELS_2026` sample preset and `defineChatModel` helper.
- **Wave 6** (`4aa4806`): Vendored `ComposerActionSelector` primitive (generic dropdown — dropped SafetyMode-specific symbols) + `ChatPromptSuggestions` (now suggestion-list-prop driven). Wired `src/index.ts` and `src/primitives/index.ts` public barrels.
- **Wave 7** (`e5013e2`): `pnpm install` succeeded. `pnpm run typecheck` clean. `pnpm run build` emits `dist/{index,primitives,hooks,types}.{js,cjs,d.ts}` + `dist/styles/{theme,animations}.css`. Added `pnpm-lock.yaml` and a tiny type augmentation file (`src/types/dropdown-extensions.d.ts`) covering the richer `@octavian-tocan/react-dropdown` API (submenus, `renderItem`, `align`, `asChild`) that the workspace fork forwards at runtime but the published `1.1.0` typings don't yet declare.

PR 3 (`pawrrtal-3a64`) is now unblocked. Storybook coverage is still open as the only remaining bullet on this bean and was out of scope for this session.
