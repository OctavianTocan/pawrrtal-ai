/** Resolve and validate a remote Pawrrtal web app URL. */
export function resolveRemoteAppUrl(value: string | undefined): string | null {
	const trimmed = value?.trim();
	if (!trimmed) return null;
	const candidate = trimmed.includes('://') ? trimmed : `https://${trimmed}`;
	let parsed: URL;
	try {
		parsed = new URL(candidate);
	} catch {
		throw new Error('PAWRRTAL_REMOTE_URL must be a valid https:// URL or host.');
	}
	if (parsed.protocol !== 'https:') {
		throw new Error('PAWRRTAL_REMOTE_URL must be an https:// URL.');
	}
	if (isLoopbackHostname(parsed.hostname)) {
		throw new Error('PAWRRTAL_REMOTE_URL cannot point at localhost or loopback.');
	}
	return parsed.origin;
}

function isLoopbackHostname(hostname: string): boolean {
	const normalized = hostname
		.toLowerCase()
		.replace(/^\[|\]$/g, '')
		.split('%')[0];
	return (
		normalized === 'localhost' ||
		normalized.endsWith('.localhost') ||
		normalized === '::1' ||
		/^127(?:\.\d{1,3}){0,3}$/.test(normalized)
	);
}
