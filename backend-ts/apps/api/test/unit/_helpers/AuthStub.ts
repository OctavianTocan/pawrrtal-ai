import type { UserId } from '@pawrrtal/api-core/Lib/TypeIds';
import { AllowedUserMiddlewareService, AuthenticationMiddlewareService } from '@pawrrtal/api-core/Modules/Auth/Api';
import { CurrentUser, User } from '@pawrrtal/api-core/Modules/Auth/Domain';
import { Effect, Layer } from 'effect';

const stubUser = new User({
  id: '00000000-0000-4000-8000-000000000001' as UserId,
  email: 'test@example.com',
  is_active: true,
  is_superuser: false,
  is_verified: true
});

/** Injects a fixed `CurrentUser` for HttpApi groups that require auth middleware. */
export const AuthMiddlewareStubLive = Layer.succeed(AuthenticationMiddlewareService)({
  // Match production `AuthenticationLayer` shape; skip cookie → SessionStore lookup in unit tests.
  cookie: (httpEffect) => Effect.provideService(httpEffect, CurrentUser, stubUser)
});

/** Injects a fixed `CurrentUser` for HttpApi groups that require allowed user middleware. */
export const AllowedUserMiddlewareStubLive = Layer.succeed(AllowedUserMiddlewareService, (httpEffect) => httpEffect);
