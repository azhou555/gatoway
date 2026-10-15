"""In-memory REST API for bookings. Single-file WSGI; create_app() per PEP 3333."""
import json


class _Api:
    def __init__(self):
        self._store = {}
        self._next = 1

    def __call__(self, environ, start_response):
        method = environ["REQUEST_METHOD"]
        parts = [p for p in environ.get("PATH_INFO", "").split("/") if p]
        query = _parse_query(environ.get("QUERY_STRING", ""))
        try:
            length = int(environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            length = 0
        raw = environ["wsgi.input"].read(length) if length else b""

        def reply(status, payload):
            body = b"" if payload is None else json.dumps(payload).encode()
            start_response(status, [("Content-Type", "application/json"),
                                    ("Content-Length", str(len(body)))])
            return [body]

        if parts == ["bookings"]:
            if method == "GET":
                rows = list(self._store.values())
                if "room" in query:
                    rows = [r for r in rows if str(r.get("room")) == query["room"]]
                return reply("200 OK", rows)
            if method == "POST":
                try:
                    data = json.loads(raw or b"{}")
                except ValueError:
                    return reply("400 Bad Request", {"error": "invalid json"})
                if not _valid(data):
                    return reply("400 Bad Request", {"error": "invalid fields"})
                row = {"id": self._next}
                row.update({k: data[k] for k in ["room", "slot"] if k in data})
                self._store[self._next] = row
                self._next += 1
                return reply("201 Created", row)
            return reply("405 Method Not Allowed", {"error": "method"})

        if len(parts) == 2 and parts[0] == "bookings" and parts[1].isdigit():
            rid = int(parts[1])
            if rid not in self._store:
                return reply("404 Not Found", {"error": "not found"})
            if method == "GET":
                return reply("200 OK", self._store[rid])
            if method == "DELETE":
                del self._store[rid]
                return reply("204 No Content", None)

            return reply("405 Method Not Allowed", {"error": "method"})

        return reply("404 Not Found", {"error": "not found"})


def _parse_query(qs):
    out = {}
    for pair in qs.split("&"):
        if "=" in pair:
            key, value = pair.split("=", 1)
            out[key] = value
    return out


def _valid(data):
    if not isinstance(data, dict):
        return False
    if not isinstance(data.get("room"), str):
        return False
    if not isinstance(data.get("slot"), int):
        return False
    return True


def create_app():
    return _Api()
