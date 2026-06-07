import path from 'node:path';
import react from '@vitejs/plugin-react';
import { defineConfig, type Plugin } from 'vitest/config';

// Force NODE_ENV=test before vitest's React plugin picks the build to
// alias.  Without this, Bun's vitest runtime defaults to production for
// react-dom, which strips `React.act` and breaks @testing-library's
// `render` helper.  Set as early as possible — the React plugin reads
// it during module init.

/**
 * Vite plugin that stubs MDX collection imports used by `.source/server.ts`.
 *
 * Fumadocs' code-generated `.source/server.ts` imports every MDX file with
 * a custom `?collection=<name>` query parameter so the fumadocs-mdx Vite
 * plugin can process them. In a Vitest run there is no fumadocs-mdx pipeline,
 * so we intercept those virtual imports and return a minimal ESM stub that
 * satisfies `fumadocs-mdx/runtime/server`'s expectations: a default export
 * (the MDX React component) plus the `toc`, `structuredData`, and
 * `frontmatter` side-car exports.
 */
function fumadocsMdxCollectionStub(): Plugin {
	return {
		name: 'fumadocs-mdx-collection-stub',
		enforce: 'pre',
		resolveId(id: string, importer: string | undefined): string | null {
			// `.source/server.ts` imports each MDX file as a relative specifier
			// with a `?collection=<name>` query that the fumadocs-mdx Vite plugin
			// normally processes.  Vite may strip the query before calling
			// resolveId, so we match on the file extension alone when the importer
			// is the generated server file, or match on the full specifier with
			// the query param as a belt-and-braces fallback.
			const isFromServer = importer?.includes('.source/server');
			if (/\.(mdx?)\?collection=/.test(id) || (isFromServer && /\.(mdx?)$/.test(id))) {
				return `\0fumadocs-stub:${id}`;
			}
			return null;
		},
		load(id: string): string | null {
			if (!id.startsWith('\0fumadocs-stub:')) return null;
			// Return just enough for fumadocs-mdx/runtime/server to build page
			// objects: a default React component, an empty toc, empty
			// structuredData, and a minimal frontmatter with a title derived
			// from the file path so loader.getPages() counts it.
			const filePath = id.replace('\0fumadocs-stub:', '').replace(/\?collection=\w+$/, '');
			const title =
				filePath
					.split('/')
					.pop()
					?.replace(/\.mdx?$/, '') ?? 'page';
			return [
				'import { createElement } from "react";',
				'export default function MDXContent() { return createElement("div", null); }',
				'export const toc = [];',
				'export const structuredData = { contents: [], headings: [] };',
				`export const frontmatter = { title: ${JSON.stringify(title)} };`,
			].join('\n');
		},
	};
}

if (process.env.NODE_ENV === undefined) {
	// `process.env.NODE_ENV` is typed `readonly` under @types/node when
	// strictly resolved, even though the runtime mutation works fine.
	// Cast through `unknown` to keep TS happy without disabling strict.
	(process.env as unknown as Record<string, string>).NODE_ENV = 'test';
}

export default defineConfig({
	plugins: [react(), fumadocsMdxCollectionStub()],
	resolve: {
		alias: {
			'@': path.resolve(__dirname),
			// Fumadocs' generated `.source/server.ts` is re-exported under the
			// `collections/*` path alias defined in tsconfig.json. Vitest needs
			// the same mapping so tests that import `@/lib/source` (which in
			// turn imports `collections/server`) can resolve the generated file.
			'collections/server': path.resolve(__dirname, '.source/server.ts'),
			// Use the local vendored package when it exists; fall back to the
			// manual __mocks__ stub so tests work in ephemeral checkouts where
			// the lib/react-dropdown subpackage hasn't been set up.
			'@octavian-tocan/react-dropdown': (() => {
				const vendored = path.resolve(__dirname, 'lib/react-dropdown/src/index.ts');
				const stub = path.resolve(
					__dirname,
					'__mocks__/@octavian-tocan/react-dropdown.tsx'
				);
				// biome-ignore lint/style/useNodejsImportProtocol: CJS require in IIFE
				return require('fs').existsSync(vendored) ? vendored : stub;
			})(),
			'@octavian-tocan/react-overlay': path.resolve(
				__dirname,
				'lib/react-overlay/src/index.ts'
			),
			// streamdown is ESM-only; inline it so vite can transform it, or
			// use the plain-text stub in environments where ESM interop is tricky.
			streamdown: path.resolve(__dirname, '__mocks__/streamdown.tsx'),
		},
	},
	// Vitest doesn't force NODE_ENV=test by default; React 19 loads its
	// production bundle (no React.act) when NODE_ENV=production.  Explicitly
	// set it here so @testing-library/react can call React.act correctly.
	define: {
		'process.env.NODE_ENV': JSON.stringify('test'),
	},
	test: {
		environment: 'jsdom',
		// Reset `.mock.calls` / `.mock.results` between tests so a spy from
		// one test can't quietly satisfy an assertion in another. We
		// deliberately don't enable `mockReset` / `restoreMocks` so test-
		// scoped `vi.fn()` implementations and `vi.spyOn` stubs survive
		// across assertions inside the same test. See #278 for context.
		clearMocks: true,
		exclude: [
			'**/.next/**',
			'**/node_modules/**',
			'**/e2e/**',
			// react-dropdown owns its own vitest config (globals enabled). When
			// the frontend's runner picks them up, the bare `describe/it/expect`
			// references fail to resolve. Run package tests via:
			//   `cd lib/react-dropdown && bunx vitest run`
			'lib/react-dropdown/**',
			'lib/react-overlay/**',
		],
		globals: false,
		setupFiles: ['./test/setup.ts'],
		coverage: {
			provider: 'v8',
			reporter: ['text', 'json-summary', 'html'],
			include: [
				'lib/**/*.{ts,tsx}',
				'hooks/**/*.{ts,tsx}',
				'features/**/*.{ts,tsx}',
				'components/**/*.{ts,tsx}',
			],
			exclude: [
				'**/*.test.{ts,tsx}',
				'**/*.spec.{ts,tsx}',
				'**/__tests__/**',
				'**/node_modules/**',
				'**/.next/**',
				'components/ui/**',
				'app/**',
				// V8 coverage remaps currently parse this untested TSX file as
				// plain JS under Rolldown. Keep hook/reducer coverage active and
				// exclude this presentation layer until the parser path supports TSX.
				'features/chat/ChatView.tsx',
				// This helper imports Next's server-only marker. Vitest's V8
				// uncovered-file pass remaps it as plain JS, so collect coverage
				// through callers instead of parsing this server-only shim.
				'lib/server-api.ts',
				// Coverage for the vendored react-dropdown package is owned by
				// its own vitest config in lib/react-dropdown/.
				'lib/react-dropdown/**',
				'lib/react-overlay/**',
			],
		},
	},
});
