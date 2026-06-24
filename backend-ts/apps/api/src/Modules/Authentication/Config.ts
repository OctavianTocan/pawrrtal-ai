import { Config } from 'effect';

/** Config for the allowed emails list. */
export const AllowedEmailsConfig = Config.string('ALLOWED_EMAILS').pipe(
	Config.withDefault(''),
	Config.map(parseAllowedEmails)
);

/** Parse a comma-separated list of email addresses into a set of lowercase email addresses. */
export function parseAllowedEmails(raw: string): ReadonlySet<string> {
	return new Set(
		raw
			.split(',')
			.map((addr) => addr.trim().toLowerCase())
			.filter((addr) => addr.length > 0)
	);
}

/** Config for the authentication module. */
export const AuthenticationConfig = Config.all({
	allowedEmails: AllowedEmailsConfig,
});

/** Type for the authentication module config. */
export type AuthenticationConfig = Config.Success<typeof AuthenticationConfig>;
