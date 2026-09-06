Make `WebhookProcessor.process(event_id, payload, handler)` safe for production
retries and concurrent delivery.

Required behavior:

- after a successful call, later calls with the same event ID return the saved
  result without invoking the handler again;
- concurrent calls for the same event ID invoke the handler only once and all
  callers receive its result;
- a handler failure is not recorded as complete, so a later call can retry;
- handlers for different event IDs must be able to run concurrently.

Use only the Python standard library and keep the public class and method
signatures intact.

