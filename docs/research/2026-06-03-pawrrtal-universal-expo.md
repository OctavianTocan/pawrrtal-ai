# Pawrrtal Universal Expo Research

## Summary

It is plausible to make Pawrrtal work across web, iOS, Android, and desktop-adjacent shells, but not by mechanically converting all React DOM to React Native in one pass. The better path is to introduce a universal UI boundary: shared app state, API clients, chat data models, design tokens, and high-level feature contracts, with platform-specific renderers where the DOM and native worlds diverge.

The interesting bet is not "rewrite Pawrrtal in Expo." It is "make Pawrrtal's product model portable, then migrate the UI surface one vertical slice at a time."

## Current Pawrrtal Shape

Pawrrtal frontend is a Next.js App Router app using React 19, Tailwind v4, Radix/shadcn-style components, custom `ai-elements`, and local React-only packages such as `@octavian-tocan/react-chat-composer`, `@octavian-tocan/react-dropdown`, and `@octavian-tocan/react-overlay`.

Good portability candidates:

- Backend API clients in `frontend/lib/`.
- TanStack Query state and mutations.
- Conversation/message/tool/artifact schemas.
- Design tokens from `DESIGN.md` and `frontend/app/globals.css`.
- High-level feature modules under `frontend/features/`.

Hard portability points:

- DOM elements, CSS variables, Tailwind v4 utilities, and layout semantics.
- Radix/shadcn primitives, dropdowns, overlays, hover cards, and command menus.
- The chat composer and rich AI rendering surface.
- Next-only routing, server components, MDX/docs, and browser APIs.
- Desktop-specific wrapper assumptions in Electron.

## Liza Reference

The local Liza app at `/mnt/HC_Volume_105512717/dev/liza-rft` is a useful reference because it already uses Expo Router, React 19, React Native 0.83, `react-native-web`, EAS scripts, and a small core primitive layer.

The pattern worth copying is the primitive boundary:

- `CoreText` wraps React Native `Text` and owns typography/color tokens.
- `CoreCard` wraps `View` and owns surface/radius/border tokens.
- `CoreButton` wraps a pressable primitive and owns accessibility, pressed states, platform motion, and design tokens.
- Platform-specific files such as `.web.tsx` and `.native.tsx` are used where behavior truly diverges.

That is a better target than trying to teach a converter that every `<div>` is a native `<View>` and every Tailwind class has an equivalent.

## Architecture Direction

Create a universal package layer before creating a mobile app:

```text
packages/
  paw-core/          shared API clients, schemas, auth/session helpers
  paw-design/        tokens and platform-neutral design decisions
  paw-ui/            universal primitives and simple components
apps/
  web/               existing Next app, gradually consuming shared packages
  mobile/            Expo app, initially thin and experimental
```

Start with a small set of universal primitives:

| Primitive | Web implementation | Native implementation |
| --- | --- | --- |
| `PawText` | text element / class tokens | `Text` / `StyleSheet` |
| `PawView` | `div` / layout classes | `View` |
| `PawPressable` | `button` / pointer events | `Pressable` |
| `PawScrollView` | scroll container | `ScrollView` or list primitive |
| `PawInput` | input/textarea wrappers | `TextInput` |
| `PawModal` | existing overlay package initially | native modal/bottom sheet later |

Then migrate vertical slices:

1. Shared API/client schemas.
2. Authentication/session bootstrap.
3. Basic conversation list.
4. Read-only chat transcript.
5. Chat composer.
6. Tool/artifact rendering.
7. Settings/integrations.
8. Advanced desktop/web-only docs and admin surfaces.

## Converter Idea

An automatic converter is still useful, but as an assisted migration tool rather than a one-shot transpiler.

V1 converter behavior:

- Parse TSX with a real AST.
- Classify files as `portable`, `adapter-needed`, or `web-only`.
- Replace simple DOM elements with universal primitives.
- Convert obvious event props (`onClick` -> `onPress`) only when semantics are clear.
- Extract hard CSS/Tailwind usage into TODO annotations or design-token lookups.
- Generate `.native.tsx` scaffolds next to web components for hard cases.
- Produce a report with blocked dependencies and unsupported patterns.

It should not try to convert Radix menus, complex overlays, server components, MDX/docs pages, or web-specific editor/browser APIs automatically.

## Build And Test Model

Use Liza's working split as the reference:

- Fast web loop: Expo web or existing Next web, depending on the slice.
- Native artifact boundary: EAS Build for APK/AAB and later iOS.
- Android validation: Redroid plus ws-scrcpy for browser-visible proof.
- E2E: Playwright for web and Maestro for native.
- Package checks: `expo install --check`, typecheck, lint, and focused component tests.

## Open Questions

- Whether the first Expo app should live in this repo as `apps/mobile` or start as a sibling experiment.
- Whether `NativeWind` is mature enough for Pawrrtal's design system, or whether a token-to-StyleSheet compiler is a better fit.
- Whether chat composer should be rebuilt as a universal primitive or replaced with a native-specific composer while sharing only message state.
- Whether docs/admin surfaces should remain web-only indefinitely.
- Whether Electron remains the desktop path while Expo owns mobile, or whether Expo web eventually becomes the primary app shell.

## Recommendation

Do not switch Pawrrtal to Expo now. Start by making the product portable:

1. Extract shared API/state/schema code.
2. Define universal design tokens and primitives.
3. Build a tiny Expo mobile shell that can log in and render a read-only conversation.
4. Build a converter/report tool that identifies what is portable and what needs an adapter.
5. Use the results to decide whether full universal migration is worth it.

## Sources

- Expo docs via Context7: `/websites/expo_dev`
- React Native docs via Context7: `/facebook/react-native-website`
- NativeWind docs via Context7: `/websites/nativewind_dev`
- Expo docs: https://docs.expo.dev/
- React Native docs: https://reactnative.dev/docs/components-and-apis
- NativeWind docs: https://www.nativewind.dev/docs
- Liza local reference: `/mnt/HC_Volume_105512717/dev/liza-rft`
