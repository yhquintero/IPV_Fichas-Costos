"""Licencias por período para IPV Fichas de Costo (servidor web / PC).

Modelo
------
* El equipo genera un **código de solicitud** a partir de su identificador de hardware
  (Windows: MachineGuid; Linux: /etc/machine-id). El identificador NUNCA sale del equipo:
  se transforma con SHA-256 + sal de la aplicación y se muestra en grupos legibles
  con dígitos de control:  IPVW-ABCDE-FGHIJ-KLMNO-PQRST-XY
* El cliente envía ese código por WhatsApp. El emisor lo introduce en el Keygen
  (keygen/keygen.py) junto con Usuario y Plan, y obtiene una **licencia firmada**
  con ECDSA P-256 (clave privada solo en poder del emisor).
* La aplicación verifica la firma con la clave pública incrustada, que el ID del
  dispositivo coincide y que la fecha está dentro del período. Una licencia copiada
  a otro equipo no sirve; modificar el usuario/plan/fecha invalida la firma.
* Protección contra retroceso del reloj: se guarda la fecha más alta vista.

Implementación ECDSA P-256 en Python puro (sin dependencias), compatible con
`SHA256withECDSA` de Java/Android (firma DER).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import secrets
import threading
import time
import uuid
from pathlib import Path

# Estos dos valores los escribe `python keygen/keygen.py init`. Vacío = licencias desactivadas (modo desarrollo).
PUBLIC_KEY_HEX = ""
WHATSAPP_NUMBER = ""

APP_WEB = "W"
APP_ANDROID = "A"
APP_NAMES = {APP_WEB: "IPV Web (servidor/PC)", APP_ANDROID: "IPV Android (móvil)"}
DAY = 86400
ROLLBACK_TOLERANCE = DAY

# Plan -> (nombre, días, precio USD Web, precio USD Android). Ver docs/precios-y-licencias.md
PLANS = {
    "1S": ("1 Semana", 7, 6, 3),
    "1M": ("1 Mes", 30, 18, 8),
    "3M": ("3 Meses", 90, 48, 21),
    "6M": ("6 Meses", 180, 90, 39),
    "1A": ("1 Año", 365, 160, 70),
    "2A": ("2 Años", 730, 280, 120),
}

_B32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"

# ---------------------------------------------------------------- P-256 --------
P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
A = P - 3
B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
G = (0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
     0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5)


def _on_curve(pt) -> bool:
    x, y = pt
    return 0 <= x < P and 0 <= y < P and (y * y - (x * x * x + A * x + B)) % P == 0


# Coordenadas jacobianas (sin inversiones en cada paso)
def _jdouble(pt):
    x, y, z = pt
    if y == 0 or z == 0:
        return (0, 1, 0)
    ysq = y * y % P
    s = 4 * x * ysq % P
    m = (3 * x * x + A * pow(z, 4, P)) % P
    nx = (m * m - 2 * s) % P
    ny = (m * (s - nx) - 8 * ysq * ysq) % P
    return (nx, ny, 2 * y * z % P)


def _jadd(p1, p2):
    if p1[2] == 0:
        return p2
    if p2[2] == 0:
        return p1
    x1, y1, z1 = p1
    x2, y2, z2 = p2
    z1s, z2s = z1 * z1 % P, z2 * z2 % P
    u1, u2 = x1 * z2s % P, x2 * z1s % P
    s1, s2 = y1 * z2s * z2 % P, y2 * z1s * z1 % P
    if u1 == u2:
        return _jdouble(p1) if s1 == s2 else (0, 1, 0)
    h, r = (u2 - u1) % P, (s2 - s1) % P
    h2 = h * h % P
    h3 = h * h2 % P
    u1h2 = u1 * h2 % P
    nx = (r * r - h3 - 2 * u1h2) % P
    ny = (r * (u1h2 - nx) - s1 * h3) % P
    return (nx, ny, h * z1 * z2 % P)


def _to_affine(pt):
    if pt[2] == 0:
        return None
    zi = pow(pt[2], -1, P)
    return (pt[0] * zi * zi % P, pt[1] * zi * zi * zi % P)


def _mul(k: int, pt):
    result, addend = (0, 1, 0), (pt[0], pt[1], 1)
    while k:
        if k & 1:
            result = _jadd(result, addend)
        addend = _jdouble(addend)
        k >>= 1
    return result


def _hash_int(msg: bytes) -> int:
    return int.from_bytes(hashlib.sha256(msg).digest(), "big")


def generate_keypair() -> tuple[int, str]:
    """Devuelve (clave privada d, clave pública hex X||Y de 128 caracteres)."""
    d = secrets.randbelow(N - 1) + 1
    x, y = _to_affine(_mul(d, G))
    return d, f"{x:064x}{y:064x}"


def public_from_private(d: int) -> str:
    x, y = _to_affine(_mul(d, G))
    return f"{x:064x}{y:064x}"


def _der_int(v: int) -> bytes:
    raw = v.to_bytes((v.bit_length() + 8) // 8 or 1, "big")  # bit extra: evita que se lea como negativo
    return b"\x02" + bytes([len(raw)]) + raw


def sign(d: int, msg: bytes) -> bytes:
    """Firma ECDSA-SHA256 en formato DER (lo que espera java.security.Signature)."""
    z = _hash_int(msg)
    while True:
        k = secrets.randbelow(N - 1) + 1
        r = _to_affine(_mul(k, G))[0] % N
        if r == 0:
            continue
        s = pow(k, -1, N) * (z + r * d) % N
        if s == 0:
            continue
        s = min(s, N - s)  # forma canónica "low-S"
        body = _der_int(r) + _der_int(s)
        return b"\x30" + bytes([len(body)]) + body


def _parse_der(sig: bytes) -> tuple[int, int]:
    if len(sig) < 8 or sig[0] != 0x30 or sig[1] != len(sig) - 2:
        raise ValueError("firma mal formada")
    out, i = [], 2
    for _ in range(2):
        if sig[i] != 0x02:
            raise ValueError("firma mal formada")
        ln = sig[i + 1]
        if ln == 0 or ln > 33:
            raise ValueError("firma mal formada")
        out.append(int.from_bytes(sig[i + 2:i + 2 + ln], "big"))
        i += 2 + ln
    if i != len(sig):
        raise ValueError("firma mal formada")
    return out[0], out[1]


def verify(pub_hex: str, msg: bytes, sig: bytes) -> bool:
    try:
        q = (int(pub_hex[:64], 16), int(pub_hex[64:128], 16))
        if len(pub_hex) != 128 or not _on_curve(q):
            return False
        r, s = _parse_der(sig)
    except (ValueError, IndexError):
        return False
    if not (1 <= r < N and 1 <= s < N):
        return False
    w = pow(s, -1, N)
    z = _hash_int(msg)
    pt = _to_affine(_jadd(_mul(z * w % N, G), _mul(r * w % N, (q[0], q[1]))))
    return pt is not None and pt[0] % N == r


def spki_der_b64(pub_hex: str) -> str:
    """Clave pública en formato X.509 SubjectPublicKeyInfo (para Android KeyFactory)."""
    prefix = bytes.fromhex("3059301306072a8648ce3d020106082a8648ce3d030107034200")
    return base64.b64encode(prefix + b"\x04" + bytes.fromhex(pub_hex)).decode()


# ---------------------------------------------------------- Códigos -----------
def _b32(data: bytes) -> str:
    return base64.b32encode(data).decode().rstrip("=")


def _check(body: str) -> str:
    return _b32(hashlib.sha256(("IPV-CHK|" + body).encode()).digest())[:2]


def request_code(app: str, raw_id: str) -> str:
    """ID de hardware -> código de solicitud irreversible (SHA-256 con sal de la app)."""
    body = _b32(hashlib.sha256(f"IPV-LIC-v1|{app}|{raw_id.strip().lower()}".encode()).digest())[:20]
    groups = "-".join(body[i:i + 5] for i in range(0, 20, 5))
    return f"IPV{app}-{groups}-{_check(body)}"


def parse_request_code(code: str) -> tuple[str, str]:
    """Valida el formato y los dígitos de control. Devuelve (app, cuerpo de 20 caracteres)."""
    clean = "".join(ch for ch in code.upper() if ch.isalnum())
    if len(clean) != 26 or not clean.startswith("IPV") or clean[3] not in APP_NAMES:
        raise ValueError("El código de solicitud no tiene el formato IPVW-XXXXX-XXXXX-XXXXX-XXXXX-XX.")
    body, chk = clean[4:24], clean[24:]
    if any(ch not in _B32 for ch in body) or _check(body) != chk:
        raise ValueError("El código de solicitud tiene un error de transcripción (dígitos de control).")
    return clean[3], body


def machine_id() -> str:
    """Identificador estable del equipo (no cambia al reinstalar la aplicación)."""
    if platform.system() == "Windows":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography",
                                0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
                return str(winreg.QueryValueEx(key, "MachineGuid")[0])
        except OSError:
            pass
    for candidate in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            value = Path(candidate).read_text(encoding="ascii").strip()
            if value:
                return value
        except OSError:
            continue
    return f"mac-{uuid.getnode():012x}"


# ---------------------------------------------------------- Licencias ---------
def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64u(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def issue(d: int, user: str, code: str, plan: str, now: float | None = None) -> str:
    """Emite una licencia firmada (lo usa el Keygen)."""
    app, body = parse_request_code(code)
    if plan not in PLANS:
        raise ValueError(f"Plan desconocido: {plan}. Opciones: {', '.join(PLANS)}")
    user = " ".join(user.split())[:80]
    if not user:
        raise ValueError("Indique el nombre del usuario/cliente.")
    iat = int(now if now is not None else time.time())
    payload = {"v": 1, "app": app, "dev": body, "usr": user, "plan": plan,
               "iat": iat, "exp": iat + PLANS[plan][1] * DAY, "sn": secrets.token_hex(4).upper()}
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    return f"IPV1.{_b64u(raw)}.{_b64u(sign(d, raw))}"


def decode(token: str, pub_hex: str) -> dict:
    """Comprueba la firma y devuelve el contenido (sin validar dispositivo ni fechas)."""
    token = "".join(token.split())
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != "IPV1":
        raise ValueError("La licencia no tiene un formato válido.")
    try:
        raw, sig = _unb64u(parts[1]), _unb64u(parts[2])
    except ValueError as exc:
        raise ValueError("La licencia está incompleta o dañada.") from exc
    if not verify(pub_hex, raw, sig):
        raise ValueError("Firma no válida: la licencia fue alterada o no la emitió el proveedor.")
    data = json.loads(raw)
    if data.get("v") != 1 or data.get("plan") not in PLANS:
        raise ValueError("Versión de licencia no admitida.")
    return data


def check(token: str, pub_hex: str, app: str, device_body: str, now: float, last_seen: float = 0) -> dict:
    data = decode(token, pub_hex)
    if data["app"] != app:
        raise ValueError(f"Esta licencia es para {APP_NAMES.get(data['app'], data['app'])}.")
    if data["dev"] != device_body:
        raise ValueError("Esta licencia pertenece a otro dispositivo.")
    if now + ROLLBACK_TOLERANCE < max(data["iat"], last_seen):
        raise ValueError("La fecha del equipo es anterior a la última registrada. Corrija la fecha y la hora.")
    if now >= data["exp"]:
        raise ValueError(f"La licencia venció el {time.strftime('%d/%m/%Y', time.localtime(data['exp']))}.")
    return data


def public_info(data: dict, now: float) -> dict:
    return {"user": data["usr"], "plan": data["plan"], "plan_name": PLANS[data["plan"]][0],
            "serial": data["sn"], "issued_at": data["iat"], "expires_at": data["exp"],
            "days_left": max(0, int((data["exp"] - now) // DAY))}


class LicenseStore:
    """Licencia del servidor: data/licencia.lic + data/licencia.state (fecha máxima vista)."""

    def __init__(self, data_dir: Path, pub_hex: str | None = None, raw_id: str | None = None):
        self.dir = Path(data_dir)
        # La clave pública solo viene del código: aceptarla por variable de entorno permitiría al
        # cliente sustituirla por una propia y fabricarse licencias.
        self.pub = (pub_hex if pub_hex is not None else PUBLIC_KEY_HEX).strip().lower()
        self.code = request_code(APP_WEB, raw_id if raw_id is not None else machine_id())
        self.body = parse_request_code(self.code)[1]
        self.lock = threading.Lock()
        self._cache: tuple[float, dict] | None = None

    @property
    def enforced(self) -> bool:
        return bool(self.pub)

    def _read(self, name: str) -> str:
        try:
            return (self.dir / name).read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def _write(self, name: str, text: str) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.dir / f"{name}.tmp"
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(self.dir / name)

    def _last_seen(self) -> float:
        try:
            return float(json.loads(self._read("licencia.state") or "{}").get("last_seen", 0))
        except (ValueError, TypeError, AttributeError):
            return 0.0

    def status(self, now: float | None = None, use_cache: bool = True) -> dict:
        now = time.time() if now is None else now
        base = {"enforced": self.enforced, "request_code": self.code,
                "whatsapp": os.environ.get("IPV_LICENSE_WHATSAPP", WHATSAPP_NUMBER).strip(),
                "plans": {k: {"name": v[0], "days": v[1], "usd": v[2]} for k, v in PLANS.items()}}
        if not self.enforced:
            return {**base, "valid": True, "reason": "Licencias desactivadas (sin clave pública configurada)."}
        with self.lock:
            if use_cache and self._cache and now - self._cache[0] < 60:
                return {**base, **self._cache[1]}
            token = self._read("licencia.lic")
            last = self._last_seen()
            try:
                if not token:
                    raise ValueError("Este equipo no tiene licencia activada.")
                data = check(token, self.pub, APP_WEB, self.body, now, last)
                result = {"valid": True, "reason": "", **public_info(data, now)}
                if now > last + 600:
                    self._write("licencia.state", json.dumps({"last_seen": int(now)}))
            except ValueError as exc:
                result = {"valid": False, "reason": str(exc)}
            self._cache = (now, result)
            return {**base, **result}

    def activate(self, token: str, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        token = "".join(str(token).split())
        with self.lock:
            data = check(token, self.pub, APP_WEB, self.body, now, self._last_seen())  # ValueError si no vale
            self._write("licencia.lic", token)
            self._write("licencia.state", json.dumps({"last_seen": int(max(now, self._last_seen()))}))
            self._cache = None
        return public_info(data, now)


# ------------------------------------------------- Integración con server.py ---
LICENSE_FREE = ("/api/health", "/api/version", "/api/openapi.yaml", "/api/license")


def install(srv) -> LicenseStore:
    """Exige licencia válida para toda la API salvo salud/versión y la propia activación."""
    store = LicenseStore(Path(srv.DB_PATH).parent)
    srv.LICENSE = store
    handler = srv.Handler
    if not store.enforced:
        print("[LICENCIA] Sin clave pública: licencias desactivadas (ejecute keygen/keygen.py init).")
    original_pre = handler._pre_check
    original_get, original_post = handler.do_GET, handler.do_POST

    def _pre_check(self) -> bool:
        if not original_pre(self):
            return False
        path = self._api_path()
        if store.enforced and path.startswith("/api") and not path.startswith(LICENSE_FREE):
            st = store.status()
            if not st["valid"]:
                self.send_json({"error": f"Licencia requerida: {st['reason']}", "license_required": True,
                                "request_code": st["request_code"], "whatsapp": st["whatsapp"]}, 402)
                return False
        return True

    def _license_pre(self) -> bool:
        """Lista de IP y límite de peticiones, sin exigir sesión (el cliente aún no puede iniciarla)."""
        saved = self._check_auth
        self._check_auth = lambda: setattr(self, "user", None)
        try:
            return original_pre(self)
        finally:
            self._check_auth = saved

    def do_GET(self):
        self._normalize_version()
        if self._api_path() != "/api/license":
            return original_get(self)
        if _license_pre(self):
            self.send_json(store.status())

    def do_POST(self):
        self._normalize_version()
        if self._api_path() != "/api/license":
            return original_post(self)
        try:
            data = self.body_json()
        except srv.APIError as exc:
            return self.send_json({"error": exc.message}, exc.status)
        if not _license_pre(self):
            return None
        if not store.enforced:
            return self.send_json({"error": "Las licencias no están activadas en este servidor."}, 409)
        # Con licencia vigente, solo un administrador puede sustituirla (renovación)
        if store.status(use_cache=False)["valid"]:
            try:
                self._check_auth()
                if (self.user or {}).get("role") != "admin":
                    raise srv.APIError("Solo un administrador puede renovar la licencia.", 403)
            except srv.APIError as exc:
                return self.send_json({"error": exc.message}, exc.status)
        ip = self.client_ip()
        try:
            info = store.activate(str(data.get("license", ""))[:4000])
        except ValueError as exc:
            srv.audit_log("LICENSE_REJECTED", str(exc)[:200], ip)
            return self.send_json({"error": str(exc)}, 400)
        srv.audit_log("LICENSE_ACTIVATED", f"usuario={info['user']} plan={info['plan']} serie={info['serial']}", ip)
        return self.send_json({"ok": True, **store.status(use_cache=False)})

    handler._pre_check = _pre_check
    handler.do_GET = do_GET
    handler.do_POST = do_POST
    return store
