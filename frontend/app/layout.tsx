/**
 * Root Next.js layout: HTML shell, theme bootstrap script, and global providers.
 *
 * @fileoverview Applies FOUC-safe dark-mode class before hydration and wraps the tree in {@link Providers}.
 */

import { Agentation } from 'agentation';
import { RootProvider } from 'fumadocs-ui/provider/next';
import type { Metadata } from 'next';
import { Geist, Geist_Mono, Newsreader } from 'next/font/google';
import Script from 'next/script';
import './globals.css';
import { Providers } from './providers';

/**
 * Editorial display face — Mistral-inspired near-serif voice for hero
 * displays and `h1`. Self-hosted via `next/font/google` so the variable
 * file is FOUC-safe; the loaded family is exposed as the CSS variable
 * `--font-display-loaded`, which the `--font-display-stack` in
 * `globals.css` references with a system-serif fallback chain so heading
 * type still has editorial character before the web font arrives.
 */
const newsreader = Newsreader({
	subsets: ['latin'],
	weight: ['400', '500', '600'],
	variable: '--font-display-loaded',
	display: 'swap',
});

/**
 * Geist + Geist Mono — preloaded so the Cursor preset's typography
 * actually renders the moment the user picks it. The fonts cite
 * themselves by name (`"Geist"`, `"Geist Mono"`) inside the preset's
 * font stack, so as long as the families are resident in the DOM, the
 * preset paints correctly.
 */
const geist = Geist({
	subsets: ['latin'],
	variable: '--font-geist-loaded',
	display: 'swap',
});
const geistMono = Geist_Mono({
	subsets: ['latin'],
	variable: '--font-geist-mono-loaded',
	display: 'swap',
});

export const metadata: Metadata = {
	title: 'Pawrrtal',
	description:
		'An AI chat application built with Next.js and FastAPI, all by hand, no code generation tools (or AI) used.',
};

/**
 * Agentation is an interactive inspection layer that intentionally blocks page
 * interactions while active. Keep it opt-in so normal dev sessions, including
 * Tailscale-served login flows, remain usable.
 */
const enableAgentation =
	process.env.NODE_ENV === 'development' && process.env.ENABLE_AGENTATION === 'true';

/**
 * Root layout for all routes: `Providers` + blocking theme script on `<html>`.
 */
export default function RootLayout({
	children,
}: Readonly<{
	children: React.ReactNode;
}>) {
	return (
		<html
			lang="en"
			suppressHydrationWarning
			className={`${newsreader.variable} ${geist.variable} ${geistMono.variable}`}
		>
			{/*
				suppressHydrationWarning is required because the blocking theme script
				below may add the 'dark' class to <html> before React hydration, causing
				a mismatch between server and client. This is intentional and safe — the
				script only modifies the class list, not the DOM structure.
			*/}
			<head>
				{/* System theme detection — runs synchronously before hydration
				    to prevent FOUC.  Body lives in `frontend/public/theme-detection.js`.

				    Why a `src="/theme-detection.js"` script rather than an inline body:
				    React 19's client reconciler emits a fatal warning ("Encountered
				    a script tag while rendering React component") for any `<script>`
				    element it sees with inline content — including those produced by
				    `next/script` with `dangerouslySetInnerHTML` or children.  The
				    warning cascades and breaks hydration of the rest of the tree
				    (notably the `QueryClientProvider` in `app/providers.tsx`, which
				    surfaces as a secondary "No QueryClient set" error).  A `<Script
				    src>` tag has no body and is treated identically to the React Grab
				    loader below — React skips it on the client and the warning never
				    fires.  Verified against the failure mode reported by the operator
				    on 2026-05-08. */}
				<Script src="/theme-detection.js" strategy="beforeInteractive" />
				{/* React Grab */}
				{enableAgentation && (
					<Script
						src="//unpkg.com/react-grab/dist/index.global.js"
						crossOrigin="anonymous"
						strategy="beforeInteractive"
					/>
				)}
			</head>
			<body>
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
					search={{
						// preload=false keeps the SearchDialog (and its Radix Dialog
						// tree) out of the server render and initial hydration. With
						// the default preload=true, fumadocs renders <Dialog
						// open={false}> on every page; once Radix's `aria-hidden`
						// package marks elements as `data-aria-hidden` (e.g. via a
						// sibling dialog opening), the next hydration on a docs
						// route surfaces an `aria-hidden` attribute mismatch on the
						// SearchDialogFooter div. Mounting only on first invocation
						// (Cmd/Ctrl+K) avoids the SSR/CSR divergence entirely.
						preload: false,
					}}
				>
					<Providers>{children}</Providers>
					{enableAgentation && <Agentation />}
				</RootProvider>
			</body>
		</html>
	);
}
