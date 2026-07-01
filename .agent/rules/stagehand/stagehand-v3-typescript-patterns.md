---
name: Follow Stagehand V3 TypeScript patterns
paths: ["**/*stagehand*", "**/e2e/**", "**/playwright/**"]
---

# Follow Stagehand V3 TypeScript patterns

When editing files under these paths, align with Stagehand V3 APIs. For the documentation index and MCP workflow, see `stagehand-documentation-and-mcp.md` in this folder. Cursor users also have `.cursor/rules/stagehand-v3-typescript.mdc` (always-on reference).

## Initialize

```typescript
import { Stagehand } from "@browserbasehq/stagehand";

const stagehand = new Stagehand({
	env: "LOCAL", // or "BROWSERBASE"
	verbose: 2, // 0, 1, or 2
	model: "openai/gpt-4.1-mini", // or any supported model
});

await stagehand.init();

const page = stagehand.context.pages()[0];
const context = stagehand.context;

const page2 = await stagehand.context.newPage();
```

## Act

Call `act` on `stagehand` (not the page). Instructions must be **atomic and specific**.

```typescript
await stagehand.act("click the sign in button");

await stagehand.act("click the sign in button", { page: page2 });
```

## Observe + act (recommended)

```typescript
const instruction = "Click the sign in button";

const actions = await stagehand.observe(instruction);

await stagehand.act(actions[0]);
```

With a non-active page:

```typescript
const actions = await stagehand.observe("select blue as the favorite color", {
	page: page2,
});
await stagehand.act(actions[0], { page: page2 });
```

## Extract

**With Zod schema:**

```typescript
import { z } from "zod";

const data = await stagehand.extract(
	"extract all apartment listings with prices and addresses",
	z.object({
		listings: z.array(
			z.object({
				price: z.string(),
				address: z.string(),
			}),
		),
	}),
);
```

**Simple extraction:**

```typescript
const result = await stagehand.extract("extract the sign in button text");
const { extraction } = await stagehand.extract("extract the sign in button text");
```

**Selector-scoped:**

```typescript
const reason = await stagehand.extract(
	"extract the reason why script injection fails",
	z.string(),
	{ selector: "/html/body/div[2]/div[3]/iframe/html/body/p[2]" },
);
```

Use `z.string().url()` for URLs. Pass `{ page }` for a specific page.

## Observe

```typescript
const [action] = await stagehand.observe("Click the sign in button");
await stagehand.act(action);
```

## Agent

```typescript
const page = stagehand.context.pages()[0];
await page.goto("https://www.google.com");

const agent = stagehand.agent({
	model: "google/gemini-2.0-flash",
	executionModel: "google/gemini-2.0-flash",
});

const result = await agent.execute({
	instruction: "Search for the stock price of NVDA",
	maxSteps: 20,
});

console.log(result.message);
```

**CUA mode:**

```typescript
const agent = stagehand.agent({
	mode: "cua",
	model: "anthropic/claude-sonnet-4-6",
	systemPrompt: `You are a helpful assistant that can use a web browser.
		Do not ask follow up questions, the user will trust your judgement.`,
});

await agent.execute({
	instruction: "Apply for a library card at the San Francisco Public Library",
	maxSteps: 30,
});
```

**External MCP integrations:**

```typescript
const agent = stagehand.agent({
	integrations: [`https://mcp.exa.ai/mcp?exaApiKey=${process.env.EXA_API_KEY}`],
	systemPrompt: `You have access to the Exa search tool.`,
});
```

## Advanced

**DeepLocator:**

```typescript
await page
	.deepLocator("/html/body/div[2]/div[3]/iframe/html/body/p")
	.highlight({
		durationMs: 5000,
		contentColor: { r: 255, g: 0, b: 0 },
	});
```

**Multi-page:** pass `{ page }` to `act`, `extract`, and `observe` when not using the active page.

## Verify

Are `act` strings single-step? Did I use `observe` + cached action when the DOM might change between plan and execution?
