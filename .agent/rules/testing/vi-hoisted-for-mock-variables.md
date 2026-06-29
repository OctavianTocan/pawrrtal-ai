---
name: vi-hoisted-for-mock-variables
paths: ["**/*.test.{ts,tsx}", "**/*.spec.{ts,tsx}", "**/__tests__/**"]
---

# vi.hoisted() for Mock Variables

Variables used inside `vi.mock()` factory functions must be declared with `vi.hoisted()`. Without it, the variable is undefined when the mock factory executes because `vi.mock()` is hoisted above all other code.

## Rule

```typescript
// Bad — mockLogger is undefined when vi.mock() runs
const mockLogger = vi.fn();
vi.mock('../logger', () => ({ log: mockLogger }));

// Good — vi.hoisted() executes before vi.mock()
const { mockLogger } = vi.hoisted(() => ({
  mockLogger: vi.fn(),
}));
vi.mock('../logger', () => ({ log: mockLogger }));
```

## Why

Vitest hoists `vi.mock()` calls to the top of the file at transform time, before any other code runs. Regular variable declarations stay in place. The mock factory can't see variables that haven't been declared yet. `vi.hoisted()` ensures the variable declaration is also hoisted.

## Verify

- Run `vitest` on a file with a non-hoisted mock variable: confirm the factory receives `undefined`
- Run tests after refactoring to `vi.hoisted()`: confirm mocks are properly initialized
- Check that `vi.mock()` is called at module scope, not inside a function (hoisting only works at file scope)

## Patterns

- **Always pair `vi.hoisted()` with `vi.mock()`:** If you have a `vi.mock()`, any factory variable must come from `vi.hoisted()`
- **Object destructuring from hoisted:** Use `const { mockFn } = vi.hoisted(() => ({ mockFn: vi.fn() }))` for clean factory exports
- **Keep hoisted variables simple:** Avoid complex initialization logic inside `vi.hoisted()` — move it to a helper if needed
