/**
 * Derive a 1-2-letter initial string from a display name.
 *
 * @param name - Full display name (e.g. "Octavian Tocan")
 * @returns Uppercase initials ("OT"), or "?" when the input is empty.
 */
export function getInitials(name: string): string {
	const parts = name.trim().split(/\s+/).filter(Boolean);
	if (parts.length === 0) return '?';
	const first = parts[0]?.[0] ?? '';
	const last = parts.length > 1 ? (parts[parts.length - 1]?.[0] ?? '') : '';
	return `${first}${last}`.toUpperCase();
}
