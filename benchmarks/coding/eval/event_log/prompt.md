# Events REST API

Scaffold a small in-memory REST API for **events** as a single Python module, using only the standard library (no third-party packages).

Expose a factory `create_app()` that returns a WSGI application (callable `app(environ, start_response)` per PEP 3333). Each call to `create_app()` must return an app with its own fresh, empty state.

Each event has fields: `message` (str), `level` (int). Required on create: `message`, `level`. The server assigns an integer `id`.

Endpoints (all request/response bodies are JSON):
- `GET /events` — list all; `200`.
- `POST /events` — create; `201` with the created object (including its `id`); `400` if the body is not valid JSON or a required field is missing or the wrong type.
- `GET /events/<id>` — fetch one; `200`, or `404` if unknown.
- `DELETE /events/<id>` — delete; `204`, or `404` if unknown.
- `PUT /events/<id>` — replace the given fields of an existing record; `200` with the updated object, `404` if unknown, `400` on an invalid body.
- `GET /events?min_level=...` — the list endpoint also accepts a `min_level` query parameter: keep rows whose `level` is >= the integer value.

Respond with a single ```python code block defining the module (including `create_app`).
