import { Effect, Option } from 'effect';
import type { ConfigError } from './Errors';
import { failConfig } from './Errors';
import type { OptionalText, PersistedConfigRecord, PersistedConfigValue } from './Schemas';

/**
 * Rejects profile config values that include secret-looking keys.
 *
 * @param value - Profile config object to inspect.
 * @param path - Logical path used in validation messages.
 * @returns Effect that succeeds when no secret-looking key is present.
 */
export function validateNoSecrets(value: PersistedConfigRecord, path = 'config'): Effect.Effect<void, ConfigError> {
  return Option.match(findSecretPath(value, path), {
    onNone: () => Effect.void,
    onSome: (secretPath) => failConfig(`Profile config cannot persist secret field '${secretPath}'.`),
  });
}

/** Returns the first secret-looking nested path, if any. */
function findSecretPath(value: PersistedConfigValue, path: string): OptionalText {
  if (!isConfigRecord(value)) {
    return Option.none();
  }

  for (const [key, nested] of Object.entries(value)) {
    const nextPath = `${path}.${key}`;
    if (isSecretKey(key)) {
      return Option.some(nextPath);
    }
    const nestedPath = findSecretPath(nested, nextPath);
    if (Option.isSome(nestedPath)) {
      return nestedPath;
    }
  }

  return Option.none();
}

/** Returns true for persisted config records. */
function isConfigRecord(value: PersistedConfigValue): value is PersistedConfigRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** Returns true when a field name looks like auth or secret material. */
function isSecretKey(key: string): boolean {
  const normalized = key.toLowerCase().replaceAll('-', '_');
  return (
    normalized.includes('token') ||
    normalized.includes('secret') ||
    normalized.includes('cookie') ||
    normalized.includes('password') ||
    normalized.includes('api_key') ||
    normalized.includes('access_key') ||
    normalized.includes('private_key') ||
    normalized.includes('signing_key') ||
    normalized.includes('auth_key') ||
    normalized.includes('encryption_key') ||
    normalized === 'key'
  );
}
