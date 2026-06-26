/**
 * dependency-cruiser config — Pawrrtal frontend
 *
 * Mirrors the layer ordering in `.sentrux/rules.toml`. Sentrux's OSS
 * build only evaluates 4 of the 17 rules in that file; this config plugs
 * the gap for the frontend half (the backend half is enforced by
 * `backend/.importlinter`).
 *
 * Layer ordering (sentrux convention: lower order = higher in the stack):
 *   0 fe-app           frontend/app/*
 *   1 fe-features      frontend/features/*
 *   1 fe-shell         frontend/components/{app-*, nav-*, new-*, signup-form.tsx}
 *   2 fe-ai-elements   frontend/components/ai-elements/*
 *   3 fe-ui-primitives frontend/components/ui/*, frontend/components/icons/*
 *   4 fe-lib           frontend/lib/*, frontend/hooks/*
 *
 * Higher-order layers can import from lower-order ones but never the other
 * way round. Same-order sibling layers (`fe-features` ↔ `fe-shell`) may
 * import each other.
 *
 * Run locally:  cd frontend && bunx depcruise --config .dependency-cruiser.cjs .
 * Lint config:  cd frontend && bunx depcruise --validate
 */

/**
 * Patterns shared between rules so we touch one definition per layer.
 *
 * Paths are anchored relative to the directory dependency-cruiser runs from
 * (the frontend workspace root), so `frontend/` is stripped.
 */
const LAYER = {
  feApp: '^app/',
  feFeatures: '^features/',
  feShell: '^components/(app-|nav-|new-|signup-form)',
  feAiElements: '^components/ai-elements/',
  feUiPrim: '^components/(ui/|icons/)',
  feLib: '^(lib|hooks)/',
};

/**
 * Build a forbidden rule that says "files matching `fromPath` cannot import
 * files matching any of `toPaths`". `name` becomes the rule id in
 * dependency-cruiser output.
 */
function noImport(name, comment, fromPath, toPaths) {
  return {
    name,
    severity: 'error',
    comment,
    from: { path: fromPath },
    to: { path: toPaths.length === 1 ? toPaths[0] : `(?:${toPaths.join('|')})` },
  };
}

module.exports = {
  forbidden: [
    // --- Cross-stack boundary --------------------------------------------
    {
      name: 'no-frontend-to-backend',
      severity: 'error',
      comment: 'Frontend must talk to backend only via HTTP. Never import Python.',
      // Use a relative-up path because depcruise is invoked from `frontend/`.
      from: { path: '.*' },
      to: { path: '^\\.\\./backend/' },
    },

    // --- Layer ordering (upward imports are violations) ------------------
    noImport(
      'no-lib-to-anywhere',
      'fe-lib (order 4) is the foundation; nothing above it may be imported.',
      LAYER.feLib,
      [LAYER.feApp, LAYER.feFeatures, LAYER.feShell, LAYER.feAiElements, LAYER.feUiPrim]
    ),
    noImport(
      'no-ui-primitives-to-above',
      'fe-ui-primitives (order 3) cannot reach into ai-elements, features, shell, or app.',
      LAYER.feUiPrim,
      [LAYER.feApp, LAYER.feFeatures, LAYER.feShell, LAYER.feAiElements]
    ),
    noImport(
      'no-ai-elements-to-above',
      'fe-ai-elements (order 2) cannot reach into features, shell, or app.',
      LAYER.feAiElements,
      [LAYER.feApp, LAYER.feFeatures, LAYER.feShell]
    ),
    noImport('no-features-to-app', 'fe-features (order 1) cannot import the app router layer.', LAYER.feFeatures, [
      LAYER.feApp,
    ]),
    noImport('no-shell-to-app', 'fe-shell (order 1) cannot import the app router layer.', LAYER.feShell, [LAYER.feApp]),

    // --- Universal hygiene -----------------------------------------------
    {
      name: 'no-circular',
      severity: 'error',
      comment:
        'Runtime cycles fail this rule. Type-only `import type` and JSDoc ' +
        '`import(...)` annotations are excluded (see `tsPreCompilationDeps`).',
      from: {},
      to: { circular: true },
    },
  ],

  options: {
    // Use the project's tsconfig so the `@/*` path alias resolves.
    tsConfig: { fileName: 'tsconfig.json' },

    // Skip type-only deps (matches sentrux's runtime-only cycle counting).
    tsPreCompilationDeps: false,

    // Don't follow into vendored packages — they have their own boundaries.
    doNotFollow: {
      path: 'node_modules',
    },

    exclude: {
      // Test files and Next.js generated types live outside the layered model.
      path: [
        '\\.test\\.(ts|tsx|js|jsx)$',
        '\\.spec\\.(ts|tsx|js|jsx)$',
        '^e2e/',
        '^test/',
        '^\\.next/',
        '^\\.source/',
        '^lib/react-(dropdown|overlay|chat-composer)/',
      ],
    },

    moduleSystems: ['es6', 'cjs', 'tsd'],

    enhancedResolveOptions: {
      exportsFields: ['exports'],
      conditionNames: ['import', 'require', 'node', 'default', 'types'],
      extensions: ['.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs'],
    },

    reporterOptions: {
      // dot+archi reports help local exploration; text is the CI gate.
      text: { highlightFocused: true },
    },
  },
};
