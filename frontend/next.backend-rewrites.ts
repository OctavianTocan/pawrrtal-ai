const DEFAULT_BACKEND_INTERNAL_URL = 'http://127.0.0.1:8000';

export interface BackendRewriteRule {
	source: string;
	destination: string;
}

interface BackendRewriteEnv {
	BACKEND_INTERNAL_URL?: string;
	NEXT_ENABLE_BACKEND_REWRITES?: string;
	NODE_ENV?: string;
}

function backendRewritesEnabled(env: BackendRewriteEnv): boolean {
	return (
		env.NODE_ENV !== 'production' ||
		Boolean(env.BACKEND_INTERNAL_URL) ||
		env.NEXT_ENABLE_BACKEND_REWRITES === '1'
	);
}

export function backendRewriteRules(env: BackendRewriteEnv = process.env): BackendRewriteRule[] {
	if (!backendRewritesEnabled(env)) {
		return [];
	}

	const destinationBase = (env.BACKEND_INTERNAL_URL ?? DEFAULT_BACKEND_INTERNAL_URL).replace(
		/\/$/,
		''
	);

	return [
		{
			source: '/api/v1/:path*',
			destination: `${destinationBase}/api/v1/:path*`,
		},
		{
			source: '/auth/:path*',
			destination: `${destinationBase}/auth/:path*`,
		},
		{
			source: '/users/:path*',
			destination: `${destinationBase}/users/:path*`,
		},
	];
}
