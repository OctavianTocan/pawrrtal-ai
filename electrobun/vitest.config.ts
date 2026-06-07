/**
 * Vitest config for the Electrobun main-process workspace.
 *
 * Runs in a node environment — tests exercise pure logic in src/bun/
 * (workspace validation, permission state machine, JSON store) without
 * needing a real Electrobun/Bun runtime or a display server.
 *
 * The electrobun/bun import used in main process files is mocked via
 * vi.mock() in each test file so tests don't require the native binary.
 */
import { defineConfig } from 'vitest/config';

export default defineConfig({
	test: {
		environment: 'node',
		include: ['src/**/*.test.ts'],
		exclude: ['dist/**', 'node_modules/**'],
		setupFiles: ['./vitest.setup.ts'],
		coverage: {
			provider: 'v8',
			reporter: ['text', 'json-summary', 'html'],
			include: ['src/bun/**/*.ts'],
			exclude: ['**/*.test.ts', 'src/bun/index.ts'],
		},
	},
});
