"""
IPV Fichas y Costos - Seguridad avanzada (solo librería estándar).
Autor: Ing. Yosvany Hernández Quintero

- TOTP (RFC 6238) compatible con Google Authenticator, Microsoft Authenticator, Aegis, etc.
- Códigos de recuperación de un solo uso (hash SHA-256).
- Lista de IPs/redes permitidas (IPV_IP_ALLOWLIST).
- Resolución segura de la IP del cliente (X-Forwarded-For solo desde proxies de confianza).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import os
import secrets
import struct
import time
from urllib.parse import quote

ISSUER = "IPV Fichas y Costos"
TOTP_PERIOD = 30
TOTP_DIGITS = 6


# ---------------------------------------------------------------------------
#  TOTP
# ---------------------------------------------------------------------------
def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _hotp(secret: str, counter: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** TOTP_DIGITS)
    return str(code).zfill(TOTP_DIGITS)


def totp_now(secret: str, at: float | None = None) -> str:
    return _hotp(secret, int((at or time.time()) // TOTP_PERIOD))


def verify_totp(secret: str, code: str, last_step: int = -1, window: int = 1) -> int:
    """Devuelve el paso temporal usado (>0) si el código es válido, o -1.
    Rechaza reutilizar un código ya aceptado (protección anti-replay)."""
    code = "".join(ch for ch in str(code) if ch.isdigit())
    if len(code) != TOTP_DIGITS or not secret:
        return -1
    step = int(time.time() // TOTP_PERIOD)
    for delta in range(-window, window + 1):
        candidate = step + delta
        if candidate > last_step and hmac.compare_digest(_hotp(secret, candidate), code):
            return candidate
    return -1


def otpauth_uri(secret: str, account: str) -> str:
    label = quote(f"{ISSUER}:{account}")
    return (f"otpauth://totp/{label}?secret={secret}&issuer={quote(ISSUER)}"
            f"&algorithm=SHA1&digits={TOTP_DIGITS}&period={TOTP_PERIOD}")


def new_recovery_codes(n: int = 8) -> list[str]:
    return [f"{secrets.token_hex(3)}-{secrets.token_hex(3)}".upper() for _ in range(n)]


def hash_code(code: str) -> str:
    return hashlib.sha256(code.strip().upper().encode()).hexdigest()


# ---------------------------------------------------------------------------
#  Red: IP del cliente y lista de permitidas
# ---------------------------------------------------------------------------
def _parse_networks(raw: str):
    nets = []
    for item in raw.split(","):
        item = item.strip()
        if item:
            try:
                nets.append(ipaddress.ip_network(item, strict=False))
            except ValueError:
                print(f"⚠ Red no válida ignorada: {item}")
    return nets


ALLOWLIST = _parse_networks(os.environ.get("IPV_IP_ALLOWLIST", ""))
TRUSTED_PROXIES = _parse_networks(os.environ.get("IPV_TRUSTED_PROXIES", ""))


def _in(ip: str, nets) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if addr.version == 6 and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return any(addr in n for n in nets)


def resolve_client_ip(peer: str, forwarded: str) -> str:
    """Solo se acepta X-Forwarded-For si la conexión llega desde un proxy de confianza."""
    if forwarded and TRUSTED_PROXIES and _in(peer, TRUSTED_PROXIES):
        hops = [h.strip() for h in forwarded.split(",") if h.strip()]
        # Recorre de derecha a izquierda descartando proxies de confianza
        for hop in reversed(hops):
            if not _in(hop, TRUSTED_PROXIES):
                try:
                    ipaddress.ip_address(hop)
                    return hop
                except ValueError:
                    break
    return peer


def ip_allowed(ip: str) -> bool:
    if not ALLOWLIST:
        return True
    return ip in ("127.0.0.1", "::1") or _in(ip, ALLOWLIST)
