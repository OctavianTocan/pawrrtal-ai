import path from 'node:path';
import type { ViteUserConfig } from 'vitest/config';

const config: ViteUserConfig = {
	esbuild: {
		target: 'es2020',
	},
	optimizeDeps: {
		exclude: ['bun:sqlite'],
	},
	resolve: {
		// Mirror the apps/api tsconfig `@/*` alias so test fixtures can
		// `import { DatabaseLive } from '@/Infrastructure/Database'` like
		// production code does. The root tsconfig is consumed by `tsc`;
		// vitest's resolver is vite, so it needs the alias too.
		alias: {
			'@': path.resolve(__dirname, 'apps/api/src'),
		},
	},
};

export default config;
