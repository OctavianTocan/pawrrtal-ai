---
name: check-bookkeeping-before-theory
paths: ["**/*.{ts,tsx,js,jsx,yaml,yml}"]
---
# Check Bookkeeping State Before Theorizing

When diagnosing pipeline or system failures, the first instinct is to theorize about upstream causes: "the API must be down", "the provider changed their format", "there's a network issue". In practice, **80%+ of failures are misaligned internal state** — a stale session ID, a database row in an unexpected status, a config value pointing at the wrong environment.

Before forming any theory about external causes, verify the bookkeeping: Is the session ID valid? Does the database record exist and have the expected status? Are the config values what you think they are? Is the feature flag enabled? Are the timestamps within expected ranges?

This takes 2 minutes and short-circuits hours of upstream investigation. Only after internal state is verified clean should you look outward.

## Verify

"Have I verified the internal state (IDs, DB records, config, flags) before blaming an external system?"

## Patterns

Bad — theorizing before checking state:

```typescript
// "The payment provider must be rejecting our requests"
// *spends 2 hours investigating provider API*
// *discovers the order record had status='cancelled' all along*
```

Good — verify bookkeeping first:

```typescript
// Step 1: Check internal state
const order = await db.orders.findById(orderId);
console.log("Order state:", {
 status: order.status,
 paymentId: order.paymentId,
 createdAt: order.createdAt,
 env: process.env.PAYMENT_ENV,
});
// Output: { status: 'cancelled', paymentId: null, ... }
// Root cause found in 30 seconds: order was already cancelled

// Step 2: Only if internal state looks correct, check external
if (order.status === "pending" && order.paymentId) {
 const providerStatus = await paymentProvider.check(order.paymentId);
 // Now external investigation is justified
}
```
