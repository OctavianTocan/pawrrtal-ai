/** Return the server-side backend origin for Next.js runtime fetches. */
export function getBackendInternalUrl(): string {
	return (
		process.env.BACKEND_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8000'
	);
}

/** Build an absolute backend URL for server-side Next.js fetches. */
export function buildServerApiUrl(path: string): string {
	const baseUrl = getBackendInternalUrl().replace(/\/$/, '');
	const normalizedPath = path.startsWith('/') ? path : `/${path}`;
	return `${baseUrl}${normalizedPath}`;
}
