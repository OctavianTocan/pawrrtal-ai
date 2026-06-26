/* System theme detection — runs synchronously before hydration.
 *
 * Loaded from `frontend/app/layout.tsx` via:
 *
 *   <Script src="/theme-detection.js" strategy="beforeInteractive" />
 *
 * The IIFE adds the `dark` class to `<html>` when the OS reports
 * `prefers-color-scheme: dark` and updates it live on preference
 * changes.  Wrapped in try/catch because `matchMedia` can throw on
 * unusual user agents — theme detection failing should never break
 * the app.
 *
 * Why this lives at `public/theme-detection.js` rather than as an
 * inline `dangerouslySetInnerHTML` body inside React JSX:
 *
 *   React 19's client reconciler emits a fatal warning ("Encountered
 *   a script tag while rendering React component") for ANY <script>
 *   element it traverses with body content, including those produced
 *   by `next/script` with `dangerouslySetInnerHTML`.  The warning
 *   cascades and breaks hydration of the rest of the tree.
 *   `<Script src="/theme-detection.js">` produces a `<script src>`
 *   element with no body — the reconciler ignores it the same way
 *   it ignores the React Grab loader a few lines below in layout.tsx.
 *
 * Keep this file pure JS (no transpilation, no imports).  Next.js
 * serves it directly from `public/` and any framework features here
 * would silently break.
 */
(() => {
  try {
    const d = document.documentElement;
    const m = window.matchMedia('(prefers-color-scheme:dark)');
    if (m.matches) d.classList.add('dark');
    m.addEventListener('change', (e) => {
      if (e.matches) {
        d.classList.add('dark');
      } else {
        d.classList.remove('dark');
      }
    });
  } catch (_e) {
    /* matchMedia unavailable — leave the default light theme. */
  }
})();
