"""Pruebas del acceso seguro por HTTPS (módulo `tls_seguro`).

Se genera un certificado de prueba con OpenSSL; si el sistema no lo tiene,
las pruebas que necesitan un certificado real se omiten.
"""
import http.client
import shutil
import ssl
import subprocess  # nosec B404 - solo se invoca openssl para crear un certificado de prueba
import tempfile
import unittest
from pathlib import Path

import tls_seguro

OPENSSL = shutil.which("openssl")


def _make_cert(directory: Path, days: int = 825) -> tuple[Path, Path]:
    """Certificado autofirmado de prueba (CN=sqlserver, SAN DNS/IP)."""
    cert, key = directory / "cert.pem", directory / "key.pem"
    subprocess.run(  # nosec B603 - ruta absoluta de openssl y argumentos fijos
        [
            OPENSSL, "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(key), "-out", str(cert), "-days", str(days),
            "-subj", "/CN=sqlserver",
            "-addext", "subjectAltName=DNS:sqlserver,DNS:localhost,IP:127.0.0.1",
        ],
        check=True, capture_output=True,
    )
    return cert, key


class ConfiguracionTlsTest(unittest.TestCase):
    def test_version_minima(self):
        self.assertEqual(tls_seguro.parse_min_version("1.2"), ssl.TLSVersion.TLSv1_2)
        self.assertEqual(tls_seguro.parse_min_version("1.3"), ssl.TLSVersion.TLSv1_3)
        self.assertEqual(tls_seguro.parse_min_version("TLSv1.3"), ssl.TLSVersion.TLSv1_3)
        self.assertEqual(tls_seguro.parse_min_version("sslv3"), ssl.TLSVersion.TLSv1_2)  # nunca por debajo de 1.2
        self.assertEqual(tls_seguro.parse_min_version(None), ssl.TLSVersion.TLSv1_2)

    def test_cert_y_clave_van_juntos(self):
        with self.assertRaises(tls_seguro.TLSConfigError):
            tls_seguro.validate_config("cert.pem", "", False)
        with self.assertRaises(tls_seguro.TLSConfigError):
            tls_seguro.validate_config("", "key.pem", False)
        tls_seguro.validate_config("", "", False)  # modo HTTP explícito: válido

    def test_require_tls_bloquea_el_modo_claro(self):
        with self.assertRaises(tls_seguro.TLSConfigError):
            tls_seguro.validate_config("", "", True)
        tls_seguro.validate_config("cert.pem", "key.pem", True)  # no toca el disco: solo coherencia

    def test_rutas_inexistentes(self):
        with self.assertRaises(tls_seguro.TLSConfigError):
            tls_seguro.build_context("/no/existe/cert.pem", "/no/existe/key.pem")

    def test_certificado_ausente_no_lanza(self):
        self.assertEqual(tls_seguro.certificate_info("/no/existe/cert.pem"), {})
        self.assertEqual(tls_seguro.certificate_warning("/no/existe/cert.pem"), "")

    def test_direcciones_locales(self):
        direcciones = tls_seguro.local_addresses()
        self.assertIn("127.0.0.1", direcciones)


@unittest.skipUnless(OPENSSL, "OpenSSL no está disponible")
class CertificadoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.cert, cls.key = _make_cert(Path(cls.tmp.name))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_contexto_endurecido(self):
        ctx = tls_seguro.build_context(self.cert, self.key)
        self.assertGreaterEqual(ctx.minimum_version, ssl.TLSVersion.TLSv1_2)
        self.assertTrue(ctx.options & ssl.OP_NO_COMPRESSION)
        self.assertTrue(ctx.options & ssl.OP_CIPHER_SERVER_PREFERENCE)
        self.assertTrue(ctx.options & ssl.OP_NO_SSLv3)
        # Ningún cifrado sin secreto hacia adelante ni sin autenticar
        nombres = [c["name"] for c in ctx.get_ciphers()]
        self.assertTrue(nombres)
        for nombre in nombres:
            self.assertFalse(nombre.startswith(("AES", "DES", "RC4", "NULL")), nombre)

    def test_solo_tls13(self):
        ctx = tls_seguro.build_context(self.cert, self.key, minimum="1.3")
        self.assertEqual(ctx.minimum_version, ssl.TLSVersion.TLSv1_3)

    def test_datos_del_certificado(self):
        info = tls_seguro.certificate_info(self.cert)
        self.assertEqual(info["subject"], "sqlserver")
        self.assertIn("sqlserver", info["hostnames"])
        self.assertIn("127.0.0.1", info["hostnames"])
        self.assertGreater(info["days_left"], 30)
        self.assertTrue(info["expires_at"])

    def test_aviso_de_renovacion(self):
        self.assertEqual(tls_seguro.certificate_warning(self.cert), "")
        with tempfile.TemporaryDirectory() as tmp:
            corto, _ = _make_cert(Path(tmp), days=10)
            aviso = tls_seguro.certificate_warning(corto)
            self.assertIn("caduca en", aviso)
            self.assertIn("-Renew", aviso)

    def test_handshake_real_rechaza_tls11(self):
        """Un cliente limitado a TLS 1.1 no puede hablar con el servidor."""
        import http.server
        import threading

        ctx = tls_seguro.build_context(self.cert, self.key)
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), http.server.BaseHTTPRequestHandler)
        httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
        puerto = httpd.server_address[1]
        hilo = threading.Thread(target=httpd.serve_forever, daemon=True)
        hilo.start()
        try:
            cliente = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            cliente.check_hostname = False
            cliente.verify_mode = ssl.CERT_NONE
            cliente.maximum_version = ssl.TLSVersion.TLSv1_1
            import socket
            with self.assertRaises(ssl.SSLError):
                with socket.create_connection(("127.0.0.1", puerto), timeout=5) as sock:
                    with cliente.wrap_socket(sock, server_hostname="sqlserver"):
                        pass
        finally:
            httpd.shutdown()
            httpd.server_close()


def _puerto_libre() -> int:
    import socket
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class RedireccionHttpsTest(unittest.TestCase):
    def test_redirige_a_https_conservando_la_ruta(self):
        servidor = tls_seguro.start_redirector(_puerto_libre(), 8443, "127.0.0.1")
        self.assertIsNotNone(servidor)
        puerto = servidor.server_address[1]
        try:
            for metodo, ruta in (("GET", "/api/health?x=1"), ("POST", "/api/auth/login")):
                conexion = http.client.HTTPConnection("127.0.0.1", puerto, timeout=5)
                try:
                    conexion.request(metodo, ruta, headers={"Host": f"sqlserver:{puerto}"})
                    respuesta = conexion.getresponse()
                    respuesta.read()
                    self.assertEqual(respuesta.status, 308, metodo)
                    self.assertEqual(respuesta.getheader("Location"), f"https://sqlserver:8443{ruta}")
                finally:
                    conexion.close()
        finally:
            servidor.shutdown()
            servidor.server_close()

    def test_desactivado_por_configuracion(self):
        self.assertIsNone(tls_seguro.start_redirector(0, 0))
        self.assertIsNone(tls_seguro.start_redirector(8443, 8443))


if __name__ == "__main__":
    unittest.main()
