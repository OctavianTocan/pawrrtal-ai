import type { AccessRequest } from './types';

/**
 * Renders the summary text with highlighted handles and counts.
 *
 * Important information (`@handle`, `N others`) is rendered in
 * `font-semibold text-foreground` so it visually pops against the muted
 * connecting words ("and", "is requesting access"). This two-tone pattern
 * matches the reference design where the eye is drawn to the actionable
 * parts first, then the supporting context fades into the background.
 */
export function SummaryText({ requests }: { requests: AccessRequest[] }) {
  const first = requests[0];
  const second = requests[1];

  if (!first) return null;

  if (requests.length === 1) {
    return (
      <span className="text-sm text-muted-foreground">
        <span className="font-semibold text-foreground">@{first.name}</span> is requesting access
      </span>
    );
  }

  if (requests.length === 2 && second) {
    return (
      <span className="text-sm text-muted-foreground">
        <span className="font-semibold text-foreground">@{first.name}</span> and{' '}
        <span className="font-semibold text-foreground">@{second.name}</span> are requesting access
      </span>
    );
  }

  return (
    <span className="text-sm text-muted-foreground">
      <span className="font-semibold text-foreground">@{first.name}</span> and{' '}
      <span className="font-semibold text-foreground">{requests.length - 1} others</span> are requesting access
    </span>
  );
}
