// An API handler that contributes additional content to the "coding" skill

//<skill-gen>
// ---
// name: coding
// description: "General coding patterns and conventions."
// ---
//
// ## Error Handling
//
// - Always use typed errors, never throw raw strings
// - Handle errors at boundaries, not everywhere
// - Log context before rethrowing
//</skill-gen>

/** Return a fixed success response; a placeholder body for the fixture. */
export function handleRequest() {
  return { status: 200 };
}
