"""Generate REST-scaffold coding tasks (reference WSGI app + matching hidden
test + task.toml + prompt.md) from compact specs. Correct-by-construction: the
hidden test is built from the same spec as the reference, so they can't drift.

Single-file, stdlib-only (sandbox is --network none --read-only, python:3.13-slim
has no web deps). Contract: solution exposes create_app() -> WSGI app.
"""
from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

ROOT = Path(__file__).resolve().parent.parent / "benchmarks" / "coding"


class Spec:
    def __init__(self, task_id, split, resource, fields, required, filt, difficulty,
                 update=False):
        self.task_id = task_id          # dir name
        self.split = split              # train | eval
        self.resource = resource        # url segment, e.g. "items"
        self.fields = fields            # {name: "str"|"int"}
        self.required = required         # list of required field names
        self.filt = filt                # (param, field, kind) kind: ge|eq|contains  or None
        self.difficulty = difficulty
        self.update = update            # held-out eval capability: PUT /<res>/<id>


# ---- reference WSGI app (one self-contained module) -------------------------
REF = '''\
"""In-memory REST API for {resource}. Single-file WSGI; create_app() per PEP 3333."""
import json


class _Api:
    def __init__(self):
        self._store = {{}}
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

        if parts == ["{resource}"]:
            if method == "GET":
                rows = list(self._store.values())
{filter_block}
                return reply("200 OK", rows)
            if method == "POST":
                try:
                    data = json.loads(raw or b"{{}}")
                except ValueError:
                    return reply("400 Bad Request", {{"error": "invalid json"}})
                if not _valid(data):
                    return reply("400 Bad Request", {{"error": "invalid fields"}})
                row = {{"id": self._next}}
                row.update({{k: data[k] for k in {field_names} if k in data}})
                self._store[self._next] = row
                self._next += 1
                return reply("201 Created", row)
            return reply("405 Method Not Allowed", {{"error": "method"}})

        if len(parts) == 2 and parts[0] == "{resource}" and parts[1].isdigit():
            rid = int(parts[1])
            if rid not in self._store:
                return reply("404 Not Found", {{"error": "not found"}})
            if method == "GET":
                return reply("200 OK", self._store[rid])
            if method == "DELETE":
                del self._store[rid]
                return reply("204 No Content", None)
{put_block}
            return reply("405 Method Not Allowed", {{"error": "method"}})

        return reply("404 Not Found", {{"error": "not found"}})


def _parse_query(qs):
    out = {{}}
    for pair in qs.split("&"):
        if "=" in pair:
            key, value = pair.split("=", 1)
            out[key] = value
    return out


def _valid(data):
    if not isinstance(data, dict):
        return False
{valid_checks}
    return True


def create_app():
    return _Api()
'''

FILTER_SRC = {
    None: "",
    "ge": '''\
                if "{param}" in query:
                    try:
                        bound = int(query["{param}"])
                    except ValueError:
                        return reply("400 Bad Request", {{"error": "bad filter"}})
                    rows = [r for r in rows if r.get("{field}", 0) >= bound]''',
    "eq": '''\
                if "{param}" in query:
                    rows = [r for r in rows if str(r.get("{field}")) == query["{param}"]]''',
    "contains": '''\
                if "{param}" in query:
                    rows = [r for r in rows if query["{param}"] in str(r.get("{field}", ""))]''',
}


def valid_checks(spec):
    lines = []
    for name in spec.required:
        typ = spec.fields[name]
        pytype = {"str": "str", "int": "int"}[typ]
        lines.append(f'    if not isinstance(data.get("{name}"), {pytype}):')
        lines.append('        return False')
    return "\n".join(lines) if lines else "    pass"


PUT_SRC = '''\
            if method == "PUT":
                try:
                    data = json.loads(raw or b"{{}}")
                except ValueError:
                    return reply("400 Bad Request", {{"error": "invalid json"}})
                if not _valid(data):
                    return reply("400 Bad Request", {{"error": "invalid fields"}})
                self._store[rid].update({{k: data[k] for k in {field_names} if k in data}})
                return reply("200 OK", self._store[rid])'''


def reference(spec):
    filt = ""
    if spec.filt:
        param, field, kind = spec.filt
        filt = FILTER_SRC[kind].format(param=param, field=field)
    field_names = json.dumps(list(spec.fields))
    put = PUT_SRC.format(field_names=field_names) if spec.update else ""
    return REF.format(
        resource=spec.resource, field_names=field_names,
        filter_block=filt, valid_checks=valid_checks(spec), put_block=put,
    )


# ---- hidden test (drives the WSGI app in-process via a stdlib client) -------
def hidden_test(spec):
    # pick a valid create body and an invalid one (drop a required field)
    sample = {}
    for name, typ in spec.fields.items():
        sample[name] = ("x" + name) if typ == "str" else 7
    bad = {k: v for k, v in sample.items() if k not in spec.required[:1]}

    filter_test = ""
    if spec.filt:
        param, field, kind = spec.filt
        if kind == "ge":
            a = dict(sample); a[field] = 2
            b = dict(sample); b[field] = 9
            filter_test = (f'''
    def test_filter(self):
        self.call("POST", "/{spec.resource}", {a!r})
        self.call("POST", "/{spec.resource}", {b!r})
        code, rows = self.call("GET", "/{spec.resource}?{param}=5")
        self.assertEqual(code, 200)
        self.assertTrue(all(r["{field}"] >= 5 for r in rows))
        self.assertEqual(len(rows), 1)''')
        elif kind == "eq":
            a = dict(sample); a[field] = "red"
            b = dict(sample); b[field] = "blue"
            filter_test = (f'''
    def test_filter(self):
        self.call("POST", "/{spec.resource}", {a!r})
        self.call("POST", "/{spec.resource}", {b!r})
        code, rows = self.call("GET", "/{spec.resource}?{param}=red")
        self.assertEqual(code, 200)
        self.assertEqual([r["{field}"] for r in rows], ["red"])''')
        elif kind == "contains":
            a = dict(sample); a[field] = "alpha"
            b = dict(sample); b[field] = "beta"
            filter_test = (f'''
    def test_filter(self):
        self.call("POST", "/{spec.resource}", {a!r})
        self.call("POST", "/{spec.resource}", {b!r})
        code, rows = self.call("GET", "/{spec.resource}?{param}=lph")
        self.assertEqual(code, 200)
        self.assertEqual([r["{field}"] for r in rows], ["alpha"])''')

    update_test = ""
    if spec.update:
        ufield = list(spec.fields)[0]
        uval = ("changed" if spec.fields[ufield] == "str" else 123)
        updated = dict(sample); updated[ufield] = uval
        update_test = (f'''
    def test_update(self):
        _, row = self.call("POST", "/{spec.resource}", {sample!r})
        code, got = self.call("PUT", "/{spec.resource}/" + str(row["id"]), {updated!r})
        self.assertEqual(code, 200)
        self.assertEqual(got["{ufield}"], {uval!r})
        self.assertEqual(self.call("GET", "/{spec.resource}/" + str(row["id"]))[1]["{ufield}"], {uval!r})

    def test_update_missing_is_404(self):
        self.assertEqual(self.call("PUT", "/{spec.resource}/999", {sample!r})[0], 404)''')

    return dedent(f'''\
import io, json, unittest
from solution import create_app


class RestApi(unittest.TestCase):
    def setUp(self):
        self.app = create_app()

    def call(self, method, path, body=None):
        raw = json.dumps(body).encode() if body is not None else b""
        cap = {{}}
        def start_response(status, headers):
            cap["status"] = status
        environ = {{"REQUEST_METHOD": method, "PATH_INFO": path.split("?")[0],
                   "QUERY_STRING": path.split("?", 1)[1] if "?" in path else "",
                   "CONTENT_LENGTH": str(len(raw)), "wsgi.input": io.BytesIO(raw)}}
        data = b"".join(self.app(environ, start_response))
        return int(cap["status"].split()[0]), (json.loads(data) if data else None)

    def test_empty_list(self):
        self.assertEqual(self.call("GET", "/{spec.resource}"), (200, []))

    def test_create_and_fetch(self):
        code, row = self.call("POST", "/{spec.resource}", {sample!r})
        self.assertEqual(code, 201)
        self.assertIn("id", row)
        code, got = self.call("GET", "/{spec.resource}/" + str(row["id"]))
        self.assertEqual(code, 200)
        self.assertEqual(got, row)

    def test_missing_is_404(self):
        self.assertEqual(self.call("GET", "/{spec.resource}/999")[0], 404)

    def test_bad_body_is_400(self):
        self.assertEqual(self.call("POST", "/{spec.resource}", {bad!r})[0], 400)

    def test_delete_then_gone(self):
        _, row = self.call("POST", "/{spec.resource}", {sample!r})
        self.assertEqual(self.call("DELETE", "/{spec.resource}/" + str(row["id"]))[0], 204)
        self.assertEqual(self.call("GET", "/{spec.resource}/" + str(row["id"]))[0], 404)
{filter_test}{update_test}

if __name__ == "__main__":
    unittest.main()
''')


RUBRIC = [
    "exposes create_app() returning a fresh WSGI application",
    "routes by method and path with correct status codes (201/204/400/404)",
    "validates the request body and isolates per-instance state",
    "clear structure: routing separated from handlers, no global mutable state",
]


def prompt_md(spec):
    fields = ", ".join(f"`{n}` ({t})" for n, t in spec.fields.items())
    req = ", ".join(f"`{n}`" for n in spec.required)
    lines = [
        f"# {spec.resource.title()} REST API",
        "",
        f"Scaffold a small in-memory REST API for **{spec.resource}** as a single "
        "Python module, using only the standard library (no third-party packages).",
        "",
        "Expose a factory `create_app()` that returns a WSGI application "
        "(callable `app(environ, start_response)` per PEP 3333). Each call to "
        "`create_app()` must return an app with its own fresh, empty state.",
        "",
        f"Each {spec.resource[:-1] if spec.resource.endswith('s') else spec.resource} "
        f"has fields: {fields}. Required on create: {req}. The server assigns an "
        "integer `id`.",
        "",
        "Endpoints (all request/response bodies are JSON):",
        f"- `GET /{spec.resource}` — list all; `200`.",
        f"- `POST /{spec.resource}` — create; `201` with the created object "
        "(including its `id`); `400` if the body is not valid JSON or a required "
        "field is missing or the wrong type.",
        f"- `GET /{spec.resource}/<id>` — fetch one; `200`, or `404` if unknown.",
        f"- `DELETE /{spec.resource}/<id>` — delete; `204`, or `404` if unknown.",
    ]
    if spec.update:
        lines.append(
            f"- `PUT /{spec.resource}/<id>` — replace the given fields of an "
            "existing record; `200` with the updated object, `404` if unknown, "
            "`400` on an invalid body.")
    if spec.filt:
        param, field, kind = spec.filt
        how = {"ge": f"keep rows whose `{field}` is >= the integer value",
               "eq": f"keep rows whose `{field}` equals the value exactly",
               "contains": f"keep rows whose `{field}` contains the value as a substring"}[kind]
        lines.append(
            f"- `GET /{spec.resource}?{param}=...` — the list endpoint also accepts "
            f"a `{param}` query parameter: {how}.")
    lines += ["", "Respond with a single ```python code block defining the module "
              "(including `create_app`)."]
    return "\n".join(lines) + "\n"


def task_toml(spec):
    rubric = ",\n".join(f'  "{r}"' for r in RUBRIC)
    return (f'language = "python"\n'
            f'neighborhood = "rest scaffolding"\n'
            f'entrypoint = "create_app"\n'
            f'difficulty = {spec.difficulty}\n'
            f'rubric = [\n{rubric},\n]\n')


SPECS = [
    # --- train: CRUD resource (3) ---
    Spec("inventory_items", "train", "items",
         {"name": "str", "qty": "int"}, ["name", "qty"], None, 0.4),
    Spec("booking_slots", "train", "bookings",
         {"room": "str", "slot": "int"}, ["room", "slot"], None, 0.45),
    Spec("note_cards", "train", "notes",
         {"title": "str", "body": "str"}, ["title"], None, 0.4),
    # --- train: filtered list / query (3) ---
    Spec("inventory_search", "train", "items",
         {"name": "str", "qty": "int"}, ["name", "qty"], ("min_qty", "qty", "ge"), 0.55),
    Spec("booking_by_room", "train", "bookings",
         {"room": "str", "slot": "int"}, ["room", "slot"], ("room", "room", "eq"), 0.5),
    Spec("note_tag_filter", "train", "notes",
         {"title": "str", "tag": "str"}, ["title", "tag"], ("tag", "tag", "eq"), 0.5),
    # --- eval split (3): separate domains, held out ---
    Spec("task_tracker", "eval", "tasks",
         {"title": "str", "status": "str"}, ["title", "status"], ("status", "status", "eq"), 0.55,
         update=True),
    Spec("contact_book", "eval", "contacts",
         {"name": "str", "phone": "str"}, ["name"], ("q", "name", "contains"), 0.6,
         update=True),
    Spec("event_log", "eval", "events",
         {"message": "str", "level": "int"}, ["message", "level"], ("min_level", "level", "ge"), 0.55,
         update=True),
]


def write_all():
    for spec in SPECS:
        test = hidden_test(spec)
        # Guard: every test method must be indented into the TestCase class.
        # A module-level `def test_` (e.g. from an over-eager dedent) is silently
        # skipped by unittest -- the bug that made filter/PUT tests never run.
        for line in test.splitlines():
            if line.lstrip().startswith("def test_"):
                assert line.startswith("    def test_"), f"{spec.task_id}: {line!r}"
        # Filter/update tasks must collect more tests than the 5 CRUD basics.
        n = sum(1 for line in test.splitlines() if line.startswith("    def test_"))
        expected = 5 + (1 if spec.filt else 0) + (2 if spec.update else 0)
        assert n == expected, f"{spec.task_id}: {n} tests, expected {expected}"

        d = ROOT / spec.split / spec.task_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "reference.py").write_text(reference(spec))
        (d / "test_hidden.py").write_text(test)
        (d / "task.toml").write_text(task_toml(spec))
        (d / "prompt.md").write_text(prompt_md(spec))
        print(f"wrote {d}  ({n} tests)")


if __name__ == "__main__":
    write_all()
