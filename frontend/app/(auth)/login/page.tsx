import { canUseDevAdminLogin } from '@/features/auth/dev-login-availability';
import { LoginForm } from '@/features/auth/LoginForm';
import { OnboardingBackdrop } from '@/features/onboarding/OnboardingBackdrop';

/**
 * Validate a ``?redirect=`` target before forwarding it to the form.
 *
 * Only same-origin, leading-slash paths are accepted — anything else
 * (full URLs, protocol-relative ``//evil.com``, query-only strings,
 * arrays from repeated query params) collapses to ``/``. This guards
 * against open-redirect abuse: an attacker can't craft
 * ``/login?redirect=https://attacker`` and bounce a freshly-authed
 * user off-site.
 *
 * @param raw - The raw ``?redirect=`` value from the page's
 *   ``searchParams`` prop. Strings or arrays per Next.js's typing.
 * @returns A safe path to navigate to after login.
 */
function safeRedirectTarget(raw: string | string[] | undefined): string {
	if (typeof raw !== 'string') return '/';
	if (!raw.startsWith('/') || raw.startsWith('//')) return '/';
	return raw;
}

interface LoginPageProps {
	searchParams: Promise<{ redirect?: string | string[] }>;
}

/**
 * Login page — renders the login form on the same scenic dotted backdrop
 * used by the onboarding modal so the auth surface and post-login surface
 * read as one design language. The form sits centered with the standard
 * `popover-styled onboarding-panel` chrome around it.
 *
 * Reads ``?redirect=`` server-side (Next.js 15+ ``searchParams`` is a
 * Promise) so the client form doesn't need ``useSearchParams`` and the
 * page can keep its static prerender without a Suspense bail-out. The
 * value is validated against open-redirect before threading to
 * ``LoginForm``.
 *
 * @param props - Page props provided by Next.js. ``searchParams`` is a
 *   Promise that resolves to the URL query string parsed into an object.
 * @returns The rendered login page.
 */
export default async function Page({ searchParams }: LoginPageProps): Promise<React.JSX.Element> {
	const showDevAdminLogin = canUseDevAdminLogin();
	const { redirect } = await searchParams;
	const postLoginTarget = safeRedirectTarget(redirect);

	return (
		<div className="relative flex min-h-svh w-full items-center justify-center overflow-hidden bg-background p-6 md:p-10">
			<OnboardingBackdrop />
			<div className="relative z-10 w-full max-w-md">
				<LoginForm
					canUseDevAdminLogin={showDevAdminLogin}
					postLoginTarget={postLoginTarget}
				/>
			</div>
		</div>
	);
}
