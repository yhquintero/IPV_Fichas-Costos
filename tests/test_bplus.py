"""Pruebas del paquete B+: sesiones por dispositivo, alertas de IP nueva,
caducidad/historial de contraseñas y cifrado de la base de datos."""
import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import auth
import dbcrypt
import rate_limiter
import server

PW = "Clave#2026segura"


class SessionsApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        server.DB_PATH = Path(cls.tmp.name) / "bplus.db"
        server.init_db()
        auth.JWT_SECRET = "test-secret-" + "y" * 32
        auth.JWT_ENABLED = True
        with server.connect() as conn:
            auth.create_user(conn, {"email": "jefe@ipv.cu", "name": "Jefe", "role": "admin", "password": PW}, server.now_iso)
            auth.create_user(conn, {"email": "ana@ipv.cu", "name": "Ana", "role": "editor", "password": PW}, server.now_iso)
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

    def req(self, method, path, body=None, token=None, ua="Mozilla/5.0 (Windows NT 10.0) Chrome/130.0"):
        headers = {"Content-Type": "application/json", "User-Agent": ua}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(r) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read())

    def login(self, email, password=PW, ua="Mozilla/5.0 (Windows NT 10.0) Chrome/130.0"):
        status, data = self.req("POST", "/api/auth/login", {"email": email, "password": password}, ua=ua)
        self.assertEqual(status, 200, data)
        return data

    def test_device_sessions_list_and_revoke(self):
        pc = self.login("ana@ipv.cu")
        phone = self.login("ana@ipv.cu", ua="okhttp/4.12.0")
        status, sessions = self.req("GET", "/api/auth/sessions", token=pc["access_token"])
        self.assertEqual(status, 200)
        by_id = {s["id"]: s for s in sessions}
        self.assertTrue(by_id[pc["session_id"]]["current"])
        self.assertEqual(by_id[pc["session_id"]]["device"], "Chrome · Windows")
        self.assertEqual(by_id[phone["session_id"]]["device"], "App Android")
        # Cerrar la sesión del teléfono desde el PC: su access y refresh dejan de valer
        self.assertEqual(self.req("DELETE", f"/api/auth/sessions/{phone['session_id']}", token=pc["access_token"])[0], 200)
        self.assertEqual(self.req("GET", "/api/products", token=phone["access_token"])[0], 401)
        self.assertEqual(self.req("POST", "/api/auth/refresh", {"refresh_token": phone["refresh_token"]})[0], 401)
        self.assertEqual(self.req("GET", "/api/products", token=pc["access_token"])[0], 200)
        # Un usuario no puede cerrar sesiones ajenas
        jefe = self.login("jefe@ipv.cu")
        self.assertEqual(self.req("DELETE", f"/api/auth/sessions/{pc['session_id']}", token=jefe["access_token"])[0], 404)

    def test_revoke_other_sessions_and_logout(self):
        a = self.login("jefe@ipv.cu")
        b = self.login("jefe@ipv.cu")
        status, data = self.req("POST", "/api/auth/sessions/revoke-others", {}, token=a["access_token"])
        self.assertEqual(status, 200)
        self.assertGreaterEqual(data["closed"], 1)
        self.assertEqual(self.req("GET", "/api/products", token=b["access_token"])[0], 401)
        self.assertEqual(self.req("GET", "/api/products", token=a["access_token"])[0], 200)
        # Logout cierra también la sesión del dispositivo (el access deja de valer al instante)
        self.req("POST", "/api/auth/logout", {"refresh_token": a["refresh_token"]}, token=a["access_token"])
        self.assertEqual(self.req("GET", "/api/products", token=a["access_token"])[0], 401)

    def test_refresh_keeps_session(self):
        a = self.login("ana@ipv.cu")
        status, data = self.req("POST", "/api/auth/refresh", {"refresh_token": a["refresh_token"]})
        self.assertEqual(status, 200)
        sessions = self.req("GET", "/api/auth/sessions", token=data["access_token"])[1]
        self.assertTrue(any(s["id"] == a["session_id"] and s["current"] for s in sessions))

    def test_forced_password_change_and_history(self):
        with server.connect() as conn:
            auth.create_user(conn, {"email": "nuevo@ipv.cu", "name": "Nuevo", "role": "editor", "password": PW,
                                    "must_change_password": True}, server.now_iso)
        d = self.login("nuevo@ipv.cu")
        self.assertTrue(d["password_expired"])
        blocked = self.req("GET", "/api/products", token=d["access_token"])
        self.assertEqual(blocked[0], 403)
        self.assertTrue(blocked[1]["password_expired"])
        # No puede repetir la actual; sí cambiarla. Recibe tokens nuevos ya sin restricción
        self.assertEqual(self.req("POST", "/api/auth/password", {"current": PW, "new": PW}, token=d["access_token"])[0], 400)
        status, changed = self.req("POST", "/api/auth/password", {"current": PW, "new": "Otra#2026segura"}, token=d["access_token"])
        self.assertEqual(status, 200, changed)
        self.assertFalse(changed["password_expired"])
        self.assertEqual(self.req("GET", "/api/products", token=changed["access_token"])[0], 200)
        self.assertEqual(self.req("GET", "/api/products", token=d["access_token"])[0], 401)  # token viejo invalidado
        # Historial: volver a la contraseña anterior está prohibido
        status, err = self.req("POST", "/api/auth/password", {"current": "Otra#2026segura", "new": PW},
                               token=changed["access_token"])
        self.assertEqual(status, 400)
        self.assertIn("reutilizar", err["error"])

    def test_admin_can_force_password_change(self):
        admin = self.login("jefe@ipv.cu")
        with server.connect() as conn:
            uid = conn.execute("SELECT id FROM users WHERE email='ana@ipv.cu'").fetchone()[0]
        self.assertEqual(self.req("PUT", f"/api/users/{uid}", {"force_password_change": True}, token=admin["access_token"])[0], 200)
        self.assertTrue(self.login("ana@ipv.cu")["password_expired"])
        with server.connect() as conn:  # restaurar para las demás pruebas
            conn.execute("UPDATE users SET must_change_password=0 WHERE id=?", (uid,))

    def test_failed_login_alerts_and_summary(self):
        import enterprise  # noqa: F401
        with server.connect() as conn:
            auth.create_user(conn, {"email": "pepe@ipv.cu", "name": "Pepe", "role": "viewer", "password": PW}, server.now_iso)
        with mock.patch.dict(rate_limiter.PROFILES, {"auth": (100, 60)}), \
                mock.patch("email_notifications.notify_failed_logins") as alert:
            for _ in range(2):
                self.assertEqual(self.req("POST", "/api/auth/login", {"email": "pepe@ipv.cu", "password": "mal"})[0], 401)
            alert.assert_not_called()
            self.req("POST", "/api/auth/login", {"email": "pepe@ipv.cu", "password": "mal"})   # 3.º → alerta
            self.assertEqual(alert.call_count, 1)
            self.assertEqual(alert.call_args.args[3], 3)
            self.assertFalse(alert.call_args.args[4])
            self.req("POST", "/api/auth/login", {"email": "pepe@ipv.cu", "password": "mal"})
            self.req("POST", "/api/auth/login", {"email": "pepe@ipv.cu", "password": "mal"})   # 5.º → bloqueo
            self.assertTrue(alert.call_args.args[4])
            self.assertEqual(self.req("POST", "/api/auth/login", {"email": "pepe@ipv.cu", "password": PW})[0], 423)
            with server.connect() as conn:
                conn.execute("UPDATE users SET locked_until=0 WHERE email='pepe@ipv.cu'")
            ok = self.login("pepe@ipv.cu")
            self.assertEqual(ok["failed_attempts_since_last_login"], 5)
            self.assertEqual(ok["last_failed_ip"], "127.0.0.1")
            self.assertEqual(self.login("pepe@ipv.cu")["failed_attempts_since_last_login"], 0)

    def test_password_spraying_detection(self):
        import enterprise
        with mock.patch.dict(rate_limiter.PROFILES, {"auth": (100, 60)}), \
                mock.patch.object(enterprise, "NOTIFY_EMAIL", "seguridad@ipv.cu"), \
                mock.patch("email_notifications.notify_suspicious_ip") as alert:
            for i in range(enterprise.SPRAY_ACCOUNTS + 2):
                self.req("POST", "/api/auth/login", {"email": f"victima{i}@ipv.cu", "password": "Verano2026!"})
            self.assertEqual(alert.call_count, 1)  # una sola alerta por hora e IP
            self.assertEqual(alert.call_args.args[1], "127.0.0.1")

    def test_security_status_reports_bplus(self):
        admin = self.login("jefe@ipv.cu")
        status, data = self.req("GET", "/api/security/status", token=admin["access_token"])
        self.assertEqual(status, 200)
        for key in ("db_encryption", "password_max_age_days", "password_history", "new_ip_alerts"):
            self.assertIn(key, data)


class CspTest(unittest.TestCase):
    def test_strict_script_policy(self):
        import enterprise
        directives = {d.split()[0]: d.split()[1:] for d in (x.strip() for x in enterprise.CSP.split(";")) if d}
        self.assertEqual(directives["script-src"], ["'self'"])
        self.assertEqual(directives["script-src-attr"], ["'none'"])
        self.assertNotIn("'unsafe-inline'", directives["style-src"])
        self.assertNotIn("'unsafe-eval'", enterprise.CSP)
        self.assertEqual(directives["frame-ancestors"], ["'none'"])

    def test_no_inline_script_in_html(self):
        html = (Path(server.ROOT) / "web" / "index.html").read_text(encoding="utf-8")
        import re
        self.assertIsNone(re.search(r"\son[a-z]+\s*=", html), "manejador de evento en línea")
        self.assertIsNone(re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), "<script> en línea")
        self.assertNotIn("javascript:", html)
        self.assertNotIn("fonts.googleapis", html)


class AuthUnitTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(auth, "JWT_SECRET", "unit-secret-" + "z" * 32)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.conn = dbcrypt.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        auth.init_auth(self.conn, server.now_iso)
        auth.create_user(self.conn, {"email": "u@ipv.cu", "name": "U", "role": "viewer", "password": PW}, server.now_iso)
        self.uid = self.conn.execute("SELECT id FROM users").fetchone()[0]

    def test_new_ip_detection(self):
        now = server.now_iso()
        self.assertFalse(auth.register_login_ip(self.conn, self.uid, "10.0.0.5", now))   # primer acceso: sin alerta
        self.assertFalse(auth.register_login_ip(self.conn, self.uid, "10.0.0.5", now))   # IP conocida
        self.assertTrue(auth.register_login_ip(self.conn, self.uid, "203.0.113.9", now))  # IP nueva → alerta
        self.assertFalse(auth.register_login_ip(self.conn, self.uid, "", now))

    def test_new_ip_alert_is_sent_on_login(self):
        with mock.patch("email_notifications.notify_new_login") as notify:
            import enterprise  # noqa: F401 - ya instalado por server
            auth.register_login_ip(self.conn, self.uid, "10.0.0.5", server.now_iso())
            self.assertTrue(auth.login(self.conn, "u@ipv.cu", PW, server.now_iso, ip="198.51.100.7")["new_ip"])
            self.assertFalse(auth.login(self.conn, "u@ipv.cu", PW, server.now_iso, ip="198.51.100.7")["new_ip"])
            notify.assert_not_called()  # el envío lo hace la capa HTTP, no auth

    def test_password_age_expiry(self):
        with mock.patch.object(auth, "PASSWORD_MAX_AGE_DAYS", 90):
            row = self.conn.execute("SELECT * FROM users").fetchone()
            self.assertFalse(auth.password_status(row)["expired"])
            self.assertIn(auth.password_status(row)["days_left"], (89, 90))
            self.conn.execute("UPDATE users SET password_changed_at='2020-01-01T00:00:00Z'")
            row = self.conn.execute("SELECT * FROM users").fetchone()
            self.assertTrue(auth.password_status(row)["expired"])
            self.assertTrue(auth.login(self.conn, "u@ipv.cu", PW, server.now_iso)["password_expired"])
        row = self.conn.execute("SELECT * FROM users").fetchone()
        self.assertFalse(auth.password_status(row)["expired"])  # 0 = sin caducidad

    def test_device_labels(self):
        self.assertEqual(auth.device_label("Mozilla/5.0 (Windows NT 10.0) Chrome/130 Edg/130"), "Edge · Windows")
        self.assertEqual(auth.device_label("Mozilla/5.0 (Linux; Android 14) Chrome/130"), "Chrome · Android")
        self.assertEqual(auth.device_label(""), "Desconocido")


@unittest.skipIf(dbcrypt._cipher is None, "SQLCipher no instalado (pip install sqlcipher3-binary)")
class DbCryptTest(unittest.TestCase):
    KEY = "frase-de-prueba-muy-larga-2026"

    def test_encrypt_existing_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "plano.db"
            with sqlite3.connect(db) as conn:
                conn.execute("CREATE TABLE t(nombre TEXT)")
                conn.execute("INSERT INTO t VALUES('Aceite de girasol')")
            self.assertTrue(dbcrypt.is_plaintext(db))
            backup = dbcrypt.encrypt_file(db, key=self.KEY)
            self.assertTrue(backup.exists())
            self.assertFalse(dbcrypt.is_plaintext(db))
            self.assertNotIn(b"Aceite de girasol", db.read_bytes())
            conn = dbcrypt.connect(db, key=self.KEY)
            self.assertEqual(conn.execute("SELECT nombre FROM t").fetchone()[0], "Aceite de girasol")
            conn.close()
            with self.assertRaises(dbcrypt.CryptoConfigError):
                dbcrypt.connect(db, key="clave-incorrecta-1234567")
            with self.assertRaises(dbcrypt.CryptoConfigError):  # ya cifrada
                dbcrypt.encrypt_file(db, key=self.KEY)

    def test_plaintext_db_refused_when_key_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "plano.db"
            sqlite3.connect(db).execute("CREATE TABLE t(a)").connection.commit()
            with self.assertRaises(dbcrypt.CryptoConfigError):
                dbcrypt.connect(db, key=self.KEY)

    def test_rekey_and_decrypt(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "c.db"
            conn = dbcrypt.connect(db, key=self.KEY)
            conn.execute("CREATE TABLE t(a)"); conn.execute("INSERT INTO t VALUES(7)"); conn.commit(); conn.close()
            new_key = "otra-frase-distinta-2026-xyz"
            dbcrypt.rekey(db, new_key, key=self.KEY)
            with self.assertRaises(dbcrypt.CryptoConfigError):
                dbcrypt.connect(db, key=self.KEY)
            plain = Path(tmp) / "plano.db"
            dbcrypt.decrypt_to(db, plain, key=new_key)
            self.assertTrue(dbcrypt.is_plaintext(plain))
            self.assertEqual(sqlite3.connect(plain).execute("SELECT a FROM t").fetchone()[0], 7)


if __name__ == "__main__":
    unittest.main()
