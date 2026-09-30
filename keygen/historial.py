"""IPV Keygen — historial completo de licencias en SQLite (solo librería estándar).

Es la única fuente de verdad de las licencias emitidas (antes: registro_licencias.csv).
Lo comparten el Keygen Web (keygen/webapp.py), el Keygen de escritorio (keygen.py, CLI y
ventana) y el Creador de Licencias integrado en la app: emitan desde donde emitan, todo
queda en keygen/licencias.db con su cliente, plan, vigencia, precio, pago, quién la creó
y una línea de tiempo de eventos (emitida, renovada, reenviada, anulada, pagada…).

Reglas de diseño:
  * Nada se borra: una licencia anulada solo cambia de estado y queda el motivo y el autor.
  * Las licencias se identifican por su número de serie (`sn`, único y firmado en el token).
  * El registro antiguo (registro_licencias.csv) se importa una sola vez y sin duplicar.
  * Las consultas devuelven el estado calculado: vigente · por_vencer · programada ·
    vencida · revocada.
"""
from __future__ import annotations

import csv
import io
import os
import sqlite3
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

try:  # con IPV_DB_KEY la base también se cifra; el Keygen puede usarse sin este módulo
    import dbcrypt
except ImportError:  # pragma: no cover - depende de cómo se distribuya el Keygen
    dbcrypt = None

HERE = Path(__file__).resolve().parent


def home() -> Path:
    """Carpeta de datos del Keygen: por defecto keygen/; con KEYGEN_HOME se puede sacar del
    repositorio (p. ej. a una unidad cifrada). Allí van clave_privada.json, tasas.json,
    licencias.db y web_secret.key."""
    return Path(os.environ.get("KEYGEN_HOME") or HERE)


DB_FILE = home() / "licencias.db"          # las pruebas lo redirigen a un directorio temporal
LEGACY_CSV = home() / "registro_licencias.csv"
DAY = 86400
EXPIRING_DAYS = 7                           # «por vencer»: igual que el aviso de la app
STATES = ("vigente", "por_vencer", "programada", "vencida", "revocada")
STATE_LABELS = {"vigente": "Vigente", "por_vencer": "Por vencer", "programada": "Programada",
                "vencida": "Vencida", "revocada": "Anulada"}
LOCK = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS licenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    serial TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    created_by TEXT NOT NULL DEFAULT '',
    customer TEXT NOT NULL,
    contact TEXT NOT NULL DEFAULT '',
    app TEXT NOT NULL,
    plan TEXT NOT NULL,
    request_code TEXT NOT NULL DEFAULT '',
    device TEXT NOT NULL DEFAULT '',
    issued_at INTEGER NOT NULL DEFAULT 0,
    valid_from TEXT NOT NULL DEFAULT '',
    valid_until TEXT NOT NULL DEFAULT '',
    expires_at INTEGER NOT NULL DEFAULT 0,
    price_usd REAL NOT NULL DEFAULT 0,
    price_cup REAL NOT NULL DEFAULT 0,
    usd_rate REAL NOT NULL DEFAULT 0,
    paid INTEGER NOT NULL DEFAULT 0,
    paid_at TEXT NOT NULL DEFAULT '',
    pay_method TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    token TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','revoked')),
    revoked_at TEXT NOT NULL DEFAULT '',
    revoked_by TEXT NOT NULL DEFAULT '',
    revoked_reason TEXT NOT NULL DEFAULT '',
    renewed_from TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT 'web'
);
CREATE INDEX IF NOT EXISTS idx_lic_created ON licenses(created_at);
CREATE INDEX IF NOT EXISTS idx_lic_customer ON licenses(customer COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_lic_device ON licenses(device);
CREATE INDEX IF NOT EXISTS idx_lic_expires ON licenses(expires_at);
CREATE TABLE IF NOT EXISTS license_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    license_id INTEGER NOT NULL,
    at TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_evt_license ON license_events(license_id);
"""

# Estado calculado en SQL: así se puede filtrar, contar y ordenar sin cargar todo en memoria.
STATE_SQL = ("CASE WHEN status='revoked' THEN 'revocada' "
             "WHEN expires_at <= :now THEN 'vencida' "
             "WHEN valid_from <> '' AND valid_from > :today THEN 'programada' "
             f"WHEN expires_at - :now <= {EXPIRING_DAYS * DAY} THEN 'por_vencer' "
             "ELSE 'vigente' END")

SORTABLE = {"created_at": "created_at", "customer": "customer COLLATE NOCASE", "plan": "plan",
            "expires_at": "expires_at", "price_usd": "price_usd", "serial": "serial", "app": "app"}


class HistorialError(ValueError):
    """Dato no válido o registro inexistente (se muestra tal cual al usuario)."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


# ---------------------------------------------------------------- conexión ----
def connect(path=None):
    """Conexión al historial (SQLite, o SQLCipher si IPV_DB_KEY está definida)."""
    target = Path(path) if path else DB_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = dbcrypt.connect(target, timeout=20) if dbcrypt else sqlite3.connect(str(target), timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 20000")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init(conn) -> None:
    conn.executescript(SCHEMA)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _own(conn):
    """Devuelve (conexión, cerrar): abre una propia si no se recibió ninguna."""
    if conn is not None:
        return conn, False
    own = connect()
    init(own)
    return own, True


# ---------------------------------------------------------------- escritura ----
def add_event(conn, license_id: int, actor: str, action: str, detail: str = "") -> None:
    conn.execute("INSERT INTO license_events(license_id,at,actor,action,detail) VALUES(?,?,?,?,?)",
                 (license_id, now_iso(), actor[:80], action[:30], detail[:500]))


def record_issue(*, token: str, data: dict, request_code: str, price_usd: float, price_cup: float,
                 usd_rate: float, created_by: str = "", contact: str = "", notes: str = "",
                 paid: bool = False, pay_method: str = "", renewed_from: str = "",
                 source: str = "web", conn=None) -> dict:
    """Guarda una licencia recién firmada. `data` es el contenido ya verificado del token."""
    conn, close = _own(conn)
    try:
        with LOCK:
            cur = conn.execute(
                "INSERT INTO licenses(serial,created_at,created_by,customer,contact,app,plan,request_code,device,"
                "issued_at,valid_from,valid_until,expires_at,price_usd,price_cup,usd_rate,paid,paid_at,pay_method,"
                "notes,token,renewed_from,source) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (data["sn"], now_iso(), created_by[:80], data["usr"], contact.strip()[:120], data["app"],
                 data["plan"], request_code.strip().upper()[:80], data["dev"], int(data["iat"]),
                 data.get("start_date", ""), data.get("end_date", ""), int(data["exp"]),
                 float(price_usd), float(price_cup), float(usd_rate), 1 if paid else 0,
                 now_iso() if paid else "", pay_method.strip()[:40], notes.strip()[:1000], token,
                 renewed_from.strip().upper()[:20], source[:20]))
            lid = cur.lastrowid
            add_event(conn, lid, created_by, "RENEWED" if renewed_from else "ISSUED",
                      f"Plan {data['plan']}" + (f" · renueva {renewed_from.upper()}" if renewed_from else ""))
            if paid:
                add_event(conn, lid, created_by, "PAID", pay_method.strip()[:40])
            if close:
                conn.commit()
        return get(conn, lid)
    finally:
        if close:
            conn.close()


def _require(conn, license_id):
    row = get(conn, license_id)
    if not row:
        raise HistorialError("Licencia no encontrada.", 404)
    return row


def revoke(conn, license_id, actor: str, reason: str) -> dict:
    reason = " ".join(str(reason or "").split())[:300]
    if len(reason) < 3:
        raise HistorialError("Indique el motivo de la anulación (mínimo 3 caracteres).")
    row = _require(conn, license_id)
    if row["status"] == "revoked":
        raise HistorialError("La licencia ya está anulada.", 409)
    conn.execute("UPDATE licenses SET status='revoked', revoked_at=?, revoked_by=?, revoked_reason=? WHERE id=?",
                 (now_iso(), actor[:80], reason, row["id"]))
    add_event(conn, row["id"], actor, "REVOKED", reason)
    return get(conn, row["id"])


def reactivate(conn, license_id, actor: str) -> dict:
    row = _require(conn, license_id)
    if row["status"] != "revoked":
        raise HistorialError("La licencia no está anulada.", 409)
    conn.execute("UPDATE licenses SET status='active', revoked_at='', revoked_by='', revoked_reason='' WHERE id=?",
                 (row["id"],))
    add_event(conn, row["id"], actor, "REACTIVATED", f"Antes anulada: {row['revoked_reason']}")
    return get(conn, row["id"])


def update_fields(conn, license_id, actor: str, changes: dict, allow_notes: bool = True,
                  allow_money: bool = False) -> dict:
    """Edita datos de gestión. Nunca toca lo firmado (plan, fechas, dispositivo, serie)."""
    row = _require(conn, license_id)
    sets, params, events = [], [], []
    if "notes" in changes or "contact" in changes:
        if not allow_notes:
            raise HistorialError("Su rol no puede editar las notas ni el contacto.", 403)
        if "notes" in changes:
            sets.append("notes=?"); params.append(str(changes["notes"] or "").strip()[:1000])
            events.append(("NOTE", "Notas actualizadas"))
        if "contact" in changes:
            sets.append("contact=?"); params.append(str(changes["contact"] or "").strip()[:120])
    if "paid" in changes or "pay_method" in changes:
        if not allow_money:
            raise HistorialError("Su rol no puede registrar pagos.", 403)
        if "pay_method" in changes:
            sets.append("pay_method=?"); params.append(str(changes["pay_method"] or "").strip()[:40])
        if "paid" in changes:
            paid = bool(changes["paid"])
            if paid != bool(row["paid"]):
                sets += ["paid=?", "paid_at=?"]
                params += [1 if paid else 0, now_iso() if paid else ""]
                events.append(("PAID" if paid else "UNPAID",
                               str(changes.get("pay_method", row["pay_method"]) or "")[:40]))
    if not sets:
        raise HistorialError("No hay cambios que guardar.")
    conn.execute(f"UPDATE licenses SET {', '.join(sets)} WHERE id=?", (*params, row["id"]))  # nosec B608
    for action, detail in events:
        add_event(conn, row["id"], actor, action, detail)
    return get(conn, row["id"])


# ---------------------------------------------------------------- lectura ------
def _decorate(row, now: float | None = None) -> dict:
    now = time.time() if now is None else now
    item = dict(row)
    item["paid"] = bool(item["paid"])
    item["state"] = state_of(item, now)
    item["state_label"] = STATE_LABELS[item["state"]]
    item["days_left"] = max(0, int((item["expires_at"] - now) // DAY)) if item["expires_at"] else None
    item["has_token"] = bool(item.get("token"))
    return item


def state_of(item, now: float | None = None) -> str:
    now = time.time() if now is None else now
    if item["status"] == "revoked":
        return "revocada"
    if item["expires_at"] and item["expires_at"] <= now:
        return "vencida"
    if item["valid_from"] and item["valid_from"] > datetime.fromtimestamp(now, timezone.utc).date().isoformat():
        return "programada"
    if item["expires_at"] and item["expires_at"] - now <= EXPIRING_DAYS * DAY:
        return "por_vencer"
    return "vigente"


def get(conn, license_id) -> dict | None:
    """Licencia por identificador numérico."""
    row = conn.execute("SELECT * FROM licenses WHERE id=?", (int(license_id),)).fetchone()
    return _decorate(row) if row else None


def by_serial(conn, serial: str) -> dict | None:
    """Licencia por número de serie (8 caracteres hexadecimales)."""
    row = conn.execute("SELECT * FROM licenses WHERE serial=?", (str(serial).strip().upper(),)).fetchone()
    return _decorate(row) if row else None


def recent(conn, limit: int = 100) -> list[dict]:
    """Las últimas licencias emitidas (la más reciente primero)."""
    rows = conn.execute("SELECT * FROM licenses ORDER BY id DESC LIMIT ?", (max(1, min(int(limit), 500)),))
    now = time.time()
    return [_decorate(r, now) for r in rows]


def count(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM licenses").fetchone()[0]


def events(conn, license_id: int) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT id,at,actor,action,detail FROM license_events WHERE license_id=? ORDER BY id DESC",
        (license_id,))]


def _where(filters: dict, only_actor: str | None = None):
    """Condiciones comunes de las consultas (lista, exportación y estadísticas)."""
    now = time.time()
    where, params = ["1=1"], {"now": now, "today": _today()}
    q = " ".join(str(filters.get("q", "")).split())[:80]
    if q:
        params["q"] = f"%{q.replace('%', '').replace('_', '')}%"
        where.append("(serial LIKE :q OR customer LIKE :q OR contact LIKE :q OR request_code LIKE :q "
                     "OR notes LIKE :q OR created_by LIKE :q OR device LIKE :q)")
    state = str(filters.get("state", "")).strip()
    if state:
        if state not in STATES:
            raise HistorialError("Estado no válido.")
        params["state"] = state
        where.append(f"({STATE_SQL}) = :state")
    plan = str(filters.get("plan", "")).strip().upper()
    if plan:
        params["plan"] = plan
        where.append("plan = :plan")
    app = str(filters.get("app", "")).strip().upper()[:1]
    if app in ("W", "A"):
        params["app"] = app
        where.append("app = :app")
    paid = str(filters.get("paid", "")).strip().lower()
    if paid in ("1", "si", "sí", "yes", "true"):
        where.append("paid = 1")
    elif paid in ("0", "no", "false"):
        where.append("paid = 0 AND status = 'active'")
    for key, op in (("from", ">="), ("to", "<=")):
        value = str(filters.get(key, "")).strip()
        if value:
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise HistorialError("Las fechas del filtro deben tener el formato AAAA-MM-DD.") from exc
            params[f"d_{key}"] = value if key == "from" else (date.fromisoformat(value) + timedelta(days=1)).isoformat()
            where.append(f"created_at {op if key == 'from' else '<'} :d_{key}")
    by = str(filters.get("created_by", "")).strip()
    if by:
        params["by"] = by
        where.append("created_by = :by COLLATE NOCASE")
    if only_actor is not None:  # rol operador: solo ve lo que él mismo emitió
        params["actor"] = only_actor
        where.append("created_by = :actor COLLATE NOCASE")
    return " AND ".join(where), params


def query(conn, filters: dict | None = None, only_actor: str | None = None, hide_prices: bool = False) -> dict:
    filters = filters or {}
    where, params = _where(filters, only_actor)
    try:
        limit = max(1, min(int(filters.get("limit", 25)), 200))
        offset = max(0, int(filters.get("offset", 0)))
    except (TypeError, ValueError) as exc:
        raise HistorialError("Paginación no válida.") from exc
    sort = SORTABLE.get(str(filters.get("sort", "created_at")), "created_at")
    direction = "ASC" if str(filters.get("dir", "desc")).lower() == "asc" else "DESC"
    total = conn.execute(f"SELECT COUNT(*) FROM licenses WHERE {where}", params).fetchone()[0]  # nosec B608
    rows = conn.execute(f"SELECT * FROM licenses WHERE {where} ORDER BY {sort} {direction}, id DESC "  # nosec B608
                        "LIMIT :limit OFFSET :offset", {**params, "limit": limit, "offset": offset}).fetchall()
    now = params["now"]
    items = [_decorate(r, now) for r in rows]
    if hide_prices:
        items = [strip_prices(i) for i in items]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def strip_prices(item: dict) -> dict:
    """Quita los importes y los datos de cobro (roles sin acceso a precios)."""
    hidden = ("price_usd", "price_cup", "usd_rate", "pay_method", "paid_at", "paid")
    clean = {k: (None if k in hidden else v) for k, v in item.items()}
    clean["prices_hidden"] = True
    return clean


def stats(conn, only_actor: str | None = None, with_money: bool = True) -> dict:
    """Cifras del panel: estados, ingresos, vencimientos cercanos y evolución mensual."""
    now = time.time()
    where, params = _where({}, only_actor)
    rows = conn.execute(f"SELECT *, ({STATE_SQL}) AS st FROM licenses WHERE {where}", params).fetchall()  # nosec B608
    out = {"total": len(rows), "by_state": {s: 0 for s in STATES}, "by_plan": {}, "by_app": {"W": 0, "A": 0},
           "expiring": [], "months": [], "with_money": with_money}
    month_key = datetime.now(timezone.utc).strftime("%Y-%m")
    revenue_usd = revenue_cup = unpaid_usd = unpaid_cup = month_usd = month_cup = 0.0
    unpaid = 0
    months: dict[str, dict] = {}
    for r in rows:
        st = r["st"]
        out["by_state"][st] += 1
        out["by_plan"][r["plan"]] = out["by_plan"].get(r["plan"], 0) + 1
        out["by_app"][r["app"]] = out["by_app"].get(r["app"], 0) + 1
        bucket = months.setdefault(r["created_at"][:7], {"month": r["created_at"][:7], "count": 0, "usd": 0.0})
        bucket["count"] += 1
        if st != "revocada":  # una licencia anulada no cuenta como ingreso
            bucket["usd"] += r["price_usd"]
            revenue_usd += r["price_usd"]
            revenue_cup += r["price_cup"]
            if r["created_at"][:7] == month_key:
                month_usd += r["price_usd"]
                month_cup += r["price_cup"]
            if not r["paid"]:
                unpaid += 1
                unpaid_usd += r["price_usd"]
                unpaid_cup += r["price_cup"]
        if st in ("vigente", "por_vencer") and r["expires_at"] - now <= 30 * DAY:
            out["expiring"].append({"id": r["id"], "serial": r["serial"], "customer": r["customer"],
                                    "app": r["app"], "plan": r["plan"], "expires_at": r["expires_at"],
                                    "valid_until": r["valid_until"], "days_left": max(0, int((r["expires_at"] - now) // DAY)),
                                    "contact": r["contact"]})
    out["expiring"].sort(key=lambda e: e["expires_at"])
    out["expiring"] = out["expiring"][:10]
    # Últimos 12 meses consecutivos (con ceros) para el gráfico
    cursor = datetime.now(timezone.utc).replace(day=1)
    keys = []
    for _ in range(12):
        keys.append(cursor.strftime("%Y-%m"))
        cursor = (cursor - timedelta(days=1)).replace(day=1)
    out["months"] = [months.get(k, {"month": k, "count": 0, "usd": 0.0}) for k in reversed(keys)]
    if with_money:
        out["money"] = {"revenue_usd": round(revenue_usd, 2), "revenue_cup": round(revenue_cup, 2),
                        "month_usd": round(month_usd, 2), "month_cup": round(month_cup, 2),
                        "unpaid_count": unpaid, "unpaid_usd": round(unpaid_usd, 2), "unpaid_cup": round(unpaid_cup, 2)}
    else:
        for m in out["months"]:
            m["usd"] = None
    return out


def recent_events(conn, limit: int = 12, only_actor: str | None = None) -> list[dict]:
    sql = ("SELECT e.at,e.actor,e.action,e.detail,l.serial,l.customer FROM license_events e "
           "JOIN licenses l ON l.id=e.license_id")
    params: list = []
    if only_actor is not None:
        sql += " WHERE l.created_by = ? COLLATE NOCASE"
        params.append(only_actor)
    sql += " ORDER BY e.id DESC LIMIT ?"
    params.append(max(1, min(int(limit), 50)))
    return [dict(r) for r in conn.execute(sql, params)]


# ---------------------------------------------------------------- exportación --
EXPORT_COLUMNS = [("serial", "serie"), ("created_at", "fecha"), ("customer", "cliente"), ("contact", "contacto"),
                  ("app", "app"), ("plan", "plan"), ("valid_from", "desde"), ("valid_until", "hasta"),
                  ("expires_at", "vence"), ("state_label", "estado"), ("price_usd", "precio_usd"),
                  ("price_cup", "precio_cup"), ("paid", "pagada"), ("pay_method", "metodo_pago"),
                  ("created_by", "emitida_por"), ("request_code", "codigo_solicitud"),
                  ("renewed_from", "renueva_a"), ("revoked_reason", "motivo_anulacion"), ("notes", "notas")]
MONEY_COLUMNS = {"price_usd", "price_cup", "paid", "pay_method"}


def _csv_safe(value) -> str:
    """Evita la inyección de fórmulas al abrir el CSV en Excel/LibreOffice."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def export_csv(conn, filters: dict | None = None, only_actor: str | None = None,
               include_prices: bool = True) -> str:
    filters = dict(filters or {})
    filters.update({"limit": 200, "offset": 0})
    columns = [c for c in EXPORT_COLUMNS if include_prices or c[0] not in MONEY_COLUMNS]
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow([label for _, label in columns])
    offset = 0
    while True:
        page = query(conn, {**filters, "offset": offset}, only_actor)
        for item in page["items"]:
            row = []
            for key, _ in columns:
                value = item.get(key)
                if key == "expires_at":
                    value = item["valid_until"] or datetime.fromtimestamp(item["expires_at"], timezone.utc).date().isoformat()
                elif key == "paid":
                    value = "sí" if item["paid"] else "no"
                elif key == "app":
                    value = "Web" if item["app"] == "W" else "Android"
                row.append(_csv_safe(value))
            writer.writerow(row)
        offset += page["limit"]
        if offset >= page["total"]:
            break
    return "\ufeff" + buffer.getvalue()  # BOM: Excel abre los acentos correctamente


# ---------------------------------------------------------------- importación --
def import_legacy_csv(conn, source=None) -> dict:
    """Importa registro_licencias.csv (o un texto CSV con esas columnas). Idempotente por serie."""
    if source is None:
        if not LEGACY_CSV.exists():
            return {"imported": 0, "skipped": 0, "invalid": 0, "found": False}
        text = LEGACY_CSV.read_text(encoding="utf-8-sig")
    else:
        text = str(source).lstrip("\ufeff")
    try:
        from licencia import PLANS
    except ImportError:  # pragma: no cover
        PLANS = {}
    imported = skipped = invalid = 0
    for row in csv.DictReader(io.StringIO(text)):
        serial = (row.get("serie") or row.get("serial") or "").strip().upper()
        plan = (row.get("plan") or "").strip().upper()
        app = (row.get("app") or "").strip().upper()[:1]
        customer = " ".join((row.get("usuario") or row.get("cliente") or "").split())
        if not serial or not customer or plan not in PLANS or app not in ("W", "A"):
            invalid += 1
            continue
        if conn.execute("SELECT 1 FROM licenses WHERE serial=?", (serial,)).fetchone():
            skipped += 1
            continue
        stamp = (row.get("fecha") or "").strip()
        try:
            issued = int(time.mktime(time.strptime(stamp[:16], "%Y-%m-%d %H:%M")))
        except ValueError:
            try:
                issued = int(datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp())
            except ValueError:
                issued = int(time.time())
        until = (row.get("hasta") or row.get("vence") or "").strip()
        if plan == "PX" and until:
            try:
                expires = int(datetime.combine(date.fromisoformat(until) + timedelta(days=1), datetime.min.time(),
                                               timezone.utc).timestamp())
            except ValueError:
                expires = issued + PLANS[plan][1] * DAY
        else:
            expires = issued + PLANS[plan][1] * DAY
        def number(key):
            try:
                return float(str(row.get(key) or 0).replace(",", "."))
            except ValueError:
                return 0.0
        usd, cup = number("precio_usd"), number("precio_cup")
        cur = conn.execute(
            "INSERT INTO licenses(serial,created_at,created_by,customer,app,plan,request_code,issued_at,valid_from,"
            "valid_until,expires_at,price_usd,price_cup,usd_rate,notes,source) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (serial, datetime.fromtimestamp(issued, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "", customer,
             app, plan, (row.get("codigo_solicitud") or "").strip().upper()[:80], issued,
             (row.get("desde") or "").strip(), until if plan == "PX" else "", expires, usd, cup,
             round(cup / usd, 4) if usd else 0.0, "Importada del registro CSV", "csv"))
        add_event(conn, cur.lastrowid, "", "IMPORTED", "Registro antiguo (CSV)")
        imported += 1
    return {"imported": imported, "skipped": skipped, "invalid": invalid, "found": True}


def backup_to(conn, target: Path) -> Path:
    """Copia consistente de toda la base (usuarios, historial y auditoría) con la API de SQLite."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    dest = sqlite3.connect(str(target)) if not (dbcrypt and getattr(dbcrypt, "ENABLED", False)) \
        else dbcrypt.connect(target)
    try:
        conn.backup(dest)
    finally:
        dest.close()
    return target
