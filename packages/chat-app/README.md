# @pawrrtal/chat-app

A standalone **React Native + Expo** chat app UI, built in **Effect-TS v4**.
It lives in the Pawrrtal monorepo as its own self-contained package and is
**not** wired into the web frontend or the Python backend — it is a pure
UI/UX surface with no live functionality yet.

The scaffolding (Expo SDK, Expo Router, Biome, Reanimated, TypeScript config,
Metro/Babel) mirrors the `liza-rft` app one-to-one so it builds and exports
the same way. The visual design is a 1:1 reproduction of the reference chat
app: the "Ask / Imagine" home canvas, the model-tier selector, the attachment
menu, the full-screen voice capture, the conversation-history drawer, and the
settings screen — restyled with this package's own dark design tokens.

## Stack

| Concern        | Choice                                                       |
| -------------- | ------------------------------------------------------------ |
| Runtime        | Expo SDK 55, React Native 0.83, React 19.2                   |
| Routing        | Expo Router (file-based, `app/`)                             |
| Language       | TypeScript 5.9 (strict)                                      |
| Effect system  | **Effect v4** (`4.0.0-beta.83`)                              |
| State / DI     | Effect `Context.Service` + `Layer` + `ManagedRuntime`        |
| Reactive state | `SubscriptionRef` bridged to React via `useSyncExternalStore`|
| Lint / format  | Biome 2 (React Native domain)                                |
| Animation      | Reanimated 4 + worklets                                      |

## Effect v4 — why and how

The whole app runs on a single Effect v4 `ManagedRuntime`:

- **Services** (`src/services/`) are `Context.Service` definitions with `*Live`
  layers: `AppStore` (transient UI state in a `SubscriptionRef`), `Catalog`
  (static models + conversations), and `Navigation` (an Effect facade over
  `expo-router`, so navigation is just another effect).
- **Runtime** (`src/runtime/`) merges those layers (`AppLayer`) into one
  `ManagedRuntime` (`appRuntime`). The React bridge (`react.tsx`) subscribes to
  the store's `changes` stream via `useSyncExternalStore` and dispatches action
  effects through `useRun`. Reads are synchronous (`SubscriptionRef.getUnsafe`),
  so there is no loading flicker.
- **Domain** (`src/domain/`) is defined with Effect `Schema`; errors are
  `Schema.TaggedErrorClass`.

> **Note on the React bridge.** The community `@effect-atom/atom-react` package
> still peer-depends on Effect **v3** (`^3.19`) and has no v4 release, so this
> app deliberately does **not** use it. Instead it bridges the v4
> `ManagedRuntime` to React by hand with `useSyncExternalStore` — the documented
> v4-safe approach. Metro needs `unstable_enablePackageExports` (set in
> `metro.config.js`) to resolve Effect v4's `exports`-map subpaths.

## Commands

```bash
cd packages/chat-app
npm install            # standalone install (not part of the root pnpm workspace)
npm run start          # Expo dev server (native + web)
npm run web            # web dev server
npm run typecheck      # tsc --noEmit
npm run lint           # biome check
npm run check          # lint + typecheck
npm run build:web      # static web export -> dist/
npm run prebuild       # generate native android/ ios projects
```

## Why it is standalone (not a pnpm workspace member)

Expo 55 pins `react@19.2.0`, while the repo root overrides React to a different
patch for the Next.js frontend. Joining the root pnpm workspace would force a
single shared resolution and break Expo's expected React/React Native versions.
Keeping this package self-contained (its own `package-lock.json` and `.npmrc`)
lets it build exactly like `liza-rft`. The root Biome config excludes
`packages/chat-app` so this package's own toolchain stays authoritative.

## Layout

```
packages/chat-app/
├── app/                      Expo Router routes
│   ├── _layout.tsx           fonts + providers + Stack
│   ├── index.tsx             home ("Ask / Imagine") + overlays
│   ├── conversations.tsx     history drawer
│   └── settings.tsx          settings list
├── src/
│   ├── components/
│   │   ├── core/             ThemedText, Pressable
│   │   ├── chat/             Composer, overlays, rows, waveform
│   │   └── icons/            icon registry + brand logo
│   ├── constants/            design tokens (colors, type, spacing, radii, motion)
│   ├── domain/               Effect Schema models + tagged errors
│   ├── data/                 in-memory seed fixtures
│   ├── services/             Effect services (AppStore, Catalog, Navigation)
│   └── runtime/              ManagedRuntime + React bridge + actions
└── assets/                   app icon / splash / favicon
```
