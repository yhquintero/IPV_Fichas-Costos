"""Pruebas del Creador de Licencias (creador_licencias.py + rutas /api/keygen)."""
import json
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import auth
import licencia as L
import rate_limiter
import server
from keygen import keygen as kg
import creador_licencias as C

ROOT = Path(__file__).resolve().parent.parent
PWD = "Clave-Segura-2026!"
PASS = "Clave-Firma-2026!"


def _req(base, method, path, body=None, token=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    r = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None,
                               headers=h, method=method)
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


class CreadorLicenciasTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        work = Path(cls.tmp.name)
        # Redirige clave, registro, tasas y ficheros parcheables a un directorio temporal
        kg.KEY_FILE = work / "clave_privada.json"
        kg.LEDGER = work / "registro_licencias.csv"
        kg.RATES_FILE = work / "tasas.json"
        cls.lic_py = work / "licencia.py"
        cls.lic_kt = work / "License.kt"
        cls.lic_py.write_text('PUBLIC_KEY_HEX = ""\nWHATSAPP_NUMBER = ""\n', encoding="utf-8")
        cls.lic_kt.write_text('const val PUBLIC_KEY_B64 = ""\nconst val WHATSAPP_NUMBER = ""\n', encoding="utf-8")
        C.LICENCIA_PY, C.LICENSE_KT = cls.lic_py, cls.lic_kt
        cls.saved = (L.PUBLIC_KEY_HEX, L.WHATSAPP_NUMBER)

        server.DB_PATH = work / "creador.db"
        server.init_db()
        auth.JWT_SECRET = "creador-test-" + "z" * 32
        auth.JWT_ENABLED = True
        with server.connect() as conn:
            auth.create_user(conn, {"email": "jefe@ipv.cu", "name": "Jefe", "role": "admin", "password": PWD}, server.now_iso)
            auth.create_user(conn, {"email": "ana@ipv.cu", "name": "Ana", "role": "editor", "password": PWD}, server.now_iso)
        cls.store = server.LICENSE
        cls.saved_store = (cls.store.pub, cls.store.dir)
        cls.store.pub, cls.store.dir, cls.store._cache = "", work, None
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_port}"
        # Sesiones creadas ANTES de activar las licencias: con licencias activadas y sin
        # licencia de equipo, /api/auth/login responde 402 (comportamiento esperado).
        rate_limiter._hits.clear()
        cls.admin = _req(cls.base, "POST", "/api/auth/login", {"email": "jefe@ipv.cu", "password": PWD})[1]["access_token"]
        cls.editor = _req(cls.base, "POST", "/api/auth/login", {"email": "ana@ipv.cu", "password": PWD})[1]["access_token"]

    @classmethod
    def tearDownClass(cls):
        cls.store.pub, cls.store.dir = cls.saved_store
        cls.store._cache = None
        L.PUBLIC_KEY_HEX, L.WHATSAPP_NUMBER = cls.saved
        C.LICENCIA_PY = ROOT / "licencia.py"
        C.LICENSE_KT = ROOT / "android/app/src/main/java/cu/ipvcostos/app/License.kt"
        auth.JWT_ENABLED = False
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.tmp.cleanup()

    def setUp(self):
        rate_limiter._hits.clear()

    @property
    def token(self):
        return self.admin

    def req(self, method, path, body=None, token=None):
        return _req(self.base, method, path, body, token)

    def login(self, email):
        return self.req("POST", "/api/auth/login", {"email": email, "password": PWD})

    # ---------------------------------------------------------- pruebas ----
    def test_01_estado_sin_configurar(self):
        st, _ = self.req("GET", "/api/keygen/status")
        self.assertEqual(st, 401)  # sin sesión no se puede usar el Creador
        st, info = self.req("GET", "/api/keygen/status", token=self.token)
        self.assertEqual((st, info["configured"], info["has_key_file"]), (200, False, False))
        self.assertIn("plans", info)

    def test_02_emision_sin_clave_rechazada(self):
        code = L.request_code(L.APP_WEB, "pc-cliente")
        st, res = self.req("POST", "/api/keygen/emit", {"user": "Ana", "code": code, "plan": "1M", "passphrase": PASS}, token=self.token)
        self.assertEqual(st, 400)
        self.assertIn("clave", res["error"])

    def test_03_init_crea_clave_y_activa_al_instante(self):
        # Contraseña corta → rechazo
        st, res = self.req("POST", "/api/keygen/init", {"passphrase": "corta", "whatsapp": "53555555"}, token=self.token)
        self.assertEqual(st, 400)
        # Clave correcta: las licencias se activan en caliente
        st, res = self.req("POST", "/api/keygen/init", {"passphrase": PASS, "whatsapp": "53 5555 5555", "force": True}, token=self.token)
        self.assertEqual(st, 200)
        self.assertTrue(res["configured"])
        self.assertIn("-", res["fingerprint"])
        self.assertEqual(res["whatsapp"], "5355555555")
        self.assertIn("licencia.py", res["patched"])
        self.assertTrue(kg.KEY_FILE.exists())
        self.assertIn(f'PUBLIC_KEY_HEX = "{L.PUBLIC_KEY_HEX}"', self.lic_py.read_text(encoding="utf-8"))
        self.assertIn("PUBLIC_KEY_B64 = \"MFkw", self.lic_kt.read_text(encoding="utf-8"))
        # El servidor ya exige licencia: la API de negocio responde 402…
        st, res = self.req("GET", "/api/dashboard", token=self.token)
        self.assertEqual((st, res.get("license_required")), (402, True))
        # …pero el Creador sigue accesible (rutas libres de licencia, solo admin)
        self.assertEqual(self.req("GET", "/api/keygen/status", token=self.token)[0], 200)

    def test_04_init_requiere_force_con_clave_existente(self):
        st, res = self.req("POST", "/api/keygen/init", {"passphrase": PASS, "whatsapp": "", "force": False}, token=self.token)
        self.assertEqual(st, 400)
        self.assertIn("Ya existe", res["error"])

    def test_05_emitir_y_verificar(self):
        code = L.request_code(L.APP_ANDROID, "movil-cliente")
        # Contraseña incorrecta
        st, res = self.req("POST", "/api/keygen/emit", {"user": "Luis", "code": code, "plan": "6M", "passphrase": "mala-clave-123"}, token=self.token)
        self.assertEqual(st, 400)
        self.assertIn("Contraseña", res["error"])
        # Código inválido
        st, res = self.req("POST", "/api/keygen/emit", {"user": "Luis", "code": "IPVA-NO", "plan": "6M", "passphrase": PASS}, token=self.token)
        self.assertEqual(st, 400)
        # Emisión correcta
        st, res = self.req("POST", "/api/keygen/emit", {"user": "Luis Pérez", "code": code, "plan": "6M", "passphrase": PASS}, token=self.token)
        self.assertEqual(st, 200)
        self.assertEqual((res["app"], res["plan"]), (L.APP_ANDROID, "6M"))
        data = L.decode(res["license"], L.PUBLIC_KEY_HEX)
        self.assertEqual(data["usr"], "Luis Pérez")
        self.assertEqual(res["price_usd"], 39)          # precio Android 6M
        # Verificar
        st, info = self.req("POST", "/api/keygen/verify", {"license": res["license"]}, token=self.token)
        self.assertEqual((st, info["user"], info["app_name"]), (200, "Luis Pérez", "IPV Android (móvil)"))
        # Emisión personalizada: fechas inclusivas UTC, precio manual y firma verificable.
        start = (datetime.now(timezone.utc).date() + timedelta(days=1))
        end = start + timedelta(days=20)
        st, missing = self.req("POST", "/api/keygen/emit", {
            "user": "Luis Pérez", "code": code, "plan": "PX", "passphrase": PASS,
        }, token=self.token)
        self.assertEqual(st, 400)
        self.assertIn("Desde, Hasta", missing["error"])
        for fields in (
            {"start_date": (start + timedelta(days=1)).isoformat(), "end_date": start.isoformat(), "custom_price_usd": "22.75"},
            {"start_date": start.isoformat(), "end_date": end.isoformat(), "custom_price_usd": "-0.01"},
        ):
            st, rejected = self.req("POST", "/api/keygen/emit", {
                "user": "Luis Pérez", "code": code, "plan": "PX", "passphrase": PASS, **fields,
            }, token=self.token)
            self.assertEqual(st, 400, rejected)
        st, custom = self.req("POST", "/api/keygen/emit", {
            "user": "Luis Pérez", "code": code, "plan": "PX", "passphrase": PASS,
            "start_date": start.isoformat(), "end_date": end.isoformat(), "custom_price_usd": "22.75",
        }, token=self.token)
        self.assertEqual(st, 200, custom)
        self.assertEqual((custom["plan"], custom["valid_from"], custom["valid_until"], custom["price_usd"]),
                         ("PX", start.isoformat(), end.isoformat(), 22.75))
        custom_data = L.decode(custom["license"], L.PUBLIC_KEY_HEX)
        self.assertEqual((custom_data["start_date"], custom_data["end_date"]), (start.isoformat(), end.isoformat()))
        st, custom_info = self.req("POST", "/api/keygen/verify", {"license": custom["license"]}, token=self.token)
        self.assertEqual((st, custom_info["valid_from"], custom_info["valid_until"]),
                         (200, start.isoformat(), end.isoformat()))
        # Historial
        st, items = self.req("GET", "/api/keygen/ledger", token=self.token)
        self.assertEqual(st, 200)
        self.assertEqual(items["items"][0]["usuario"], "Luis Pérez")
        self.assertEqual((items["items"][0]["plan"], items["items"][0]["desde"], items["items"][0]["hasta"]),
                         ("PX", start.isoformat(), end.isoformat()))
        # La licencia emitida activa este mismo servidor si el código es el suyo
        self_lic = self.req("POST", "/api/keygen/emit", {"user": "Empresa Propia", "code": self.store.code,
                                                         "plan": "1A", "passphrase": PASS}, token=self.token)[1]
        st, res2 = self.req("POST", "/api/license", {"license": self_lic["license"]}, token=self.token)
        self.assertEqual((st, res2["valid"]), (200, True))
        st, res3 = self.req("GET", "/api/dashboard", token=self.token)
        self.assertEqual(st, 200)

    def test_06_solo_administradores(self):
        st, _ = self.req("GET", "/api/keygen/status")
        self.assertEqual(st, 401)  # sin sesión
        st, res = self.req("GET", "/api/keygen/status", token=self.editor)
        self.assertEqual((st, res["error"]), (403, "Permisos insuficientes."))
        st, _ = self.req("POST", "/api/keygen/emit", {"user": "x", "code": "x", "plan": "1M", "passphrase": "x"*12}, token=self.editor)
        self.assertEqual(st, 403)

    def test_07_tasas(self):
        st, res = self.req("POST", "/api/keygen/rates", {"rates": {"USD": "750,50", "EUR": "850"}}, token=self.token)
        self.assertEqual((st, res["rates"]["USD"], res["rates"]["EUR"]), (200, 750.5, 850.0))
        st, res = self.req("POST", "/api/keygen/rates", {"rates": {"USD": "0"}}, token=self.token)
        self.assertEqual(st, 400)
        st, res = self.req("POST", "/api/keygen/rates", {"rates": {"XYZ": "10"}}, token=self.token)
        self.assertEqual(st, 400)


if __name__ == "__main__":
    unittest.main()
