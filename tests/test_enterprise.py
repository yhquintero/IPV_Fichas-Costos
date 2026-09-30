import http.client
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import auth
import rate_limiter
import server


class EnterpriseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        server.DB_PATH = Path(cls.temp_dir.name) / "enterprise.db"
        server.init_db()
        auth.JWT_SECRET = "test-secret-" + "x" * 32
        auth.JWT_ENABLED = True
        with server.connect() as conn:
            auth.create_user(conn, {"email": "admin@ipv.cu", "name": "Admin", "role": "ADMINISTRADOR",
                                    "password": "Admin#2026seguro"}, server.now_iso)
            auth.create_user(conn, {"email": "lector@ipv.cu", "name": "Lector", "role": "ALMACENERO",
                                    "password": "Lector#2026seguro"}, server.now_iso)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_port}"

    @classmethod
    def tearDownClass(cls):
        auth.JWT_ENABLED = False
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.temp_dir.cleanup()

    def setUp(self):
        rate_limiter._hits.clear()

    def req(self, method, path, body=None, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(r) as resp:
                return resp.status, json.loads(resp.read()), dict(resp.headers)
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read()), dict(err.headers)

    def login(self, email, password):
        return self.req("POST", "/api/auth/login", {"email": email, "password": password})

    def test_requires_token_and_roles(self):
        self.assertEqual(self.req("GET", "/api/products")[0], 401)
        self.assertEqual(self.req("GET", "/api/health")[0], 200)
        status, data, headers = self.login("admin@ipv.cu", "Admin#2026seguro")
        self.assertEqual(status, 200)
        self.assertIn("X-RateLimit-Limit", headers)
        admin = data["access_token"]
        self.assertEqual(self.req("GET", "/api/v1/products", token=admin)[0], 200)
        viewer = self.login("lector@ipv.cu", "Lector#2026seguro")[1]["access_token"]
        self.assertEqual(self.req("GET", "/api/products", token=viewer)[0], 200)
        self.assertEqual(self.req("POST", "/api/products", {"code": "X", "name": "X", "category": "X"},
                                  token=viewer)[0], 403)
        self.assertEqual(self.req("GET", "/api/audit", token=viewer)[0], 403)
        audit_log = self.req("GET", "/api/audit?action=LOGIN", token=admin)[1]
        self.assertGreaterEqual(audit_log["total"], 1)

    def test_refresh_rotation_and_tampering(self):
        tokens = self.login("admin@ipv.cu", "Admin#2026seguro")[1]
        status, new = self.req("POST", "/api/auth/refresh", {"refresh_token": tokens["refresh_token"]})[:2]
        self.assertEqual(status, 200)
        # El refresh usado queda revocado
        self.assertEqual(self.req("POST", "/api/auth/refresh", {"refresh_token": tokens["refresh_token"]})[0], 401)
        forged = new["access_token"][:-3] + "abc"
        self.assertEqual(self.req("GET", "/api/products", token=forged)[0], 401)

    def test_lockout_after_failed_attempts(self):
        with server.connect() as conn:
            auth.create_user(conn, {"email": "bloq@ipv.cu", "name": "B", "role": "ALMACENERO",
                                    "password": "Bloqueo#2026x"}, server.now_iso)
        for _ in range(auth.MAX_FAILED):
            self.assertEqual(self.login("bloq@ipv.cu", "mala")[0], 401)
            rate_limiter._hits.clear()
        self.assertEqual(self.login("bloq@ipv.cu", "Bloqueo#2026x")[0], 423)

    def test_auth_rate_limit(self):
        codes = [self.login("nadie@ipv.cu", "x")[0] for _ in range(7)]
        self.assertIn(429, codes)

    def test_soft_delete_material_and_backup(self):
        admin = self.login("admin@ipv.cu", "Admin#2026seguro")[1]["access_token"]
        mats = self.req("GET", "/api/materials", token=admin)[1]
        self.assertEqual(self.req("DELETE", f"/api/materials/{mats[0]['id']}", token=admin)[0], 200)
        target = mats[0]["id"]
        # El borrado es lógico: sale de la lista y queda en la papelera
        mats = {m["id"]: m for m in self.req("GET", "/api/materials", token=admin)[1]}
        self.assertNotIn(target, mats)
        trash = self.req("GET", "/api/trash", token=admin)[1]["items"]
        self.assertIn(target, [t["id"] for t in trash if t["kind"] == "materials"])
        # Deshacer: restaurar desde la papelera
        self.assertEqual(self.req("POST", f"/api/materials/{target}/restore", {}, token=admin)[0], 200)
        mats = {m["id"]: m for m in self.req("GET", "/api/materials", token=admin)[1]}
        self.assertEqual(mats[target]["status"], "Vigente")
        self.assertEqual(self.req("POST", f"/api/materials/{target}/restore", {}, token=admin)[0], 404)
        prod = self.req("GET", "/api/products", token=admin)[1][0]["id"]
        self.assertEqual(self.req("DELETE", f"/api/products/{prod}", token=admin)[0], 200)
        self.assertEqual(self.req("POST", f"/api/products/{prod}/restore", {}, token=admin)[0], 200)
        self.assertEqual(self.req("POST", f"/api/products/{prod}/restore", {}, token=admin)[0], 404)
        # Regresión: deshacer/rehacer sobre la MISMA conexión keep-alive (como un navegador)
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_port, timeout=5)
        hdr = {"Authorization": f"Bearer {admin}", "Content-Type": "application/json"}
        try:
            for method, path, body in (("DELETE", f"/api/materials/{target}", None),
                                       ("POST", f"/api/materials/{target}/restore", "{}"),
                                       ("DELETE", f"/api/materials/{target}", None),
                                       ("POST", f"/api/materials/{target}/restore", "{}")):
                conn.request(method, path, body=body, headers=hdr)
                resp = conn.getresponse()
                resp.read()
                self.assertEqual(resp.status, 200, f"{method} {path}")
        finally:
            conn.close()
        status, backup = self.req("GET", "/api/backup", token=admin)[:2]
        self.assertEqual(status, 200)
        self.assertTrue(backup["success"])
        self.assertNotIn("path", backup)

    def test_password_policy(self):
        with self.assertRaises(auth.AuthError):
            auth.validate_password_strength("corta")


if __name__ == "__main__":
    unittest.main()
