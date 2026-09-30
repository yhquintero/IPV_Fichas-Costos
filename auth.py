"""
IPV Fichas y Costos - Autenticación JWT (solo librería estándar).
Autor: Ing. Yosvany Hernández Quintero

- Tokens JWT HS256 firmados con HMAC-SHA256 (access + refresh).
- Contraseñas con PBKDF2-HMAC-SHA256 (310 000 iteraciones) y sal aleatoria.
- Revocación de refresh tokens (logout) mediante tabla `revoked_tokens`.
- Roles: admin, editor, viewer.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timezone

import security

JWT_SECRET = os.environ.get("IPV_JWT_SECRET", "").strip()
ACCESS_TTL = int(os.environ.get("IPV_ACCESS_TTL", "1800"))        # 30 min
REFRESH_TTL = int(os.environ.get("IPV_REFRESH_TTL", "604800"))    # 7 días
PBKDF2_ITERATIONS = 310_000
PASSWORD_MAX_AGE_DAYS = int(os.environ.get("IPV_PASSWORD_MAX_AGE_DAYS", "0") or 0)  # 0 = sin caducidad
PASSWORD_HISTORY = int(os.environ.get("IPV_PASSWORD_HISTORY", "5") or 0)
PASSWORD_WARN_DAYS = 7
FAILED_ALERT_AT = int(os.environ.get("IPV_FAILED_LOGIN_ALERT", "3") or 0)  # 0 = sin alertas
ROLES = ("admin", "editor", "viewer")
JWT_ENABLED = bool(JWT_SECRET)


class AuthError(Exception):
    def __init__(self, message: str, status: int = 401):
        super().__init__(message)
        self.message = message
        self.status = status


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _secret() -> bytes:
    if not JWT_SECRET:
        raise AuthError("JWT no configurado en el servidor.", 503)
    return JWT_SECRET.encode("utf-8")


def encode_token(user: dict, token_type: str = "access", sid: str = "", pwx: bool = False) -> str:
    now = int(time.time())
    payload = {
        "sub": user["id"], "email": user["email"], "role": user["role"], "ver": user.get("ver", 0), "mfa": bool(user.get("mfa")),
        "type": token_type, "iat": now,
        "exp": now + (ACCESS_TTL if token_type == "access" else REFRESH_TTL),
        "jti": secrets.token_urlsafe(16),
    }
    if sid:
        payload["sid"] = sid
    if pwx:
        payload["pwx"] = True  # contraseña caducada: solo puede cambiarla
    header = _b64e(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64e(hmac.new(_secret(), f"{header}.{body}".encode(), hashlib.sha256).digest())
    return f"{header}.{body}.{sig}"


def decode_token(token: str, token_type: str = "access") -> dict:
    try:
        header, body, sig = token.split(".")
        head = json.loads(_b64d(header))
    except (ValueError, json.JSONDecodeError):
        raise AuthError("Token mal formado.")
    if not isinstance(head, dict) or head.get("alg") != "HS256":
        raise AuthError("Algoritmo de token no permitido.")
    expected = _b64e(hmac.new(_secret(), f"{header}.{body}".encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, sig):
        raise AuthError("Firma de token inválida.")
    try:
        payload = json.loads(_b64d(body))
        if not isinstance(payload, dict):
            raise ValueError("payload")
    except (ValueError, json.JSONDecodeError, TypeError):
        raise AuthError("Token mal formado.")
    if payload.get("type") != token_type:
        raise AuthError("Tipo de token incorrecto.")
    try:
        expires = int(payload.get("exp", 0))
    except (ValueError, TypeError):
        raise AuthError("Token mal formado.")
    if expires <= int(time.time()):
        raise AuthError("El token ha expirado.")
    return payload


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iterations, salt, digest = stored.split("$")
        new = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iterations))
        return hmac.compare_digest(new.hex(), digest)
    except (ValueError, AttributeError):
        return False


def validate_password_strength(password: str) -> None:
    if len(password) < 10:
        raise AuthError("La contraseña debe tener al menos 10 caracteres.", 400)
    checks = [any(c.islower() for c in password), any(c.isupper() for c in password),
              any(c.isdigit() for c in password), any(not c.isalnum() for c in password)]
    if sum(checks) < 3:
        raise AuthError("La contraseña debe combinar mayúsculas, minúsculas, números o símbolos.", 400)


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer' CHECK(role IN ('admin','editor','viewer')),
    password_hash TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    last_login TEXT
);
CREATE TABLE IF NOT EXISTS revoked_tokens (
    jti TEXT PRIMARY KEY,
    expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    ip TEXT NOT NULL DEFAULT '',
    user_agent TEXT NOT NULL DEFAULT '',
    expires_at INTEGER NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id, revoked);
CREATE TABLE IF NOT EXISTS login_ips (
    user_id INTEGER NOT NULL,
    ip TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    PRIMARY KEY (user_id, ip)
);
"""

MAX_FAILED = 5
LOCK_SECONDS = 900


MIGRATIONS = {
    "totp_secret": "TEXT NOT NULL DEFAULT ''",
    "totp_enabled": "INTEGER NOT NULL DEFAULT 0",
    "totp_last_step": "INTEGER NOT NULL DEFAULT -1",
    "recovery_codes": "TEXT NOT NULL DEFAULT ''",
    "token_version": "INTEGER NOT NULL DEFAULT 0",
    "password_changed_at": "TEXT NOT NULL DEFAULT ''",
    "password_history": "TEXT NOT NULL DEFAULT ''",
    "must_change_password": "INTEGER NOT NULL DEFAULT 0",
    "failed_since_login": "INTEGER NOT NULL DEFAULT 0",
    "last_failed_ip": "TEXT NOT NULL DEFAULT ''",
}


class LoginFailed(AuthError):
    """Credenciales o segundo factor incorrectos sobre una cuenta existente.
    Lleva los datos necesarios para las alertas (nunca se envían al cliente)."""
    def __init__(self, message: str, email: str, attempts: int, locked: bool, status: int = 401):
        super().__init__(message, status)
        self.email = email
        self.attempts = attempts
        self.locked = locked


class MFARequired(AuthError):
    def __init__(self):
        super().__init__("Introduzca el código de verificación de su aplicación autenticadora.", 401)


def init_auth(conn, now_iso) -> None:
    conn.executescript(SCHEMA)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
    for name, ddl in MIGRATIONS.items():
        if name not in cols:
            conn.execute(f"ALTER TABLE users ADD COLUMN {name} {ddl}")
    email = os.environ.get("IPV_ADMIN_EMAIL", "").strip()
    password = os.environ.get("IPV_ADMIN_PASSWORD", "").strip()
    if email and password and not conn.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
        validate_password_strength(password)
        conn.execute(
            "INSERT INTO users(email,name,role,password_hash,created_at) VALUES(?,?,?,?,?)",
            (email, "Administrador", "admin", hash_password(password), now_iso()),
        )


def public_user(row) -> dict:
    keys = row.keys()
    return {"id": row["id"], "email": row["email"], "name": row["name"], "role": row["role"],
            "mfa": bool(row["totp_enabled"]) if "totp_enabled" in keys else False,
            "ver": row["token_version"] if "token_version" in keys else 0}


def _check_second_factor(conn, row, otp: str) -> None:
    """Valida TOTP o un código de recuperación de un solo uso."""
    if not row["totp_enabled"]:
        return
    if not otp:
        raise MFARequired()
    step = security.verify_totp(row["totp_secret"], otp, row["totp_last_step"])
    if step > 0:
        conn.execute("UPDATE users SET totp_last_step=? WHERE id=?", (step, row["id"]))
        return
    codes = [c for c in row["recovery_codes"].split(",") if c]
    hashed = security.hash_code(otp)
    if hashed in codes:
        codes.remove(hashed)
        conn.execute("UPDATE users SET recovery_codes=? WHERE id=?", (",".join(codes), row["id"]))
        return
    raise AuthError("Código de verificación incorrecto.")


def login(conn, email: str, password: str, now_iso, otp: str = "", ip: str = "", user_agent: str = "") -> dict:
    row = conn.execute("SELECT * FROM users WHERE email=?", (email.strip(),)).fetchone()
    now = time.time()
    if row and row["locked_until"] > now:
        raise AuthError("Cuenta bloqueada temporalmente por intentos fallidos.", 423)
    if not row or not row["active"] or not verify_password(password, row["password_hash"]):
        if row:
            _record_failure(conn, row, now, ip, "Credenciales inválidas.")
        raise AuthError("Credenciales inválidas.")
    try:
        _check_second_factor(conn, row, otp)
    except MFARequired:
        raise
    except AuthError as exc:
        _record_failure(conn, row, now, ip, exc.message)
    failed_before = row["failed_since_login"]
    last_failed_ip = row["last_failed_ip"]
    conn.execute("UPDATE users SET failed_attempts=0, locked_until=0, failed_since_login=0, last_failed_ip='', "
                 "last_login=? WHERE id=?", (now_iso(), row["id"]))
    row = conn.execute("SELECT * FROM users WHERE id=?", (row["id"],)).fetchone()
    user = public_user(row)
    new_ip = register_login_ip(conn, row["id"], ip, now_iso())
    sid = create_session(conn, row["id"], ip, user_agent, now_iso())
    return {**_issue(user, sid, row), "new_ip": new_ip, "session_id": sid,
            "failed_attempts_since_last_login": failed_before, "last_failed_ip": last_failed_ip if failed_before else ""}


def _record_failure(conn, row, now: float, ip: str, message: str):
    attempts = row["failed_attempts"] + 1
    locked = attempts >= MAX_FAILED
    conn.execute("UPDATE users SET failed_attempts=?, locked_until=?, failed_since_login=failed_since_login+1, "
                 "last_failed_ip=? WHERE id=?",
                 (0 if locked else attempts, now + LOCK_SECONDS if locked else 0, ip[:64], row["id"]))
    raise LoginFailed(message, row["email"], attempts, locked)


def _issue(user: dict, sid: str, row) -> dict:
    pw = password_status(row)
    return {"access_token": encode_token(user, "access", sid, pw["expired"]),
            "refresh_token": encode_token(user, "refresh", sid, pw["expired"]),
            "token_type": "bearer", "expires_in": ACCESS_TTL, "user": user,
            "password_expired": pw["expired"], "password_expires_in_days": pw["days_left"]}


def refresh(conn, refresh_token: str, ip: str = "") -> dict:
    payload = decode_token(refresh_token, "refresh")
    if conn.execute("SELECT 1 FROM revoked_tokens WHERE jti=?", (payload["jti"],)).fetchone():
        raise AuthError("Token revocado.")
    row = conn.execute("SELECT * FROM users WHERE id=? AND active=1", (payload["sub"],)).fetchone()
    if not row:
        raise AuthError("Usuario no disponible.")
    if payload.get("ver", 0) != row["token_version"]:
        raise AuthError("La sesión fue invalidada. Inicie sesión de nuevo.")
    sid = payload.get("sid", "")
    if not sid or not _session_active(conn, sid, row["id"]):
        raise AuthError("La sesión de este dispositivo fue cerrada. Inicie sesión de nuevo.")
    # Rotación: el refresh usado queda revocado
    conn.execute("INSERT OR IGNORE INTO revoked_tokens(jti,expires_at) VALUES(?,?)", (payload["jti"], payload["exp"]))
    if sid:
        conn.execute("UPDATE sessions SET last_seen=?, ip=CASE WHEN ?<>'' THEN ? ELSE ip END, expires_at=? WHERE id=?",
                     (_now(), ip, ip, int(time.time()) + REFRESH_TTL, sid))
    return _issue(public_user(row), sid, row)


def revoke(conn, refresh_token: str) -> None:
    try:
        payload = decode_token(refresh_token, "refresh")
    except AuthError:
        return
    conn.execute("INSERT OR IGNORE INTO revoked_tokens(jti,expires_at) VALUES(?,?)", (payload["jti"], payload["exp"]))
    if payload.get("sid"):
        conn.execute("UPDATE sessions SET revoked=1 WHERE id=?", (payload["sid"],))
    conn.execute("DELETE FROM revoked_tokens WHERE expires_at < ?", (int(time.time()),))
    conn.execute("DELETE FROM sessions WHERE expires_at < ? OR (revoked=1 AND last_seen < ?)",
                 (int(time.time()), _now(-30 * 86400)))


def create_user(conn, data: dict, now_iso) -> dict:
    email = str(data.get("email", "")).strip()
    name = str(data.get("name", "")).strip()[:120]
    role = str(data.get("role", "viewer"))
    password = str(data.get("password", ""))
    if "@" not in email or len(email) > 200:
        raise AuthError("Correo electrónico no válido.", 400)
    if not name:
        raise AuthError("El nombre es obligatorio.", 400)
    if role not in ROLES:
        raise AuthError("Rol no válido.", 400)
    validate_password_strength(password)
    if conn.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
        raise AuthError("Ya existe un usuario con ese correo.", 409)
    cur = conn.execute("INSERT INTO users(email,name,role,password_hash,created_at,password_changed_at,"
                       "must_change_password) VALUES(?,?,?,?,?,?,?)",
                       (email, name, role, hash_password(password), now_iso(), now_iso(),
                        1 if data.get("must_change_password") else 0))
    return {"id": cur.lastrowid, "email": email, "name": name, "role": role}


# ---------------------------------------------------------------------------
#  Validación de sesión activa (usuario activo + versión de token vigente)
# ---------------------------------------------------------------------------
def session_valid(conn, payload: dict) -> bool:
    row = conn.execute("SELECT active, token_version FROM users WHERE id=?", (payload.get("sub"),)).fetchone()
    if not (row and row["active"] and row["token_version"] == payload.get("ver", 0)):
        return False
    sid = payload.get("sid")
    return bool(sid and _session_active(conn, sid, payload.get("sub")))


def _user(conn, user_id):
    row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        raise AuthError("Usuario no encontrado.", 404)
    return row


# ---------------------------------------------------------------------------
#  Verificación en dos pasos (TOTP)
# ---------------------------------------------------------------------------
def mfa_setup(conn, user_id) -> dict:
    row = _user(conn, user_id)
    if row["totp_enabled"]:
        raise AuthError("La verificación en dos pasos ya está activa.", 409)
    secret = security.new_totp_secret()
    conn.execute("UPDATE users SET totp_secret=?, totp_last_step=-1 WHERE id=?", (secret, user_id))
    return {"secret": secret, "otpauth_uri": security.otpauth_uri(secret, row["email"])}


def mfa_enable(conn, user_id, code: str) -> dict:
    row = _user(conn, user_id)
    if row["totp_enabled"]:
        raise AuthError("La verificación en dos pasos ya está activa.", 409)
    step = security.verify_totp(row["totp_secret"], code)
    if step < 0:
        raise AuthError("Código incorrecto. Revise la hora del teléfono e inténtelo de nuevo.", 400)
    codes = security.new_recovery_codes()
    conn.execute("UPDATE users SET totp_enabled=1, totp_last_step=?, recovery_codes=?, "
                 "token_version=token_version+1 WHERE id=?",
                 (step, ",".join(security.hash_code(c) for c in codes), user_id))
    # Los tokens anteriores a la activación de MFA no representan una sesión
    # verificada con segundo factor; obligar a iniciar sesión de nuevo.
    conn.execute("UPDATE sessions SET revoked=1 WHERE user_id=?", (user_id,))
    return {"enabled": True, "recovery_codes": codes}


def mfa_disable(conn, user_id, password: str, code: str) -> dict:
    row = _user(conn, user_id)
    if not verify_password(password, row["password_hash"]):
        raise AuthError("Contraseña incorrecta.", 400)
    _check_second_factor(conn, row, code)
    conn.execute("UPDATE users SET totp_enabled=0, totp_secret='', recovery_codes='' WHERE id=?", (user_id,))
    return {"enabled": False}


# ---------------------------------------------------------------------------
#  Contraseñas y administración de usuarios
# ---------------------------------------------------------------------------
def change_password(conn, user_id, current: str, new: str, now_iso, sid: str = "") -> dict:
    row = _user(conn, user_id)
    if not verify_password(current, row["password_hash"]):
        raise AuthError("La contraseña actual no es correcta.", 400)
    if current == new:
        raise AuthError("La nueva contraseña debe ser distinta de la actual.", 400)
    validate_password_strength(new)
    history = [h for h in row["password_history"].split(",") if h]
    if any(verify_password(new, h) for h in history[:PASSWORD_HISTORY]):
        raise AuthError(f"No puede reutilizar ninguna de sus últimas {PASSWORD_HISTORY} contraseñas.", 400)
    history = ([row["password_hash"]] + history)[:max(PASSWORD_HISTORY, 0)]
    # Subir token_version invalida todas las sesiones abiertas en otros dispositivos;
    # este dispositivo recibe tokens nuevos y conserva su sesión.
    conn.execute("UPDATE users SET password_hash=?, password_changed_at=?, password_history=?, must_change_password=0, "
                 "token_version=token_version+1 WHERE id=?", (hash_password(new), now_iso(), ",".join(history), user_id))
    conn.execute("UPDATE sessions SET revoked=1 WHERE user_id=? AND id<>?", (user_id, sid))
    row = _user(conn, user_id)
    return {"ok": True, **_issue(public_user(row), sid, row)}


def update_user(conn, actor_id, user_id, data: dict) -> dict:
    row = _user(conn, user_id)
    fields, params = [], []
    if "role" in data:
        if data["role"] not in ROLES:
            raise AuthError("Rol no válido.", 400)
        fields.append("role=?"); params.append(data["role"])
    if "active" in data:
        fields.append("active=?"); params.append(1 if data["active"] else 0)
    if data.get("unlock"):
        fields += ["failed_attempts=0", "locked_until=0"]
    if data.get("reset_mfa"):
        fields += ["totp_enabled=0", "totp_secret=''", "recovery_codes=''"]
    if data.get("force_password_change"):
        fields.append("must_change_password=1")
    revoke_all = data.get("revoke_sessions") or "role" in data or data.get("active") is False or data.get("reset_mfa")
    if revoke_all:
        fields.append("token_version=token_version+1")
    if not fields:
        raise AuthError("No hay cambios que aplicar.", 400)
    if int(user_id) == int(actor_id) and (data.get("role", "admin") != "admin" or data.get("active") is False):
        raise AuthError("No puede quitarse a sí mismo el rol de administrador ni desactivarse.", 400)
    if row["role"] == "admin" and (data.get("role", "admin") != "admin" or data.get("active") is False):
        admins = conn.execute("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]
        if admins <= 1:
            raise AuthError("Debe existir al menos un administrador activo.", 400)
    # `fields` solo contiene fragmentos literales definidos arriba; los valores van parametrizados.
    conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE id=?", (*params, user_id))  # nosec B608
    if revoke_all:
        conn.execute("UPDATE sessions SET revoked=1 WHERE user_id=?", (user_id,))
    return public_user(_user(conn, user_id))


# ---------------------------------------------------------------------------
#  Caducidad de contraseñas
# ---------------------------------------------------------------------------
def _parse_iso(text: str):
    try:
        return datetime.fromisoformat(str(text).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def password_status(row) -> dict:
    """{'expired': bool, 'days_left': int|None}. `must_change_password` obliga siempre."""
    keys = row.keys()
    if "must_change_password" in keys and row["must_change_password"]:
        return {"expired": True, "days_left": 0}
    if PASSWORD_MAX_AGE_DAYS <= 0:
        return {"expired": False, "days_left": None}
    changed = _parse_iso(row["password_changed_at"]) if "password_changed_at" in keys else None
    changed = changed or _parse_iso(row["created_at"]) or datetime.now(timezone.utc)
    age = (datetime.now(timezone.utc) - changed).total_seconds() / 86400
    left = int(PASSWORD_MAX_AGE_DAYS - age)
    return {"expired": age >= PASSWORD_MAX_AGE_DAYS, "days_left": max(left, 0)}


# ---------------------------------------------------------------------------
#  Sesiones por dispositivo e IPs conocidas
# ---------------------------------------------------------------------------
def _now(offset_seconds: int = 0) -> str:
    return datetime.fromtimestamp(time.time() + offset_seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _session_active(conn, sid: str, user_id) -> bool:
    row = conn.execute("SELECT revoked, expires_at FROM sessions WHERE id=? AND user_id=?", (sid, user_id)).fetchone()
    return bool(row and not row["revoked"] and row["expires_at"] >= time.time())


def create_session(conn, user_id, ip: str, user_agent: str, now: str) -> str:
    sid = secrets.token_urlsafe(18)
    conn.execute("INSERT INTO sessions(id,user_id,created_at,last_seen,ip,user_agent,expires_at) VALUES(?,?,?,?,?,?,?)",
                 (sid, user_id, now, now, ip[:64], user_agent[:300], int(time.time()) + REFRESH_TTL))
    return sid


def register_login_ip(conn, user_id, ip: str, now: str) -> bool:
    """Registra la IP. Devuelve True si es un acceso desde una IP nunca vista
    (y el usuario ya tenía accesos previos: el primer inicio no genera alerta)."""
    if not ip:
        return False
    known = conn.execute("SELECT ip FROM login_ips WHERE user_id=?", (user_id,)).fetchall()
    if any(r["ip"] == ip for r in known):
        conn.execute("UPDATE login_ips SET last_seen=? WHERE user_id=? AND ip=?", (now, user_id, ip))
        return False
    conn.execute("INSERT INTO login_ips(user_id,ip,first_seen,last_seen) VALUES(?,?,?,?)", (user_id, ip[:64], now, now))
    return bool(known)


def device_label(user_agent: str) -> str:
    ua = user_agent or ""
    if "okhttp" in ua.lower() or "Dalvik/" in ua or "IPV-FichasCostos/" in ua:
        return "App Android"
    browser = next((name for key, name in (("Edg/", "Edge"), ("OPR/", "Opera"), ("Firefox/", "Firefox"),
                                           ("Chrome/", "Chrome"), ("Safari/", "Safari")) if key in ua), "Navegador")
    system = next((name for key, name in (("Windows", "Windows"), ("Android", "Android"), ("iPhone", "iPhone"),
                                          ("iPad", "iPad"), ("Mac OS", "macOS"), ("Linux", "Linux")) if key in ua), "")
    if not ua:
        return "Desconocido"
    return f"{browser} · {system}" if system else browser


def list_sessions(conn, user_id, current_sid: str = "") -> list:
    rows = conn.execute("SELECT id,created_at,last_seen,ip,user_agent FROM sessions WHERE user_id=? AND revoked=0 "
                        "AND expires_at>=? ORDER BY last_seen DESC", (user_id, int(time.time()))).fetchall()
    return [{"id": r["id"], "created_at": r["created_at"], "last_seen": r["last_seen"], "ip": r["ip"],
             "device": device_label(r["user_agent"]), "current": r["id"] == current_sid} for r in rows]


def revoke_session(conn, user_id, sid: str) -> None:
    cur = conn.execute("UPDATE sessions SET revoked=1 WHERE id=? AND user_id=? AND revoked=0", (sid, user_id))
    if cur.rowcount == 0:
        raise AuthError("Sesión no encontrada.", 404)


def revoke_other_sessions(conn, user_id, current_sid: str) -> int:
    return conn.execute("UPDATE sessions SET revoked=1 WHERE user_id=? AND id<>? AND revoked=0",
                        (user_id, current_sid)).rowcount
