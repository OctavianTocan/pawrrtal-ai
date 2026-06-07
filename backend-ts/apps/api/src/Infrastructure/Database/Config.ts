/**
 * @title Database file location (SQLite)
 *
 * Replicates the Python backend's DATABASE_URL + SQLITE_DB_FILENAME logic
 * exactly so the Effect TS strangler hits the identical .db file in dev.
 *
 * Python source of truth:
 * - backend/app/infrastructure/config.py:28 (database_url + sqlite_db_filename fields + docstrings)
 * - backend/app/infrastructure/config_urls.py:8 (normalize_database_url)
 * - backend/app/infrastructure/config.py:473 (_normalized_database_url property)
 *
 * The derivation must be behaviorally identical for the file path.
 * We only extract the bare filename because @effect/sql-sqlite-node + better-sqlite3
 * takes a path string (or ":memory:"), unlike SQLAlchemy which wants full URLs.
 */

import { Config } from 'effect';

/** Subset of `@effect/sql-sqlite-node` `SqliteClientConfig` used by `SqliteClient.layerConfig`. */
type SqliteFilenameConfig = { readonly filename: string };

/* ────────────────────────────────────────────────────────────────────────── */
/* Raw inputs — match the Python Settings fields 1:1                          */
/* ────────────────────────────────────────────────────────────────────────── */

const databaseUrl = Config.string('DATABASE_URL').pipe(Config.withDefault(''));

const sqliteDbFilename = Config.string('SQLITE_DB_FILENAME').pipe(
	Config.withDefault('pawrrtal.db')
);

/* ────────────────────────────────────────────────────────────────────────── */
/* Pure derivation (the only "logic" — keep it small and obvious)             */
/* ────────────────────────────────────────────────────────────────────────── */

/**
 * Mirrors Python's normalize_database_url + extracts the bare filename
 * that better-sqlite3 expects.
 */
const resolveFilename = (url: string, filename: string): string => {
	const u = url.trim();
	const name = filename.trim() || 'pawrrtal.db';

	if (!u) return name;
	if (u.includes(':memory:')) return ':memory:';

	// Legacy postgres:// → postgresql:// (same as Python)
	const normalized = u.replace(/^postgres:\/\//, 'postgresql://');

	// Non-sqlite explicit DATABASE_URL (common when other services use Postgres).
	// Fall back to the sqlite name so local TS dev isn't polluted.
	if (normalized.startsWith('postgresql://')) {
		return name;
	}

	// Bare filename with no scheme (Python treats this as sqlite:///<value>)
	if (!normalized.includes('://')) {
		return normalized;
	}

	if (normalized.startsWith('sqlite')) {
		const rest = normalized.replace(/^sqlite(\+[^:]+)?:\/\//i, '');

		// sqlite:///./pawrrtal.db  → ./pawrrtal.db
		// sqlite:////tmp/foo.db    → /tmp/foo.db
		if (rest.startsWith('/./') || rest.startsWith('/../')) return rest.slice(1);
		if (rest.startsWith('//')) return rest.slice(1);
		return rest || name;
	}

	return name;
};

/* ────────────────────────────────────────────────────────────────────────── */
/* The thing you hand to SqliteClient.layerConfig                             */
/* ────────────────────────────────────────────────────────────────────────── */

export const DatabaseConfig: Config.Wrap<SqliteFilenameConfig> = {
	filename: Config.all({ databaseUrl, sqliteDbFilename }).pipe(
		Config.map(({ databaseUrl, sqliteDbFilename }) =>
			resolveFilename(databaseUrl, sqliteDbFilename)
		)
	),
};
