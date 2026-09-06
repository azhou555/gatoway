class WebhookProcessor:
    def __init__(self):
        self._completed = {}

    def process(self, event_id, payload, handler):
        if event_id in self._completed:
            return self._completed[event_id]

        result = handler(payload)
        self._completed[event_id] = result
        return result

