---
name: import-only-what-you-use
paths: ["**/*.{ts,tsx}"]
---
# Import Only the Functions You Use, Not Entire Libraries - Tree Shaking Can't Always Help

**Avoid barrel file imports** for icon and component libraries. Barrel
files (`index.ts` with `export * from`) can load thousands of unused
modules (200-800ms import cost). Import directly from the source module.

**Lazy-load heavy components** not needed on initial render using
`next/dynamic` or `React.lazy`. Large dependencies in the main bundle
directly hurt TTI and LCP.

## Verify

"Are there imports from barrel files of large libraries (lucide-react,
@mui/material, lodash, date-fns, react-icons)? Are there heavy components
(editors, charts, maps) imported statically that could be lazy-loaded?"

## Patterns

Bad — barrel import loads entire library:

```tsx
import { Check, X, Menu } from 'lucide-react';
// Loads 1,583 modules, 200-800ms cold start cost
```

Good — direct source imports:

```tsx
import Check from 'lucide-react/dist/esm/icons/check';
import X from 'lucide-react/dist/esm/icons/x';
import Menu from 'lucide-react/dist/esm/icons/menu';
```

Good — Next.js optimizePackageImports (alternative):

```js
// next.config.js
module.exports = {
  experimental: {
    optimizePackageImports: ['lucide-react', '@mui/material'],
  },
};
```

Bad — heavy component in main bundle:

```tsx
import { MonacoEditor } from './monaco-editor'; // ~300KB
```

Good — lazy-loaded on demand:

```tsx
import dynamic from 'next/dynamic';
const MonacoEditor = dynamic(
  () => import('./monaco-editor').then((m) => m.MonacoEditor),
  { ssr: false }
);
```

Commonly affected libraries: lucide-react, @mui/material, @tabler/icons-react,
react-icons, lodash, date-fns, rxjs.
