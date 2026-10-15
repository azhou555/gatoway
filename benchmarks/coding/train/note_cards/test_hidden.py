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
        self.assertEqual(self.call("GET", "/notes"), (200, []))

    def test_create_and_fetch(self):
        code, row = self.call("POST", "/notes", {'title': 'xtitle', 'body': 'xbody'})
        self.assertEqual(code, 201)
        self.assertIn("id", row)
        code, got = self.call("GET", "/notes/" + str(row["id"]))
        self.assertEqual(code, 200)
        self.assertEqual(got, row)

    def test_missing_is_404(self):
        self.assertEqual(self.call("GET", "/notes/999")[0], 404)

    def test_bad_body_is_400(self):
        self.assertEqual(self.call("POST", "/notes", {'body': 'xbody'})[0], 400)

    def test_delete_then_gone(self):
        _, row = self.call("POST", "/notes", {'title': 'xtitle', 'body': 'xbody'})
        self.assertEqual(self.call("DELETE", "/notes/" + str(row["id"]))[0], 204)
        self.assertEqual(self.call("GET", "/notes/" + str(row["id"]))[0], 404)


if __name__ == "__main__":
    unittest.main()
