---
name: check-official-docs-and-skills-first
paths: ["**/*"]
---

# Check Official Docs, CLI, and Agent Skills Before Inventing or Hacking

## Rule

Before writing custom code or working around a perceived missing feature in
a library, framework, or platform, **first check whether the official tools
already solve the problem**:

1. The library's **official docs** (TanStack docs, Electron docs, FastAPI
   docs, etc.) — fetch the canonical page, don't reason from training data.
2. The library's **CLI**, if one exists (e.g. `@tanstack/cli`,
   `npx @tanstack/intent@latest list/load`).
3. The library's **agent skills**, if it ships them (the `@tanstack/intent`
   ecosystem is the canonical example; many libraries ship `SKILL.md` files
   under `node_modules/<package>/skills/`).
4. The repo's existing **`.claude/rules/`** — there's almost always a rule
   for the area you're touching.

Only after confirming the official path does *not* exist or does *not* fit
the constraint should custom code or a workaround be written — and that
decision should be **documented inline** so the next person reading it
knows the official option was considered and why it was rejected.

## Why

This is one of the most common, costly mistakes when working in this
repo. Real examples from the migration history:

- **Electron production server.** Wrote an 80-line Node `http.createServer`
  to serve the SPA. The official answer is `protocol.handle('app:', ...)`,
  documented for years, single-call API. The custom server also broke
  TanStack Router (router#5509) because `file://` makes `window.origin`
  the literal string `"null"`.
- **TanStack Router auth gate.** Wrote a probe-on-first-nav shim. The
  canonical pattern is `createRootRouteWithContext<{auth}>` +
  `RouterProvider context={{auth}}`, documented in the
  `auth-and-guards` agent skill (`@tanstack/intent load
  @tanstack/router-core#auth-and-guards`).
- **Login route.** Skipped `validateSearch`. The official skill says it's
  required for typed `?redirect=` params and an already-authed bounce.

In every case the custom approach took more code, was less correct, and
had to be ripped out the moment someone read the actual docs. The cost
of "look it up first" is 5 minutes; the cost of "build it then realise"
is hours of refactor.

## Verify

Before you start writing the first new file:

> "Have I checked the library's official docs / CLI / skills for this
> exact problem? Have I read what `npx @tanstack/intent@latest list`
> reports for the package I'm changing? Is there a rule under
> `.claude/rules/` that already covers this?"

If the answer to all three is no, stop and check.

## Patterns

Bad — invent first, look up later:

```ts
// Electron production: SPA static server
import { createServer } from 'node:http';
const server = createServer((req, res) => {
  // 80 lines of MIME mapping, fallback, range-request handling...
});
```

Good — find the official answer, then write the small bridge:

```ts
// Electron's modern `protocol.handle` is the canonical SPA-in-desktop
// pattern.  Avoids `file://` (discouraged + breaks router URL parsing)
// and gives the renderer a real origin for cookies + fetch.
import { protocol, net } from 'electron';
protocol.registerSchemesAsPrivileged([{ scheme: 'app', privileges: { /* ... */ } }]);
protocol.handle('app', async (request) => net.fetch(`file://${pathFor(request)}`));
```

Bad — workaround for missing API:

```tsx
// Custom auth probe in beforeLoad to compensate for "no router context"
beforeLoad: async () => {
  const ok = await fetch('/api/probe', { credentials: 'include' });
  if (!ok) throw redirect({ to: '/login' });
}
```

Good — the framework already has the abstraction:

```tsx
// `createRootRouteWithContext` is the official channel for passing
// app state into route guards.  See @tanstack/router-core's
// auth-and-guards skill.
export const Route = createRootRouteWithContext<{ auth: AuthState }>()({
  component: () => <Outlet />,
});

// In _app.tsx:
beforeLoad: ({ context, location }) => {
  if (!context.auth.isAuthenticated) {
    throw redirect({ to: '/login', search: { redirect: location.href } });
  }
};
```

## How to Look Things Up

In rough order of authority:

1. **TanStack ecosystem:** `npx @tanstack/intent@latest list` then
   `npx @tanstack/intent@latest load <package>#<skill>`.
   Or: `npx @tanstack/cli search-docs "<query>" --library router
   --framework react --json` for ad-hoc searches.
2. **Context7 MCP:** for general library docs (registered in this repo's
   `.mcp.json`). Use it before web search when the question is library-
   specific.
3. **DeepWiki MCP:** when you need to understand a repo's internals
   (also in `.mcp.json`).
4. **Stagehand docs:** `https://docs.stagehand.dev/llms.txt` plus the
   `stagehand-docs` MCP — see `.claude/rules/stagehand/`.
5. **Web fetch:** the actual canonical docs site, not StackOverflow.
   Prefer the docs over a blog post that's two years old.

## Learned From

- The Pawrrtal migration off Next.js (PR #126), where the first pass
  reinvented three things that all had official answers, all of which
  surfaced the moment the agent skills were installed.
- Tavi's standing instruction: "find official tools before inventing or
  hacking, especially for AI tooling and frameworks."
