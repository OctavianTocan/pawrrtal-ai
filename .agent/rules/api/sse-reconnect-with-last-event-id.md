---
name: sse-reconnect-with-last-event-id
paths: ["**/*.{ts,tsx,js,jsx}"]
---
# Send Last-Event-ID When Reconnecting SSE Streams

Server-Sent Events (SSE) connections drop regularly — network switches, server deployments, load balancer timeouts. When reconnecting, if you don't send the `Last-Event-ID` header, the server either replays everything from the beginning (duplicating events) or starts from "now" (losing events during the disconnect window).

The SSE spec defines the `Last-Event-ID` header specifically for this: the server uses it to resume the stream from where the client left off. Most SSE servers support it, but the client must track the last received event ID and include it on reconnect.

The native `EventSource` API handles this automatically, but if you're using `fetch()` for SSE (common in React Native or when you need custom headers), you must implement reconnection and Last-Event-ID tracking yourself.

## Verify

"When this SSE connection reconnects, does it send the Last-Event-ID? Will it miss events or replay duplicates?"

## Patterns

Bad — reconnect without Last-Event-ID:

```typescript
function connectSSE(url: string, onEvent: (data: string) => void) {
 const connect = () => {
  const eventSource = new EventSource(url);
  eventSource.onmessage = (e) => onEvent(e.data);
  eventSource.onerror = () => {
   eventSource.close();
   setTimeout(connect, 1000); // Reconnect without ID
   // ❌ Server replays all events or starts from now
  };
 };
 connect();
}
```

Good — track and send Last-Event-ID (native EventSource):

```typescript
// EventSource handles Last-Event-ID automatically
// Just make sure your server sends `id:` fields
const eventSource = new EventSource(url);
eventSource.onmessage = (e) => {
 // e.lastEventId is tracked automatically
 // On reconnect, browser sends Last-Event-ID header
 handleEvent(e.data);
};
```

Good — manual Last-Event-ID with fetch-based SSE:

```typescript
async function connectSSE(
 url: string,
 onEvent: (data: string) => void,
) {
 let lastEventId: string | null = null;

 const connect = async () => {
  const headers: Record<string, string> = {
   Accept: "text/event-stream",
  };
  if (lastEventId) {
   headers["Last-Event-ID"] = lastEventId;
  }

  const response = await fetch(url, { headers });
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();

  while (true) {
   const { done, value } = await reader.read();
   if (done) break;

   const text = decoder.decode(value);
   for (const line of text.split("\n")) {
    if (line.startsWith("id:")) {
     lastEventId = line.slice(3).trim();
    } else if (line.startsWith("data:")) {
     onEvent(line.slice(5).trim());
    }
   }
  }

  // Connection closed — reconnect with last ID
  setTimeout(connect, 1000);
 };

 connect();
}
```
