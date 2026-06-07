/**
 * Next.js request middleware: session gate for protected app routes.
 *
 * @fileoverview Runs on matched paths (see {@link config.matcher}). Public auth pages and
 *              the public `/docs/**` documentation surface bypass the session check; all
 *              other routes require the `session_token` cookie or redirect to `/login`.
 */

import { type NextRequest, NextResponse } from 'next/server';

/** Application roots that require an authenticated session. */
const protectedRoutes = ['/'];

/** Exact-match routes that must stay reachable without a session (sign-in flows). */
const publicRoutes = ['/login', '/signup'];

/**
 * Path prefixes that are public for the entire subtree.
 *
 * `/docs` hosts the public Fumadocs documentation site (handbook + product
 * sections). Without this carve-out, the `protectedRoutes = ['/']`
 * `startsWith` check below treats every URL — including `/docs/*` — as
 * protected, redirecting anonymous visitors to `/login`.
 */
const publicPrefixes = ['/docs'];

/** True when `path` is under any protected prefix. */
const isProtectedRoute = (path: string) => protectedRoutes.some((route) => path.startsWith(route));

/** True when `path` is a public auth page or sits under a public subtree. */
const isPublicRoute = (path: string) =>
	publicRoutes.includes(path) ||
	publicPrefixes.some((prefix) => path === prefix || path.startsWith(`${prefix}/`));

/**
 * Next.js middleware entrypoint: enforces cookie auth on protected paths.
 *
 * @param request - Incoming request (pathname + cookies).
 * @returns `NextResponse.next()` to continue, or a redirect to `/login` when unauthenticated.
 */
export function proxy(request: NextRequest) {
	const path = request.nextUrl.pathname;
	const sessionToken = request.cookies.get('session_token');

	if (isPublicRoute(path)) {
		return NextResponse.next();
	}

	if (isProtectedRoute(path) && !sessionToken) {
		// Preserve where the user was so the login page can return them
		// after a fresh sign-in (issue #94). ``useAuthedFetch`` uses the
		// same ``?redirect=`` contract when a stale-token 401 bounces a
		// running session back to /login.
		const loginUrl = new URL('/login', request.url);
		const target = path + request.nextUrl.search;
		loginUrl.searchParams.set('redirect', target);
		return NextResponse.redirect(loginUrl);
	}

	return NextResponse.next();
}

/**
 * Limits middleware to page navigations; skips backend-owned prefixes,
 * framework static assets, favicon, and anything served from
 * `frontend/public/` (matched heuristically by trailing file extension —
 * e.g. `theme-detection.js`, `*.svg`, `*.png`). Without the file-extension
 * carve-out, every `public/` asset request from a cold client gets
 * redirected to `/login` itself, returning HTML that the browser tries to
 * parse as JS.
 */
export const config = {
	matcher: ['/((?!api|auth|users|_next/static|_next/image|favicon.ico|.+\\.[a-zA-Z0-9]+$).*)'],
};
