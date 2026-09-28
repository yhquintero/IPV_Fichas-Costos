import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import auth
import licencia as L
import rate_limiter
import server

ROOT = Path(__file__).resolve().parent.parent
PWD = "Clave-Segura-2026!"


class LicenciaCryptoTest(unittest.TestCase):
    def setUp(self):
        self.d, self.pub = L.generate_keypair()
        self.code = L.request_code(L.APP_WEB, "equipo-cliente-1")
        self.body = L.parse_request_code(self.code)[1]

    def test_firma_y_rechazos(self):
        now = time.time()
        tok = L.issue(self.d, "Ana López", self.code, "1M", now=now)
        data = L.check(tok, self.pub, L.APP_WEB, self.body, now + 10)
        self.assertEqual((data["usr"], data["plan"], data["exp"] - data["iat"]), ("Ana López", "1M", 30 * L.DAY))
        # Otro dispositivo, otra app, vencida, reloj atrasado, firma de otra clave, contenido alterado
        other = L.parse_request_code(L.request_code(L.APP_WEB, "otro-equipo"))[1]
        cases = [
            (lambda: L.check(tok, self.pub, L.APP_WEB, other, now), "otro dispositivo"),
            (lambda: L.check(tok, self.pub, L.APP_ANDROID, self.body, now), "es para"),
            (lambda: L.check(tok, self.pub, L.APP_WEB, self.body, now + 31 * L.DAY), "venció"),
            (lambda: L.check(tok, self.pub, L.APP_WEB, self.body, now, last_seen=now + 3 * L.DAY), "fecha del equipo"),
            (lambda: L.check(tok, L.generate_keypair()[1], L.APP_WEB, self.body, now), "Firma no válida"),
        ]
        head, payload, sig = tok.split(".")
        forged = json.loads(L._unb64u(payload))
        forged["plan"], forged["exp"] = "2A", forged["exp"] + 700 * L.DAY
        cases.append((lambda: L.decode(f"{head}.{L._b64u(json.dumps(forged).encode())}.{sig}", self.pub), "Firma no válida"))
        for fn, msg in cases:
            with self.assertRaises(ValueError) as ctx:
                fn()
            self.assertIn(msg, str(ctx.exception))

    def test_codigo_de_solicitud(self):
        self.assertRegex(self.code, r"^IPVW(-[A-Z2-7]{5}){4}-[A-Z2-7]{2}$")
        self.assertEqual(L.parse_request_code(self.code.lower().replace("-", " ")), (L.APP_WEB, self.body))
        self.assertNotIn("equipo-cliente-1", self.code)
        typo = self.code[:6] + ("A" if self.code[6] != "A" else "B") + self.code[7:]
        with self.assertRaises(ValueError):
            L.parse_request_code(typo)
        with self.assertRaises(ValueError):
            L.issue(self.d, "x", self.code, "5A")

    def test_todos_los_planes(self):
        for plan, (_n, days, usd_web, usd_android) in L.PLANS.items():
            data = L.decode(L.issue(self.d, "Cliente", self.code, plan), self.pub)
            self.assertEqual(data["exp"] - data["iat"], days * L.DAY)
            self.assertGreater(usd_web, usd_android)


class LicenciaServidorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        server.DB_PATH = Path(cls.tmp.name) / "lic.db"
        server.init_db()
        auth.JWT_SECRET = "lic-test-" + "z" * 32
        auth.JWT_ENABLED = True
        with server.connect() as conn:
            auth.create_user(conn, {"email": "jefe@ipv.cu", "name": "Jefe", "role": "admin", "password": PWD}, server.now_iso)
            auth.create_user(conn, {"email": "ana@ipv.cu", "name": "Ana", "role": "editor", "password": PWD}, server.now_iso)
        cls.d, pub = L.generate_keypair()
        cls.store = server.LICENSE
        cls.saved = (cls.store.pub, cls.store.dir)
        cls.store.pub, cls.store.dir, cls.store._cache = pub, Path(cls.tmp.name), None
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.store.pub, cls.store.dir = cls.saved
        cls.store._cache = None
        auth.JWT_ENABLED = False
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.tmp.cleanup()

    def setUp(self):
        rate_limiter._hits.clear()

    def req(self, method, path, body=None, token=None):
        h = {"Content-Type": "application/json"}
        if token:
            h["Authorization"] = f"Bearer {token}"
        r = urllib.request.Request(self.base + path, data=json.dumps(body).encode() if body is not None else None,
                                   headers=h, method=method)
        try:
            with urllib.request.urlopen(r) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def login(self, email):
        return self.req("POST", "/api/auth/login", {"email": email, "password": PWD})

    def test_flujo_completo(self):
        # 1) Sin licencia: la API se bloquea con 402 y el código de solicitud; salud y activación siguen abiertas
        st, info = self.req("GET", "/api/license")
        self.assertEqual((st, info["valid"], info["enforced"]), (200, False, True))
        self.assertEqual(info["request_code"], self.store.code)
        self.assertEqual(self.req("GET", "/api/health")[0], 200)
        st, tok = self.login("jefe@ipv.cu")
        self.assertEqual(st, 402)
        self.assertTrue(tok["license_required"])
        self.assertEqual(tok["request_code"], self.store.code)
        # 2) Licencias no válidas
        other = L.issue(self.d, "Pirata", L.request_code(L.APP_WEB, "otra-pc"), "1A")
        self.assertIn("otro dispositivo", self.req("POST", "/api/license", {"license": other})[1]["error"])
        android = L.issue(self.d, "Móvil", L.request_code(L.APP_ANDROID, "x"), "1A")
        self.assertEqual(self.req("POST", "/api/license", {"license": android})[0], 400)
        fake = L.issue(L.generate_keypair()[0], "Falsa", self.store.code, "2A")
        self.assertIn("Firma", self.req("POST", "/api/license", {"license": fake})[1]["error"])
        # 3) Activación correcta (sin sesión: el equipo aún no puede iniciarla)
        good = L.issue(self.d, "Empresa Cliente", self.store.code, "1M")
        st, res = self.req("POST", "/api/license", {"license": "\n".join([good[:90], good[90:]])})  # tolera saltos de línea
        self.assertEqual((st, res["valid"], res["plan"], res["user"]), (200, True, "1M", "Empresa Cliente"))
        self.assertTrue((Path(self.tmp.name) / "licencia.lic").exists())
        st, tok = self.login("jefe@ipv.cu")
        self.assertEqual(st, 200)
        self.assertEqual(self.req("GET", "/api/dashboard", token=tok["access_token"])[0], 200)
        # 4) Con licencia vigente, renovar exige administrador
        renew = L.issue(self.d, "Empresa Cliente", self.store.code, "1A")
        self.assertEqual(self.req("POST", "/api/license", {"license": renew})[0], 401)
        editor = self.login("ana@ipv.cu")[1]["access_token"]
        self.assertEqual(self.req("POST", "/api/license", {"license": renew}, token=editor)[0], 403)
        st, res = self.req("POST", "/api/license", {"license": renew}, token=tok["access_token"])
        self.assertEqual((st, res["plan"]), (200, "1A"))
        with server.connect() as conn:
            actions = {r[0] for r in conn.execute("SELECT action FROM audit_log")}
        self.assertTrue({"LICENSE_ACTIVATED", "LICENSE_REJECTED"} <= actions)
        # 5) Vencimiento: con el reloj adelantado la API vuelve a bloquearse
        later = time.time() + 400 * L.DAY
        self.assertFalse(self.store.status(now=later, use_cache=False)["valid"])
        self.store._cache = None


class KeygenCliTest(unittest.TestCase):
    def test_init_emitir_verificar(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            (work / "keygen").mkdir()
            for rel in ("licencia.py", "keygen/keygen.py"):
                (work / rel).write_text((ROOT / rel).read_text(encoding="utf-8"), encoding="utf-8")
            kt = work / "android/app/src/main/java/cu/ipvcostos/app/License.kt"
            kt.parent.mkdir(parents=True)
            kt.write_text('const val PUBLIC_KEY_B64 = ""\nconst val WHATSAPP_NUMBER = ""\n', encoding="utf-8")
            env = {**os.environ, "IPV_KEYGEN_PASS": "contraseña-muy-larga-1"}
            run = lambda *a, e=env: subprocess.run([sys.executable, "keygen/keygen.py", *a], cwd=work, env=e, check=False,
                                                   capture_output=True, text=True, timeout=120)
            self.assertEqual(run("init", "--whatsapp", "+53 5555 5555").returncode, 0)
            self.assertIn('WHATSAPP_NUMBER = "5355555555"', (work / "licencia.py").read_text(encoding="utf-8"))
            self.assertIn("MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE", kt.read_text(encoding="utf-8"))
            key = json.loads((work / "keygen/clave_privada.json").read_text())
            self.assertNotIn("d", key)  # la clave privada solo existe cifrada
            code = L.request_code(L.APP_ANDROID, "movil-1")
            out = run("emitir", "--usuario", "Luis", "--codigo", code, "--plan", "6M")
            self.assertEqual(out.returncode, 0, out.stderr)
            token = next(line for line in out.stdout.splitlines() if line.startswith("IPV1."))
            self.assertEqual(L.decode(token, key["public"])["plan"], "6M")
            self.assertIn("39 USD = 28 860 CUP", out.stdout)
            self.assertIn("Firma válida", run("verificar", "--licencia", token).stdout)
            bad = run("emitir", "--usuario", "x", "--codigo", code, "--plan", "1M", e={**env, "IPV_KEYGEN_PASS": "mala"})
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn("Contraseña incorrecta", bad.stderr)
            self.assertEqual(len((work / "keygen/registro_licencias.csv").read_text(encoding="utf-8").splitlines()), 2)


if __name__ == "__main__":
    unittest.main()
