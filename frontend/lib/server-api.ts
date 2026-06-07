import 'server-only';
import { API_ENDPOINTS } from './api';
import { buildServerApiUrl } from './server-api-url';

/** Fetch a backend route from server-only Next.js code. */
export function serverApiFetch(path: string, init?: RequestInit): Promise<Response> {
	const serverApiKey = process.env.BACKEND_API_KEY ?? '';
	const headers = new Headers(init?.headers);
	if (serverApiKey) {
		headers.set('X-Pawrrtal-Key', serverApiKey);
	}
	return fetch(buildServerApiUrl(path), { ...init, headers });
}

export { API_ENDPOINTS };
