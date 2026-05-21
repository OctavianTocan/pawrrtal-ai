## Initializing Palette UX Journal
## 2024-05-18 - Loading States on Async Form Submissions
**Learning:** Auth forms with multiple backend steps (register + immediate login) can cause a noticeable delay before redirection. Without visual feedback, users may click submit multiple times or assume the application is frozen. Adding disabled states with explicit loading spinners and text changes (e.g. "Creating Account...") provides crucial reassurance during these async multi-step operations.
**Action:** Always add loading spinners (`Loader2Icon` or similar) inside submit buttons and disable the button while `isSubmitting` is true on critical user-blocking forms.

## 2025-02-23 - AppEmptyState CTA ARIA Labels
**Learning:** Shared UI primitives for empty states (`AppEmptyState`) that abstract away button labels often render `<button>` elements with generic text like "Create". When these components lack the ability to accept `aria-label` overrides, it forces screen readers into relying on surrounding context, degrading accessibility for core conversion actions (CTAs).
**Action:** When designing primitive layout components that render interactive elements (buttons, links), ensure the API surface exposes necessary ARIA attributes (like `ariaLabel`) alongside visible labels.
