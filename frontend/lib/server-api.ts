import 'server-only';
import { API_ENDPOINTS } from './api';
import { buildServerApiUrl } from './server-api-url';

/** Fetch a backend route from server-only Next.js code. */
export function serverApiFetch(path: string, init?: RequestInit): Promise<Response> {
	const headers = new Headers(init?.headers);
	return fetch(buildServerApiUrl(path), { ...init, headers });
}

export { API_ENDPOINTS };
