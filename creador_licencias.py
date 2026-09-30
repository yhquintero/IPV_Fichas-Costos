"""
IPV Fichas y Costos — Creador de Licencias (API del servidor, solo librería estándar).
Autor: Ing. Yosvany Hernández Quintero

Panel de administración (rol admin) que sustituye al Keygen de escritorio para el
trabajo del día a día. Sin salir de la aplicación permite:

  1. Crear la clave de firma ECDSA P-256 (la primera vez) → las licencias pasan de
     «desactivadas» a activadas AL INSTANTE, sin reiniciar el servidor. La clave
     privada se guarda cifrada con la contraseña del proveedor en
     keygen/clave_privada.json (mismo formato que el Keygen de escritorio, son
     intercambiables) y la clave pública se escribe en licencia.py y License.kt.
  2. Emitir licencias firmadas para cualquier código de solicitud IPVW-… (PC) o
     IPVA-… (móvil), con registro en el historial keygen/licencias.db (SQLite).
  3. Verificar licencias, consultar el historial y actualizar las tasas de cambio.

Rutas (todas solo para administradores, auditarlas en el visor de auditoría):
  GET  /api/keygen/status    — estado del sistema de licencias
  POST /api/keygen/init      — crear (o reemplazar) la clave de firma
  POST /api/keygen/emit      — emitir una licencia firmada
  POST /api/keygen/verify    — verificar una licencia
  GET  /api/keygen/ledger    — licencias emitidas
  POST /api/keygen/rates     — actualizar tasas de cambio

Seguridad: la contraseña de la clave NUNCA se guarda en el servidor; el cliente la
envía en cada operación y solo se usa en memoria para descifrar la clave privada.
Las rutas /api/keygen quedan exentas del bloqueo por licencia (LICENSE_FREE) para
que el proveedor pueda emitir una licencia nueva aunque la del servidor haya
vencido; siguen exigiendo autenticación y rol admin.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from pathlib import Path

from urllib.parse import parse_qs, urlparse

import licencia as L
from keygen import historial as H
from keygen import keygen as kg

ROOT = Path(L.__file__).resolve().parent
# Clave, tasas e historial se comparten con el Keygen Web y el de escritorio (keygen/keygen.py:
# kg.KEY_FILE, kg.RATES_FILE y keygen.historial.DB_FILE son la única fuente de verdad; las
# pruebas los redirigen a un directorio temporal).
#
# Para dar un servicio completo al proveedor (usuarios, roles, 2FA, historial con filtros,
# anulaciones y pagos) use el Keygen Web:  python keygen/keygen.py
LICENCIA_PY = ROOT / "licencia.py"
LICENSE_KT = ROOT / "android" / "app" / "src" / "main" / "java" / "cu" / "ipvcostos" / "app" / "License.kt"

_LOCK = threading.Lock()


def fingerprint(pub_hex: str) -> str:
    """Huella corta y verificable a simple vista de la clave pública."""
    digest = hashlib.sha256(pub_hex.encode("ascii")).hexdigest()[:16].upper()
    return "-".join(digest[i:i + 4] for i in range(0, 16, 4))


def clean_phone(num: str) -> str:
    digits = re.sub(r"\D", "", num or "")
    if digits and not 8 <= len(digits) <= 15:
        raise ValueError("Número de WhatsApp no válido. Formato internacional sin «+»: 5355555555")
    return digits


# ------------------------------------------------------------- operaciones ----
def patch_files(pub_hex: str, whatsapp: str) -> list[str]:
    """Escribe la clave pública y el WhatsApp en licencia.py y License.kt."""
    changed = []
    if LICENCIA_PY.exists():
        s = LICENCIA_PY.read_text(encoding="utf-8")
        s = re.sub(r'^PUBLIC_KEY_HEX = ".*"$', f'PUBLIC_KEY_HEX = "{pub_hex}"', s, count=1, flags=re.MULTILINE)
        s = re.sub(r'^WHATSAPP_NUMBER = ".*"$', f'WHATSAPP_NUMBER = "{whatsapp}"', s, count=1, flags=re.MULTILINE)
        LICENCIA_PY.write_text(s, encoding="utf-8")
        changed.append("licencia.py")
    if LICENSE_KT.exists():
        k = LICENSE_KT.read_text(encoding="utf-8")
        k = re.sub(r'const val PUBLIC_KEY_B64 = ".*"', f'const val PUBLIC_KEY_B64 = "{L.spki_der_b64(pub_hex)}"', k, count=1)
        k = re.sub(r'const val WHATSAPP_NUMBER = ".*"', f'const val WHATSAPP_NUMBER = "{whatsapp}"', k, count=1)
        LICENSE_KT.write_text(k, encoding="utf-8")
        changed.append("License.kt")
    return changed


def activate_runtime(pub_hex: str, whatsapp: str) -> None:
    """Activa el sistema de licencias en el servidor en marcha, sin reiniciar."""
    L.PUBLIC_KEY_HEX = pub_hex
    L.WHATSAPP_NUMBER = whatsapp
    store = _store()
    if store is not None:
        store.pub = pub_hex
        store._cache = None


def _store():
    return getattr(_SRV, "LICENSE", None)


_SRV = None  # módulo server (lo fija install)


def status() -> dict:
    pub = (L.PUBLIC_KEY_HEX or "").strip().lower()
    store = _store()
    lic = {}
    if store is not None:
        st = store.status()
        lic = {"enforced": st.get("enforced", False), "valid": st.get("valid", False),
               "reason": st.get("reason", ""), "request_code": st.get("request_code", ""),
               "plan_name": st.get("plan_name", ""), "user": st.get("user", ""),
               "days_left": st.get("days_left"), "expires_at": st.get("expires_at")}
    rates = kg.rates()
    usd = rates.get("USD", 1)
    plans = {k: {"name": v[0], "days": v[1], "usd_web": v[2], "usd_android": v[3],
                 "cup_web": round(v[2] * usd, 2), "cup_android": round(v[3] * usd, 2)}
             for k, v in L.PLANS.items()}
    count = 0
    if H.DB_FILE.exists():  # consultar el estado nunca debe crear el historial como efecto secundario
        try:
            conn = H.connect()
            try:
                H.init(conn)
                count = H.count(conn)
            finally:
                conn.close()
        except Exception:  # un historial ilegible no debe impedir ver el estado
            count = 0
    return {"configured": bool(pub), "fingerprint": fingerprint(pub) if pub else "",
            "has_key_file": kg.KEY_FILE.exists(), "whatsapp": L.WHATSAPP_NUMBER or "",
            "plans": plans, "rates": rates, "ledger_count": count, "license": lic}


def init_key(passphrase: str, whatsapp: str, force: bool = False) -> dict:
    """Crea la clave de firma, la guarda cifrada y activa las licencias al instante."""
    passphrase = str(passphrase or "")
    if len(passphrase) < 10:
        raise ValueError("La contraseña de la clave debe tener al menos 10 caracteres.")
    phone = clean_phone(whatsapp)
    with _LOCK:
        if kg.KEY_FILE.exists() and not force:
            raise ValueError("Ya existe una clave de firma. Marque «Reemplazar clave» solo si desea "
                             "invalidar TODAS las licencias emitidas.")
        d, pub = L.generate_keypair()
        kg.save_private_key(d, passphrase, kg.KEY_FILE)
        changed = patch_files(pub, phone)
    activate_runtime(pub, phone)
    return {"ok": True, "fingerprint": fingerprint(pub), "whatsapp": phone,
            "patched": changed, **{k: v for k, v in status().items() if k != "rates"}}


def emit_license(user: str, code: str, plan: str, passphrase: str,
                 start_date: str | None = None, end_date: str | None = None,
                 custom_price_usd: str | int | float | None = None, actor: str = "") -> dict:
    """Emite una licencia firmada; PX usa fechas inclusivas UTC y precio manual."""
    app, _body = L.parse_request_code(str(code or ""))
    plan = str(plan or "").upper()
    if plan not in L.PLANS:
        raise ValueError(f"Plan desconocido: {plan}. Opciones: {', '.join(L.PLANS)}")
    if plan == "PX":
        if not start_date or not end_date or custom_price_usd is None or str(custom_price_usd).strip() == "":
            raise ValueError("El plan PX requiere Desde, Hasta y precio acordado en USD.")
    elif start_date is not None or end_date is not None or custom_price_usd is not None:
        raise ValueError("Las fechas y el precio manual solo se admiten con el plan PX.")
    with _LOCK:
        try:
            d = kg.load_private_key(str(passphrase or ""), kg.KEY_FILE)
        except SystemExit as exc:
            raise ValueError("Aún no existe la clave de firma: cree primero la clave en este panel.") from exc
        token, reply = kg.emit(d, str(user or ""), str(code or ""), plan,
                               start_date, end_date, custom_price_usd,
                               created_by=actor, source="embebido")
    data = L.decode(token, L.public_from_private(d))
    usd = kg.price_usd(app, plan, custom_price_usd)
    cup = round(usd * kg.rates()["USD"], 2)
    return {"ok": True, "license": token, "reply": reply, "user": data["usr"], "plan": plan,
            "plan_name": L.PLANS[plan][0], "app": app, "app_name": L.APP_NAMES[app],
            "serial": data["sn"], "issued_at": data["iat"], "expires_at": data["exp"],
            "valid_from": data.get("start_date"), "valid_until": data.get("end_date"),
            "price_usd": usd, "price_cup": cup}


def verify_license(token: str) -> dict:
    pub = kg.current_public()
    if not pub:
        pub = (L.PUBLIC_KEY_HEX or "").strip().lower()
    if not pub:
        raise ValueError("No hay clave pública configurada: cree primero la clave de firma.")
    data = L.decode(str(token or ""), pub)
    return {"ok": True, "signature": "Válida ✔", **L.public_info(data, time.time()),
            "app": data["app"], "app_name": L.APP_NAMES.get(data["app"], data["app"]),
            "device": data["dev"]}


def ledger_rows(limit: int = 100) -> list[dict]:
    """Licencias emitidas, la más reciente primero (mismos campos que el antiguo registro CSV)."""
    conn = H.connect()
    try:
        H.init(conn)
        with H.LOCK, conn:
            kg.import_legacy(conn)  # primera vez: incorpora el registro_licencias.csv antiguo
        items = H.recent(conn, limit)
    finally:
        conn.close()
    return [{"fecha": i["created_at"][:16].replace("T", " "), "serie": i["serial"], "usuario": i["customer"],
             "app": i["app"], "plan": i["plan"], "desde": i["valid_from"], "hasta": i["valid_until"],
             "vence": i["valid_until"] or time.strftime("%Y-%m-%d", time.gmtime(i["expires_at"])),
             "codigo_solicitud": i["request_code"], "precio_usd": i["price_usd"], "precio_cup": i["price_cup"],
             "estado": i["state_label"], "emitida_por": i["created_by"]} for i in items]


def save_rates(rates: dict) -> dict:
    """Actualiza keygen/tasas.json (solo divisas conocidas, valores positivos)."""
    clean = {}
    for key, value in dict(rates or {}).items():
        if key not in kg.DEFAULT_RATES:
            continue
        try:
            num = round(float(str(value).replace(",", ".")), 2)
        except (TypeError, ValueError):
            raise ValueError(f"Tasa no válida para {key}: {value!r}")
        if num <= 0:
            raise ValueError(f"La tasa de {key} debe ser mayor que cero.")
        clean[key] = num
    if not clean:
        raise ValueError("Indique al menos una tasa de cambio.")
    kg.RATES_FILE.parent.mkdir(parents=True, exist_ok=True)
    kg.RATES_FILE.write_text(json.dumps({**kg.rates(), **clean}, indent=2), encoding="utf-8")
    return kg.rates()


# ---------------------------------------------------------- integración -------
def install(srv) -> None:
    """Registra las rutas /api/keygen en el servidor (solo administradores)."""
    global _SRV
    _SRV = srv
    # El Creador debe funcionar aunque la licencia del servidor esté ausente o vencida
    srv.licencia.LICENSE_FREE = tuple(srv.licencia.LICENSE_FREE) + ("/api/keygen",)
    # Rol admin obligatorio (en enterprise._check_auth)
    import enterprise
    enterprise.ADMIN_ONLY = tuple(enterprise.ADMIN_ONLY) + ("/api/keygen",)
    print("[KEYGEN] Creador de Licencias disponible en /api/keygen (solo administradores).")

    Handler = srv.Handler
    original_get, original_post = Handler.do_GET, Handler.do_POST

    def _deny(self, message: str, code: int) -> None:
        self.send_json({"error": message}, code)

    def do_GET(self):
        path = self._api_path()
        if not path.startswith("/api/keygen"):
            return original_get(self)
        try:
            if not self._pre_check():
                return None
            if path == "/api/keygen/status":
                return self.send_json(status())
            if path == "/api/keygen/ledger":
                qs = parse_qs(urlparse(self.path).query)
                raw_limits = qs.get("limit", ["100"])
                raw_limit = raw_limits[0]
                if (len(raw_limits) != 1 or len(raw_limit) > 4 or
                        not raw_limit.isascii() or not raw_limit.isdigit()):
                    return _deny(self, "El límite del historial debe ser un entero decimal positivo.", 400)
                return self.send_json({"items": ledger_rows(int(raw_limit))})
            return _deny(self, "Ruta del Creador de Licencias no encontrada.", 404)
        except srv.APIError as exc:
            return self.send_json({"error": exc.message}, exc.status)
        except (ValueError, TypeError) as exc:
            return self.send_json({"error": str(exc)}, 400)
        except Exception as exc:  # pragma: no cover
            print("KEYGEN GET error:", repr(exc))
            return self.send_json({"error": "Error interno del Creador de Licencias."}, 500)

    def do_POST(self):
        path = self._api_path()
        if not path.startswith("/api/keygen"):
            return original_post(self)
        try:
            if not self._pre_check():
                return None
            data = self.body_json()
            if path == "/api/keygen/init":
                result = init_key(data.get("passphrase", ""), data.get("whatsapp", ""),
                                  bool(data.get("force", False)))
                srv.audit_log("LICENSE_KEYGEN_INIT", f"huella={result['fingerprint']} "
                              f"archivos={','.join(result['patched'])}", self.client_ip())
                return self.send_json(result)
            if path == "/api/keygen/emit":
                result = emit_license(data.get("user", ""), data.get("code", ""),
                                      data.get("plan", ""), data.get("passphrase", ""),
                                      data.get("start_date"), data.get("end_date"),
                                      data.get("custom_price_usd"),
                                      actor=(getattr(self, "user", None) or {}).get("username", ""))
                srv.audit_log("LICENSE_ISSUED", f"usuario={result['user']} app={result['app']} "
                              f"plan={result['plan']} serie={result['serial']}", self.client_ip())
                return self.send_json(result)
            if path == "/api/keygen/verify":
                return self.send_json(verify_license(data.get("license", "")))
            if path == "/api/keygen/rates":
                result = save_rates(data.get("rates", {}))
                srv.audit_log("LICENSE_RATES_UPDATED", f"USD={result.get('USD')}", self.client_ip())
                return self.send_json({"ok": True, "rates": result})
            return _deny(self, "Ruta del Creador de Licencias no encontrada.", 404)
        except srv.APIError as exc:
            return self.send_json({"error": exc.message}, exc.status)
        except (ValueError, TypeError) as exc:
            return self.send_json({"error": str(exc)}, 400)
        except Exception as exc:  # pragma: no cover
            print("KEYGEN POST error:", repr(exc))
            return self.send_json({"error": "Error interno del Creador de Licencias."}, 500)

    Handler.do_GET = do_GET
    Handler.do_POST = do_POST
