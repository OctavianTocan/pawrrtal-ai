/** SQLite filename config — mirrors Python `DATABASE_URL` / `SQLITE_DB_FILENAME` resolution. */

import { Config } from 'effect';

type SqliteFilenameConfig = { readonly filename: string };

const databaseUrl = Config.string('DATABASE_URL').pipe(Config.withDefault(''));

const sqliteDbFilename = Config.string('SQLITE_DB_FILENAME').pipe(
	Config.withDefault('pawrrtal.db')
);

/** Derives the sqlite filename or `:memory:` path from env vars. */
const resolveFilename = (url: string, filename: string): string => {
	const u = url.trim();
	const name = filename.trim() || 'pawrrtal.db';

	if (!u) {
		return name;
	}
	if (u.includes(':memory:')) {
		return ':memory:';
	}

	const normalized = u.replace(/^postgres:\/\//, 'postgresql://');

	if (normalized.startsWith('postgresql://')) {
		return name;
	}

	if (!normalized.includes('://')) {
		return normalized;
	}

	if (normalized.startsWith('sqlite')) {
		const rest = normalized.replace(/^sqlite(\+[^:]+)?:\/\//i, '');

		if (rest.startsWith('/./') || rest.startsWith('/../')) {
			return rest.slice(1);
		}
		if (rest.startsWith('//')) {
			return rest.slice(1);
		}
		return rest || name;
	}

	return name;
};

export const DatabaseConfig: Config.Wrap<SqliteFilenameConfig> = {
	filename: Config.all({ databaseUrl, sqliteDbFilename }).pipe(
		Config.map(({ databaseUrl, sqliteDbFilename }) =>
			resolveFilename(databaseUrl, sqliteDbFilename)
		)
	),
};
