"""IPV Keygen Web — emisión visual de licencias e historial completo (solo librería estándar).

Se ejecuta en el equipo del proveedor, NUNCA en el del cliente:

    python keygen/keygen.py            # abre http://127.0.0.1:8500 en el navegador
    python keygen_web.py --port 8600   # lo mismo, eligiendo dirección y puerto

Qué ofrece
  * Entrada con USUARIO + contraseña + verificación en dos pasos (TOTP, opcional u obligatoria
    con KEYGEN_REQUIRE_MFA=1), sesiones por dispositivo y bloqueo tras 5 intentos fallidos:
    el mismo sistema de acceso que la app IPV (auth.py).
  * Roles como en «inventario»: ADMINISTRADOR, JEFE, ECONOMICO y ALMACENERO (roles.py),
    cada uno con sus capacidades sobre las licencias.
  * Emisión de licencias para IPV Web (IPVW-…) e IPV Android (IPVA-…) y el historial completo
    en SQLite (keygen/licencias.db): búsqueda, filtros, anulación, renovación, pagos, notas,
    línea de tiempo por licencia, panel con estadísticas y exportación a CSV.
  * La clave privada de firma nunca se guarda en claro: está cifrada en keygen/clave_privada.json
    y solo se descifra en memoria al «desbloquearla» con su contraseña; se vuelve a bloquear
    sola tras unos minutos sin uso (KEYGEN_UNLOCK_MINUTES, 15 por defecto).
  * Auditoría encadenada (audit.py) de todo lo que ocurre: accesos, emisiones, anulaciones…

Seguridad: escucha solo en 127.0.0.1 salvo que se indique otra dirección; valida la cabecera Host
y el Origin (contra DNS rebinding y CSRF); exige Content-Type JSON; CSP estricta; límites de
peticiones por IP; tokens en sessionStorage (no en cookies).

Variables de entorno (todas opcionales)
  KEYGEN_ADMIN_USER / KEYGEN_ADMIN_PASSWORD   crean el primer administrador sin pasar por la web
  KEYGEN_REQUIRE_MFA=1     exige 2FA a todos los usuarios para poder trabajar
  KEYGEN_UNLOCK_MINUTES    minutos que permanece desbloqueada la clave de firma (1–120)
  KEYGEN_JWT_SECRET        secreto de las sesiones (si no, se genera en keygen/web_secret.key)
  KEYGEN_ALLOWED_HOSTS     nombres de host adicionales aceptados (separados por comas)
  KEYGEN_TLS_CERT / KEYGEN_TLS_KEY   sirven el panel por HTTPS
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import secrets
import sys
import tempfile
import threading
import time
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import audit  # noqa: E402
import auth  # noqa: E402
import creador_licencias as C  # noqa: E402
import licencia as L  # noqa: E402
import rate_limiter  # noqa: E402
import roles  # noqa: E402
import security  # noqa: E402
import tls_seguro  # noqa: E402
from keygen import historial as H  # noqa: E402
from keygen import keygen as kg  # noqa: E402

APP_NAME = "IPV Keygen"
VERSION = "1.0.0"
DEFAULT_PORT = 8500
MAX_BODY = 2_000_000
STATIC_DIR = HERE / "web"
SECRET_FILE = HERE / "web_secret.key"
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
    "/qr.js": (None, "text/javascript; charset=utf-8"),   # mismo generador QR de la app IPV (web/qr.js)
}
# Con la contraseña caducada solo se puede cambiarla o salir; con 2FA obligatoria, solo activarla.
PASSWORD_EXPIRED_ALLOWED = ("/api/auth/password", "/api/auth/me", "/api/auth/logout", "/api/auth/sessions", "/api/status")
MFA_SETUP_ALLOWED = ("/api/auth/2fa/setup", "/api/auth/2fa/enable", "/api/auth/me", "/api/auth/logout",
                     "/api/auth/password", "/api/auth/sessions", "/api/status")
CSP = ("default-src 'self'; script-src 'self'; script-src-attr 'none'; style-src 'self'; style-src-elem 'self'; "
       "style-src-attr 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; "
       "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400, **extra):
        super().__init__(message)
        self.message, self.status, self.extra = message, status, extra


class Raw:
    """Respuesta binaria (descargas: CSV, copia de seguridad)."""

    def __init__(self, body: bytes, content_type: str, filename: str = ""):
        self.body, self.content_type, self.filename = body, content_type, filename


# ---------------------------------------------------------------------------
#  Bóveda de la clave de firma: descifrada solo en memoria y con caducidad
# ---------------------------------------------------------------------------
class KeyVault:
    MAX_FAILS, LOCKOUT = 5, 600

    def __init__(self, minutes: int = 15):
        self.ttl = max(1, min(int(minutes), 120)) * 60
        self._d: int | None = None
        self._until = 0.0
        self._by = ""
        self._fails: list[float] = []
        self._lock = threading.Lock()

    def unlock(self, passphrase: str, actor: str) -> dict:
        with self._lock:
            now = time.time()
            self._fails = [t for t in self._fails if now - t < self.LOCKOUT]
            if len(self._fails) >= self.MAX_FAILS:
                wait = int(self.LOCKOUT - (now - self._fails[0])) + 1
                raise ApiError(f"Demasiados intentos con la contraseña de la clave. Espere {wait} s.", 429)
            try:
                d = kg.load_private_key(str(passphrase or ""), kg.KEY_FILE)
            except SystemExit as exc:
                raise ApiError("Aún no existe la clave de firma: créela primero en «Clave de firma».", 400) from exc
            except (ValueError, KeyError, OSError) as exc:
                self._fails.append(now)
                raise ApiError("Contraseña de la clave de firma incorrecta.", 400) from exc
            self._fails.clear()
            self._d, self._until, self._by = d, time.time() + self.ttl, actor
        return self.status()

    def lock(self) -> None:
        with self._lock:
            self._d, self._until, self._by = None, 0.0, ""

    def key(self) -> int:
        """Clave privada para firmar; cada uso renueva el plazo de desbloqueo."""
        with self._lock:
            if self._d is None or time.time() > self._until:
                self._d, self._until = None, 0.0
                raise ApiError("La clave de firma está bloqueada: desbloquéela con su contraseña.", 423)
            self._until = time.time() + self.ttl
            return self._d

    def status(self) -> dict:
        with self._lock:
            live = self._d is not None and time.time() <= self._until
            return {"unlocked": live, "seconds_left": max(0, int(self._until - time.time())) if live else 0,
                    "unlocked_by": self._by if live else ""}


# ---------------------------------------------------------------------------
#  Estado de la aplicación
# ---------------------------------------------------------------------------
def _loopback(host: str) -> bool:
    return host in ("127.0.0.1", "::1", "localhost")


class KeygenApp:
    def __init__(self, db_path=None, secret_file=None, host: str = "127.0.0.1"):
        self.db_path = Path(db_path) if db_path else H.DB_FILE
        self.secret_file = Path(secret_file) if secret_file else SECRET_FILE
        self.host = host
        self.require_mfa = os.environ.get("KEYGEN_REQUIRE_MFA", "0").strip().lower() in ("1", "true", "si", "sí")
        try:
            minutes = int(os.environ.get("KEYGEN_UNLOCK_MINUTES", "15") or 15)
        except ValueError:
            minutes = 15
        self.vault = KeyVault(minutes)
        self.extra_hosts = {h.strip().lower() for h in os.environ.get("KEYGEN_ALLOWED_HOSTS", "").split(",") if h.strip()}
        self.setup_token = ""
        self.secret = ""

    # -- secretos y módulos compartidos ---------------------------------------------------
    def load_secret(self) -> str:
        env = os.environ.get("KEYGEN_JWT_SECRET", "").strip()
        if env:
            if len(env.encode()) < 32:
                raise SystemExit("KEYGEN_JWT_SECRET debe tener al menos 32 bytes.")
            return env
        try:
            value = self.secret_file.read_text(encoding="utf-8").strip()
            if len(value.encode()) >= 32:
                return value
        except OSError:
            pass
        value = secrets.token_urlsafe(48)
        self.secret_file.parent.mkdir(parents=True, exist_ok=True)
        self.secret_file.write_text(value, encoding="utf-8")
        try:
            os.chmod(self.secret_file, 0o600)
        except OSError:
            pass
        return value

    def apply_globals(self) -> None:
        """Las sesiones y la auditoría de este panel usan su propio secreto (nunca el de la app IPV)."""
        self.secret = self.load_secret()
        auth.JWT_SECRET, auth.JWT_ENABLED = self.secret, True
        audit._KEY = self.secret.encode()
        security.ISSUER = APP_NAME

    def connect(self):
        return H.connect(self.db_path)

    def init_db(self) -> None:
        conn = self.connect()
        try:
            with H.LOCK, conn:
                auth.init_auth(conn, H.now_iso,
                               admin_user=os.environ.get("KEYGEN_ADMIN_USER", ""),
                               admin_email="",
                               admin_password=os.environ.get("KEYGEN_ADMIN_PASSWORD", ""))
                H.init(conn)
                kg.import_legacy(conn)  # primera vez: incorpora el registro_licencias.csv antiguo
                users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        finally:
            conn.close()
        audit.init_audit(self.db_path)
        self.setup_token = secrets.token_urlsafe(9) if users == 0 and not _loopback(self.host) else ""

    # -- cabecera Host (contra DNS rebinding) ---------------------------------------------
    def host_allowed(self, header: str) -> bool:
        name = (header or "").strip().lower()
        if name.startswith("["):
            name = name[1:name.find("]")] if "]" in name else name
        else:
            name = name.rsplit(":", 1)[0] if name.count(":") == 1 else name
        if name in ("localhost", "127.0.0.1", "::1") or name in self.extra_hosts:
            return True
        try:
            ipaddress.ip_address(name)
            return True  # una IP literal no se puede falsificar con DNS
        except ValueError:
            return False


# ---------------------------------------------------------------------------
#  Enrutador
# ---------------------------------------------------------------------------
ROUTES: list[tuple] = []


def route(method: str, pattern: str, cap=None, public: bool = False):
    caps = (cap,) if isinstance(cap, str) else tuple(cap or ())

    def deco(fn):
        ROUTES.append((method, re.compile(f"^{pattern}$"), fn, public, caps))
        return fn
    return deco


class Ctx:
    def __init__(self, handler, app, match, query, body, user, conn):
        self.handler, self.app, self.match, self.query, self.body = handler, app, match, query, body
        self.user, self.conn = user, conn
        self.ip = handler.client_ip()
        self.ua = handler.headers.get("User-Agent", "")[:300]

    @property
    def caps(self) -> set:
        return set((self.user or {}).get("caps", ()))

    def can(self, cap: str) -> bool:
        return cap in self.caps

    def audit(self, action: str, details: str = "") -> None:
        audit.set_current_user((self.user or {}).get("username", ""))
        audit.record(H.now_iso(), action, details, self.ip)

    def arg(self, name: str, default: str = "") -> str:
        return (self.query.get(name) or [default])[0]

    def scope(self):
        """None = todo el historial; usuario = solo lo que él emitió (rol operador)."""
        return None if self.can("history_all") else (self.user or {}).get("username", "")


def _session(result: dict) -> dict:
    user = result.get("user", {})
    return {**result, "caps": sorted(roles.keygen_caps(user.get("role", "")))}


def _opt(value):
    value = None if value is None else str(value).strip()
    return value or None


# ------------------------------------------------------------------ público -------
@route("GET", r"/api/bootstrap", public=True)
def bootstrap(ctx):
    users = ctx.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    return 200, {"app": APP_NAME, "version": VERSION, "needs_setup": users == 0,
                 "setup_token_required": bool(ctx.app.setup_token), "require_mfa": ctx.app.require_mfa}


@route("POST", r"/api/setup", public=True)
def setup(ctx):
    """Primer arranque: crea al administrador. Solo funciona mientras no exista ningún usuario."""
    with H.LOCK:
        if ctx.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            raise ApiError("El sistema ya está configurado: inicie sesión.", 409)
        if ctx.app.setup_token and not secrets.compare_digest(str(ctx.body.get("token", "")), ctx.app.setup_token):
            raise ApiError("Código de instalación incorrecto (aparece en la consola donde inició el Keygen).", 403)
        data = {"username": ctx.body.get("username", ""), "name": ctx.body.get("name", ""),
                "password": ctx.body.get("password", ""), "role": roles.ADMINISTRADOR}
        created = auth.create_user(ctx.conn, data, H.now_iso, roles.ADMINISTRADOR)
    ctx.app.setup_token = ""
    audit.set_current_user(created["username"])
    ctx.audit("SETUP_ADMIN", f"user={created['username']}")
    return 201, {"ok": True, "username": created["username"]}


@route("POST", r"/api/auth/login", public=True)
def login(ctx):
    ident = str(ctx.body.get("username") or ctx.body.get("email") or "")[:120]
    try:
        result = auth.login(ctx.conn, ident, str(ctx.body.get("password", "")), H.now_iso,
                            str(ctx.body.get("otp", ""))[:20], ctx.ip, ctx.ua)
    except auth.MFARequired:
        ctx.conn.commit()
        raise
    except auth.AuthError as exc:
        ctx.conn.commit()  # conserva el contador de intentos fallidos
        ctx.audit("LOGIN_FAILED", f"user={ident}")
        if isinstance(exc, auth.LoginFailed) and exc.locked:
            ctx.audit("ACCOUNT_LOCKED", f"user={exc.username} intentos={exc.attempts}")
        raise
    audit.set_current_user(result["user"]["username"])
    ctx.audit("LOGIN", f"user={result['user']['username']} device={auth.device_label(ctx.ua)}")
    if result.get("new_ip"):
        ctx.audit("LOGIN_NEW_IP", f"user={result['user']['username']}")
    return 200, _session(result)


@route("POST", r"/api/auth/refresh", public=True)
def refresh(ctx):
    return 200, _session(auth.refresh(ctx.conn, str(ctx.body.get("refresh_token", "")), ctx.ip))


@route("POST", r"/api/auth/logout", public=True)
def logout(ctx):
    auth.revoke(ctx.conn, str(ctx.body.get("refresh_token", "")))
    return 200, {"ok": True}


# ------------------------------------------------------------------ mi cuenta -----
@route("GET", r"/api/auth/me")
def me(ctx):
    return 200, {"user": ctx.user, "caps": sorted(ctx.caps), "roles": roles.keygen_catalog(),
                 "require_mfa": ctx.app.require_mfa}


@route("POST", r"/api/auth/password")
def change_password(ctx):
    result = auth.change_password(ctx.conn, ctx.user["id"], str(ctx.body.get("current", "")),
                                  str(ctx.body.get("new", "")), H.now_iso, ctx.user.get("sid", ""))
    ctx.audit("PASSWORD_CHANGED", f"user={ctx.user['username']}")
    return 200, _session(result)


@route("POST", r"/api/auth/2fa/setup")
def mfa_setup(ctx):
    return 200, auth.mfa_setup(ctx.conn, ctx.user["id"])


@route("POST", r"/api/auth/2fa/enable")
def mfa_enable(ctx):
    result = auth.mfa_enable(ctx.conn, ctx.user["id"], str(ctx.body.get("code", "")))
    ctx.audit("MFA_ENABLED", f"user={ctx.user['username']}")
    return 200, result


@route("POST", r"/api/auth/2fa/disable")
def mfa_disable(ctx):
    if ctx.app.require_mfa:
        raise ApiError("La verificación en dos pasos es obligatoria en este Keygen.", 403)
    result = auth.mfa_disable(ctx.conn, ctx.user["id"], str(ctx.body.get("password", "")), str(ctx.body.get("code", "")))
    ctx.audit("MFA_DISABLED", f"user={ctx.user['username']}")
    return 200, result


@route("GET", r"/api/auth/sessions")
def sessions(ctx):
    return 200, auth.list_sessions(ctx.conn, ctx.user["id"], ctx.user.get("sid", ""))


@route("POST", r"/api/auth/sessions/revoke-others")
def revoke_others(ctx):
    closed = auth.revoke_other_sessions(ctx.conn, ctx.user["id"], ctx.user.get("sid", ""))
    ctx.audit("SESSIONS_REVOKED", f"user={ctx.user['username']} cerradas={closed}")
    return 200, {"ok": True, "closed": closed}


@route("DELETE", r"/api/auth/sessions/(?P<sid>[\w-]{1,64})")
def revoke_session(ctx):
    auth.revoke_session(ctx.conn, ctx.user["id"], ctx.match["sid"])
    ctx.audit("SESSION_REVOKED", f"user={ctx.user['username']}")
    return 200, {"ok": True, "current": ctx.match["sid"] == ctx.user.get("sid")}


# ------------------------------------------------------------------ usuarios ------
@route("GET", r"/api/users", cap="users")
def list_users(ctx):
    rows = ctx.conn.execute(
        "SELECT id,username,email,name,role,active,created_at,last_login,totp_enabled AS mfa,must_change_password,"
        "(locked_until > strftime('%s','now')) AS locked FROM users ORDER BY username")
    return 200, [dict(r) for r in rows]


@route("POST", r"/api/users", cap="users")
def create_user(ctx):
    created = auth.create_user(ctx.conn, ctx.body, H.now_iso, ctx.user["role"])
    ctx.audit("CREATE_USER", f"user={created['username']} role={created['role']}")
    return 201, created


@route("PUT", r"/api/users/(?P<uid>\d+)", cap="users")
def update_user(ctx):
    uid = int(ctx.match["uid"])
    result = auth.update_user(ctx.conn, ctx.user["id"], uid, ctx.body, ctx.user["role"])
    keys = ",".join(k for k in ("role", "name", "email", "active", "unlock", "reset_mfa", "revoke_sessions",
                                "force_password_change", "password") if k in ctx.body)
    ctx.audit("UPDATE_USER", f"user={result['username']} cambios={keys}")
    return 200, result


# ------------------------------------------------------------------ estado --------
def _key_info(app: KeygenApp) -> dict:
    has_file = kg.KEY_FILE.exists()
    pub = kg.current_public() if has_file else (L.PUBLIC_KEY_HEX or "").strip().lower()
    created = ""
    if has_file:
        try:
            created = json.loads(kg.KEY_FILE.read_text(encoding="utf-8")).get("created", "")
        except (OSError, ValueError):
            pass
    return {"configured": bool(pub), "has_key_file": has_file, "fingerprint": C.fingerprint(pub) if pub else "",
            "created": created, "whatsapp": L.WHATSAPP_NUMBER or "", **app.vault.status()}


def _plans(with_prices: bool) -> dict:
    usd = kg.rates().get("USD", 1)
    out = {}
    for code, (name, days, web, android) in L.PLANS.items():
        item = {"name": name, "days": days}
        if with_prices:
            item.update({"usd_web": web, "usd_android": android, "cup_web": round(web * usd, 2),
                         "cup_android": round(android * usd, 2)})
        out[code] = item
    return out


@route("GET", r"/api/status")
def status(ctx):
    prices = ctx.can("prices")
    return 200, {"user": ctx.user, "caps": sorted(ctx.caps), "roles": roles.keygen_catalog(),
                 "key": _key_info(ctx.app), "plans": _plans(prices), "rates": kg.rates() if prices else {},
                 "require_mfa": ctx.app.require_mfa, "unlock_minutes": ctx.app.vault.ttl // 60,
                 "app_names": L.APP_NAMES, "version": VERSION,
                 "history_count": H.count(ctx.conn) if ctx.can("history_all") else None}


# ------------------------------------------------------------------ clave de firma --
@route("POST", r"/api/key/init", cap="keys")
def key_init(ctx):
    passphrase = str(ctx.body.get("passphrase", ""))
    result = C.init_key(passphrase, str(ctx.body.get("whatsapp", "")), bool(ctx.body.get("force", False)))
    ctx.app.vault.unlock(passphrase, ctx.user["username"])
    ctx.audit("KEY_INIT", f"huella={result['fingerprint']} archivos={','.join(result['patched'])}")
    return 200, {"ok": True, "patched": result["patched"], "key": _key_info(ctx.app)}


@route("POST", r"/api/key/whatsapp", cap="keys")
def key_whatsapp(ctx):
    phone = C.clean_phone(str(ctx.body.get("whatsapp", "")))
    pub = kg.current_public() if kg.KEY_FILE.exists() else (L.PUBLIC_KEY_HEX or "")
    if not pub:
        raise ApiError("Cree primero la clave de firma.", 400)
    patched = C.patch_files(pub, phone)
    L.WHATSAPP_NUMBER = phone
    ctx.audit("KEY_WHATSAPP", f"numero={phone}")
    return 200, {"ok": True, "patched": patched, "key": _key_info(ctx.app)}


@route("POST", r"/api/key/unlock", cap="emit")
def key_unlock(ctx):
    info = ctx.app.vault.unlock(str(ctx.body.get("passphrase", "")), ctx.user["username"])
    ctx.audit("KEY_UNLOCK", f"minutos={ctx.app.vault.ttl // 60}")
    return 200, {"ok": True, "key": {**_key_info(ctx.app), **info}}


@route("POST", r"/api/key/lock", cap="emit")
def key_lock(ctx):
    ctx.app.vault.lock()
    ctx.audit("KEY_LOCK", "")
    return 200, {"ok": True, "key": _key_info(ctx.app)}


# ------------------------------------------------------------------ licencias -----
def _wa_link(contact: str, text: str) -> str:
    digits = re.sub(r"\D", "", contact or "")
    base = f"https://wa.me/{digits}" if 8 <= len(digits) <= 15 and "@" not in (contact or "") else "https://wa.me/"
    return f"{base}?text={quote(text)}"


def _public_license(ctx, lic: dict, with_token: bool = True) -> dict:
    item = dict(lic)
    if not with_token:
        item.pop("token", None)
    return item if ctx.can("prices") else H.strip_prices(item)


def _visible(ctx, lic):
    """Un operador solo puede ver lo que él mismo emitió (404: no se revela que existe)."""
    scope = ctx.scope()
    if not lic or (scope is not None and lic["created_by"].lower() != scope.lower()):
        raise ApiError("Licencia no encontrada.", 404)
    return lic


@route("POST", r"/api/licenses", cap="emit")
def emit(ctx):
    b = ctx.body
    plan = str(b.get("plan", "")).upper()
    if plan not in L.PLANS:
        raise ApiError(f"Plan desconocido: {plan or '—'}. Opciones: {', '.join(L.PLANS)}")
    customer = " ".join(str(b.get("customer", "")).split())
    if not customer:
        raise ApiError("Indique el nombre del usuario/cliente.")
    code = str(b.get("code", "")).strip()
    try:
        app_letter, device = L.parse_request_code(code)
    except ValueError as exc:
        raise ApiError(str(exc)) from exc
    start, end, custom = _opt(b.get("start_date")), _opt(b.get("end_date")), b.get("custom_price_usd")
    custom = None if custom is None or str(custom).strip() == "" else custom
    if plan == "PX":
        if not start or not end or custom is None:
            raise ApiError("El plan PX requiere Desde, Hasta y precio acordado en USD.")
    elif start or end or custom is not None:
        raise ApiError("Las fechas y el precio manual solo se admiten con el plan PX.")
    wants_money = bool(b.get("paid")) or bool(_opt(b.get("pay_method")))
    if wants_money and not ctx.can("prices"):
        raise ApiError("Su rol no puede registrar cobros.", 403)
    renews = (_opt(b.get("renews")) or "").upper()
    if renews and not H.by_serial(ctx.conn, renews):
        raise ApiError("La licencia que desea renovar no existe en el historial.")
    d = ctx.app.vault.key()
    try:
        token, reply = kg.emit(d, customer, code, plan, start, end, custom,
                               contact=str(b.get("contact", "")), notes=str(b.get("notes", "")),
                               created_by=ctx.user["username"], paid=bool(b.get("paid")),
                               pay_method=str(b.get("pay_method", "")), renewed_from=renews,
                               source="web", conn=ctx.conn)
    except ValueError as exc:
        raise ApiError(str(exc)) from exc
    data = L.decode(token, L.public_from_private(d))
    lic = H.by_serial(ctx.conn, data["sn"])
    duplicates = [r["serial"] for r in ctx.conn.execute(
        "SELECT serial FROM licenses WHERE device=? AND status='active' AND expires_at>? AND serial<>?",
        (device, time.time(), data["sn"]))]
    warnings = ([f"Este dispositivo ya tenía licencia vigente (serie {', '.join(duplicates)}). "
                 "Si es una renovación, anule la anterior desde el historial."] if duplicates and not renews else [])
    ctx.audit("LICENSE_ISSUED", f"serie={data['sn']} cliente={data['usr']} app={app_letter} plan={plan}")
    return 201, {"license": _public_license(ctx, lic), "token": token, "reply": reply, "warnings": warnings,
                 "whatsapp_url": _wa_link(lic["contact"], reply), "app_name": L.APP_NAMES[app_letter]}


@route("GET", r"/api/licenses", cap=("history_all", "history_own"))
def list_licenses(ctx):
    filters = {k: v[0] for k, v in ctx.query.items() if v}
    page = H.query(ctx.conn, filters, ctx.scope(), hide_prices=not ctx.can("prices"))
    for item in page["items"]:
        item.pop("token", None)  # el token solo viaja en el detalle
    return 200, page


@route("GET", r"/api/licenses/(?P<lid>\d+)", cap=("history_all", "history_own"))
def license_detail(ctx):
    lic = _visible(ctx, H.get(ctx.conn, int(ctx.match["lid"])))
    verification = {"signature": "sin_token", "message": "Licencia importada del registro antiguo: no conserva el token."}
    if lic.get("token"):
        pub = kg.current_public() if kg.KEY_FILE.exists() else (L.PUBLIC_KEY_HEX or "")
        if not pub:
            verification = {"signature": "sin_clave", "message": "No hay clave pública para verificarla."}
        else:
            try:
                L.decode(lic["token"], pub)
                verification = {"signature": "valida", "message": "Firma válida con la clave actual."}
            except ValueError as exc:
                verification = {"signature": "invalida", "message": str(exc)}
    return 200, {"license": _public_license(ctx, lic), "events": H.events(ctx.conn, lic["id"]),
                 "verification": verification,
                 "can": {"edit": ctx.can("emit") or ctx.can("prices"), "money": ctx.can("prices"),
                         "revoke": ctx.can("revoke"), "resend": ctx.can("emit")}}


@route("PATCH", r"/api/licenses/(?P<lid>\d+)", cap=("emit", "prices"))
def license_patch(ctx):
    lic = _visible(ctx, H.get(ctx.conn, int(ctx.match["lid"])))
    changes = {k: v for k, v in ctx.body.items() if k in ("notes", "contact", "paid", "pay_method")}
    updated = H.update_fields(ctx.conn, lic["id"], ctx.user["username"], changes,
                              allow_notes=ctx.can("emit") or ctx.can("prices"), allow_money=ctx.can("prices"))
    ctx.audit("LICENSE_UPDATED", f"serie={lic['serial']} campos={','.join(sorted(changes))}")
    return 200, {"license": _public_license(ctx, updated)}


@route("POST", r"/api/licenses/(?P<lid>\d+)/revoke", cap="revoke")
def license_revoke(ctx):
    lic = H.get(ctx.conn, int(ctx.match["lid"]))
    if not lic:
        raise ApiError("Licencia no encontrada.", 404)
    updated = H.revoke(ctx.conn, lic["id"], ctx.user["username"], ctx.body.get("reason", ""))
    ctx.audit("LICENSE_REVOKED", f"serie={lic['serial']} motivo={updated['revoked_reason'][:120]}")
    return 200, {"license": _public_license(ctx, updated)}


@route("POST", r"/api/licenses/(?P<lid>\d+)/reactivate", cap="revoke")
def license_reactivate(ctx):
    lic = H.get(ctx.conn, int(ctx.match["lid"]))
    if not lic:
        raise ApiError("Licencia no encontrada.", 404)
    updated = H.reactivate(ctx.conn, lic["id"], ctx.user["username"])
    ctx.audit("LICENSE_REACTIVATED", f"serie={lic['serial']}")
    return 200, {"license": _public_license(ctx, updated)}


@route("POST", r"/api/licenses/(?P<lid>\d+)/resend", cap="emit")
def license_resend(ctx):
    """Registra el reenvío y devuelve el mensaje listo para WhatsApp."""
    lic = _visible(ctx, H.get(ctx.conn, int(ctx.match["lid"])))
    if not lic.get("token"):
        raise ApiError("Esta licencia se importó del registro antiguo y no conserva el token: emita una nueva.", 409)
    if lic["status"] == "revoked":
        raise ApiError("La licencia está anulada: no se puede reenviar.", 409)
    pub = kg.current_public() if kg.KEY_FILE.exists() else (L.PUBLIC_KEY_HEX or "")
    try:
        data = L.decode(lic["token"], pub)
    except ValueError as exc:
        raise ApiError(f"La firma ya no es válida con la clave actual: {exc}", 409) from exc
    reply = kg.whatsapp_reply(data, lic["token"])
    H.add_event(ctx.conn, lic["id"], ctx.user["username"], "RESENT", "Mensaje de WhatsApp")
    ctx.audit("LICENSE_RESENT", f"serie={lic['serial']}")
    return 200, {"token": lic["token"], "reply": reply, "whatsapp_url": _wa_link(lic["contact"], reply)}


@route("POST", r"/api/verify")
def verify(ctx):
    token = str(ctx.body.get("license", ""))[:4000]
    pub = kg.current_public() if kg.KEY_FILE.exists() else (L.PUBLIC_KEY_HEX or "")
    if not pub:
        raise ApiError("No hay clave pública: cree primero la clave de firma.")
    try:
        data = L.decode(token, pub)
    except ValueError as exc:
        raise ApiError(str(exc)) from exc
    info = {"ok": True, "signature": "Válida ✔", **L.public_info(data, time.time()), "app": data["app"],
            "app_name": L.APP_NAMES.get(data["app"], data["app"]), "device": data["dev"]}
    known = H.by_serial(ctx.conn, data["sn"])
    if known and (ctx.scope() is None or known["created_by"].lower() == ctx.scope().lower()):
        info["history"] = {"id": known["id"], "state": known["state"], "state_label": known["state_label"],
                           "customer": known["customer"], "revoked_reason": known["revoked_reason"]}
    return 200, info


@route("GET", r"/api/stats", cap=("history_all", "history_own"))
def stats(ctx):
    result = H.stats(ctx.conn, ctx.scope(), with_money=ctx.can("prices"))
    result["recent"] = H.recent_events(ctx.conn, 10, ctx.scope())
    return 200, result


@route("GET", r"/api/export\.csv", cap="export")
def export_csv(ctx):
    filters = {k: v[0] for k, v in ctx.query.items() if v}
    text = H.export_csv(ctx.conn, filters, ctx.scope(), include_prices=ctx.can("prices"))
    ctx.audit("CSV_EXPORTED", f"filtros={json.dumps(filters, ensure_ascii=False)[:200]}")
    return 200, Raw(text.encode("utf-8"), "text/csv; charset=utf-8",
                    f"historial-licencias-{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv")


@route("POST", r"/api/import-csv", cap="keys")
def import_csv(ctx):
    text = ctx.body.get("csv")
    result = H.import_legacy_csv(ctx.conn, text) if text else kg.import_legacy(ctx.conn)
    ctx.audit("CSV_IMPORTED", f"importadas={result['imported']} repetidas={result['skipped']} no_validas={result['invalid']}")
    return 200, result


@route("GET", r"/api/backup", cap="keys")
def backup(ctx):
    with tempfile.TemporaryDirectory() as tmp:
        target = H.backup_to(ctx.conn, Path(tmp) / "licencias.db")
        data = target.read_bytes()
    ctx.audit("BACKUP_DOWNLOADED", f"bytes={len(data)}")
    return 200, Raw(data, "application/octet-stream",
                    f"licencias-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}.db")


@route("POST", r"/api/rates", cap="rates")
def rates(ctx):
    saved = C.save_rates(ctx.body.get("rates", {}))
    ctx.audit("RATES_UPDATED", f"USD={saved.get('USD')}")
    return 200, {"ok": True, "rates": saved}


# ------------------------------------------------------------------ auditoría -----
@route("GET", r"/api/audit", cap="audit")
def audit_list(ctx):
    return 200, audit.query(limit=int(ctx.arg("limit", "50")), offset=int(ctx.arg("offset", "0")),
                            action=ctx.arg("action"), search=ctx.arg("search")[:80])


@route("GET", r"/api/audit/verify", cap="audit")
def audit_verify(ctx):
    return 200, audit.verify_chain()


# ---------------------------------------------------------------------------
#  Servidor HTTP
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "IPVKeygen"
    sys_version = ""
    protocol_version = "HTTP/1.1"
    timeout = 30  # corta conexiones lentas (slowloris)
    app: KeygenApp = None  # lo fija make_handler

    def log_message(self, *_args):  # sin registro de accesos: la auditoría ya guarda lo importante
        pass

    # -- utilidades -------------------------------------------------------------------
    def client_ip(self) -> str:
        return security.resolve_client_ip(self.client_address[0], self.headers.get("X-Forwarded-For", ""))

    def _headers(self, content_type: str, length: int, extra: dict | None = None, cache: str = "no-store") -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", cache)
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if getattr(self.server, "tls", False):
            self.send_header("Strict-Transport-Security", "max-age=31536000")
        for key, value in (extra or {}).items():
            self.send_header(key, value)

    def send_json(self, payload, status: int = 200, extra: dict | None = None) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._headers("application/json; charset=utf-8", len(raw), extra)
        self.end_headers()
        self.wfile.write(raw)

    def send_raw(self, item: Raw) -> None:
        self.send_response(200)
        disposition = {"Content-Disposition": f'attachment; filename="{item.filename}"'} if item.filename else {}
        self._headers(item.content_type, len(item.body), disposition)
        self.end_headers()
        self.wfile.write(item.body)

    def _read_body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError as exc:
            raise ApiError("Content-Length no válido.", 400) from exc
        if length <= 0:
            if self.headers.get("Transfer-Encoding"):
                raise ApiError("Envíe el cuerpo con Content-Length.", 411)
            return {}
        if length > MAX_BODY:
            raise ApiError("El cuerpo de la petición es demasiado grande.", 413)
        if not self.headers.get("Content-Type", "").lower().startswith("application/json"):
            raise ApiError("El Content-Type debe ser application/json.", 415)
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ApiError("El cuerpo no es un JSON válido.", 400) from exc
        if not isinstance(data, dict):
            raise ApiError("Se esperaba un objeto JSON.", 400)
        return data

    def _same_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        return urlparse(origin).netloc.lower() == (self.headers.get("Host") or "").lower()

    # -- autenticación ----------------------------------------------------------------
    def _authenticate(self, path: str, conn) -> dict:
        header = self.headers.get("Authorization", "")
        token = header[7:].strip() if header.startswith("Bearer ") else ""
        if not token:
            raise ApiError("Autenticación requerida.", 401)
        try:
            payload = auth.decode_token(token, "access")
        except auth.AuthError as exc:
            raise ApiError(exc.message, exc.status) from exc
        if not auth.session_valid(conn, payload):
            raise ApiError("La sesión fue revocada. Inicie sesión de nuevo.", 401)
        row = conn.execute("SELECT * FROM users WHERE id=?", (payload["sub"],)).fetchone()
        if not row or row["role"] != payload.get("role") or row["username"] != payload.get("usr"):
            raise ApiError("La sesión fue modificada. Inicie sesión de nuevo.", 401)
        user = {"id": row["id"], "username": row["username"], "name": row["name"], "email": row["email"],
                "role": row["role"], "mfa": bool(row["totp_enabled"]), "sid": payload.get("sid", ""),
                "caps": sorted(roles.keygen_caps(row["role"]))}
        if (payload.get("pwx") or auth.password_status(row)["expired"]) and not path.startswith(PASSWORD_EXPIRED_ALLOWED):
            raise ApiError("Su contraseña ha caducado. Debe cambiarla para continuar.", 403, password_expired=True)
        if self.app.require_mfa and not user["mfa"] and not path.startswith(MFA_SETUP_ALLOWED):
            raise ApiError("Active la verificación en dos pasos para usar el Keygen.", 403, mfa_setup_required=True)
        return user

    # -- despacho ---------------------------------------------------------------------
    def _serve_static(self, path: str) -> None:
        entry = STATIC.get(path)
        if not entry:
            return self.send_json({"error": "No encontrado."}, 404)
        name, content_type = entry
        file = (ROOT / "web" / "qr.js") if name is None else (STATIC_DIR / name)
        try:
            raw = file.read_bytes()
        except OSError:
            return self.send_json({"error": "Recurso no disponible."}, 404)
        self.send_response(200)
        self._headers(content_type, len(raw), cache="no-cache")
        self.end_headers()
        self.wfile.write(raw)

    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        try:
            if not self.app.host_allowed(self.headers.get("Host", "")):
                raise ApiError("Host no permitido. Use http://127.0.0.1 o añádalo en KEYGEN_ALLOWED_HOSTS.", 403)
            ip = self.client_ip()
            if not security.ip_allowed(ip):
                raise ApiError("Acceso no permitido desde esta dirección.", 403)
            if method != "GET" and not self._same_origin():
                raise ApiError("Origen no permitido.", 403)
            if not path.startswith("/api/"):
                if method != "GET":
                    raise ApiError("Método no permitido.", 405)
                return self._serve_static(path)
            ok, limit, remaining, reset = rate_limiter.check(ip, method, path)
            if not ok:
                raise ApiError("Demasiadas peticiones. Espere un momento.", 429, retry_after=reset)
            candidates = [r for r in ROUTES if r[1].match(path)]
            if not candidates:
                raise ApiError("Ruta no encontrada.", 404)
            entry = next((r for r in candidates if r[0] == method), None)
            if not entry:
                raise ApiError("Método no permitido.", 405)
            _, pattern, fn, public, caps = entry
            body = self._read_body() if method in ("POST", "PUT", "PATCH", "DELETE") else {}
            conn = self.app.connect()
            try:
                with conn:
                    user = None if public else self._authenticate(path, conn)
                    if user is not None and caps and not any(c in user["caps"] for c in caps):
                        raise ApiError("Su rol no tiene permiso para esta operación.", 403)
                    ctx = Ctx(self, self.app, pattern.match(path), parse_qs(parsed.query), body, user, conn)
                    status, payload = fn(ctx)
            finally:
                conn.close()
            if isinstance(payload, Raw):
                return self.send_raw(payload)
            self.send_json(payload, status)
        except auth.MFARequired as exc:
            self.send_json({"error": exc.message, "mfa_required": True}, 401)
        except auth.AuthError as exc:
            self.send_json({"error": exc.message}, exc.status)
        except H.HistorialError as exc:
            self.send_json({"error": exc.message}, exc.status)
        except ApiError as exc:
            extra = {"Retry-After": str(exc.extra["retry_after"])} if "retry_after" in exc.extra else None
            self.send_json({"error": exc.message, **{k: v for k, v in exc.extra.items() if k != "retry_after"}},
                           exc.status, extra)
        except (ValueError, TypeError) as exc:
            self.send_json({"error": str(exc)}, 400)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:  # pragma: no cover - último recurso: no filtrar detalles internos
            print("KEYGEN error:", repr(exc))
            self.send_json({"error": "Error interno del Keygen."}, 500)

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_PATCH(self):
        self._dispatch("PATCH")

    def do_DELETE(self):
        self._dispatch("DELETE")


def make_server(host: str = "127.0.0.1", port: int = DEFAULT_PORT, app: KeygenApp | None = None,
                tls: tuple[str, str] | None = None) -> ThreadingHTTPServer:
    """Crea (sin arrancar) el servidor; `port=0` elige uno libre (pruebas)."""
    app = app or KeygenApp(host=host)
    app.apply_globals()
    app.init_db()
    handler = type("KeygenHandler", (Handler,), {"app": app})
    httpd = ThreadingHTTPServer((host, port), handler)
    httpd.daemon_threads = True
    httpd.app = app
    httpd.tls = False
    if tls:
        httpd.socket = tls_seguro.build_context(tls[0], tls[1]).wrap_socket(httpd.socket, server_side=True)
        httpd.tls = True
    return httpd


def serve(host: str = "127.0.0.1", port: int = DEFAULT_PORT, open_browser: bool = True) -> None:
    cert = os.environ.get("KEYGEN_TLS_CERT", "").strip()
    key = os.environ.get("KEYGEN_TLS_KEY", "").strip()
    try:
        httpd = make_server(host, port, tls=(cert, key) if cert and key else None)
    except OSError as exc:
        raise SystemExit(f"No se pudo abrir {host}:{port}: {exc}. Pruebe otro puerto con --port.") from exc
    app = httpd.app
    scheme = "https" if httpd.tls else "http"
    shown = "127.0.0.1" if host in ("0.0.0.0", "") else host  # nosec B104
    url = f"{scheme}://{shown}:{httpd.server_port}"
    info = _key_info(app)
    print("═" * 62)
    print(f"  {APP_NAME} Web v{VERSION} — licencias de IPV Web e IPV Android")
    print(f"  {url}")
    print(f"  Historial: {app.db_path}")
    print(f"  Clave de firma: {'✓ huella ' + info['fingerprint'] if info['configured'] else '✗ aún no creada (Clave de firma → Crear)'}")
    print(f"  2FA obligatoria: {'sí' if app.require_mfa else 'no (recomendada; actívela en Mi cuenta)'}")
    if app.setup_token:
        print(f"  Código de instalación (primer acceso): {app.setup_token}")
    if not _loopback(host):
        print("  ⚠ Escucha fuera de este equipo: use HTTPS (KEYGEN_TLS_CERT / KEYGEN_TLS_KEY) y una red de confianza.")
    print("  Detenga el servidor con Ctrl+C.")
    print("═" * 62)
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nKeygen detenido.")
    finally:
        httpd.server_close()
