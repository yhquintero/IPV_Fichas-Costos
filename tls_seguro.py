"""IPV · Fichas y Costos — Acceso seguro por HTTPS.
Autor: Ing. Yosvany Hernández Quintero

Reúne todo lo relativo a TLS para que el servidor y el script `iniciar-https.ps1`
compartan las mismas reglas:

  · `build_context`      contexto TLS endurecido (1.2 mínimo, cifrados AEAD, sin compresión).
  · `certificate_info`   datos del certificado (nombres, emisor, caducidad, días restantes).
  · `validate_config`    avisa de configuraciones inseguras antes de arrancar.
  · `start_redirector`   envía a HTTPS a quien entre por HTTP (evita teclear el esquema).

Solo usa la librería estándar de Python.
"""
from __future__ import annotations

import datetime as _dt
import os
import socket
import ssl
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Suites AEAD con secreto hacia adelante (PFS). Se ordenan por preferencia del servidor.
DEFAULT_CIPHERS = "ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS"
# Aviso cuando al certificado le queden menos días que esto.
RENEW_WARNING_DAYS = 30

_VERSIONS = {
    "1.2": ssl.TLSVersion.TLSv1_2,
    "1.3": ssl.TLSVersion.TLSv1_3,
    "tlsv1.2": ssl.TLSVersion.TLSv1_2,
    "tlsv1.3": ssl.TLSVersion.TLSv1_3,
}


class TLSConfigError(RuntimeError):
    """Configuración de TLS incompleta o insegura."""


def parse_min_version(value: str | None) -> ssl.TLSVersion:
    """Convierte «1.2» / «1.3» en la constante de ssl. Cualquier otro valor → 1.2."""
    return _VERSIONS.get(str(value or "").strip().lower(), ssl.TLSVersion.TLSv1_2)


def build_context(certfile: str | os.PathLike, keyfile: str | os.PathLike,
                  minimum: str = "1.2", ciphers: str = DEFAULT_CIPHERS) -> ssl.SSLContext:
    """Contexto TLS de servidor endurecido.

    · TLS 1.2 como mínimo (1.3 si se pide); SSLv3/TLS 1.0/1.1 quedan fuera.
    · Solo cifrados con secreto hacia adelante y autenticados (AES-GCM / ChaCha20).
    · Sin compresión (CRIME), sin renegociación insegura y reutilización de DH/ECDH por sesión.
    · ALPN «http/1.1»: el navegador no negocia HTTP/2 con un servidor que no lo habla.
    """
    cert, key = Path(certfile), Path(keyfile)
    if not cert.is_file():
        raise TLSConfigError(f"No se encontró el certificado TLS: {cert}")
    if not key.is_file():
        raise TLSConfigError(f"No se encontró la clave privada TLS: {key}")

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = parse_min_version(minimum)
    context.options |= ssl.OP_NO_COMPRESSION
    context.options |= getattr(ssl, "OP_CIPHER_SERVER_PREFERENCE", 0)
    context.options |= getattr(ssl, "OP_SINGLE_DH_USE", 0)
    context.options |= getattr(ssl, "OP_SINGLE_ECDH_USE", 0)
    context.options |= getattr(ssl, "OP_NO_RENEGOTIATION", 0)
    if context.minimum_version < ssl.TLSVersion.TLSv1_3:
        context.set_ciphers(ciphers)          # los cifrados de TLS 1.3 ya son seguros y no se tocan
    try:
        context.set_alpn_protocols(["http/1.1"])
    except NotImplementedError:               # pragma: no cover - OpenSSL muy antiguo
        pass
    context.load_cert_chain(certfile=str(cert), keyfile=str(key))
    return context


def _oneline(value) -> str:
    """Aplana el subject/issuer que devuelve ssl (tuplas anidadas) a «CN=…»."""
    if isinstance(value, (list, tuple)):
        for rdn in value:
            for item in (rdn if isinstance(rdn, (list, tuple)) else [rdn]):
                if isinstance(item, (list, tuple)) and len(item) == 2 and item[0] == "commonName":
                    return str(item[1])
    return ""


def certificate_info(certfile: str | os.PathLike) -> dict:
    """Datos legibles del certificado PEM: nombres, emisor, caducidad y días restantes.

    Devuelve `{}` si el archivo no existe o no se puede interpretar (nunca lanza).
    """
    path = Path(certfile)
    if not path.is_file():
        return {}
    decode = getattr(ssl, "_ssl", None)
    decode = getattr(decode, "_test_decode_cert", None)
    if decode is None:                        # pragma: no cover - intérprete sin esta ayuda
        return {}
    try:
        raw = decode(str(path))
    except Exception:
        return {}
    hostnames = [v for k, v in raw.get("subjectAltName", ()) if k in ("DNS", "IP Address")]
    info = {
        "subject": _oneline(raw.get("subject")),
        "issuer": _oneline(raw.get("issuer")),
        "hostnames": hostnames,
        "serial": raw.get("serialNumber", ""),
    }
    not_after = raw.get("notAfter")
    if not_after:
        try:
            expires = _dt.datetime.fromtimestamp(ssl.cert_time_to_seconds(not_after), _dt.timezone.utc)
            info["expires_at"] = expires.isoformat()
            info["days_left"] = (expires - _dt.datetime.now(_dt.timezone.utc)).days
        except Exception:
            pass
    return info


def certificate_warning(certfile: str | os.PathLike, warn_days: int = RENEW_WARNING_DAYS) -> str:
    """Mensaje de aviso si el certificado caducó o está por caducar («» si todo va bien)."""
    info = certificate_info(certfile)
    days = info.get("days_left")
    if days is None:
        return ""
    if days < 0:
        return f"El certificado HTTPS caducó hace {abs(days)} día(s): renuévelo con .\\iniciar-https.ps1 -Renew"
    if days <= warn_days:
        return f"El certificado HTTPS caduca en {days} día(s): renuévelo con .\\iniciar-https.ps1 -Renew"
    return ""


def validate_config(certfile: str, keyfile: str, require_tls: bool = False) -> None:
    """Comprueba la coherencia de la configuración TLS antes de abrir el puerto."""
    if bool(certfile) != bool(keyfile):
        raise TLSConfigError("Configura IPV_TLS_CERT e IPV_TLS_KEY juntos para habilitar HTTPS.")
    if require_tls and not certfile:
        raise TLSConfigError(
            "IPV_REQUIRE_TLS=1 exige HTTPS: inicie con .\\iniciar-https.ps1 "
            "o defina IPV_TLS_CERT e IPV_TLS_KEY."
        )


class _RedirectHandler(BaseHTTPRequestHandler):
    """Responde 308 a https://<mismo host>:<puerto seguro><misma ruta>."""

    server_version = "IPV-HTTPS-Redirect/1.0"
    protocol_version = "HTTP/1.1"
    https_port = 8443

    def _redirect(self):
        host = (self.headers.get("Host") or "").split(":")[0].strip() or "localhost"
        if ":" in host:                                   # IPv6 literal
            host = f"[{host}]"
        target = f"https://{host}:{self.https_port}{self.path}"
        body = (
            "<!doctype html><meta charset=\"utf-8\">"
            f"<title>Use HTTPS</title><p>Este servidor solo atiende cifrado: "
            f"<a href=\"{target}\">{target}</a>"
        ).encode("utf-8")
        self.close_connection = True                      # no se lee el cuerpo: se cierra la conexión
        self.send_response(308)
        self.send_header("Location", target)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    do_GET = do_HEAD = do_POST = do_PUT = do_DELETE = do_OPTIONS = do_PATCH = _redirect

    def log_message(self, *_args):                        # silencio: el log útil es el del servidor real
        return


def start_redirector(http_port: int, https_port: int, host: str = "0.0.0.0") -> ThreadingHTTPServer | None:  # nosec B104
    """Levanta en segundo plano el redirector HTTP → HTTPS. Devuelve None si no se pudo."""
    if not http_port or http_port == https_port:
        return None
    handler = type("IPVRedirectHandler", (_RedirectHandler,), {"https_port": https_port})
    try:
        httpd = ThreadingHTTPServer((host, http_port), handler)
    except OSError:
        return None
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, name="ipv-https-redirect", daemon=True).start()
    return httpd


def local_addresses() -> list[str]:
    """Direcciones IPv4 útiles de este equipo (para imprimir las URL de acceso)."""
    found = {"127.0.0.1"}
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.add(info[4][0])
    except OSError:
        pass
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("192.0.2.1", 9))               # red de documentación: no envía tráfico real
            found.add(probe.getsockname()[0])
        finally:
            probe.close()
    except OSError:
        pass
    return sorted(found)
