# Add Fumadocs Documentation Site — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Fumadocs documentation site at `/docs` to the existing `frontend/` Next 16 app, serving `/docs/handbook/**` (curated public-safe internal docs moved from repo-root `docs/`) and `/docs/product/**` (5 seed user-facing pages).

**Architecture:** Fumadocs lives inside `frontend/`. Two `defineDocs` collections (handbook + product) feed two `loader` instances at distinct base URLs. Two per-section `app/docs/<section>/layout.tsx` files wrap their respective `[[...slug]]/page.tsx`. `RootProvider` nests around the existing `<Providers>` at the root layout, configured so the existing FOUC-safe `theme-detection.js` script stays authoritative for the `dark` class. Search is local (Orama via `fumadocs-core/search/server`). No backend changes.

**Tech Stack:** Next 16.2 App Router, React 19.2, TypeScript, Tailwind CSS v4, Bun, Biome 2.4, Vitest, `fumadocs-core@^16.8`, `fumadocs-ui@^16.8`, `fumadocs-mdx@^15.0`.

**Spec:** `docs/decisions/2026-05-14-add-fumadocs-documentation-site.md`
**Tracking bean:** `pawrrtal-s1wa`
**Working branch:** `development`

---

## Pre-flight context

Before starting, make sure you have read:

1. The spec at `docs/decisions/2026-05-14-add-fumadocs-documentation-site.md` — every decision here references back to that doc.
2. `CLAUDE.md` + `AGENTS.md` at repo root — house rules including the
   500-LOC file budget, conventional commits, Biome enforcement, the
   `bun run check` gate, beans-over-TodoWrite, and the "no pre-existing
   excuse" rule.
3. The "How We Work on Pawrrtal" rule at
   `.claude/rules/general/how-we-work-on-pawrrtal.md` — especially
   "read first, write second" and "run the toolchain after every file
   write."

**Project conventions you will be tested against:**

- All commands route through `just` when one exists. Prefer
  `cd frontend && bun run <script>` for frontend-scoped ops since
  there is no `just` shortcut for sub-build steps.
- Frontend installs use **Bun**, never npm/pnpm. Always run from
  `frontend/`.
- Commit one logical concern at a time. Five commits in this plan,
  each independently green.
- After every file write, run the formatter (Biome) and `tsc --noEmit`
  before touching the next file. See
  `.claude/rules/sweep/run-toolchain-after-writes.md`.
- `cursor-pointer` on every interactive element. The chooser page in
  Task 2 has links — they're already styled by Fumadocs but verify.
- Inline-style any error UI; Tailwind classes don't help if CSS itself
  fails. (Not applicable in this plan but worth knowing.)

## File structure

**New files** (paths absolute from repo root):

| File | Purpose |
|---|---|
| `frontend/source.config.ts` | Defines two `defineDocs` collections (handbook, product) and exports Fumadocs default config. |
| `frontend/lib/source.ts` | Two `loader()` instances with distinct `baseUrl`s. |
| `frontend/lib/layout.shared.tsx` | Shared `baseOptions` for `DocsLayout` (nav title, links). |
| `frontend/components/mdx.tsx` | MDX component registry (`getMDXComponents` + `useMDXComponents`). |
| `frontend/app/docs/page.tsx` | `/docs` landing: two-card chooser (handbook vs product). |
| `frontend/app/docs/handbook/layout.tsx` | `DocsLayout` wrapper for handbook tree. |
| `frontend/app/docs/handbook/[[...slug]]/page.tsx` | Dynamic handbook page renderer. |
| `frontend/app/docs/product/layout.tsx` | `DocsLayout` wrapper for product tree. |
| `frontend/app/docs/product/[[...slug]]/page.tsx` | Dynamic product page renderer. |
| `frontend/app/api/search/route.ts` | Orama search endpoint (Commit 5). |
| `frontend/app/sitemap.ts` | Sitemap including all `/docs/**` URLs (Commit 5). |
| `frontend/public/robots.txt` | Allow `/docs/**`, disallow `/api/`. |
| `frontend/content/docs/handbook/index.mdx` | Handbook landing. |
| `frontend/content/docs/handbook/design-system.mdx` | Thin link page → `DESIGN.md` at repo root. |
| `frontend/content/docs/product/index.mdx` | Product Introduction. |
| `frontend/content/docs/product/conversations.mdx` | Conversations & Sidebar. |
| `frontend/content/docs/product/models.mdx` | Models. |
| `frontend/content/docs/product/modes.mdx` | Modes & Reasoning. |
| `frontend/content/docs/product/settings.mdx` | Settings. |
| `frontend/test/docs-source.test.ts` | Asserts MDX-file count parity with `source.getPages()`. |

**Moved files** (via `git mv` in Commit 3):

| From | To |
|---|---|
| `docs/decisions/*.md` (8 files, includes the spec + the model-id ADR that landed today) | `frontend/content/docs/handbook/decisions/` |
| `docs/agents/*.md` (3) | `frontend/content/docs/handbook/agents/` |
| `docs/ci/*.md` (1) | `frontend/content/docs/handbook/ci/` |
| `docs/deployment/*.md` (1) | `frontend/content/docs/handbook/deployment/` |

**Modified files:**

| File | Change |
|---|---|
| `frontend/package.json` | Add 4 deps via `bun add`. |
| `frontend/next.config.ts` | Wrap export with `createMDX()` from `fumadocs-mdx/next`. Keep `.ts` extension — Next 15+ supports ESM TypeScript configs natively, so the older "must be `.mjs`" guidance does not apply. |
| `frontend/tsconfig.json` | Add `"collections/*": ["./.source/*"]` to `paths`. |
| `frontend/.gitignore` | Add `.source/` and `content/docs/**/.fumadocs/` if not already covered. |
| `frontend/app/layout.tsx` | Wrap `<Providers>` with `<RootProvider>`. |
| `frontend/app/globals.css` | Add two Fumadocs CSS imports. |
| `frontend/features/settings/sections/AppearanceSection.tsx` | Update one user-visible string citing `docs/decisions/...`. |
| `scripts/dev-console-smoke.mjs` | Add `/docs`, `/docs/handbook`, `/docs/product` to `COLD_BOOT_ROUTES`. |
| `AGENTS.md`, `CLAUDE.md`, `.claude/rules/**`, `docs/plans/**`, `.beans/**`, `frontend/app/providers.tsx`, `frontend/features/settings/sections/appearance-helpers.ts`, `frontend/features/settings/sections/AppearanceSection.tsx` | Path sweep: `docs/{decisions,agents,ci,deployment}/` → `frontend/content/docs/handbook/{decisions,agents,ci,deployment}/`. |

---

## Commit 1: Scaffold Fumadocs dependencies and config

**Goal:** Install packages, set up build-time MDX plugin and TS path alias. No new routes yet. The existing pawrrtal app builds unchanged.

### Task 1.1: Install dependencies

- [ ] **Step 1: Install the four Fumadocs packages**

Run:
```bash
cd frontend && bun add fumadocs-core@^16.8 fumadocs-ui@^16.8 fumadocs-mdx@^15.0 @types/mdx
```

Expected: four packages added to `frontend/package.json` `dependencies`. No peer-dep warnings about Next or React (Pawrrtal is on Next 16.2.6 / React 19.2.6, both within range).

- [ ] **Step 2: Verify install did not break anything**

Run:
```bash
cd frontend && bun run check
```

Expected: clean (Biome check + tsc + line-length + nesting + view-container all pass). The new deps are in `package.json` but no source yet imports them, so nothing changes in the type check.

### Task 1.2: Create `source.config.ts`

- [ ] **Step 1: Write the config file**

Create `frontend/source.config.ts`:

```ts
/**
 * Fumadocs MDX collection definitions.
 *
 * Two parallel collections (handbook, product) feed two distinct
 * loaders in `lib/source.ts`. Each collection has its own MDX
 * directory under `content/docs/`.
 */

import { defineConfig, defineDocs } from 'fumadocs-mdx/config';

/** Curated, public-safe internal handbook content. */
export const handbookDocs = defineDocs({
	dir: 'content/docs/handbook',
});

/** User-facing product documentation. */
export const productDocs = defineDocs({
	dir: 'content/docs/product',
});

export default defineConfig();
```

- [ ] **Step 2: Run Biome + tsc**

Run:
```bash
cd frontend && bunx --bun @biomejs/biome check --write source.config.ts && bunx tsc --noEmit
```

Expected: file gets formatted; tsc clean. (`tsc` will not yet resolve `collections/*` — that is set up later — but it does not import that alias yet.)

### Task 1.3: Wrap `next.config.ts` with `createMDX()`

- [ ] **Step 1: Read the current config**

Run:
```bash
cat frontend/next.config.ts
```

You should see the existing config exporting `nextConfig` with `turbopack`, `output: 'standalone'`, `experimental.authInterrupts`, and `experimental.optimizePackageImports`. Keep all of these.

- [ ] **Step 2: Modify to wrap with `createMDX`**

Edit `frontend/next.config.ts`. Add the import at the top and wrap the export at the bottom:

```ts
/**
 * Next.js configuration for the Pawrrtal frontend.
 *
 * @fileoverview Sets Turborepo monorepo root for Turbopack, enables
 * `authInterrupts` for `unauthorized()`, and rewrites barrel-style imports
 * from icon / UI libraries into direct imports at build time so the dev
 * server doesn't pay the 200–800 ms cold-start cost of resolving thousands
 * of unused re-exports.
 *
 * The export is wrapped with `createMDX()` from `fumadocs-mdx/next` so
 * MDX files under `content/docs/**` are compiled at build time and the
 * `collections/*` alias resolves to the generated `.source/*` manifest.
 */

import path from 'node:path';
import { createMDX } from 'fumadocs-mdx/next';
import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
	turbopack: {
		root: path.resolve(__dirname, '../'),
	},
	output: 'standalone',
	experimental: {
		authInterrupts: true,
		optimizePackageImports: [
			'lucide-react',
			'@tabler/icons-react',
			'@hugeicons/react',
			'@radix-ui/react-icons',
			'date-fns',
		],
	},
};

const withMDX = createMDX();

export default withMDX(nextConfig);
```

(The existing JSDoc block has been preserved with the addition. Do not delete any of the block-comment context.)

- [ ] **Step 2.5: Preserve any unrelated config edits**

If `cat` in step 1 showed any options not in the example above (a teammate may have added something), keep them. The only contract is: import `createMDX`, wrap the final export with `withMDX(nextConfig)`.

- [ ] **Step 3: Run Biome + tsc**

```bash
cd frontend && bunx --bun @biomejs/biome check --write next.config.ts && bunx tsc --noEmit
```

Expected: clean.

### Task 1.4: Add the `collections/*` TS path alias

- [ ] **Step 1: Edit `frontend/tsconfig.json`**

In the `compilerOptions.paths` block, add `"collections/*"` after the existing `@/*` mapping. The final shape:

```json
"paths": {
	"@/*": ["./*"],
	"collections/*": ["./.source/*"],
	"@octavian-tocan/react-dropdown": ["./lib/react-dropdown/src/index.ts"],
	"@octavian-tocan/react-dropdown/*": ["./lib/react-dropdown/src/*"],
	"@octavian-tocan/react-overlay": ["./lib/react-overlay/src/index.ts"],
	"@octavian-tocan/react-overlay/*": ["./lib/react-overlay/src/*"],
	"@octavian-tocan/react-chat-composer": ["./lib/react-chat-composer/src/index.ts"],
	"@octavian-tocan/react-chat-composer/*": ["./lib/react-chat-composer/src/*"]
}
```

- [ ] **Step 2: Verify**

```bash
cd frontend && bunx tsc --noEmit
```

Expected: clean. The `.source/` directory does not exist yet (it gets generated by `createMDX` on first build), so the alias resolves to a non-existent path until then — TS tolerates this.

### Task 1.5: Ensure `.source/` is gitignored

- [ ] **Step 1: Inspect `.gitignore`**

```bash
cat frontend/.gitignore
```

If `.source` or `.source/` is already present, skip Step 2.

- [ ] **Step 2: Add `.source/` and `.fumadocs/` to `frontend/.gitignore`**

Append the following lines at the end of `frontend/.gitignore`:

```
# Fumadocs MDX generated manifest
.source/

# Fumadocs cache / temp output
.fumadocs/
```

### Task 1.6: Generate the manifest and verify the first build succeeds

- [ ] **Step 1: Create empty content directories so `defineDocs` does not error**

```bash
mkdir -p frontend/content/docs/handbook frontend/content/docs/product
```

- [ ] **Step 2: Add a single placeholder MDX file in each so the loader has something to read**

Create `frontend/content/docs/handbook/index.mdx`:

```mdx
---
title: Handbook (placeholder)
description: Will be replaced in Commit 2.
---

# Handbook (placeholder)

Will be replaced in Commit 2.
```

Create `frontend/content/docs/product/index.mdx`:

```mdx
---
title: Product (placeholder)
description: Will be replaced in Commit 2.
---

# Product (placeholder)

Will be replaced in Commit 2.
```

These exist so `bun run build` does not bail on empty collections. They get overwritten in Commit 2.

- [ ] **Step 3: Run a full build**

```bash
cd frontend && bun run build
```

Expected: build succeeds. The `.source/` directory is created with generated TypeScript bindings (`handbookDocs`, `productDocs`) for the placeholder MDX files. No new routes exist yet, so the route table is identical to before.

- [ ] **Step 4: Verify the manifest was generated**

```bash
ls frontend/.source/
```

Expected: a folder with at least an `index.ts` and per-collection bindings. If empty, the MDX plugin did not run — re-check `next.config.ts` wrap.

### Task 1.7: Commit

- [ ] **Step 1: Stage and commit**

```bash
git add frontend/package.json frontend/bun.lock frontend/source.config.ts frontend/next.config.ts frontend/tsconfig.json frontend/.gitignore frontend/content/docs/handbook/index.mdx frontend/content/docs/product/index.mdx
git status --short
```

Verify only the files above are staged. If `bun add` updated something extra (e.g. a workspace lockfile elsewhere), stage that too — but no source code should be changed by this commit.

```bash
git commit -m "$(cat <<'EOF'
chore(docs): scaffold fumadocs deps + config

Install fumadocs-core, fumadocs-ui, fumadocs-mdx, and @types/mdx.
Add source.config.ts with two collections (handbook, product),
wrap next.config.ts with createMDX(), and register the
collections/* TS path alias. Empty placeholder MDX seeds let the
first build succeed; routes are added in the next commit.

Tracks: pawrrtal-s1wa

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 2: Update bean checkbox**

```bash
beans update pawrrtal-s1wa --body-replace-old "- [ ] 1. chore(docs): scaffold fumadocs deps + config" --body-replace-new "- [x] 1. chore(docs): scaffold fumadocs deps + config"
```

---

## Commit 2: Scaffold `/docs` routes and wire `RootProvider`

**Goal:** All Fumadocs routes exist and render the placeholder content. `RootProvider` is wrapped around the app without breaking the existing FOUC-safe theme script. Visiting `/docs/handbook` and `/docs/product` returns a working Fumadocs page with the stock theme.

### Task 2.1: Create `lib/source.ts`

- [ ] **Step 1: Write the file**

Create `frontend/lib/source.ts`:

```ts
/**
 * Fumadocs loader instances for the handbook and product collections.
 *
 * Two distinct `baseUrl`s drive the two route segments
 * (`/docs/handbook/**`, `/docs/product/**`). Each loader is the
 * single entry point its segment's pages and layout use to read MDX
 * metadata and the page tree.
 */

import { handbookDocs, productDocs } from 'collections/server';
import { loader } from 'fumadocs-core/source';

/** Curated, public-safe internal handbook. */
export const handbookSource = loader({
	baseUrl: '/docs/handbook',
	source: handbookDocs.toFumadocsSource(),
});

/** User-facing product documentation. */
export const productSource = loader({
	baseUrl: '/docs/product',
	source: productDocs.toFumadocsSource(),
});
```

- [ ] **Step 2: Verify it type-checks**

```bash
cd frontend && bunx tsc --noEmit
```

Expected: clean. If `collections/server` is unresolved, the manifest in `.source/` was not generated — re-run `bun run build` from Commit 1.

### Task 2.2: Create `lib/layout.shared.tsx`

- [ ] **Step 1: Write the file**

Create `frontend/lib/layout.shared.tsx`:

```tsx
/**
 * Shared `BaseLayoutProps` for Fumadocs `DocsLayout` calls across
 * sections (handbook, product). Centralises nav title + global links
 * so the chrome stays consistent.
 */

import type { BaseLayoutProps } from 'fumadocs-ui/layouts/shared';

/**
 * Returns the shared layout options consumed by every `DocsLayout`
 * instance under `/docs/**`.
 *
 * @returns shared nav title and link config
 */
export function baseOptions(): BaseLayoutProps {
	return {
		nav: {
			title: 'Pawrrtal Docs',
			url: '/docs',
		},
		// Top-right links shown on every docs page.
		links: [
			{ text: 'Handbook', url: '/docs/handbook', active: 'url' },
			{ text: 'Product', url: '/docs/product', active: 'url' },
			{ text: 'App', url: '/', external: false },
		],
	};
}
```

- [ ] **Step 2: Format + type-check**

```bash
cd frontend && bunx --bun @biomejs/biome check --write lib/layout.shared.tsx && bunx tsc --noEmit
```

Expected: clean.

### Task 2.3: Create `components/mdx.tsx`

- [ ] **Step 1: Write the file**

Create `frontend/components/mdx.tsx`:

```tsx
/**
 * MDX component registry shared by every Fumadocs page.
 *
 * Exports both `getMDXComponents` (for pages that need to inject
 * components like `createRelativeLink`) and `useMDXComponents` (the
 * standard MDX-runtime hook).
 */

import defaultMdxComponents from 'fumadocs-ui/mdx';
import type { MDXComponents } from 'mdx/types';

/**
 * Returns the merged MDX component registry: the Fumadocs default
 * components, optionally overridden by the caller.
 *
 * @param components - optional per-call overrides (e.g. a relative-link transformer)
 * @returns the full MDX component registry
 */
export function getMDXComponents(components?: MDXComponents): MDXComponents {
	return {
		...defaultMdxComponents,
		...components,
	};
}

export const useMDXComponents = getMDXComponents;

declare global {
	type MDXProvidedComponents = ReturnType<typeof getMDXComponents>;
}
```

- [ ] **Step 2: Format + type-check**

```bash
cd frontend && bunx --bun @biomejs/biome check --write components/mdx.tsx && bunx tsc --noEmit
```

Expected: clean.

### Task 2.4: Overwrite the placeholder handbook + product index seeds

- [ ] **Step 1: Replace `frontend/content/docs/handbook/index.mdx`**

```mdx
---
title: Handbook
description: Internal-but-public reference for Pawrrtal contributors and agents.
---

# Pawrrtal Handbook

This is the durable reference set for Pawrrtal: architecture decisions,
agent guidance, CI notes, and deployment. Working notes (in-flight
plans, debug write-ups) live as raw markdown in the repo and are
intentionally not rendered here.

Start with:

- [Decisions](/docs/handbook/decisions) — ADRs explaining why the
  codebase looks the way it does.
- [Agents](/docs/handbook/agents) — how agents should work in this
  repo (issue tracker, triage, domain docs).
- [CI](/docs/handbook/ci) — self-hosted runner setup.
- [Deployment](/docs/handbook/deployment) — VPS deploy notes.
- [Design system](/docs/handbook/design-system) — pointer to the
  canonical `DESIGN.md` at the repo root.
```

- [ ] **Step 2: Replace `frontend/content/docs/product/index.mdx`**

(This gets fleshed out in Commit 4. Placeholder for now so the route resolves.)

```mdx
---
title: Pawrrtal — Product Docs
description: User-facing documentation for Pawrrtal.
---

# Pawrrtal

User-facing documentation is filled in by Commit 4 of this PR.
```

### Task 2.5: Create the `/docs` landing page

- [ ] **Step 1: Write the chooser**

Create `frontend/app/docs/page.tsx`:

```tsx
/**
 * `/docs` landing page: a two-card chooser that routes visitors to
 * either the internal handbook or the user-facing product docs.
 */

import Link from 'next/link';
import type { Metadata } from 'next';

export const metadata: Metadata = {
	title: 'Pawrrtal Docs',
	description:
		'Pawrrtal documentation: handbook (contributors and agents) and product (users).',
};

/**
 * Renders the docs landing with handbook + product entries.
 *
 * @returns the chooser page
 */
export default function DocsLanding() {
	return (
		<main className="mx-auto flex max-w-3xl flex-col gap-8 px-6 py-16">
			<header className="flex flex-col gap-2">
				<h1 className="text-3xl font-medium">Pawrrtal Docs</h1>
				<p className="text-fd-muted-foreground">
					Pick a section.
				</p>
			</header>
			<div className="grid gap-4 sm:grid-cols-2">
				<Link
					href="/docs/handbook"
					className="cursor-pointer rounded-lg border border-fd-border bg-fd-card p-6 transition-colors hover:bg-fd-accent"
				>
					<h2 className="text-lg font-medium">Handbook</h2>
					<p className="mt-1 text-sm text-fd-muted-foreground">
						Architecture decisions, agent guidance, CI, deployment.
						For contributors and agents.
					</p>
				</Link>
				<Link
					href="/docs/product"
					className="cursor-pointer rounded-lg border border-fd-border bg-fd-card p-6 transition-colors hover:bg-fd-accent"
				>
					<h2 className="text-lg font-medium">Product</h2>
					<p className="mt-1 text-sm text-fd-muted-foreground">
						How to use Pawrrtal: models, modes, settings, and more.
						For users.
					</p>
				</Link>
			</div>
		</main>
	);
}
```

The `fd-*` class names (`text-fd-muted-foreground`, `bg-fd-card`, etc.) are Fumadocs theme tokens. They become available once the Fumadocs CSS imports land in Task 2.10. Until then the page will render with default colors — that is fine for this commit's intermediate states.

`cursor-pointer` is present on both `Link`s per the project rule.

### Task 2.6: Create the handbook layout + dynamic page

- [ ] **Step 1: Write the handbook layout**

Create `frontend/app/docs/handbook/layout.tsx`:

```tsx
/**
 * `DocsLayout` for the handbook section, scoped to the handbook page
 * tree. Wraps every `/docs/handbook/**` route.
 */

import { DocsLayout } from 'fumadocs-ui/layouts/docs';
import type { ReactNode } from 'react';
import { baseOptions } from '@/lib/layout.shared';
import { handbookSource } from '@/lib/source';

/**
 * Renders the handbook chrome (sidebar, breadcrumbs) around child routes.
 *
 * @param props.children - the active handbook page
 * @returns the wrapped layout
 */
export default function HandbookLayout({
	children,
}: {
	children: ReactNode;
}) {
	return (
		<DocsLayout tree={handbookSource.pageTree} {...baseOptions()}>
			{children}
		</DocsLayout>
	);
}
```

- [ ] **Step 2: Write the dynamic handbook page**

Create `frontend/app/docs/handbook/[[...slug]]/page.tsx`:

```tsx
/**
 * Dynamic `/docs/handbook/[[...slug]]` page: looks up the MDX page
 * for the active slug in `handbookSource` and renders its body.
 */

import { createRelativeLink } from 'fumadocs-ui/mdx';
import {
	DocsBody,
	DocsDescription,
	DocsPage,
	DocsTitle,
} from 'fumadocs-ui/page';
import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { getMDXComponents } from '@/components/mdx';
import { handbookSource } from '@/lib/source';

/**
 * Renders a handbook page by slug.
 *
 * @param props.params - dynamic route params (`slug?: string[]`)
 * @returns the rendered MDX page
 */
export default async function HandbookPage(props: {
	params: Promise<{ slug?: string[] }>;
}) {
	const params = await props.params;
	const page = handbookSource.getPage(params.slug);
	if (!page) notFound();

	const MDX = page.data.body;

	return (
		<DocsPage toc={page.data.toc} full={page.data.full}>
			<DocsTitle>{page.data.title}</DocsTitle>
			<DocsDescription>{page.data.description}</DocsDescription>
			<DocsBody>
				<MDX
					components={getMDXComponents({
						a: createRelativeLink(handbookSource, page),
					})}
				/>
			</DocsBody>
		</DocsPage>
	);
}

/**
 * Generates static params for every handbook MDX page so they prerender.
 *
 * @returns one params object per page
 */
export async function generateStaticParams() {
	return handbookSource.generateParams();
}

/**
 * Generates per-page metadata (title, description).
 *
 * @param props.params - dynamic route params
 * @returns the metadata for the active slug
 */
export async function generateMetadata(props: {
	params: Promise<{ slug?: string[] }>;
}): Promise<Metadata> {
	const params = await props.params;
	const page = handbookSource.getPage(params.slug);
	if (!page) notFound();
	return {
		title: page.data.title,
		description: page.data.description,
	};
}
```

- [ ] **Step 3: Format + type-check**

```bash
cd frontend && bunx --bun @biomejs/biome check --write app/docs/handbook && bunx tsc --noEmit
```

Expected: clean.

### Task 2.7: Create the product layout + dynamic page

- [ ] **Step 1: Write the product layout**

Create `frontend/app/docs/product/layout.tsx`:

```tsx
/**
 * `DocsLayout` for the product section, scoped to the product page tree.
 */

import { DocsLayout } from 'fumadocs-ui/layouts/docs';
import type { ReactNode } from 'react';
import { baseOptions } from '@/lib/layout.shared';
import { productSource } from '@/lib/source';

/**
 * Renders the product docs chrome around child routes.
 *
 * @param props.children - the active product page
 * @returns the wrapped layout
 */
export default function ProductLayout({
	children,
}: {
	children: ReactNode;
}) {
	return (
		<DocsLayout tree={productSource.pageTree} {...baseOptions()}>
			{children}
		</DocsLayout>
	);
}
```

- [ ] **Step 2: Write the dynamic product page**

Create `frontend/app/docs/product/[[...slug]]/page.tsx` — identical body to the handbook version, but every `handbookSource` becomes `productSource`:

```tsx
/**
 * Dynamic `/docs/product/[[...slug]]` page: looks up the MDX page
 * for the active slug in `productSource` and renders its body.
 */

import { createRelativeLink } from 'fumadocs-ui/mdx';
import {
	DocsBody,
	DocsDescription,
	DocsPage,
	DocsTitle,
} from 'fumadocs-ui/page';
import type { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { getMDXComponents } from '@/components/mdx';
import { productSource } from '@/lib/source';

/**
 * Renders a product page by slug.
 *
 * @param props.params - dynamic route params (`slug?: string[]`)
 * @returns the rendered MDX page
 */
export default async function ProductPage(props: {
	params: Promise<{ slug?: string[] }>;
}) {
	const params = await props.params;
	const page = productSource.getPage(params.slug);
	if (!page) notFound();

	const MDX = page.data.body;

	return (
		<DocsPage toc={page.data.toc} full={page.data.full}>
			<DocsTitle>{page.data.title}</DocsTitle>
			<DocsDescription>{page.data.description}</DocsDescription>
			<DocsBody>
				<MDX
					components={getMDXComponents({
						a: createRelativeLink(productSource, page),
					})}
				/>
			</DocsBody>
		</DocsPage>
	);
}

/**
 * Generates static params for every product MDX page so they prerender.
 *
 * @returns one params object per page
 */
export async function generateStaticParams() {
	return productSource.generateParams();
}

/**
 * Generates per-page metadata for product pages.
 *
 * @param props.params - dynamic route params
 * @returns the metadata for the active slug
 */
export async function generateMetadata(props: {
	params: Promise<{ slug?: string[] }>;
}): Promise<Metadata> {
	const params = await props.params;
	const page = productSource.getPage(params.slug);
	if (!page) notFound();
	return {
		title: page.data.title,
		description: page.data.description,
	};
}
```

- [ ] **Step 3: Format + type-check**

```bash
cd frontend && bunx --bun @biomejs/biome check --write app/docs/product && bunx tsc --noEmit
```

Expected: clean.

### Task 2.8: Wrap `<RootProvider>` around the existing `<Providers>`

- [ ] **Step 1: Edit `frontend/app/layout.tsx`**

Import `RootProvider` and wrap. The existing file already wraps `{children}` with `<Providers>{children}</Providers>`. Replace that with:

```tsx
<RootProvider
	theme={{
		// The blocking script at /theme-detection.js is the FOUC defence
		// and the source of truth for the `dark` class on <html>.
		// `attribute="class"` makes next-themes (inside RootProvider)
		// read from that class on mount rather than write its own.
		attribute: 'class',
		defaultTheme: 'system',
		enableSystem: true,
	}}
>
	<Providers>{children}</Providers>
</RootProvider>
```

Add the import at the top of the file (alongside the existing imports):

```tsx
import { RootProvider } from 'fumadocs-ui/provider/next';
```

The full diff context: locate `<body>` in `app/layout.tsx`, and change

```tsx
<body>
	<Providers>{children}</Providers>
	{process.env.NODE_ENV === 'development' && <Agentation />}
</body>
```

to

```tsx
<body>
	<RootProvider
		theme={{
			attribute: 'class',
			defaultTheme: 'system',
			enableSystem: true,
		}}
	>
		<Providers>{children}</Providers>
		{process.env.NODE_ENV === 'development' && <Agentation />}
	</RootProvider>
</body>
```

(`<Agentation />` stays inside `<RootProvider>` so it has access to theme context too. It is fine either way.)

- [ ] **Step 2: Format + type-check**

```bash
cd frontend && bunx --bun @biomejs/biome check --write app/layout.tsx && bunx tsc --noEmit
```

Expected: clean.

### Task 2.9: Add Fumadocs CSS imports

- [ ] **Step 1: Edit `frontend/app/globals.css`**

The file currently begins:

```css
@import "tailwindcss";
@import "tw-animate-css";
```

Insert the two Fumadocs imports immediately after those two lines:

```css
@import "tailwindcss";
@import "tw-animate-css";
@import "fumadocs-ui/css/neutral.css";
@import "fumadocs-ui/css/preset.css";
```

Leave the rest of the file (composer imports, font-face blocks, theme tokens) untouched.

- [ ] **Step 2: Restart dev server (mental note for the implementer)**

If a `bun run dev` is running, CSS imports require a server restart for Tailwind v4 to pick up the new import sources. This is not a step you can codify — just be aware that the first `/docs` visit after this commit may need a server restart in dev.

### Task 2.10: Add `public/robots.txt`

- [ ] **Step 1: Write the file**

Create `frontend/public/robots.txt`:

```
User-agent: *
Allow: /docs/
Disallow: /api/
Disallow: /settings
Disallow: /dev/

Sitemap: /sitemap.xml
```

The `Sitemap:` URL is relative — Next.js converts to absolute at serve time. (Vercel and the standalone bundle both handle this correctly.)

### Task 2.11: Verify everything builds and routes resolve

- [ ] **Step 1: Full build**

```bash
cd frontend && bun run build
```

Expected: succeeds. `.source/` is regenerated. The build output should list these new routes:

- `/docs`
- `/docs/handbook/[[...slug]]`
- `/docs/product/[[...slug]]`

- [ ] **Step 2: Smoke-test the dev server**

In one terminal, start the dev server:

```bash
cd frontend && bun run dev
```

In another:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3001/docs
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3001/docs/handbook
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3001/docs/product
```

Expected: each returns `200`.

- [ ] **Step 3: Run the project gate**

```bash
cd frontend && bun run check
```

Expected: clean (Biome + tsc + line + nesting + view-container).

- [ ] **Step 4: Run sentrux**

```bash
just sentrux
```

Expected: no new layer violations. The new files live in `app/`, `lib/`, `components/`, `content/docs/` — all within the existing frontend layer rules.

### Task 2.12: Commit

- [ ] **Step 1: Stage everything new + modified**

```bash
git add frontend/lib/source.ts frontend/lib/layout.shared.tsx frontend/components/mdx.tsx frontend/app/docs/ frontend/app/layout.tsx frontend/app/globals.css frontend/public/robots.txt frontend/content/docs/handbook/index.mdx frontend/content/docs/product/index.mdx
git status --short
```

Verify the set matches expectations.

```bash
git commit -m "$(cat <<'EOF'
feat(docs): scaffold /docs routes and providers

Add Fumadocs route tree (handbook + product layouts and dynamic
pages, /docs landing chooser), lib/source.ts with two loader
instances, shared layout config, MDX component registry, robots.txt,
and the two CSS imports. Wrap RootProvider around the existing
Providers at the root layout with attribute="class" so the existing
FOUC theme script remains authoritative.

Handbook and product seeds are placeholder; content lands in
commits 3 and 4.

Tracks: pawrrtal-s1wa

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 2: Update bean checkbox**

```bash
beans update pawrrtal-s1wa --body-replace-old "- [ ] 2. feat(docs): scaffold /docs routes and providers" --body-replace-new "- [x] 2. feat(docs): scaffold /docs routes and providers"
```

---

## Commit 3: Migrate handbook content

**Goal:** Move the durable subset of repo-root `docs/` into `frontend/content/docs/handbook/` and update every reference. After this commit, `/docs/handbook/decisions/2026-05-03-adopt-sentrux-architecture-gating` renders the real ADR with sidebar nav.

### Task 3.1: `git mv` the four subfolders

- [ ] **Step 1: Move all four**

```bash
git mv docs/decisions  frontend/content/docs/handbook/decisions
git mv docs/agents     frontend/content/docs/handbook/agents
git mv docs/ci         frontend/content/docs/handbook/ci
git mv docs/deployment frontend/content/docs/handbook/deployment
```

- [ ] **Step 2: Verify the move**

```bash
ls docs/decisions docs/agents docs/ci docs/deployment 2>&1 | head
ls frontend/content/docs/handbook/
```

The four `ls` of the old paths should error ("No such file or directory"). The new path should contain `decisions/`, `agents/`, `ci/`, `deployment/`.

### Task 3.2: Add YAML frontmatter to every moved file

Fumadocs requires `title:` on every MDX-rendered page. The 12 moved files use Markdown H1 headings but no YAML frontmatter.

For each file listed below, prepend a `---` frontmatter block with `title:` (and `description:` when the document has an obvious subtitle).

- [ ] **Step 1: `frontend/content/docs/handbook/decisions/2026-05-03-adopt-sentrux-architecture-gating.md`**

Current first line: `# Adopt Sentrux for Architectural Quality Gating`

Prepend:

```yaml
---
title: Adopt Sentrux for Architectural Quality Gating
description: Why and how Pawrrtal uses sentrux to gate architectural drift.
---

```

Keep the `# Adopt Sentrux ...` H1; Fumadocs renders both the YAML title (in the sidebar/breadcrumb) and the H1 (in the page body) — the page will show the title once because Fumadocs strips the leading H1 when it matches the frontmatter title.

(If that double-rendering ends up looking off in practice, drop the H1. Verify when you preview.)

- [ ] **Step 2: Repeat for every file under the four moved folders**

There are 12 source files (count may have shifted slightly — verify with `find frontend/content/docs/handbook -name '*.md' | wc -l`). For each:

1. Read the first heading or document title.
2. Prepend a frontmatter block:

```yaml
---
title: <use the heading verbatim, minus any leading date prefix>
description: <one-line description if the doc has an obvious subtitle or status line; otherwise omit>
---
```

3. If the file uses MDX features (JSX in markdown) or you want Fumadocs callouts later, rename `.md` → `.mdx`. For now, plain `.md` is fine — Fumadocs treats both as MDX sources.

Files to process (this list is the snapshot at plan-writing time; re-run `find frontend/content/docs/handbook -name '*.md'` to confirm):

```
decisions/2026-05-03-adopt-sentrux-architecture-gating.md
decisions/2026-05-03-frontend-interaction-principles.md
decisions/2026-05-05-electron-privileged-ops-in-main.md
decisions/2026-05-05-stagehand-over-browser-use-for-ai-e2e.md
decisions/2026-05-06-rip-theming-system.md
decisions/2026-05-10-react-chat-composer-styling.md
decisions/2026-05-14-add-fumadocs-documentation-site.md
decisions/2026-05-14-model-id-canonical-format-and-backend-catalog.md
agents/domain.md
agents/issue-tracker.md
agents/triage-labels.md
ci/self-hosted-runner.md
deployment/vps-deploy.md
```

- [ ] **Step 3: Verify each file got a frontmatter block**

```bash
for f in $(find frontend/content/docs/handbook -name '*.md' -o -name '*.mdx'); do
  if ! head -1 "$f" | grep -q '^---$'; then
    echo "MISSING FRONTMATTER: $f"
  fi
done
```

Expected: no output. Any file printed is missing frontmatter.

### Task 3.3: Create the `design-system.mdx` link page

- [ ] **Step 1: Write the file**

Create `frontend/content/docs/handbook/design-system.mdx`:

```mdx
---
title: Design system
description: Pointer to the canonical DESIGN.md spec at the repo root.
---

# Design system

The canonical design system spec lives at the **repo root** in
[`DESIGN.md`](https://github.com/OctavianTocan/pawrrtal/blob/main/DESIGN.md).
It is intentionally not duplicated here because `bun run design:lint`
reads that file directly and many `.claude/rules/` entries link to it
by repo-root path.

If you are working with tokens, typography, spacing, shape, motion, or
component bindings, read `DESIGN.md` and run the linter
(`bun run design:lint`) before opening a PR.

For the why behind the system, see the relevant ADRs in
[Decisions](/docs/handbook/decisions).
```

### Task 3.4: Update the index page to link to real content

- [ ] **Step 1: Edit `frontend/content/docs/handbook/index.mdx`**

The placeholder content from Commit 2 references the right slugs already (`/docs/handbook/decisions`, etc.). Verify it still reads correctly now that those sub-pages exist; tweak as needed. Sample final shape:

```mdx
---
title: Handbook
description: Pawrrtal contributor + agent reference.
---

# Pawrrtal Handbook

This is the durable reference set for Pawrrtal — architecture
decisions, agent guidance, CI notes, and deployment. Working notes
(in-flight plans, debug write-ups) live as raw markdown in the repo
and are intentionally not rendered here.

## Sections

- [Decisions](/docs/handbook/decisions) — ADRs explaining why the
  codebase looks the way it does.
- [Agents](/docs/handbook/agents) — how AI agents work in this repo
  (issue tracker, triage, domain docs).
- [CI](/docs/handbook/ci) — self-hosted runner setup.
- [Deployment](/docs/handbook/deployment) — VPS deploy notes.
- [Design system](/docs/handbook/design-system) — pointer to
  `DESIGN.md` at the repo root.
```

### Task 3.5: Path sweep across the repo

The reference paths `docs/decisions/`, `docs/agents/`, `docs/ci/`, `docs/deployment/` now resolve to nothing. Rewrite every reference to point at the new location. Scope was measured during planning: ~25–30 files.

- [ ] **Step 1: Inspect every match before rewriting**

```bash
grep -rIln --include='*.md' --include='*.mdx' --include='*.ts' --include='*.tsx' --include='*.py' --include='*.toml' --include='*.yml' --include='*.yaml' --include='*.json' -e 'docs/decisions/' -e 'docs/agents/' -e 'docs/ci/' -e 'docs/deployment/' . 2>/dev/null | grep -v node_modules | grep -v '.source/' | sort -u
```

Read every file. For files that legitimately refer to the historical location (an old commit message in a `.beans/` description, a postmortem of "we moved files from X to Y"), leave alone. For everything else, proceed to Step 2.

- [ ] **Step 2: Run the sed rewrite**

Use a script-and-review pattern; do not rely on `find -exec sed -i` blindly:

```bash
FILES=$(grep -rIln --include='*.md' --include='*.mdx' --include='*.ts' --include='*.tsx' --include='*.py' --include='*.toml' --include='*.yml' --include='*.yaml' --include='*.json' -e 'docs/decisions/' -e 'docs/agents/' -e 'docs/ci/' -e 'docs/deployment/' . 2>/dev/null | grep -v node_modules | grep -v '.source/')

for f in $FILES; do
  echo "Rewriting: $f"
  sed -i.bak \
    -e 's|docs/decisions/|frontend/content/docs/handbook/decisions/|g' \
    -e 's|docs/agents/|frontend/content/docs/handbook/agents/|g' \
    -e 's|docs/ci/|frontend/content/docs/handbook/ci/|g' \
    -e 's|docs/deployment/|frontend/content/docs/handbook/deployment/|g' \
    "$f"
  rm "${f}.bak"
done
```

(On macOS, `sed -i.bak ... && rm *.bak` is the safe variant. Linux can use `sed -i ...` directly.)

- [ ] **Step 3: Verify no stray references remain**

```bash
grep -rIln --include='*.md' --include='*.mdx' --include='*.ts' --include='*.tsx' --include='*.py' --include='*.toml' --include='*.yml' --include='*.yaml' --include='*.json' -e 'docs/decisions/' -e 'docs/agents/' -e 'docs/ci/' -e 'docs/deployment/' . 2>/dev/null | grep -v node_modules | grep -v '.source/'
```

Expected: empty (or only known intentional historical references that you whitelisted in Step 1).

### Task 3.6: Fix the user-visible Settings copy

- [ ] **Step 1: Edit `frontend/features/settings/sections/AppearanceSection.tsx`**

Line ~364 currently reads:

```tsx
description="Customize colors, typography, and behavior. (Currently a visual mock — controls do not persist or change the runtime UI; see docs/decisions/2026-05-06-rip-theming-system.md.)"
```

The sed sweep in Task 3.5 already rewrote `docs/decisions/` → `frontend/content/docs/handbook/decisions/`. That works but reads awkwardly to a user. Replace with a clean public URL:

```tsx
description="Customize colors, typography, and behavior. (Currently a visual mock — controls do not persist or change the runtime UI; see /docs/handbook/decisions/2026-05-06-rip-theming-system.)"
```

Note: the public URL drops the `.md` extension (Fumadocs strips it).

### Task 3.7: Sanity checks

- [ ] **Step 1: Build**

```bash
cd frontend && bun run build
```

Expected: succeeds. The `.source/` manifest now contains entries for all moved files. Build will fail if any MDX page has malformed YAML or `createRelativeLink` cannot resolve an internal link in a moved file — fix and re-run.

- [ ] **Step 2: Check**

```bash
cd frontend && bun run check
```

Expected: clean.

- [ ] **Step 3: Sentrux**

```bash
just sentrux
```

Expected: clean. The moved files live in `frontend/content/docs/handbook/` — not a source layer — so sentrux ignores them entirely.

- [ ] **Step 4: Dev-server smoke**

Start `bun run dev` and check a known slug:

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:3001/docs/handbook/decisions/2026-05-03-adopt-sentrux-architecture-gating
```

Expected: `200`. If `404`, the slug got mangled — Fumadocs derives slugs from filenames; verify the URL matches the filename with `.md` stripped.

### Task 3.8: Commit

- [ ] **Step 1: Stage everything**

```bash
git add -A
git status --short
```

Verify the set is:

- New files under `frontend/content/docs/handbook/` (the moved files appear as renames if `-A` is used).
- The new `design-system.mdx`.
- The path-sweep edits across `.claude/rules/`, `AGENTS.md`, `CLAUDE.md`, `frontend/app/providers.tsx`, `frontend/features/settings/sections/*.ts(x)`, `docs/plans/**`, `.beans/**`.
- Updated `frontend/features/settings/sections/AppearanceSection.tsx` user-visible string.
- Original `docs/{decisions,agents,ci,deployment}/` folders deleted.

```bash
git commit -m "$(cat <<'EOF'
feat(docs): migrate handbook content into frontend/content/docs/

Move docs/decisions, docs/agents, docs/ci, and docs/deployment into
frontend/content/docs/handbook/ so Fumadocs can render them. Add YAML
frontmatter to every moved file, create a thin design-system.mdx
that links to repo-root DESIGN.md, and sweep every reference to the
old paths across AGENTS.md, CLAUDE.md, .claude/rules/**, .beans/**,
docs/plans/**, and the Settings → Appearance description string.

Tracks: pawrrtal-s1wa

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 2: Update bean checkbox**

```bash
beans update pawrrtal-s1wa --body-replace-old "- [ ] 3. feat(docs): migrate handbook content (git mv + frontmatter + path sweep)" --body-replace-new "- [x] 3. feat(docs): migrate handbook content (git mv + frontmatter + path sweep)"
```

---

## Commit 4: Seed the product section with five pages

**Goal:** Replace the product `index.mdx` placeholder and add four more pages. Feature-tour style (per Q7 = B). Each 200–400 words, no marketing fluff.

You will need to **read the actual app** to write accurate copy. Specifically:

- `frontend/features/chat/components/ModelSelectorPopover.tsx` for the model picker UX.
- `frontend/features/chat/components/ChatComposerControls.tsx` for plan / safety / reasoning modes.
- `frontend/features/settings/` for the settings tour.
- `frontend/features/nav-chats/` for the conversation sidebar.

Write each MDX file in a separate task so they can be reviewed one at a time. Each task ends with a Biome format pass; the build/smoke runs after all five.

### Task 4.1: Write `product/index.mdx` — Introduction

- [ ] **Step 1: Read the relevant features**

```bash
ls frontend/features/chat frontend/features/nav-chats frontend/features/settings
head -40 frontend/features/chat/components/ModelSelectorPopover.tsx 2>/dev/null
```

- [ ] **Step 2: Write the file**

Replace `frontend/content/docs/product/index.mdx`:

```mdx
---
title: Introduction
description: Pawrrtal is a model-agnostic chat app for working with LLMs across providers.
---

# Pawrrtal

Pawrrtal is a chat app for working with large-language models. It is
model-agnostic — you pick which model you want each turn, from any
of the supported providers, and Pawrrtal handles the rest:
conversation history, streaming output, plan-mode previews, and
safety-aware tool execution.

This product section covers how to use the app as an end user:

- [Conversations & Sidebar](/docs/product/conversations) — creating,
  navigating, and managing chats.
- [Models](/docs/product/models) — what providers are supported, how
  to pick a model.
- [Modes & Reasoning](/docs/product/modes) — plan mode, safety
  mode, and reasoning levels.
- [Settings](/docs/product/settings) — appearance, account, and
  preferences.

If you are a contributor or an agent working on Pawrrtal itself, see
the [Handbook](/docs/handbook).
```

- [ ] **Step 3: Format**

```bash
cd frontend && bunx --bun @biomejs/biome check --write content/docs/product/index.mdx 2>&1 | tail -5
```

(Biome leaves MDX content alone but normalises whitespace; ignore "no fixes available" output.)

### Task 4.2: Write `product/conversations.mdx`

- [ ] **Step 1: Read the sidebar**

```bash
ls frontend/features/nav-chats/
head -50 frontend/features/nav-chats/components/NavChatsView.tsx 2>/dev/null
```

- [ ] **Step 2: Write the file**

Create `frontend/content/docs/product/conversations.mdx`:

```mdx
---
title: Conversations & Sidebar
description: How conversations are organised, navigated, and managed.
---

# Conversations & Sidebar

Every chat you have with Pawrrtal is a **conversation**. Conversations
persist across sessions and live in the left sidebar.

## Creating a conversation

Click anywhere in the composer at the bottom of the app and start
typing. The first message creates a new conversation; the title is
generated from your opening prompt.

## The sidebar

The sidebar lists every conversation you have started, grouped by
recency (Today, Yesterday, last 7 days, older). The active
conversation is highlighted.

- **Switch conversations**: click any title.
- **Pin**: right-click a conversation to keep it at the top.
- **Rename**: right-click → Rename. Titles are user-editable.
- **Delete**: right-click → Delete. Deleted conversations are gone;
  there is no recycle bin yet.
- **Collapse groups**: click the group label (Today / Yesterday / …)
  to collapse and expand.

## Search

The search field at the top of the sidebar filters conversations by
title. There is no full-text body search yet; if you need to find a
conversation by content, scroll the relevant time group.

## Sidebar state

The sidebar's open/collapsed state and the collapsed-group
preferences persist per browser via `localStorage`. There is no
server sync of sidebar state.
```

- [ ] **Step 3: Format**

```bash
cd frontend && bunx --bun @biomejs/biome check --write content/docs/product/conversations.mdx 2>&1 | tail -5
```

### Task 4.3: Write `product/models.mdx`

- [ ] **Step 1: Read the model selector**

```bash
head -80 frontend/features/chat/components/ModelSelectorPopover.tsx 2>/dev/null
ls backend/app/providers/ 2>/dev/null
```

The provider list (which providers Pawrrtal supports) can be inferred from `backend/app/providers/`. Common entries: Claude (Anthropic), Gemini (Google), GPT (OpenAI), and others.

- [ ] **Step 2: Write the file**

Create `frontend/content/docs/product/models.mdx`:

```mdx
---
title: Models
description: How to pick a model and what providers Pawrrtal supports.
---

# Models

Pawrrtal is model-agnostic. Every message you send is routed to the
model you pick in the composer, with no provider lock-in.

## Picking a model

Open the model selector (the chip at the top of the composer). The
popover groups available models by provider; click any model to make
it the current selection. The selection is per-conversation and
persists across reloads.

## Supported providers

The model catalogue is fetched from the backend at runtime so the
list is always current. Today it includes the major providers
(Anthropic Claude, Google Gemini, OpenAI GPT) and a handful of
specialised models for reasoning and coding.

If you have access to a provider's API but Pawrrtal does not list its
model, that means support has not been wired up yet — file a request.

## When to pick which

Rules of thumb, not absolutes:

- **General chat, balanced cost**: a mid-tier model from any
  provider (e.g. Sonnet, Gemini Flash, GPT-class mid).
- **Hard reasoning, long context**: the top tier (Opus, Gemini Pro,
  GPT-class top).
- **Speed-critical UI work, throw-away questions**: the small models
  (Haiku, Flash Lite, Mini variants).
- **Coding**: most providers' top tiers are competent; pick whichever
  you have credits for.

Pawrrtal does not pin you to one provider. Switch mid-conversation
if a model is being unhelpful — the history travels with you.
```

- [ ] **Step 3: Format**

```bash
cd frontend && bunx --bun @biomejs/biome check --write content/docs/product/models.mdx 2>&1 | tail -5
```

### Task 4.4: Write `product/modes.mdx`

- [ ] **Step 1: Read the composer controls**

```bash
head -120 frontend/features/chat/components/ChatComposerControls.tsx 2>/dev/null
grep -rIn "plan-mode\|safety-mode\|reasoning" frontend/features/chat/constants.ts 2>/dev/null | head -20
```

- [ ] **Step 2: Write the file**

Create `frontend/content/docs/product/modes.mdx`:

```mdx
---
title: Modes & Reasoning
description: Plan mode, safety mode, and reasoning levels — what each does, when to use it.
---

# Modes & Reasoning

Pawrrtal exposes three orthogonal toggles in the composer that
change how the model behaves on your next turn.

## Plan mode

When enabled, the model produces a step-by-step plan before doing
any work. Useful for:

- Multi-step tasks where you want to sanity-check the approach
  before code starts changing.
- Open-ended refactors where the "right" decomposition is not
  obvious.

The plan is shown in the conversation; you confirm before the model
proceeds. If the plan is wrong, you can correct it in plain English
and the model re-plans.

Disable plan mode for quick single-step tasks where the overhead is
not worth it.

## Safety mode

Pawrrtal can run tools (read files, edit code, run commands) when
agentic features are enabled. Safety mode adds a confirmation step
before any tool call with side effects.

- **Off**: tools run without prompting. Fastest, lowest friction.
- **On**: every tool call with side effects requires explicit
  approval. Use when working on shared infrastructure or anything
  you cannot easily roll back.

## Reasoning level

For models that support it (Claude's extended thinking, GPT-class
reasoning, Gemini's thinking budget), Pawrrtal exposes a level
selector: `low`, `medium`, `high`.

- **Low**: short reasoning, fast response. Good for simple
  questions.
- **Medium**: balanced. The default for most tasks.
- **High**: longest reasoning budget. Better for hard problems
  where you want the model to chew on the answer.

Higher levels cost more tokens and take longer. Pick `medium` unless
you have a reason to deviate.

The selector only appears for models that support reasoning. Plain
models hide it.
```

- [ ] **Step 3: Format**

```bash
cd frontend && bunx --bun @biomejs/biome check --write content/docs/product/modes.mdx 2>&1 | tail -5
```

### Task 4.5: Write `product/settings.mdx`

- [ ] **Step 1: Read the settings shell**

```bash
ls frontend/features/settings/sections/
head -40 frontend/features/settings/sections/AppearanceSection.tsx 2>/dev/null
```

- [ ] **Step 2: Write the file**

Create `frontend/content/docs/product/settings.mdx`:

```mdx
---
title: Settings
description: Tour of the Settings surface — appearance, account, and per-feature preferences.
---

# Settings

Access settings from the bottom of the sidebar (the gear icon or
your avatar). The settings surface is grouped by section.

## Appearance

Controls for theme (light, dark, system). Color and typography
customisation is **currently a visual mock** — the controls render
but do not persist or change the runtime UI. See the
[ADR explaining why](/docs/handbook/decisions/2026-05-06-rip-theming-system)
for the full context.

## Account

Email, password, and session management. Sign-out lives here.

## Other sections

Additional sections are added over time. New surfaces show up here
without an app update — the settings page is feature-driven, so any
feature can register a settings panel.

## Persistence

Most UI preferences (sidebar state, model selection, reasoning
level) persist per browser via `localStorage`. Account-level
preferences persist on the server. This means a different browser
will start fresh on UI prefs but remember your account state.
```

- [ ] **Step 3: Format**

```bash
cd frontend && bunx --bun @biomejs/biome check --write content/docs/product/settings.mdx 2>&1 | tail -5
```

### Task 4.6: Verify build + check + sentrux

- [ ] **Step 1: Build**

```bash
cd frontend && bun run build
```

Expected: succeeds. Build output should list the five product routes:

- `/docs/product`
- `/docs/product/conversations`
- `/docs/product/models`
- `/docs/product/modes`
- `/docs/product/settings`

- [ ] **Step 2: Check + sentrux**

```bash
cd frontend && bun run check
just sentrux
```

Expected: clean.

### Task 4.7: Commit

```bash
git add frontend/content/docs/product/
git commit -m "$(cat <<'EOF'
feat(docs): seed product section (5 pages)

Write Introduction, Conversations & Sidebar, Models, Modes &
Reasoning, and Settings as feature-tour starter content for the
public docs surface. Reads from the actual app features so the
guidance reflects real UX rather than aspirational behaviour.

Tracks: pawrrtal-s1wa

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 2: Update bean checkbox**

```bash
beans update pawrrtal-s1wa --body-replace-old "- [ ] 4. feat(docs): seed product section (5 pages)" --body-replace-new "- [x] 4. feat(docs): seed product section (5 pages)"
```

---

## Commit 5: Search route, sitemap, parity test, dev-console smoke

**Goal:** Add the local search endpoint, generate a sitemap that includes every docs URL, add a unit test that catches MDX-count drift, and extend the dev-console smoke to cover the docs routes.

### Task 5.1: Add the search endpoint

- [ ] **Step 1: Write the route**

Create `frontend/app/api/search/route.ts`:

```ts
/**
 * Fumadocs search endpoint: builds an Orama index at build time over
 * the handbook and product sources, served from the same Next deploy.
 * No external service.
 */

import { createFromSource } from 'fumadocs-core/search/server';
import { handbookSource, productSource } from '@/lib/source';

export const { GET } = createFromSource(handbookSource, productSource, {
	language: 'english',
});
```

If `createFromSource` does not accept multiple sources directly, the fallback is to create two endpoints (`/api/search/handbook`, `/api/search/product`) or wrap two indexes manually. Verify with `bun run build` after writing — Fumadocs `>=16.7` supports passing multiple sources to `createFromSource`.

- [ ] **Step 2: Format + tsc**

```bash
cd frontend && bunx --bun @biomejs/biome check --write app/api/search/route.ts && bunx tsc --noEmit
```

Expected: clean.

### Task 5.2: Add the sitemap

- [ ] **Step 1: Write the sitemap**

Create `frontend/app/sitemap.ts`:

```ts
/**
 * Sitemap entries for the public docs surface (`/docs/**`) plus the
 * top-level docs landing. The app surfaces (`/`, `/login`, `/signup`,
 * `/(app)/**`) are deliberately excluded — they are private to
 * authenticated users.
 */

import type { MetadataRoute } from 'next';
import { handbookSource, productSource } from '@/lib/source';

const BASE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? 'https://pawrrtal.octaviantocan.com';

/**
 * Generates sitemap entries for `/docs` + every handbook + product page.
 *
 * @returns the sitemap entries
 */
export default function sitemap(): MetadataRoute.Sitemap {
	const handbookEntries: MetadataRoute.Sitemap = handbookSource
		.getPages()
		.map((page) => ({
			url: `${BASE_URL}${page.url}`,
			lastModified: new Date(),
			changeFrequency: 'weekly',
			priority: 0.7,
		}));

	const productEntries: MetadataRoute.Sitemap = productSource
		.getPages()
		.map((page) => ({
			url: `${BASE_URL}${page.url}`,
			lastModified: new Date(),
			changeFrequency: 'weekly',
			priority: 0.8,
		}));

	return [
		{
			url: `${BASE_URL}/docs`,
			lastModified: new Date(),
			changeFrequency: 'monthly',
			priority: 0.9,
		},
		...handbookEntries,
		...productEntries,
	];
}
```

Adjust `BASE_URL` default if the production host changes.

- [ ] **Step 2: Format + tsc**

```bash
cd frontend && bunx --bun @biomejs/biome check --write app/sitemap.ts && bunx tsc --noEmit
```

Expected: clean.

### Task 5.3: Add a parity test for the loaders

- [ ] **Step 1: Write the failing test**

Create `frontend/test/docs-source.test.ts`:

```ts
import { readdir } from 'node:fs/promises';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { handbookSource, productSource } from '@/lib/source';

/**
 * Recursively counts MDX / MD files under a directory, ignoring dotfiles.
 */
async function countMdxFiles(dir: string): Promise<number> {
	const entries = await readdir(dir, { withFileTypes: true });
	let count = 0;
	for (const entry of entries) {
		if (entry.name.startsWith('.')) continue;
		const full = join(dir, entry.name);
		if (entry.isDirectory()) {
			count += await countMdxFiles(full);
		} else if (entry.name.endsWith('.mdx') || entry.name.endsWith('.md')) {
			count += 1;
		}
	}
	return count;
}

describe('Fumadocs loader parity', () => {
	it('handbook loader picks up every MDX file under content/docs/handbook/', async () => {
		const fileCount = await countMdxFiles(
			join(__dirname, '..', 'content', 'docs', 'handbook'),
		);
		const loaderCount = handbookSource.getPages().length;
		expect(loaderCount).toBe(fileCount);
	});

	it('product loader picks up every MDX file under content/docs/product/', async () => {
		const fileCount = await countMdxFiles(
			join(__dirname, '..', 'content', 'docs', 'product'),
		);
		const loaderCount = productSource.getPages().length;
		expect(loaderCount).toBe(fileCount);
	});
});
```

- [ ] **Step 2: Run the test**

```bash
cd frontend && bun run test -- docs-source.test.ts
```

Expected: PASS for both cases. If a file count mismatches, the loader is silently dropping a file — most likely missing frontmatter or a typo in the slug. Fix the offending file, not the test.

### Task 5.4: Extend the dev-console smoke

- [ ] **Step 1: Edit `scripts/dev-console-smoke.mjs`**

Locate the `COLD_BOOT_ROUTES` array:

```js
const COLD_BOOT_ROUTES = ['/login', '/'];
```

Replace with:

```js
const COLD_BOOT_ROUTES = ['/login', '/', '/docs', '/docs/handbook', '/docs/product'];
```

- [ ] **Step 2: Verify the smoke still works**

If a local dev server is running on `:3001`, run the smoke:

```bash
node scripts/dev-console-smoke.mjs
```

Expected: exit `0`. If it exits non-zero, read the console errors it reports — anything tied to Fumadocs hydration is the FOUC theme integration; revisit Task 2.8.

### Task 5.5: Final gate

- [ ] **Step 1: Full check**

```bash
cd frontend && bun run check && bun run test -- docs-source && bun run build
```

Expected: all green.

- [ ] **Step 2: Sentrux**

```bash
just sentrux
```

Expected: clean.

- [ ] **Step 3: Route smoke**

In one terminal `bun run dev`, in another:

```bash
for url in \
  /docs \
  /docs/handbook \
  /docs/handbook/decisions/2026-05-03-adopt-sentrux-architecture-gating \
  /docs/handbook/design-system \
  /docs/product \
  /docs/product/conversations \
  /docs/product/models \
  /docs/product/modes \
  /docs/product/settings \
  /api/search?query=models \
  /sitemap.xml \
  /robots.txt
do
  code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:3001$url")
  echo "$code $url"
done
```

Expected: every URL returns `200`. (The search response with no `query` param may return `400`; passing `?query=models` should return `200` with JSON.)

### Task 5.6: Commit

- [ ] **Step 1: Stage and commit**

```bash
git add frontend/app/api/search/ frontend/app/sitemap.ts frontend/test/docs-source.test.ts scripts/dev-console-smoke.mjs
git commit -m "$(cat <<'EOF'
feat(docs): search route, sitemap, parity test, dev-console smoke

Add /api/search using fumadocs-core/search/server (Orama, local, no
external service), app/sitemap.ts that enumerates every /docs/**
URL plus the landing, and a Vitest parity test that fails when the
file count under content/docs/{handbook,product}/ stops matching
source.getPages().length. Extend scripts/dev-console-smoke.mjs to
cold-boot /docs, /docs/handbook, and /docs/product so dev-only
console errors on the docs surface fail CI.

Tracks: pawrrtal-s1wa

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 2: Update bean checkbox + mark all gates done**

```bash
beans update pawrrtal-s1wa \
  --body-replace-old "- [ ] 5. feat(docs): search route + sitemap" \
  --body-replace-new "- [x] 5. feat(docs): search route + sitemap"
beans update pawrrtal-s1wa --body-replace-old "- [ ] bun run check clean" --body-replace-new "- [x] bun run check clean"
beans update pawrrtal-s1wa --body-replace-old "- [ ] bun run build succeeds" --body-replace-new "- [x] bun run build succeeds"
beans update pawrrtal-s1wa --body-replace-old "- [ ] just sentrux clean" --body-replace-new "- [x] just sentrux clean"
beans update pawrrtal-s1wa --body-replace-old "- [ ] Route smoke (200 on /docs, /docs/handbook, /docs/product, one known slug, /api/search)" --body-replace-new "- [x] Route smoke (200 on /docs, /docs/handbook, /docs/product, one known slug, /api/search)"
beans update pawrrtal-s1wa --body-replace-old "- [ ] source.test.ts asserts MDX count parity" --body-replace-new "- [x] source.test.ts asserts MDX count parity"
beans update pawrrtal-s1wa --body-replace-old "- [ ] dev-console-smoke covers /docs/handbook and /docs/product cold-boot" --body-replace-new "- [x] dev-console-smoke covers /docs/handbook and /docs/product cold-boot"
```

### Task 5.7: Push and open PR

- [ ] **Step 1: Push the branch**

```bash
just push
```

(Routes through `scripts/push.sh` which handles auth switching; do not call `git push` directly.)

- [ ] **Step 2: Open the PR**

```bash
gh pr create --title "feat(docs): add Fumadocs documentation site at /docs" --body "$(cat <<'EOF'
## Summary

- Add Fumadocs documentation site to the existing `frontend/` Next app.
- Public `/docs/handbook/**` rendering the curated subset of repo-root `docs/` (ADRs, agent guidance, CI, deployment).
- Public `/docs/product/**` seeded with 5 user-facing pages (Introduction, Conversations & Sidebar, Models, Modes & Reasoning, Settings).
- Local Orama search at `/api/search`, sitemap, robots.txt, dev-console smoke coverage.
- No backend changes. No new deployment target.

Spec: `frontend/content/docs/handbook/decisions/2026-05-14-add-fumadocs-documentation-site` (moved from `docs/decisions/...` in commit 3 — that's the new home).

Tracks: pawrrtal-s1wa

## Test plan

- [ ] CI green on `bun run check`, `bun run build`, `bun run test`, `just sentrux`.
- [ ] `/docs`, `/docs/handbook`, `/docs/product`, and at least one known handbook slug return 200 on a deployed preview.
- [ ] `/api/search?query=models` returns JSON.
- [ ] Cold-boot of `/docs/handbook` produces no React 19 hydration warnings (verified by `scripts/dev-console-smoke.mjs`).
- [ ] Spot-check that the existing app surfaces (chat, settings, login, signup) are unchanged.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

- [ ] **Step 3: Flip the bean to completed**

```bash
beans update pawrrtal-s1wa -s completed --body-append "$(cat <<'EOF'

## Summary of Changes

Added Fumadocs documentation site to the existing frontend/ Next 16 app
in 5 commits:

1. Scaffolded dependencies and config (source.config.ts, next.config.ts
   createMDX wrap, collections/* TS alias, .source/ gitignored).
2. Created the /docs route tree (landing chooser, handbook + product
   layouts, dynamic [[...slug]] pages), shared layout config, MDX
   component registry, RootProvider wrap at app/layout.tsx, robots.txt,
   Fumadocs CSS imports.
3. Migrated handbook content via `git mv` of docs/decisions, docs/agents,
   docs/ci, docs/deployment into frontend/content/docs/handbook/; added
   YAML frontmatter to every file; created design-system.mdx pointing
   at repo-root DESIGN.md; swept ~30 references across .claude/rules/,
   AGENTS.md, CLAUDE.md, .beans/, docs/plans/, and one user-visible
   Settings copy string.
4. Seeded /docs/product with 5 feature-tour pages.
5. Added /api/search (Orama, local), sitemap, Vitest parity test, and
   /docs/* coverage in scripts/dev-console-smoke.mjs.

Stock Fumadocs theme. Public surface (no auth gate). Single deployment.

Spec: /docs/handbook/decisions/2026-05-14-add-fumadocs-documentation-site
EOF
)"
```

---

## Self-review

After completing all commits, verify against the spec.

**Spec coverage:** Each section of the spec maps to tasks in this plan:

- Goals (handbook + product, stock theme, no new deployment, local search) → covered by Commits 2, 4, 5.
- File layout → Commits 1 (config), 2 (routes/providers), 3 (handbook content), 4 (product content), 5 (search/sitemap/tests).
- Routing model (two loaders, per-section layout) → Tasks 2.1, 2.6, 2.7.
- Provider composition → Task 2.8.
- Content migration → Tasks 3.1–3.6.
- Public access / SEO / search → Tasks 2.10, 5.1, 5.2.
- Testing → Tasks 5.3, 5.4, plus build/check/sentrux at every commit.
- Phasing (5 commits) → matches the plan one-for-one.
- Risks (FOUC theme integration, ESM config, path sweep) → addressed in Tasks 2.8, 1.3, 3.5.

**Placeholder scan:** No TBD / TODO entries in the plan. Every code block is complete. Every command is concrete.

**Type consistency:** `handbookSource` / `productSource` named identically across Tasks 2.1 (definition), 2.6/2.7 (consumption in pages), 5.1 (search), 5.2 (sitemap), 5.3 (test). `getMDXComponents` defined once in Task 2.3, called consistently in Tasks 2.6/2.7. `baseOptions` defined Task 2.2, called Tasks 2.6/2.7.

No issues found.
