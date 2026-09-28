import base64
import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import audit
import auth
import dbcrypt
import rate_limiter
import security
import server

PWD = "Seguro#2026clave"


class SecurityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        server.DB_PATH = Path(cls.tmp.name) / "sec.db"
        server.init_db()
        auth.JWT_SECRET = "sec-test-" + "y" * 32
        auth.JWT_ENABLED = True
        with server.connect() as conn:
            for email, role in (("root@ipv.cu", "admin"), ("ana@ipv.cu", "editor"), ("mfa@ipv.cu", "editor")):
                auth.create_user(conn, {"email": email, "name": email, "role": role, "password": PWD}, server.now_iso)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_port}"

    @classmethod
    def tearDownClass(cls):
        auth.JWT_ENABLED = False
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.tmp.cleanup()

    def setUp(self):
        rate_limiter._hits.clear()

    def req(self, method, path, body=None, token=None, headers=None):
        h = {"Content-Type": "application/json", **(headers or {})}
        if token:
            h["Authorization"] = f"Bearer {token}"
        r = urllib.request.Request(self.base + path, data=json.dumps(body).encode() if body is not None else None,
                                   headers=h, method=method)
        try:
            with urllib.request.urlopen(r) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def login(self, email, otp=None):
        body = {"email": email, "password": PWD}
        if otp:
            body["otp"] = otp
        return self.req("POST", "/api/auth/login", body)

    def test_totp_rfc6238_vector(self):
        secret = base64.b32encode(b"12345678901234567890").decode()
        self.assertEqual(security.totp_now(secret, 59), "287082")
        self.assertEqual(security.totp_now(secret, 1111111109), "081804")

    def test_full_mfa_flow_and_replay_protection(self):
        token = self.login("mfa@ipv.cu")[1]["access_token"]
        setup = self.req("POST", "/api/auth/2fa/setup", {}, token)[1]
        self.assertTrue(setup["otpauth_uri"].startswith("otpauth://totp/"))
        self.assertEqual(self.req("POST", "/api/auth/2fa/enable", {"code": "000000"}, token)[0], 400)
        code = security.totp_now(setup["secret"])
        status, enabled = self.req("POST", "/api/auth/2fa/enable", {"code": code}, token)
        self.assertEqual(status, 200)
        self.assertEqual(len(enabled["recovery_codes"]), 8)
        status, data = self.login("mfa@ipv.cu")
        self.assertEqual(status, 401)
        self.assertTrue(data.get("mfa_required"))
        # El mismo código ya usado al activar no puede reutilizarse
        self.assertEqual(self.login("mfa@ipv.cu", code)[0], 401)
        rate_limiter._hits.clear()
        # Código de recuperación: válido una sola vez
        rc = enabled["recovery_codes"][0]
        self.assertEqual(self.login("mfa@ipv.cu", rc)[0], 200)
        rate_limiter._hits.clear()
        self.assertEqual(self.login("mfa@ipv.cu", rc)[0], 401)

    def test_password_change_revokes_other_sessions(self):
        with server.connect() as conn:
            auth.create_user(conn, {"email": "pw@ipv.cu", "name": "P", "role": "editor", "password": PWD}, server.now_iso)
        old = self.login("pw@ipv.cu")[1]
        self.assertEqual(self.req("POST", "/api/auth/password", {"current": PWD, "new": "Nueva#Clave2027"},
                                  old["access_token"])[0], 200)
        self.assertEqual(self.req("GET", "/api/products", token=old["access_token"])[0], 401)
        self.assertEqual(self.req("POST", "/api/auth/refresh", {"refresh_token": old["refresh_token"]})[0], 401)

    def test_admin_user_management_and_immediate_revocation(self):
        admin = self.login("root@ipv.cu")[1]["access_token"]
        ana = self.login("ana@ipv.cu")[1]["access_token"]
        users = {u["email"]: u for u in self.req("GET", "/api/users", token=admin)[1]}
        self.assertEqual(self.req("PUT", f"/api/users/{users['ana@ipv.cu']['id']}", {"role": "viewer"}, ana)[0], 403)
        self.assertEqual(self.req("PUT", f"/api/users/{users['ana@ipv.cu']['id']}", {"active": False}, admin)[0], 200)
        self.assertEqual(self.req("GET", "/api/products", token=ana)[0], 401)
        # Protección: el último administrador no puede degradarse
        self.assertEqual(self.req("PUT", f"/api/users/{users['root@ipv.cu']['id']}", {"role": "editor"}, admin)[0], 400)
        self.req("PUT", f"/api/users/{users['ana@ipv.cu']['id']}", {"active": True}, admin)

    def test_forwarded_for_spoofing_is_ignored(self):
        codes = [self.req("POST", "/api/auth/login", {"email": "x@ipv.cu", "password": "x"},
                          headers={"X-Forwarded-For": f"10.0.0.{i}"})[0] for i in range(7)]
        self.assertIn(429, codes)

    def test_ip_allowlist(self):
        original = security.ALLOWLIST
        try:
            security.ALLOWLIST = security._parse_networks("192.168.1.0/24")
            self.assertTrue(security.ip_allowed("192.168.1.50"))
            self.assertFalse(security.ip_allowed("8.8.8.8"))
            self.assertTrue(security.ip_allowed("127.0.0.1"))
        finally:
            security.ALLOWLIST = original

    def test_audit_chain_detects_tampering(self):
        admin = self.login("root@ipv.cu")[1]["access_token"]
        status, result = self.req("GET", "/api/audit/verify", token=admin)
        self.assertEqual(status, 200)
        self.assertTrue(result["valid"], result)
        self.assertGreater(result["checked"], 0)
        with dbcrypt.connect(server.DB_PATH) as conn:
            conn.execute("UPDATE audit_log SET details='manipulado' WHERE id=(SELECT MIN(id) FROM audit_log WHERE hash!='')")
        self.assertFalse(audit.verify_chain()["valid"])


if __name__ == "__main__":
    unittest.main()
