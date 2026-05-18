## Initializing Palette UX Journal
## 2024-05-18 - Loading States on Async Form Submissions
**Learning:** Auth forms with multiple backend steps (register + immediate login) can cause a noticeable delay before redirection. Without visual feedback, users may click submit multiple times or assume the application is frozen. Adding disabled states with explicit loading spinners and text changes (e.g. "Creating Account...") provides crucial reassurance during these async multi-step operations.
**Action:** Always add loading spinners (`Loader2Icon` or similar) inside submit buttons and disable the button while `isSubmitting` is true on critical user-blocking forms.
