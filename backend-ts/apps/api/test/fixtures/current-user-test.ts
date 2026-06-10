import type { UserId } from '@pawrrtal/api-core/Modules/Projects/Domain';
import { Context, Layer } from 'effect';

/**
 * Test-only `CurrentUser` service.
 *
 * Mirrors the shape Phase C-1's real auth middleware will provide
 * (cookie `session_token` → JWT → `CurrentUser` service). For now,
 * `apps/api/src/Modules/Projects/Http.ts` keeps a `STUB_USER_ID`
 * constant; we do NOT touch that here. When the real middleware lands,
 * the import path of `CurrentUser` here moves to
 * `apps/api/src/Modules/Auth/CurrentUser.ts` and this fixture layer
 * stays the same shape.
 */
export class CurrentUser extends Context.Service<CurrentUser, { readonly userId: UserId }>()(
	'@pawrrtal/api/Auth/CurrentUser'
) {}

/**
 * Layer for tests: a fixed user id, no JWT, no cookie.
 */
export const CurrentUserTest = (
	userId: UserId = '00000000-0000-0000-0000-000000000001' as UserId
) => Layer.succeed(CurrentUser, { userId });
