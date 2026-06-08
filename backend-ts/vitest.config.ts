import { mergeConfig } from 'vitest/config';
import shared from './vitest.shared';

export default mergeConfig(shared, {
	test: {
		include: ['**/test/**/*.test.ts'],
		exclude: ['**/node_modules/**', '**/dist/**', '**/.next/**'],
		globals: false,
		testTimeout: 30_000,
	},
});
