"""
IPV Fichas y Costos - Integración Enterprise para server.py (solo librería estándar).
Autor: Ing. Yosvany Hernández Quintero

Añade al servidor, sin dependencias externas:
  * Autenticación JWT con roles (admin / editor / viewer), bloqueo por intentos
    fallidos, rotación y revocación de refresh tokens.
  * Auditoría persistente en SQLite con consulta filtrada (/api/audit).
  * Rate limiting granular por tipo de endpoint con cabeceras X-RateLimit-*.
  * Versionado de API: /api/v1/... equivale a /api/...
  * Actualizaciones en tiempo real mediante Server-Sent Events (/api/events).
  * Backups consistentes con la API de backup de SQLite y backups programados.
  * Borrado lógico (soft delete) de valores de referencia.
  * Notificaciones por correo al aprobar fichas y validar controles.
  * Content-Security-Policy y especificación OpenAPI servida por la API.
"""
from __future__ import annotations

import json
import os
import queue
import re
import sqlite3
import threading
import time
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import audit
import dbcrypt
import auth
import email_notifications
import offsite
import rate_limiter
import security

API_VERSION = "1.1.0"
BACKUP_INTERVAL_HOURS = float(os.environ.get("IPV_BACKUP_INTERVAL_HOURS", "24"))
BACKUP_KEEP = int(os.environ.get("IPV_BACKUP_KEEP", "14"))
NOTIFY_EMAIL = os.environ.get("IPV_NOTIFY_EMAIL", "").strip()
# Rociado de contraseñas: una IP que falla contra muchas cuentas en poco tiempo
SPRAY_WINDOW = 900
SPRAY_ACCOUNTS = int(os.environ.get("IPV_SPRAY_ACCOUNTS", "5"))
SPRAY_FAILURES = int(os.environ.get("IPV_SPRAY_FAILURES", "15"))
REQUIRE_ADMIN_MFA = os.environ.get("IPV_REQUIRE_ADMIN_MFA", "0").strip() in ("1", "true", "si", "sí")

# CSP estricta: ningún script en línea ni eval. Solo se permiten atributos style="…"
# (style-src-attr), que no pueden ejecutar código; hojas <style> en línea bloqueadas.
CSP = ("default-src 'self'; script-src 'self'; script-src-attr 'none'; style-src 'self'; "
       "style-src-elem 'self'; style-src-attr 'unsafe-inline'; "
       "img-src 'self' data:; font-src 'self' data:; connect-src 'self'; object-src 'none'; "
       "base-uri 'self'; form-action 'self'; frame-ancestors 'none'")

PUBLIC_API = {"/api/health", "/api/auth/login", "/api/auth/refresh", "/api/openapi.yaml", "/api/version"}
ADMIN_ONLY = ("/api/users", "/api/backup", "/api/audit")
# Rutas permitidas con la contraseña caducada (solo para poder cambiarla o salir)
PASSWORD_EXPIRED_ALLOWED = ("/api/auth/password", "/api/auth/me", "/api/auth/logout", "/api/auth/sessions",
                            "/api/security/status")
# Acciones que se difunden en tiempo real a los clientes conectados
BROADCAST_PREFIXES = ("RESTORE_", "CREATE_", "UPDATE_", "APPROVE_", "VALIDATE_", "DEACTIVATE_", "BULK_", "DELETE_")


# ---------------------------------------------------------------------------
#  Bus de eventos en tiempo real (SSE)
# ---------------------------------------------------------------------------
class EventBus:
    def __init__(self):
        self._subs: set[queue.Queue] = set()
        self._lock = threading.Lock()

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=100)
        with self._lock:
            self._subs.add(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            self._subs.discard(q)

    def publish(self, event: dict) -> None:
        with self._lock:
            subs = list(self._subs)
        for q in subs:
            try:
                q.put_nowait(event)
            except queue.Full:
                pass

    @property
    def count(self) -> int:
        return len(self._subs)


bus = EventBus()


# ---------------------------------------------------------------------------
#  Backups consistentes
# ---------------------------------------------------------------------------
def sqlite_backup(db_path: Path, target_dir: Path, prefix: str, keep: int) -> dict:
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = target_dir / f"{prefix}_{stamp}.db"
    # Con IPV_DB_KEY la copia queda cifrada con la misma clave
    src = dbcrypt.connect(db_path)
    dst = dbcrypt.connect(target)
    try:
        src.backup(dst)  # copia consistente aun con WAL y escrituras concurrentes
    finally:
        dst.close()
        src.close()
    files = sorted(target_dir.glob(f"{prefix}_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[keep:]:
        old.unlink(missing_ok=True)
    return {"success": True, "filename": target.name, "size": target.stat().st_size,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


def install(srv) -> None:  # noqa: C901 - punto único de integración
    Handler = srv.Handler
    Handler.sys_version = ""  # no revelar la versión de Python en la cabecera Server
    srv.SECURITY_HEADERS["Content-Security-Policy"] = CSP
    srv.SECURITY_HEADERS["Cross-Origin-Opener-Policy"] = "same-origin"
    srv.SECURITY_HEADERS["Cross-Origin-Embedder-Policy"] = "require-corp"
    srv.SECURITY_HEADERS["Cross-Origin-Resource-Policy"] = "same-origin"

    # ---------------- Esquema ----------------
    original_init_db = srv.init_db

    def init_db():
        dbcrypt.check_database(srv.DB_PATH)  # aborta si la configuración de cifrado es insegura
        original_init_db()
        with srv.db_session() as conn:
            auth.init_auth(conn, srv.now_iso)
        audit.init_audit(srv.DB_PATH)

    srv.init_db = init_db

    # ---------------- Auditoría ----------------
    original_audit = srv.audit_log

    def audit_log(action: str, details: str = "", client: str = "") -> None:
        original_audit(action, details, client)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        audit.record(ts, action, details, client)
        if action.startswith(BROADCAST_PREFIXES):
            bus.publish({"action": action, "details": details, "time": ts})
        if NOTIFY_EMAIL and action in ("APPROVE_FICHA", "VALIDATE_CONTROL"):
            _notify(action, details)

    srv.audit_log = audit_log
    srv.get_audit_log = lambda limit=50: audit.query(limit=limit)

    def _notify(action: str, details: str) -> None:
        try:
            ident = int(details.split("id=")[-1].split()[0])
            with srv.db_session() as conn:
                if action == "APPROVE_FICHA":
                    data = srv.ficha_detail(conn, ident) or {}
                    email_notifications.notify_ficha_approved(data, "Sistema IPV", NOTIFY_EMAIL)
                else:
                    data = srv.control_detail(conn, ident) or {}
                    email_notifications.notify_control_validated(data, "Sistema IPV", NOTIFY_EMAIL)
        except Exception as exc:  # la notificación nunca rompe la operación
            print("Notificación no enviada:", exc)

    # ---------------- Backups ----------------
    def export_database_backup():
        return sqlite_backup(srv.DB_PATH, srv.ROOT / "data" / "exports", "ipv_export", BACKUP_KEEP)

    def auto_backup():
        if not srv.DB_PATH.exists():
            return None
        folder = srv.ROOT / "data" / "backups"
        try:
            info = sqlite_backup(srv.DB_PATH, folder, "ipv_backup", BACKUP_KEEP)
            print(f"  Backup: {info['filename']}")
        except sqlite3.Error as exc:
            print(f"  Backup fallido: {exc}")
            srv.audit_log("BACKUP_FAILED", str(exc)[:200], "sistema")
            return None
        # Réplica fuera del equipo (carpetas espejo / S3) con verificación SHA-256
        rep = offsite.replicate(folder / info["filename"], encrypted=dbcrypt.ENABLED)
        for res in rep["results"]:
            if res["ok"]:
                print(f"  ↳ Réplica OK: {res['target']}")
            else:
                print(f"  ↳ Réplica FALLIDA: {res['target']} — {res['error']}")
                srv.audit_log("BACKUP_OFFSITE_FAILED", f"{res['target']}: {res['error']}"[:300], "sistema")
                if NOTIFY_EMAIL:
                    email_notifications.email_notifier.send_async(
                        NOTIFY_EMAIL, "⚠ Réplica de copia de seguridad fallida - IPV Fichas y Costos",
                        email_notifications.EmailTemplates._base_template(
                            "<h2 style='color:#dc2626'>⚠ La réplica externa del backup falló</h2>"
                            f"<p>Destino: <b>{escape(res['target'])}</b><br>Error: {escape(res['error'])}</p>"
                            "<p>La copia local sí se creó. Revise la conexión con el destino.</p>"),
                        f"Réplica fallida en {res['target']}: {res['error']}")
        info["offsite"] = rep["results"]
        return info

    srv.export_database_backup = export_database_backup
    srv.auto_backup = auto_backup

    def _backup_scheduler():
        while True:
            time.sleep(max(0.1, BACKUP_INTERVAL_HOURS) * 3600)
            auto_backup()

    original_main = srv.main

    def main():
        if BACKUP_INTERVAL_HOURS > 0:
            threading.Thread(target=_backup_scheduler, daemon=True, name="backup-scheduler").start()
        print(f"  JWT: {'✓' if auth.JWT_ENABLED else '✗ (defina IPV_JWT_SECRET)'}  "
              f"Backups cada {BACKUP_INTERVAL_HOURS:g} h  API v{API_VERSION}  "
              f"BD cifrada: {'✓ SQLCipher' if dbcrypt.ENABLED else '✗ (defina IPV_DB_KEY)'}")
        try:
            original_main()
        except dbcrypt.CryptoConfigError as exc:
            print(f"\n  ✗ Cifrado de la base de datos: {exc}\n")
            raise SystemExit(2)

    srv.main = main

    # ---------------- Seguridad por solicitud ----------------
    def _api_path(self) -> str:
        return urlparse(self.path).path.rstrip("/") or "/"

    def client_ip(self) -> str:
        return security.resolve_client_ip(self.client_address[0], self.headers.get("X-Forwarded-For", ""))

    Handler.client_ip = client_ip

    def _check_auth(self):
        self.user = None
        path = self._api_path()
        if not path.startswith("/api") or path in PUBLIC_API:
            return
        header = self.headers.get("Authorization", "")
        bearer = header[7:].strip() if header.startswith("Bearer ") else ""
        static = self.headers.get("X-API-Token", "").strip() or bearer
        # 1) Token estático de integración (IPV_API_TOKEN): acceso total
        if srv.API_TOKEN and static and srv.hmac.compare_digest(static, srv.API_TOKEN):
            self.user = {"email": "api-token", "role": "admin"}
        # 2) JWT de usuario
        elif auth.JWT_ENABLED:
            token = bearer
            if not token and path == "/api/events":  # EventSource no admite cabeceras
                token = parse_qs(urlparse(self.path).query).get("access_token", [""])[0]
            if not token:
                raise srv.APIError("Autenticación requerida.", 401)
            try:
                payload = auth.decode_token(token, "access")
            except auth.AuthError as exc:
                raise srv.APIError(exc.message, exc.status)
            # Revocación inmediata: usuario desactivado, rol cambiado o contraseña cambiada
            with srv.db_session() as conn:
                if not auth.session_valid(conn, payload):
                    raise srv.APIError("La sesión fue revocada. Inicie sesión de nuevo.", 401)
            self.user = {"id": payload["sub"], "email": payload["email"], "role": payload["role"],
                         "mfa": bool(payload.get("mfa")), "sid": payload.get("sid", "")}
            if payload.get("pwx") and not path.startswith(PASSWORD_EXPIRED_ALLOWED):
                err = srv.APIError("Su contraseña ha caducado. Debe cambiarla para continuar.", 403)
                err.password_expired = True
                raise err
            if REQUIRE_ADMIN_MFA and path.startswith(ADMIN_ONLY) and not self.user["mfa"]:
                raise srv.APIError("Active la verificación en dos pasos para usar funciones de administración.", 403)
        elif srv.API_TOKEN:
            raise srv.APIError("Autenticación requerida.", 401)
        else:
            return  # modo abierto (red local de confianza / pruebas)
        # Autorización por rol
        role = self.user["role"]
        if path.startswith(ADMIN_ONLY) and role != "admin":
            raise srv.APIError("Permisos insuficientes.", 403)
        if self.command not in ("GET", "HEAD", "OPTIONS") and role == "viewer" \
                and not path.startswith("/api/auth/"):
            raise srv.APIError("Su rol solo permite consultar.", 403)
        audit.set_current_user(self.user.get("email", ""))

    def _pre_check(self) -> bool:
        audit.set_current_user("")
        ip = self.client_ip()
        path = self._api_path()
        if not security.ip_allowed(ip):
            srv.audit_log("IP_BLOCKED", f"path={path}", ip)
            self._rate_headers = {}
            self.send_json({"error": "Acceso no permitido desde esta red."}, 403)
            return False
        if path.startswith("/api"):
            ok, limit, remaining, reset = rate_limiter.check(ip, self.command, path)
            self._rate_headers = {"X-RateLimit-Limit": str(limit), "X-RateLimit-Remaining": str(remaining),
                                  "X-RateLimit-Reset": str(reset)}
            if not ok:
                self._rate_headers["Retry-After"] = str(reset)
                srv.audit_log("RATE_LIMITED", f"path={path}", ip)
                self.send_json({"error": f"Demasiadas solicitudes. Reintente en {reset} s."}, 429)
                return False
        try:
            self._check_auth()
        except srv.APIError as exc:
            srv.audit_log("AUTH_FAILED" if exc.status == 401 else "FORBIDDEN", f"path={path}", ip)
            body = {"error": exc.message}
            if getattr(exc, "password_expired", False):
                body["password_expired"] = True
            self.send_json(body, exc.status)
            return False
        return True

    original_headers = Handler._apply_security_headers

    def _apply_security_headers(self):
        original_headers(self)
        self.send_header("API-Version", API_VERSION)
        for k, v in getattr(self, "_rate_headers", {}).items():
            self.send_header(k, v)

    Handler._api_path = _api_path
    Handler._check_auth = _check_auth
    Handler._pre_check = _pre_check
    Handler._apply_security_headers = _apply_security_headers

    # ---------------- Rutas nuevas ----------------
    def _error(self, exc):
        self.send_json({"error": exc.message}, exc.status)

    def _auth_route(self, path):
        data = self.body_json()
        ip = self.client_ip()
        with srv.WRITE_LOCK, srv.connect() as conn:
            if path == "/api/auth/login":
                try:
                    result = auth.login(conn, str(data.get("email", "")), str(data.get("password", "")),
                                        srv.now_iso, str(data.get("otp", ""))[:20], ip,
                                        self.headers.get("User-Agent", "")[:300])
                except auth.MFARequired:
                    conn.commit()
                    raise
                except auth.AuthError as exc:
                    conn.commit()  # conserva el contador de intentos fallidos
                    srv.audit_log("LOGIN_FAILED", f"email={str(data.get('email', ''))[:120]}", ip)
                    _on_login_failure(exc, str(data.get("email", ""))[:120], ip)
                    raise
                audit.set_current_user(result["user"]["email"])
                device = auth.device_label(self.headers.get("User-Agent", ""))
                srv.audit_log("LOGIN", f"user={result['user']['email']} device={device}", ip)
                if result.get("new_ip"):
                    _alert_new_ip(result["user"]["email"], ip, device)
                if result.get("password_expired"):
                    srv.audit_log("PASSWORD_EXPIRED", f"user={result['user']['email']}", ip)
            elif path == "/api/auth/refresh":
                result = auth.refresh(conn, str(data.get("refresh_token", "")), ip)
            elif path in ("/api/auth/2fa/setup", "/api/auth/2fa/enable", "/api/auth/2fa/disable", "/api/auth/password"):
                uid = (self.user or {}).get("id")
                if not uid:
                    raise srv.APIError("Requiere una sesión de usuario (JWT).", 401)
                if path.endswith("/setup"):
                    result = auth.mfa_setup(conn, uid)
                elif path.endswith("/enable"):
                    result = auth.mfa_enable(conn, uid, str(data.get("code", "")))
                    srv.audit_log("MFA_ENABLED", f"user={self.user['email']}", ip)
                elif path.endswith("/disable"):
                    result = auth.mfa_disable(conn, uid, str(data.get("password", "")), str(data.get("code", "")))
                    srv.audit_log("MFA_DISABLED", f"user={self.user['email']}", ip)
                else:
                    result = auth.change_password(conn, uid, str(data.get("current", "")), str(data.get("new", "")),
                                                  srv.now_iso, self.user.get("sid", ""))
                    srv.audit_log("PASSWORD_CHANGED", f"user={self.user['email']}", ip)
            elif path == "/api/auth/sessions/revoke-others":
                uid = (self.user or {}).get("id")
                if not uid:
                    raise srv.APIError("Requiere una sesión de usuario (JWT).", 401)
                closed = auth.revoke_other_sessions(conn, uid, self.user.get("sid", ""))
                srv.audit_log("SESSIONS_REVOKED", f"user={self.user['email']} cerradas={closed}", ip)
                result = {"ok": True, "closed": closed}
            elif path == "/api/auth/logout":
                auth.revoke(conn, str(data.get("refresh_token", "")))
                srv.audit_log("LOGOUT", "", ip)
                result = {"ok": True}
            else:
                raise srv.APIError("Ruta API no encontrada.", 404)
        return result

    spray_lock = threading.Lock()
    spray_hits: dict = {}      # ip -> [(momento, correo)]
    spray_alerted: dict = {}   # ip -> momento de la última alerta

    def _on_login_failure(exc, email: str, ip: str) -> None:
        """Alertas de intentos fallidos: por cuenta (umbral y bloqueo) y por IP (rociado)."""
        when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        try:
            if isinstance(exc, auth.LoginFailed):
                if exc.locked:
                    srv.audit_log("ACCOUNT_LOCKED", f"user={exc.email} intentos={exc.attempts}", ip)
                if exc.locked or (auth.FAILED_ALERT_AT and exc.attempts == auth.FAILED_ALERT_AT):
                    srv.audit_log("LOGIN_FAILED_ALERT", f"user={exc.email} intentos={exc.attempts}", ip)
                    for to in {exc.email.lower(), NOTIFY_EMAIL.lower()} - {""}:
                        email_notifications.notify_failed_logins(to, exc.email, ip, exc.attempts, exc.locked, when)
            now = time.time()
            with spray_lock:
                hits = [h for h in spray_hits.get(ip, []) if now - h[0] < SPRAY_WINDOW] + [(now, email.lower())]
                spray_hits[ip] = hits[-200:]
                accounts = {h[1] for h in hits}
                suspicious = (len(accounts) >= SPRAY_ACCOUNTS or len(hits) >= SPRAY_FAILURES) \
                    and now - spray_alerted.get(ip, 0) > 3600
                if suspicious:
                    spray_alerted[ip] = now
                if len(spray_hits) > 5000:  # acota la memoria ante ataques distribuidos
                    for old in [k for k, v in spray_hits.items() if now - v[-1][0] > SPRAY_WINDOW]:
                        spray_hits.pop(old, None)
            if suspicious:
                srv.audit_log("SUSPICIOUS_IP", f"fallos={len(hits)} cuentas={len(accounts)}", ip)
                if NOTIFY_EMAIL:
                    email_notifications.notify_suspicious_ip(NOTIFY_EMAIL, ip, len(hits), len(accounts), when)
        except Exception as err:  # una alerta nunca debe alterar la respuesta del login
            print("Alerta de intentos fallidos no enviada:", err)

    def _alert_new_ip(email: str, ip: str, device: str) -> None:
        when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        srv.audit_log("LOGIN_NEW_IP", f"user={email} device={device}", ip)
        try:
            email_notifications.notify_new_login(email, email, ip, device, when)
            if NOTIFY_EMAIL and NOTIFY_EMAIL.lower() != email.lower():
                email_notifications.notify_new_login(NOTIFY_EMAIL, email, ip, device, when)
        except Exception as exc:  # la alerta nunca impide el inicio de sesión
            print("Alerta de nuevo acceso no enviada:", exc)

    def _events(self):
        q = bus.subscribe()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Connection", "close")
            self.send_header("X-Accel-Buffering", "no")
            self._apply_security_headers()
            self.end_headers()
            self.close_connection = True
            self.wfile.write(b"retry: 5000\nevent: ready\ndata: {}\n\n")
            self.wfile.flush()
            while True:
                try:
                    event = q.get(timeout=15)
                    payload = json.dumps(event, ensure_ascii=False)
                    self.wfile.write(f"event: change\ndata: {payload}\n\n".encode("utf-8"))
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            bus.unsubscribe(q)

    def _normalize_version(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/v1/") or parsed.path == "/api/v1":
            self.path = "/api" + self.path[len("/api/v1"):]

    original_get = Handler.do_GET
    original_post = Handler.do_POST
    original_delete = Handler.do_DELETE
    original_put = Handler.do_PUT

    def do_GET(self):
        self._normalize_version()
        path = self._api_path()
        qs = parse_qs(urlparse(self.path).query)
        routes = ("/api/auth/sessions", "/api/auth/me", "/api/audit", "/api/audit/verify", "/api/users", "/api/security/status", "/api/events", "/api/openapi.yaml", "/api/version")
        if path not in routes:
            return original_get(self)
        if not self._pre_check():
            return
        try:
            if path == "/api/events":
                return _events(self)
            if path == "/api/openapi.yaml":
                raw = (srv.ROOT / "docs" / "openapi.yaml").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "application/yaml; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self._apply_security_headers()
                self.end_headers()
                self.wfile.write(raw)
                return
            if path == "/api/version":
                result = {"version": API_VERSION, "api": ["v1"], "jwt": auth.JWT_ENABLED,
                          "realtime": "sse", "clients": bus.count}
            elif path == "/api/audit/verify":
                result = audit.verify_chain()
            elif path == "/api/security/status":
                result = {"jwt": auth.JWT_ENABLED, "require_admin_mfa": REQUIRE_ADMIN_MFA,
                          "ip_allowlist": bool(security.ALLOWLIST), "trusted_proxies": bool(security.TRUSTED_PROXIES),
                          "tls": bool(srv.TLS_CERT), "your_ip": self.client_ip(), "user": self.user,
                          "db_encryption": dbcrypt.status(srv.DB_PATH)["file_encrypted"] and dbcrypt.ENABLED,
                          "password_max_age_days": auth.PASSWORD_MAX_AGE_DAYS,
                          "password_history": auth.PASSWORD_HISTORY, "new_ip_alerts": True,
                          "failed_login_alert_at": auth.FAILED_ALERT_AT,
                          "offsite_backup": offsite.status() if self.user and self.user.get("role") == "admin"
                          else {"configured": offsite.configured()}}
            elif path == "/api/auth/me":
                result = {"user": self.user, "jwt": auth.JWT_ENABLED}
            elif path == "/api/auth/sessions":
                if not (self.user or {}).get("id"):
                    raise srv.APIError("Requiere una sesión de usuario (JWT).", 401)
                with srv.db_session() as conn:
                    result = auth.list_sessions(conn, self.user["id"], self.user.get("sid", ""))
            elif path == "/api/audit":
                first = lambda k, d="": qs.get(k, [d])[0]  # noqa: E731
                result = audit.query(limit=int(first("limit", "50")), offset=int(first("offset", "0")),
                                     action=first("action")[:80], search=first("q")[:100])
            else:  # /api/users
                with srv.db_session() as conn:
                    result = [dict(r) for r in conn.execute(
                        "SELECT id,email,name,role,active,created_at,last_login,totp_enabled AS mfa,must_change_password,"
                        "(locked_until > strftime('%s','now')) AS locked FROM users ORDER BY email")]
            self.send_json(result)
        except (ValueError, TypeError):
            self.send_json({"error": "Parámetros no válidos."}, 400)
        except srv.APIError as exc:
            _error(self, exc)

    def do_POST(self):
        self._normalize_version()
        path = self._api_path()
        restore = re.fullmatch(r"/api/(products|materials)/(\d+)/restore", path)
        if restore:
            # Consumir el cuerpo: si queda en el socket keep-alive corrompe la siguiente petición
            try:
                pending = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                pending = 0
            if 0 < pending <= 1_048_576:
                self.rfile.read(pending)
            if not self._pre_check():
                return
            kind, ident = restore.group(1), int(restore.group(2))
            try:
                with srv.WRITE_LOCK, srv.connect() as conn:
                    if kind == "products":
                        cur = conn.execute("UPDATE products SET active=1, deleted_at='', updated_at=? "
                                           "WHERE id=? AND (active=0 OR deleted_at<>'')", (srv.now_iso(), ident))
                    else:
                        cur = conn.execute("UPDATE materials SET status='Vigente', effective_to='', deleted_at='', updated_at=? "
                                           "WHERE id=? AND (status='Inactivo' OR deleted_at<>'')", (srv.now_iso(), ident))
                    if cur.rowcount == 0:
                        raise srv.APIError("Registro no encontrado o ya activo.", 404)
                srv.audit_log(f"RESTORE_{'PRODUCT' if kind == 'products' else 'MATERIAL'}", f"id={ident}", self.client_ip())
                return self.send_json({"ok": True, "restored": True})
            except srv.APIError as exc:
                return _error(self, exc)
        if not (path.startswith("/api/auth/") or path == "/api/users"):
            return original_post(self)
        if not self._pre_check():
            return
        try:
            if path == "/api/users":
                data = self.body_json()
                with srv.WRITE_LOCK, srv.connect() as conn:
                    result = auth.create_user(conn, data, srv.now_iso)
                srv.audit_log("CREATE_USER", f"email={result['email']} role={result['role']}", self.client_ip())
                return self.send_json(result, 201)
            self.send_json(_auth_route(self, path))
        except auth.MFARequired as exc:
            self.send_json({"error": exc.message, "mfa_required": True}, 401)
        except auth.AuthError as exc:
            self.send_json({"error": exc.message}, exc.status)
        except srv.APIError as exc:
            _error(self, exc)

    def do_DELETE(self):
        self._normalize_version()
        path = self._api_path()
        if path.startswith("/api/auth/sessions/"):
            if not self._pre_check():
                return
            try:
                if not (self.user or {}).get("id"):
                    raise srv.APIError("Requiere una sesión de usuario (JWT).", 401)
                sid = path.rsplit("/", 1)[-1][:64]
                with srv.WRITE_LOCK, srv.connect() as conn:
                    auth.revoke_session(conn, self.user["id"], sid)
                srv.audit_log("SESSION_REVOKED", f"user={self.user['email']}", self.client_ip())
                return self.send_json({"ok": True, "current": sid == self.user.get("sid")})
            except auth.AuthError as exc:
                return self.send_json({"error": exc.message}, exc.status)
            except srv.APIError as exc:
                return _error(self, exc)
        return original_delete(self)

    def do_PUT(self):
        self._normalize_version()
        path = self._api_path()
        if not path.startswith("/api/users/"):
            return original_put(self)
        if not self._pre_check():
            return
        try:
            user_id = int(path.split("/")[-1])
            data = self.body_json()
            actor = (self.user or {}).get("id")
            if actor is None:
                raise srv.APIError("Requiere una sesión de usuario (JWT).", 401)
            with srv.WRITE_LOCK, srv.connect() as conn:
                result = auth.update_user(conn, actor, user_id, data)
            changes = ",".join(k for k in ("role", "active", "unlock", "reset_mfa", "revoke_sessions",
                                           "force_password_change") if k in data)
            srv.audit_log("UPDATE_USER", f"id={user_id} cambios={changes}", self.client_ip())
            self.send_json(result)
        except ValueError:
            self.send_json({"error": "Identificador no válido."}, 400)
        except auth.AuthError as exc:
            self.send_json({"error": exc.message}, exc.status)
        except srv.APIError as exc:
            _error(self, exc)

    Handler._normalize_version = _normalize_version
    Handler.do_GET = do_GET
    Handler.do_POST = do_POST
    Handler.do_DELETE = do_DELETE
    Handler.do_PUT = do_PUT
