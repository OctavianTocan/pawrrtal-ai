interface DevLoginAvailabilityEnv {
	NODE_ENV?: string;
	PAWRRTAL_ENABLE_DEV_LOGIN?: string;
}

/** Returns whether the dev admin login shortcut should be rendered. */
export function canUseDevAdminLogin(env: DevLoginAvailabilityEnv = process.env): boolean {
	const override = env.PAWRRTAL_ENABLE_DEV_LOGIN;
	if (override !== undefined) {
		return override === '1' || override.toLowerCase() === 'true';
	}
	return env.NODE_ENV === 'development';
}
