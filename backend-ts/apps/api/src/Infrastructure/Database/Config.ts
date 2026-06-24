import { Config } from 'effect';

type SqliteFilenameConfig = { readonly filename: string };

/** Default SQLite database filename. */
const DEFAULT_SQLITE_DB_FILENAME = 'pawrrtal.db';

/** Database URL. */
const databaseUrl = Config.string('DATABASE_URL').pipe(Config.withDefault(''));

/** SQLite database filename. */
const sqliteDbFilename = Config.string('SQLITE_DB_FILENAME').pipe(
	Config.withDefault(DEFAULT_SQLITE_DB_FILENAME)
);

/** Maps `DATABASE_URL` and `SQLITE_DB_FILENAME` to a sqlite path or `:memory:`. */
const resolveFilename = (databaseUrl: string, sqliteDbFilename: string): string => {
	const databaseUrlTrimmed = databaseUrl.trim();
	const sqliteFilename = sqliteDbFilename.trim() || DEFAULT_SQLITE_DB_FILENAME;

	if (!databaseUrlTrimmed) {
		return sqliteFilename;
	}
	if (databaseUrlTrimmed.includes(':memory:')) {
		return ':memory:';
	}

	const normalizedUrl = databaseUrlTrimmed.replace(/^postgres:\/\//, 'postgresql://');

	if (normalizedUrl.startsWith('postgresql://')) {
		return sqliteFilename;
	}

	if (!normalizedUrl.includes('://')) {
		return normalizedUrl;
	}

	if (normalizedUrl.startsWith('sqlite')) {
		const sqlitePath = normalizedUrl.replace(/^sqlite(\+[^:]+)?:\/\//i, '');

		if (sqlitePath.startsWith('/./') || sqlitePath.startsWith('/../')) {
			return sqlitePath.slice(1);
		}
		if (sqlitePath.startsWith('//')) {
			return sqlitePath.slice(1);
		}
		return sqlitePath || sqliteFilename;
	}

	return sqliteFilename;
};

/** Effect config for the sqlite filename consumed by `SqliteClient.layerConfig`. */
export const DatabaseConfig: Config.Wrap<SqliteFilenameConfig> = {
	filename: Config.all({ databaseUrl, sqliteDbFilename }).pipe(
		Config.map(({ databaseUrl: url, sqliteDbFilename: filename }) =>
			resolveFilename(url, filename)
		)
	),
};
