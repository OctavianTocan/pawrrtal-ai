import 'server-only';
import { API_ENDPOINTS } from './api';

const BACKEND_INTERNAL_URL = process.env.BACKEND_INTERNAL_URL ?? 'http://127.0.0.1:8000';

const SERVER_API_KEY = process.env.BACKEND_API_KEY ?? process.env.NEXT_PUBLIC_BACKEND_API_KEY ?? '';

function buildServerApiUrl(path: string): string {
	const baseUrl = BACKEND_INTERNAL_URL.replace(/\/$/, '');
	const normalizedPath = path.startsWith('/') ? path : `/${path}`;
	return `${baseUrl}${normalizedPath}`;
}

/** Fetch a backend route from server-only Next.js code. */
export function serverApiFetch(path: string, init?: RequestInit): Promise<Response> {
	const headers = new Headers(init?.headers);
	if (SERVER_API_KEY) {
		headers.set('X-Pawrrtal-Key', SERVER_API_KEY);
	}
	return fetch(buildServerApiUrl(path), { ...init, headers });
}

export { API_ENDPOINTS };
