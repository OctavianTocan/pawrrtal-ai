---
name: use-direct-named-imports-not-namespace
paths: ["**/*.{ts,tsx}"]
---
# Use Direct Named Imports (import { x }), Not Namespace Imports (import * as React)

Use direct named imports from 'react' instead of the React namespace.
Namespace imports obscure what's actually used and resist tree-shaking.

## Verify

"Are there any React.X namespace usages that should be direct named
imports? (e.g., React.MutableRefObject instead of importing MutableRefObject)"

## Patterns

Bad:

```ts
import React from 'react';
const ref: React.MutableRefObject<string> = ...
```

Good:

```ts
import { type MutableRefObject } from 'react';
const ref: MutableRefObject<string> = ...
```
