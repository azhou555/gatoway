# Notes REST API

Endpoints (all request/response bodies are JSON):
- `GET /notes` — list all; `200`.
- `POST /notes` — create; `201` with the created object (including its `id`); `400` if the body is not valid JSON or a required field is missing or the wrong type.
- `GET /notes/<id>` — fetch one; `200`, or `404` if unknown.
- `DELETE /notes/<id>` — delete; `204`, or `404` if unknown.

Scaffold a small in-memory REST API for **notes** as a single Python module, using only the standard library (no third-party packages).

Expose a factory `create_app()` that returns a WSGI application (callable `app(environ, start_response)` per PEP 3333). Each call to `create_app()` must return an app with its own fresh, empty state.

Each note has fields: `title` (str), `body` (str). Required on create: `title`. The server assigns an integer `id`.

Respond with a single ```python code block defining the module (including `create_app`).
