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
        self.assertEqual(self.call("GET", "/events"), (200, []))

    def test_create_and_fetch(self):
        code, row = self.call("POST", "/events", {'message': 'xmessage', 'level': 7})
        self.assertEqual(code, 201)
        self.assertIn("id", row)
        code, got = self.call("GET", "/events/" + str(row["id"]))
        self.assertEqual(code, 200)
        self.assertEqual(got, row)

    def test_missing_is_404(self):
        self.assertEqual(self.call("GET", "/events/999")[0], 404)

    def test_bad_body_is_400(self):
        self.assertEqual(self.call("POST", "/events", {'level': 7})[0], 400)

    def test_delete_then_gone(self):
        _, row = self.call("POST", "/events", {'message': 'xmessage', 'level': 7})
        self.assertEqual(self.call("DELETE", "/events/" + str(row["id"]))[0], 204)
        self.assertEqual(self.call("GET", "/events/" + str(row["id"]))[0], 404)

    def test_filter(self):
        self.call("POST", "/events", {'message': 'xmessage', 'level': 2})
        self.call("POST", "/events", {'message': 'xmessage', 'level': 9})
        code, rows = self.call("GET", "/events?min_level=5")
        self.assertEqual(code, 200)
        self.assertTrue(all(r["level"] >= 5 for r in rows))
        self.assertEqual(len(rows), 1)
    def test_update(self):
        _, row = self.call("POST", "/events", {'message': 'xmessage', 'level': 7})
        code, got = self.call("PUT", "/events/" + str(row["id"]), {'message': 'changed', 'level': 7})
        self.assertEqual(code, 200)
        self.assertEqual(got["message"], 'changed')
        self.assertEqual(self.call("GET", "/events/" + str(row["id"]))[1]["message"], 'changed')

    def test_update_missing_is_404(self):
        self.assertEqual(self.call("PUT", "/events/999", {'message': 'xmessage', 'level': 7})[0], 404)

if __name__ == "__main__":
    unittest.main()
