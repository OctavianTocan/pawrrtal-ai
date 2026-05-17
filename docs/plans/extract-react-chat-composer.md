# Plan — Extract `@octavian-tocan/react-chat-composer`

Implementation plan for lifting the pawrrtal chat composer surface out of
`frontend/features/chat/components/` into its own self-contained,
npm-publishable React package, modelled on the existing
`@octavian-tocan/react-overlay` and `@octavian-tocan/react-dropdown`
submodules.

Owner: Octavian
Status: **complete** — all three planned PRs + the runtime vendor follow-up
landed on `feat/extract-react-chat-composer`. Submodule is at main
`0b076cc`; host imports flipped; in-tree composer code deleted.
Branch in this repo: `feat/extract-react-chat-composer`
(from `feat/react-overlay-submodule-create-project`)
Pull request: [#166](https://github.com/OctavianTocan/Pawrrtal-AI/pull/166)
Submodule: <https://github.com/OctavianTocan/react-chat-composer>

> **Historical document.** Everything below was the up-front plan written
> via `/grill-with-docs` and executed largely as designed. Beans
> `pawrrtal-c1mf`, `pawrrtal-idpr`, `pawrrtal-k19r`, `pawrrtal-3a64` all
> completed; epic `pawrrtal-f1vm` closed. Kept verbatim so future readers
> can trace plan → shipped. Post-migration patches (TooltipProvider self-
> provision, globals.css token bridge) noted in the epic's summary.

---

## 1. Scope

**In** — pure UI for the composer surface:

- The composer island (textarea, autosize, paste, attachment chips, submit button)
- Footer chrome (attach button + right-side cluster: model selector, mic, submit)
- The voice-recording lifecycle + waveform timeline (sans the upload, which is consumer-provided)
- The model + reasoning picker (sans the model list, which is consumer-provided)
- The empty-state prompt suggestions list (`ChatPromptSuggestions`)
- A reusable "dropdown with icon variants" primitive extracted from `AutoReviewSelector`

**Out** — explicitly NOT in this package:

- Message-list / thread view, streaming UI, tool-call rendering — future
  `@octavian-tocan/react-chat-thread` package, separate scope
- Any backend integration (conversation persistence, STT proxy, model APIs)
- Pawrrtal-specific concepts (`PlanButton`, `AutoReviewSelector`, safety modes,
  `chat-composer:*` localStorage keys)
- React Native support
- Pre-baked default model list (lists age in months; consumer always supplies)

## 2. Package identity

| Field | Value |
| --- | --- |
| npm name | `@octavian-tocan/react-chat-composer` |
| GitHub repo | `OctavianTocan/react-chat-composer` (new, public) |
| Submodule path in this repo | `frontend/lib/react-chat-composer/` |
| Branch (this repo) | `feat/extract-react-chat-composer` |
| Branch (submodule) | `main` |
| License | MIT (matches precedent) |
| First npm publish | deferred — submodule import path works locally without publishing |

Bootstrapping = create the GitHub repo, push initial scaffold commit, then
`git submodule add`. Identical to how `react-overlay` was set up.

## 3. Tooling (matches `react-overlay` template)

Inside the submodule:

- Build: `tsup` (ESM + CJS + DTS), per-feature subpath exports
- Test: `vitest` + `@testing-library/react` + `jsdom`
- Stories: `storybook` (covering all composer states)
- Visual regression: `lost-pixel`
- Lint/format: `eslint` + `prettier` (NOT biome — the package is its own world,
  matching precedent)
- Release: `semantic-release` via `.releaserc.json`
- Type check: `tsc --noEmit`
- Package manager: `pnpm`

This repo (host) stays on `bun` + biome — the submodule is self-contained.

## 4. Public API surface

### 4.1 Main entry — `@octavian-tocan/react-chat-composer`

```ts
// The flagship component.
export function ChatComposer(props: ChatComposerProps): JSX.Element;

// Empty-state suggestion list.
export function ChatPromptSuggestions(
  props: ChatPromptSuggestionsProps,
): JSX.Element;

// Helpers for building the model list.
export function defineChatModel(option: ChatModelOption): ChatModelOption;

// Sample preset — exported but NOT used as a default.
export const CHAT_MODELS_2026: ChatModelOption[];

// Types
export type {
  ChatComposerProps,
  ChatComposerMessage,
  ChatModelOption,
  ChatReasoningLevel,
  ChatPromptSuggestion,
  ChatProviderSlug,
};
```

`ChatComposerProps` (controlled + uncontrolled):

```ts
interface ChatComposerProps {
  // --- text: controlled (value + onChange) OR uncontrolled (defaultValue)
  value?: string;
  defaultValue?: string;
  onChange?: (text: string) => void;

  // --- submit
  onSubmit: (message: ChatComposerMessage) => void | Promise<void>;
  isLoading?: boolean; // shows stop icon when true

  // --- voice (optional; mic button hidden if undefined)
  onTranscribeAudio?: (audio: Blob, mimeType: string) => Promise<string>;

  // --- model selector (optional; button hidden if both undefined)
  models?: ChatModelOption[];
  selectedModelId?: string;
  onSelectModel?: (modelId: string) => void;
  reasoningLevels?: ChatReasoningLevel[];
  selectedReasoning?: string;
  onSelectReasoning?: (level: string) => void;

  // --- slots
  /**
   * Rendered between AttachButton and the right cluster. Consumer plugs in
   * product-specific actions (PlanButton, permission selector, etc.).
   */
  footerActions?: ReactNode;

  // --- presentation
  className?: string;
  placeholder?: string; // overrides rotating tips
  placeholders?: string[]; // rotates when empty (defaults to a generic list)

  // --- a11y
  ariaLabel?: string;
}

interface ChatComposerMessage {
  text: string;
  attachments: File[];
}
```

### 4.2 Subpath `@octavian-tocan/react-chat-composer/primitives`

```ts
/** Generic dropdown-with-icon-variants pattern extracted from AutoReviewSelector. */
export function ComposerActionSelector<T extends string>(
  props: ComposerActionSelectorProps<T>,
): JSX.Element;

/** Bundled SVG provider logos. Falls back to a generic icon for unknown slugs. */
export function ProviderLogo(props: ProviderLogoProps): JSX.Element;

/** The animated waveform timeline used during voice recording. */
export function VoiceMeter(props: VoiceMeterProps): JSX.Element;
```

### 4.3 Subpath `@octavian-tocan/react-chat-composer/hooks`

```ts
/** Recording lifecycle + state machine. Takes the transcribe callback. */
export function useVoiceRecording(
  options: UseVoiceRecordingOptions,
): UseVoiceRecordingResult;
```

### 4.4 Subpath `@octavian-tocan/react-chat-composer/types`

Re-exports of every public type — useful for `import type` consumers.

### 4.5 Subpath stylesheets

- `@octavian-tocan/react-chat-composer/styles/theme.css` — Tailwind v4 `@theme`
  block with light + dark defaults for every `--color-chat-*`, `--radius-chat-*`,
  `--shadow-chat-*`, `--animate-chat-*` token the package uses.
- `@octavian-tocan/react-chat-composer/styles/animations.css` — non-Tailwind
  keyframes (`composer-placeholder-enter`, `waveform-scroll`) + the animated
  utility classes that reference them.

## 5. Style strategy

**Tailwind v4 only** (matches host stack; v3 compat would be busywork for zero
current consumers).

Token namespace: `chat-*` (e.g. `--color-chat-bg-elevated`, `--color-chat-muted`,
`--radius-chat-lg`, `--shadow-chat-minimal`, `--animate-chat-placeholder`).

### Consumer integration (one-time)

```css
/* host globals.css */
@import "tailwindcss";

/* 1. Tell Tailwind to scan the package's compiled JS for utility classes. */
@source "../node_modules/@octavian-tocan/react-chat-composer/dist";

/* 2. Bring in the chat-* token defaults (light + dark). */
@import "@octavian-tocan/react-chat-composer/styles/theme.css";

/* 3. Bring in the non-Tailwind keyframes + animation classes. */
@import "@octavian-tocan/react-chat-composer/styles/animations.css";

/* 4. (Optional) Override any chat-* token to theme the composer. */
:root {
  --color-chat-accent: #ff6b35;
}
```

That's it. The composer renders with sensible defaults if step 4 is skipped.

### Why a Tailwind preset / token theme over a compiled CSS bundle

- **Themability**: consumers swap one CSS variable to recolor without forking.
- **Bundle size**: classes are compiled by the consumer's Tailwind, no duplicate
  styles shipped.
- **Precedent**: `react-overlay` and `react-dropdown` both rely on the consumer
  running Tailwind v4. Diverging would mean two style models in one workspace.

The trade-off: consumers without Tailwind can't use the package. That's an
acceptable precondition for a 2026-era React UI library scoped to one author's
projects.

This decision is captured in **ADR `2026-05-10-react-chat-composer-styling.md`**
(see §11).

## 6. Vendoring plan

Everything the composer borrows from pawrrtal gets copied into the package and
adapted. Pawrrtal-specific concepts get genericised; pawrrtal-specific concepts
that don't generalise get dropped.

| From pawrrtal | Action in the package |
| --- | --- |
| `frontend/components/ai-elements/prompt-input-form.tsx` | Copy → `src/prompt-input/PromptInputForm.tsx`. Adapt classNames to `chat-*` tokens. |
| `frontend/components/ai-elements/prompt-input-textarea.tsx` | Copy → `src/prompt-input/PromptInputTextarea.tsx`. |
| `frontend/components/ai-elements/prompt-input-attachments.tsx` | Copy → `src/prompt-input/PromptInputAttachments.tsx`. |
| `frontend/components/ai-elements/prompt-input-context.tsx` | Copy → `src/prompt-input/promptInputContext.tsx`. |
| `PromptInputFooter` + `PromptInputSubmit` from `prompt-input-layout.tsx` | Extract just those two pieces → `src/prompt-input/PromptInputLayout.tsx`. |
| Other 30+ AI Elements exports (action menus, hover cards, tabs, commands) | DROP. Not used. |
| `frontend/components/ui/button.tsx` (shadcn) | Reimplement minimally inside `src/ui/Button.tsx`. The composer only needs ghost/icon/icon-sm/icon-xs variants. |
| `frontend/components/ui/tooltip.tsx` (shadcn → Radix) | Keep Radix Tooltip as a peer dep (`@radix-ui/react-tooltip`). Wrap thin in `src/ui/Tooltip.tsx`. |
| `@octavian-tocan/react-dropdown` (composer's submenu picker) | Real peer dep — composer uses `DropdownMenu`, `DropdownSubmenu`, etc. from the existing package. |
| `frontend/hooks/use-persisted-state.ts` | Copy → `src/hooks/usePersistedState.ts`. Drop the pawrrtal-specific key shapes; expose generic hook. |
| `frontend/hooks/use-tooltip-dropdown.ts` | Copy → `src/hooks/useTooltipDropdown.ts`. Pure UI, no adaptation needed. |
| `frontend/features/chat/hooks/use-voice-transcribe.ts` | Rewrite → `src/hooks/useVoiceRecording.ts`. Strip backend dependency, accept `onTranscribeAudio` callback. |
| `frontend/lib/utils.ts` (`cn` helper) | Copy → `src/utils/cn.ts`. Standard clsx + tailwind-merge pattern. |
| `frontend/features/chat/constants.ts` | DROP pawrrtal-specific bits; keep nothing in package. Defaults move into component code. |
| `frontend/features/chat/components/ChatComposer.tsx` | Split into `src/composer/ChatComposer.tsx` (container) + `src/composer/ChatComposerView.tsx`. |
| `frontend/features/chat/components/ChatComposerControls.tsx` | Split into many smaller files under `src/composer/controls/`. |
| `frontend/features/chat/components/ModelSelectorPopover.tsx` | Split into `src/model-selector/ModelSelectorPopover.tsx` + `.../ModelSelectorPopoverView.tsx`. Drop hardcoded `MODEL_OPTIONS`, accept via props. |
| `frontend/features/chat/components/ChatPromptSuggestions.tsx` | Move → `src/prompt-suggestions/ChatPromptSuggestions.tsx`. Already mostly pure. |
| `chat-composer-input-group`, `chat-composer-dropdown-menu`, `popover-styled` CSS classes from `globals.css` | Move keyframes + class defs into `src/styles/animations.css` (renamed `chat-composer-*`). |
| `--background-elevated`, `--radius-surface-lg`, `--shadow-minimal` etc. | Re-create as `--color-chat-bg-elevated`, `--radius-chat-lg`, `--shadow-chat-minimal` in `src/styles/theme.css`. |
| External fetch to `https://models.dev/logos/{provider}.svg` | DROP. Bundle ~8 monochrome provider SVGs in `src/primitives/ProviderLogo.tsx`. Per-model `logo` override available. |

**NOTICE.md** in the package crediting Vercel AI Elements (MIT) and shadcn/ui
(MIT) for the vendored pieces.

## 7. Voice / model-selector extension points

### Voice

```ts
<ChatComposer
  onTranscribeAudio={async (audio, mimeType) => {
    // Consumer plugs in their own STT — OpenAI Whisper, Deepgram, xAI, etc.
    const fd = new FormData();
    fd.append('file', audio, `voice.${mimeType.includes('mp4') ? 'mp4' : 'webm'}`);
    const res = await fetch('/api/transcribe', { method: 'POST', body: fd });
    return (await res.json()).text ?? '';
  }}
/>
```

If `onTranscribeAudio` is omitted, the mic button is hidden entirely. Graceful
degradation — no broken-looking UI in projects without STT.

### Model selector

```ts
<ChatComposer
  models={[
    {
      id: 'claude-opus-4-7',
      shortName: 'Claude Opus 4.7',
      name: 'Claude Opus 4.7',
      provider: 'anthropic', // → bundled SVG logo
      description: 'Most capable for ambitious work',
    },
    {
      id: 'my-custom-model',
      shortName: 'My Model',
      name: 'My Internal Model',
      provider: 'custom',
      description: 'Internal-only model',
      logo: <MyCustomLogo />, // per-model override
    },
  ]}
  selectedModelId={modelId}
  onSelectModel={setModelId}
  reasoningLevels={['low', 'medium', 'high', 'extra-high']}
  selectedReasoning={reasoning}
  onSelectReasoning={setReasoning}
/>
```

Both `models` and `reasoningLevels` are optional. If both are omitted the
selector trigger is hidden. Defaults for known providers: anthropic, openai,
google, mistral, xai, meta, deepseek, qwen.

## 8. View/Container audit script

**File**: `scripts/check-view-container.mjs` in this repo (NOT in the submodule).

**Behaviour**:

1. Walks `frontend/features/` + `frontend/components/`. Excludes `node_modules`,
   `components/ui/` (shadcn primitives), `components/ai-elements/` (vendored
   upstream), `frontend/lib/react-*` (vendored sibling packages), `*.test.tsx`,
   `*.stories.tsx`, `page.tsx`, `layout.tsx`.
2. For each remaining `.tsx` file:
   - **IMPURE_VIEW check** — if the file name ends in `View.tsx`, parse the AST
     and flag if it calls any hook outside the allowlist
     `{useId, useMemo, useCallback, useMediaQuery}`. The hook allowlist is for
     pure derivations + viewport queries; everything else belongs in a
     container.
   - **MONOLITH check** — if the file is NOT a `*View.tsx` and exceeds the size
     threshold (default: 80 LOC) and calls 3+ React hooks AND contains JSX,
     compute `score = hookCount * ceil(lineCount / 100)` and flag.
3. Sort offenders by score descending; print `{severity, path, score, summary}`.
4. Exit 0 in advisory mode (default). Exit 1 if `STRICT_VC=1` env var is set.

**Wiring**:

- Add `bun run check:view-container` to `package.json` scripts.
- Add the script to `bun run check` (which fans out to biome + file-lines +
  nesting + this).
- CI runs advisory mode initially. Promote to `STRICT_VC=1` once the codebase
  reaches green.

**Exempt allowlist**: maintained inline in the script, mirroring
`EXEMPT_FUNCTIONS` in `check-nesting.mjs`. Each entry tagged with a TODO + bean
ID for follow-up. Do not grow the allowlist as a workaround — fix the function
instead.

## 9. Migration plan (host repo)

Only ~4 external import sites in pawrrtal currently use the composer files:

- `frontend/features/chat/ChatContainer.tsx` — types from `ModelSelectorPopover`
- `frontend/features/chat/ChatView.tsx` — `ChatComposer`, `ChatPromptSuggestions`,
  types from `ModelSelectorPopover`
- `frontend/features/chat/constants.ts` — types from `ModelSelectorPopover`
- `frontend/features/chat/hooks/use-chat.ts` — types from `ModelSelectorPopover`

**No barrel layer needed.** Each site flips directly to
`@octavian-tocan/react-chat-composer`.

Pawrrtal-specific types (`ChatModelId`, `ChatReasoningLevel` as narrow unions)
become host-local in `features/chat/constants.ts`:

```ts
// constants.ts in pawrrtal AFTER migration
import type { ChatModelOption } from '@octavian-tocan/react-chat-composer';

export const PAWRRTAL_MODELS = [
  { id: 'claude-opus-4-7', shortName: 'Claude Opus 4.7', ... },
  // ...
] as const satisfies ChatModelOption[];

export type ChatModelId = (typeof PAWRRTAL_MODELS)[number]['id'];
```

PawrrtalPlanButton + the pawrrtal-specific `AutoReviewSelector` get rebuilt as
small wrappers in `features/chat/components/`:

```tsx
// features/chat/components/PlanButton.tsx (pawrrtal-local)
export function PlanButton() {
  // Same JSX as before, no longer in the package
}

// features/chat/components/SafetyModeSelector.tsx (pawrrtal-local)
import { ComposerActionSelector } from '@octavian-tocan/react-chat-composer/primitives';

export function SafetyModeSelector() {
  const [mode, setMode] = usePersistedState({ ... });
  return <ComposerActionSelector trigger={...} items={SAFETY_MODES} ... />;
}

// And in ChatView:
<ChatComposer
  footerActions={
    <>
      {planVisible && <PlanButton />}
      <SafetyModeSelector />
    </>
  }
  onTranscribeAudio={async (blob, mime) => {
    // existing useVoiceTranscribe logic, rewrapped as a callback
  }}
  models={PAWRRTAL_MODELS}
  ...
/>
```

`useVoiceTranscribe` stays in pawrrtal (it owns the backend `/api/v1/stt`
integration) but is refactored to be called from the composer's
`onTranscribeAudio` prop.

`globals.css` adds:

```css
@source "../lib/react-chat-composer/src";
@import "../lib/react-chat-composer/src/styles/theme.css";
@import "../lib/react-chat-composer/src/styles/animations.css";
```

(Using the submodule path for the local dev build; switches to the npm-published
path once we publish.)

## 10. PR sequencing

Three PRs from the `feat/extract-react-chat-composer` branch:

### PR 1 — `chore: add view/container audit + convert chat composer to View/Container in-place`

- **New**: `scripts/check-view-container.mjs` (advisory mode wired into
  `bun run check`)
- **Modified, in-place split**:
  - `ChatComposer.tsx` → container + `ChatComposerView.tsx`
  - `ChatComposerControls.tsx` → break out per-control files
    (`AttachButton.tsx`, `VoiceMeter.tsx`, `AutoReviewSelector.tsx`,
    `AutoReviewSelectorView.tsx`, etc.)
  - `ModelSelectorPopover.tsx` → container + `ModelSelectorPopoverView.tsx`
  - `ChatPromptSuggestions.tsx` → minor cleanup (already mostly pure)
- **No package work yet** — all changes inside `features/chat/components/`
- Tests pass, biome clean, view-container script advisory mode green for new
  splits, audit allowlist seeded with pre-existing offenders

### PR 2 — `feat: scaffold @octavian-tocan/react-chat-composer submodule`

- Create `OctavianTocan/react-chat-composer` on GitHub (empty public repo)
- Push initial commit there: scaffold from `react-overlay` template (tsup,
  vitest, storybook, lost-pixel, semantic-release configs, NOTICE.md, README,
  AGENTS.md/CLAUDE.md)
- `git submodule add` into `frontend/lib/react-chat-composer/`
- Copy + adapt all the vendored pieces from §6
- Storybook covers every state: empty, with text, multiline, with attachments,
  recording, transcribing, transcription error, mic-disabled (no
  `onTranscribeAudio`), model selector with/without, model selector with custom
  logo, footerActions slot populated, isLoading streaming, mobile width
- Update `scripts/check-file-lines.mjs` and `scripts/check-nesting.mjs` to add
  `'frontend/lib/react-chat-composer/'` to `EXEMPT_PATH_FRAGMENTS` (matching the
  precedent)
- Host still imports from `features/chat/`; package is built but unused

### PR 3 — `refactor: migrate pawrrtal to @octavian-tocan/react-chat-composer`

- Flip the 4 import sites
- Add the `@source` + `@import` lines to `globals.css`
- Build host-local `PlanButton`, `SafetyModeSelector` wrappers
- Wire `onTranscribeAudio` to existing pawrrtal `useVoiceTranscribe`
- Convert `ChatModelId` to a host-local narrow union derived from a
  `PAWRRTAL_MODELS` const
- Delete the original `frontend/features/chat/components/ChatComposer.tsx`,
  `ChatComposerControls.tsx`, `ModelSelectorPopover.tsx`,
  `ChatPromptSuggestions.tsx` (now obsolete)
- Drop the pawrrtal-specific keyframes (`composer-placeholder-enter`,
  `waveform-scroll`) from host `globals.css` — they live in the package now
- Verify: app builds, biome passes, Stagehand E2E composer specs still green,
  visual regression unchanged
- Optionally bump the audit script to `STRICT_VC=1` in a follow-up PR once the
  monolith list is empty

## 11. ADR

One decision crosses the bar (hard-to-reverse + surprising + real trade-off):

**`frontend/content/docs/handbook/decisions/2026-05-10-react-chat-composer-styling.md`** — explains the
Tailwind v4 preset / token-theme approach over a compiled CSS bundle, including
the precondition (consumers must run Tailwind v4) and why precedent consistency
with `react-overlay` / `react-dropdown` outweighs the portability win of a
compiled bundle.

Other decisions (scope, naming, voice swap point, model selector pluggability)
are recorded in this plan and don't need separate ADRs.

## 12. Out of scope / follow-ups

- React Native support
- `@octavian-tocan/react-chat-thread` (message-list / streaming / tool-call
  rendering)
- Markdown rendering inside the composer (mentions, slash commands)
- Multi-modal input (image paste, drag-drop preview, audio inline)
- A `@octavian-tocan/react-chat-toolkit` meta-package that bundles the composer
  + thread once both exist
