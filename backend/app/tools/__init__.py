"""Provider-agnostic tools that any chat backend can use.

Each tool lives in its own module with three layers:

* a pure async core function that takes plain Python args and returns a
  plain Python value.
* provider-specific adapters that translate the core function into the
  provider's tool-call shape.

Adding a new tool means adding a new module under this package and wiring it
into providers without duplicating network logic across them.
"""
