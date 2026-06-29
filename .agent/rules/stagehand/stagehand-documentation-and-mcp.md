---

name: Use Stagehand documentation index and MCP servers
paths: ["frontend/e2e/**", "**/*.spec.ts", "**/*.spec.tsx"]
---

# Use Stagehand documentation index and MCP servers

When implementing or debugging **Stagehand** (`@browserbasehq/stagehand`) browser automation, fetch current behavior from docs and MCP tools instead of guessing from training data.

## Documentation index

Fetch the complete documentation index at: https://docs.stagehand.dev/llms.txt

Use that file to discover all available pages before exploring further.

## MCP servers

Project MCP configuration includes:

- **stagehand-docs** — `https://docs.stagehand.dev/mcp` (official docs)
- **context7** — `npx -y @upstash/context7-mcp` ([Context7](https://github.com/upstash/context7))
- **deepwiki** — `https://mcp.deepwiki.com/mcp` ([DeepWiki](https://mcp.deepwiki.com/))

Configs: `.cursor/mcp.json`, `.mcp.json`, and `config/mcporter.json`.

Prefer **stagehand-docs** for act/observe/extract/agent semantics; use **context7** / **deepwiki** for ecosystem or dependency context.

For **Stagehand Python** (`act` / `extract` / `observe` on `Page`), see [stagehand-python](https://github.com/browserbase/stagehand-python) and the same documentation index above where applicable.

## Security

- Never commit API keys; use environment variables for MCP or model keys.
- Prefer `observe` before `act`; keep `act` instructions atomic and specific.

## Verify

Did I fetch or consult `https://docs.stagehand.dev/llms.txt` (or stagehand-docs MCP) before asserting Stagehand V3 APIs, options, or method signatures?
