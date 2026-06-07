import type * as React from 'react';

/** Multi-color Google "G" logo. */
export function GoogleIcon({ className }: { className?: string }): React.ReactNode {
	return (
		<svg
			aria-hidden="true"
			className={className}
			viewBox="0 0 24 24"
			xmlns="http://www.w3.org/2000/svg"
		>
			<title>Google</title>
			<path
				d="M21.35 11.1H12v2.83h5.39c-.23 1.38-1.65 4.05-5.39 4.05-3.24 0-5.88-2.69-5.88-6s2.64-6 5.88-6c1.84 0 3.08.78 3.79 1.45l2.59-2.5C16.62 3.4 14.55 2.5 12 2.5 6.74 2.5 2.5 6.74 2.5 12s4.24 9.5 9.5 9.5c5.49 0 9.12-3.86 9.12-9.3 0-.63-.07-1.1-.17-1.6z"
				fill="#4285F4"
			/>
			<path
				d="M12 22c2.7 0 4.96-.9 6.62-2.43l-3.16-2.59c-.85.59-2 1-3.46 1-2.66 0-4.92-1.79-5.73-4.19H3.04v2.63A9.5 9.5 0 0012 22z"
				fill="#34A853"
			/>
			<path
				d="M6.27 13.79A5.7 5.7 0 015.96 12c0-.62.11-1.22.31-1.79V7.58H3.04a9.5 9.5 0 000 8.84l3.23-2.63z"
				fill="#FBBC05"
			/>
			<path
				d="M12 5.95c1.47 0 2.46.63 3.02 1.16l2.21-2.16C15.93 3.66 14.18 2.9 12 2.9A9.5 9.5 0 003.04 7.58l3.23 2.63C7.08 7.74 9.34 5.95 12 5.95z"
				fill="#EA4335"
			/>
		</svg>
	);
}
