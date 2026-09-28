"""Pruebas de inyección SQL contra la API.

El escaneo activo de OWASP ZAP marca «SQL Injection» y «Spring4Shell» en esta API:
son **falsos positivos** (la validación estricta responde 400 y el servidor no es
Java/Spring). Estas pruebas dejan constancia comprobable de que:

  * los parámetros numéricos se validan y nunca llegan a la consulta como texto;
  * el texto libre viaja siempre parametrizado (no altera la consulta);
  * ninguna carga maliciosa borra datos ni salta la autenticación;
  * los mensajes de error no filtran detalles internos de Python.
"""
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import auth
import rate_limiter
import server

PW = "Inyeccion#2026x"
EMAIL = "inyeccion@ipv.cu"

CARGAS_TEXTO = [
    "' OR '1'='1",
    "'; DROP TABLE audit_log; --",
    "x' UNION SELECT 1,2,3,4,5,6 -- ",
    '" OR ""="',
    "1; DELETE FROM products",
]
CARGAS_NUMERICAS = [
    "50 AND 1=1 -- ",
    "50 AND 1=2 -- ",
    "0; SELECT 1",
    "1 OR 1=1",
]


class PruebaInyeccion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.db_previa = server.DB_PATH
        server.DB_PATH = Path(cls.tmp.name) / "inyeccion.db"
        server.init_db()
        auth.JWT_SECRET = "test-secret-" + "z" * 32
        auth.JWT_ENABLED = True
        with server.connect() as conn:
            auth.create_user(conn, {"email": EMAIL, "name": "Auditor", "role": "admin", "password": PW},
                             server.now_iso)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_port}"
        rate_limiter._hits.clear()
        with mock.patch.dict(rate_limiter.PROFILES, {"auth": (1000, 60)}):
            cls.token = cls._login(EMAIL, PW)

    @classmethod
    def tearDownClass(cls):
        auth.JWT_ENABLED = False
        cls.httpd.shutdown()
        cls.httpd.server_close()
        server.DB_PATH = cls.db_previa
        cls.tmp.cleanup()

    def setUp(self):
        rate_limiter._hits.clear()

    # ------------------------------------------------------------------
    @classmethod
    def _peticion(cls, ruta, token=None, metodo="GET", cuerpo=None):
        req = urllib.request.Request(cls.base + ruta, method=metodo)
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        datos = None
        if cuerpo is not None:
            datos = json.dumps(cuerpo).encode()
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, datos, timeout=10) as resp:  # nosec B310 - servidor local de prueba
                return resp.status, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", "replace")

    @classmethod
    def _login(cls, email, password):
        estado, cuerpo = cls._peticion("/api/auth/login", metodo="POST",
                                       cuerpo={"email": email, "password": password})
        return json.loads(cuerpo)["access_token"] if estado == 200 else ""

    # ------------------------------------------------------------------
    def test_token_de_administrador(self):
        self.assertTrue(self.token, "el administrador de pruebas debe poder entrar")

    def test_parametros_numericos_se_rechazan(self):
        """Un «limit» con SQL dentro nunca llega a la consulta: se responde 400."""
        for carga in CARGAS_NUMERICAS:
            with self.subTest(carga=carga):
                ruta = "/api/audit?limit=" + urllib.parse.quote(carga)
                estado, cuerpo = self._peticion(ruta, self.token)
                self.assertEqual(estado, 400, cuerpo[:120])
                self.assertNotIn("sqlite", cuerpo.lower())

    def test_texto_libre_va_parametrizado(self):
        """Las cargas en «q» se buscan como texto literal, no como SQL.

        Se antepone un texto imposible: si la inyección funcionara, la condición
        «OR 1=1» devolvería todos los registros en lugar de ninguno.
        """
        estado, cuerpo = self._peticion("/api/audit?limit=1", self.token)
        self.assertEqual(estado, 200, cuerpo[:120])
        self.assertGreater(json.loads(cuerpo)["total"], 0)
        for carga in CARGAS_TEXTO:
            with self.subTest(carga=carga):
                ruta = "/api/audit?limit=50&q=" + urllib.parse.quote("zzz-texto-imposible" + carga)
                estado, cuerpo = self._peticion(ruta, self.token)
                self.assertEqual(estado, 200, cuerpo[:120])
                datos = json.loads(cuerpo)
                self.assertEqual(datos["total"], 0, "la carga no debe alterar la consulta")
                self.assertEqual(datos["entries"], [])

    def test_la_auditoria_sigue_intacta(self):
        """Después de todas las cargas la tabla sigue existiendo y con registros."""
        estado, cuerpo = self._peticion("/api/audit?limit=50", self.token)
        self.assertEqual(estado, 200)
        self.assertGreater(json.loads(cuerpo)["total"], 0)

    def test_login_no_se_puede_saltar(self):
        """Ni el correo ni la contraseña permiten alterar la consulta de acceso."""
        with mock.patch.dict(rate_limiter.PROFILES, {"auth": (1000, 60)}):
            for carga in CARGAS_TEXTO:
                with self.subTest(carga=carga):
                    estado, _ = self._peticion("/api/auth/login", metodo="POST",
                                               cuerpo={"email": EMAIL, "password": carga})
                    self.assertEqual(estado, 401, "nunca debe conceder acceso")
                    estado, _ = self._peticion("/api/auth/login", metodo="POST",
                                               cuerpo={"email": carga, "password": "x"})
                    self.assertEqual(estado, 401, "nunca debe conceder acceso")

    def test_busqueda_global_con_cargas(self):
        for carga in CARGAS_TEXTO:
            with self.subTest(carga=carga):
                ruta = "/api/search?q=" + urllib.parse.quote(carga)
                estado, cuerpo = self._peticion(ruta, self.token)
                self.assertEqual(estado, 200, cuerpo[:120])

    def test_los_errores_no_filtran_detalles_internos(self):
        """Un cuerpo mal formado responde en español y sin trazas de Python."""
        estado, cuerpo = self._peticion("/api/fichas", self.token, "POST",
                                        {"product_id": "abc", "items": []})
        self.assertEqual(estado, 400, cuerpo[:120])
        for fuga in ("int()", "NoneType", "Traceback", "literal for"):
            self.assertNotIn(fuga, cuerpo)

    def test_los_datos_siguen_ahi(self):
        estado, cuerpo = self._peticion("/api/products", self.token)
        self.assertEqual(estado, 200)
        self.assertGreater(len(json.loads(cuerpo)), 0, "las cargas no deben borrar productos")


if __name__ == "__main__":
    unittest.main()
