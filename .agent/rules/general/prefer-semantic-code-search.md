---
name: prefer-semantic-code-search
paths: ["**/*"]
---

# Prefer Semantic Code Search Before Raw Text Search

When semantic code tools are available in the session, use them before
broad text search for code exploration. CodeGraph, Serena, language-server
symbol search, and similar tools understand symbols and call relationships;
they usually find the right implementation faster than scanning strings.

## Rule

Before using `rg` to understand code structure, try the semantic tool that
best matches the question:

- Use context/search for "where is this implemented?" or "what code matters
  for this task?"
- Use callers/callees when tracing behavior across functions.
- Use impact/dependency queries before changing shared symbols.
- Use node/symbol details when you know the exact class, function, type, or
  component name.

If the semantic tool is unavailable, uninitialized, lacks the needed
language, or returns insufficient results, fall back to `rg` immediately and
keep moving. Use `rg` first for exact literals, log messages, route strings,
config keys, docs, generated files, and other non-symbol text.

## Why

Raw text search is fast, but it loses structure. It can miss renamed symbols,
over-report unrelated string matches, and burn time reconstructing call flow
manually. Semantic search gives the agent the ownership, symbol, and
dependency shape first; text search is then a targeted follow-up instead of
the starting point for every investigation.

## Verify

"Do I have access to CodeGraph, Serena, language-server search, or another
semantic code tool in this session? If yes, did I try it before broad `rg`
for code exploration? If I used `rg` first, was I searching for a literal,
config/doc text, or working around an unavailable semantic tool?"
