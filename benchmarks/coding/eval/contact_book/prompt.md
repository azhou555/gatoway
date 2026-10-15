# Contacts REST API

Endpoints (all request/response bodies are JSON):
- `GET /contacts` — list all; `200`.
- `POST /contacts` — create; `201` with the created object (including its `id`); `400` if the body is not valid JSON or a required field is missing or the wrong type.
- `GET /contacts/<id>` — fetch one; `200`, or `404` if unknown.
- `DELETE /contacts/<id>` — delete; `204`, or `404` if unknown.
- `PUT /contacts/<id>` — replace the given fields of an existing record; `200` with the updated object, `404` if unknown, `400` on an invalid body.
- `GET /contacts?q=...` — the list endpoint also accepts a `q` query parameter: keep rows whose `name` contains the value as a substring.

Scaffold a small in-memory REST API for **contacts** as a single Python module, using only the standard library (no third-party packages).

Expose a factory `create_app()` that returns a WSGI application (callable `app(environ, start_response)` per PEP 3333). Each call to `create_app()` must return an app with its own fresh, empty state.

Each contact has fields: `name` (str), `phone` (str). Required on create: `name`. The server assigns an integer `id`.

Respond with a single ```python code block defining the module (including `create_app`).
