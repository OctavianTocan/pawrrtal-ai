# Retro: Lesson 2 over-prescribed

User feedback: I made Lesson 2 too easy by giving them the code
verbatim — the `Layer.effect` body, the `client.get` call, the
`Schema.decodeUnknown` step, the `FetchHttpClient.layer` pipe, even
the scratchpad. "You literally just gave me the code."

## Implication for future lessons

The point of the lesson arc is to build muscle memory for the v4
`Layer.effect` + `yield*` + `Layer.provide` shape. Hand-coding the
answer defeats the purpose. The right level of prescription is:

- **Give:** the goal, the concepts, the references (file:line), the
  verify command, hints on what might trip you up.
- **Don't give:** the body of any function, the scratchpad code, the
  exact `Layer.effect` shape, the `client.get` call.

If the user gets stuck, point at a specific reference to read. Don't
write the answer.

## Reusable pattern

When teaching a shape that's already in the live codebase (like
`Projects/Service.ts:117-178` for `Layer.effect`), the "lesson" is
mostly *directing the user to the right reference* and *making them
synthesize*. The reference IS the answer; the lesson's job is to make
sure they read it and apply it.

## Status

Lesson 2 (`lessons/0002-sessionstore-with-real-cookie.md`) rewritten
2026-06-14 to be much less prescriptive. User is re-attempting.
