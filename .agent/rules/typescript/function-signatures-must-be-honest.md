---
name: function-signatures-must-be-honest
paths: ["**/*.{ts,tsx}"]
---
# Function Signatures Must Honestly Declare What They Accept and Return - No Surprise Types

When calling library functions, pass arguments in the order and type the API
expects. Mismatched arguments cause silent bugs: wrong debounce timing,
swallowed errors, broken callbacks. Read the type signature before calling
unfamiliar APIs.

## Verify

"For each library function call, do the arguments match the expected
parameter types and order? Are there calls where arguments might be
swapped or missing, causing a different overload to be selected?"

## Patterns

Bad:

```ts
// useDebouncedCallback(callback, delay) but passing array as second arg
const debouncedSave = useDebouncedCallback(save, [user, uuid]);
```

Good:

```ts
const debouncedSave = useDebouncedCallback(save, DEBOUNCE_MS);
```
