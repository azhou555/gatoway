import io, json, unittest
from solution import create_app


class RestApi(unittest.TestCase):
    def setUp(self):
        self.app = create_app()

    def call(self, method, path, body=None):
        raw = json.dumps(body).encode() if body is not None else b""
        cap = {}
        def start_response(status, headers):
            cap["status"] = status
        environ = {"REQUEST_METHOD": method, "PATH_INFO": path.split("?")[0],
                   "QUERY_STRING": path.split("?", 1)[1] if "?" in path else "",
                   "CONTENT_LENGTH": str(len(raw)), "wsgi.input": io.BytesIO(raw)}
        data = b"".join(self.app(environ, start_response))
        return int(cap["status"].split()[0]), (json.loads(data) if data else None)

    def test_empty_list(self):
        self.assertEqual(self.call("GET", "/tasks"), (200, []))

    def test_create_and_fetch(self):
        code, row = self.call("POST", "/tasks", {'title': 'xtitle', 'status': 'xstatus'})
        self.assertEqual(code, 201)
        self.assertIn("id", row)
        code, got = self.call("GET", "/tasks/" + str(row["id"]))
        self.assertEqual(code, 200)
        self.assertEqual(got, row)

    def test_missing_is_404(self):
        self.assertEqual(self.call("GET", "/tasks/999")[0], 404)

    def test_bad_body_is_400(self):
        self.assertEqual(self.call("POST", "/tasks", {'status': 'xstatus'})[0], 400)

    def test_delete_then_gone(self):
        _, row = self.call("POST", "/tasks", {'title': 'xtitle', 'status': 'xstatus'})
        self.assertEqual(self.call("DELETE", "/tasks/" + str(row["id"]))[0], 204)
        self.assertEqual(self.call("GET", "/tasks/" + str(row["id"]))[0], 404)

    def test_filter(self):
        self.call("POST", "/tasks", {'title': 'xtitle', 'status': 'red'})
        self.call("POST", "/tasks", {'title': 'xtitle', 'status': 'blue'})
        code, rows = self.call("GET", "/tasks?status=red")
        self.assertEqual(code, 200)
        self.assertEqual([r["status"] for r in rows], ["red"])
    def test_update(self):
        _, row = self.call("POST", "/tasks", {'title': 'xtitle', 'status': 'xstatus'})
        code, got = self.call("PUT", "/tasks/" + str(row["id"]), {'title': 'changed', 'status': 'xstatus'})
        self.assertEqual(code, 200)
        self.assertEqual(got["title"], 'changed')
        self.assertEqual(self.call("GET", "/tasks/" + str(row["id"]))[1]["title"], 'changed')

    def test_update_missing_is_404(self):
        self.assertEqual(self.call("PUT", "/tasks/999", {'title': 'xtitle', 'status': 'xstatus'})[0], 404)

if __name__ == "__main__":
    unittest.main()
