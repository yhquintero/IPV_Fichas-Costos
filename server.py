#!/usr/bin/env python3
"""IPV · Fichas y Costos — API profesional segura. Python estándar + SQLite.
Autor: Ing. Yosvany Hernández Quintero

Seguridad implementada:
  - Rate limiting por IP (configurable)
  - Cabeceras de seguridad (CSP, X-Frame-Options, HSTS, etc.)
  - Autenticación por token API (opcional, activable con IPV_API_TOKEN)
  - Sanitización y validación estricta de entradas
  - Protección contra path traversal
  - Límite de tamaño de solicitudes
  - Logging de auditoría
  - CORS restrictivo
  - Consultas SQL parametrizadas
  - TLS 1.2+ obligatorio en modo HTTPS
"""
from __future__ import annotations

import sys
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3

import dbcrypt
import ssl
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# ==========================================================================
#  CONFIGURACIÓN
# ==========================================================================

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("IPV_DB_PATH", ROOT / "data" / "ipv.db")).resolve()
# Escucha en todas las interfaces a propósito: acceso desde la red local (https://sqlserver:8443)
HOST = os.environ.get("IPV_HOST", "0.0.0.0")  # nosec B104
PORT = int(os.environ.get("PORT", os.environ.get("IPV_PORT", "8000")))
TLS_CERT = os.environ.get("IPV_TLS_CERT", "").strip()
TLS_KEY = os.environ.get("IPV_TLS_KEY", "").strip()

# Seguridad
API_TOKEN = os.environ.get("IPV_API_TOKEN", "").strip()
RATE_LIMIT_MAX = int(os.environ.get("IPV_RATE_LIMIT", "120"))  # requests por ventana
RATE_LIMIT_WINDOW = int(os.environ.get("IPV_RATE_WINDOW", "60"))  # segundos
MAX_BODY_SIZE = int(os.environ.get("IPV_MAX_BODY", "512000"))  # 500 KB
ALLOWED_ORIGINS = os.environ.get("IPV_ALLOWED_ORIGINS", "*").strip()

CENT = Decimal("0.01")
WRITE_LOCK = threading.RLock()

# Rate limiter storage
_rate_lock = threading.Lock()
_rate_data: dict[str, list[float]] = defaultdict(list)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sanitize_text(value: str, max_length: int = 500) -> str:
    """Sanitize text input: strip control chars, limit length."""
    if not isinstance(value, str):
        return ""
    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', value).strip()
    return cleaned[:max_length]


def sanitize_code(value: str) -> str:
    """Sanitize code fields: uppercase, alphanumeric + hyphens only."""
    if not isinstance(value, str):
        return ""
    cleaned = re.sub(r'[^A-Za-z0-9\-]', '', value.strip().upper())
    return cleaned[:30]


def check_rate_limit(client_ip: str) -> bool:
    """Return True if the request is within rate limits."""
    now = time.monotonic()
    with _rate_lock:
        timestamps = _rate_data[client_ip]
        # Purge old entries
        cutoff = now - RATE_LIMIT_WINDOW
        _rate_data[client_ip] = [t for t in timestamps if t > cutoff]
        if len(_rate_data[client_ip]) >= RATE_LIMIT_MAX:
            return False
        _rate_data[client_ip].append(now)
        return True


def audit_log(action: str, details: str = "", client: str = "") -> None:
    """Write an audit log entry to stderr."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[AUDIT {ts}] {action} | client={client} | {details}")


def amount(value, default="0") -> Decimal:
    try:
        result = Decimal(str(default if value is None or value == "" else value))
        if not result.is_finite():
            raise InvalidOperation
        return result
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Importe o cantidad no válido.")


def money(value) -> str:
    return str(amount(value).quantize(CENT, rounding=ROUND_HALF_UP))


def quantity_text(value) -> str:
    return format(amount(value).normalize(), "f")


# ==========================================================================
#  DATABASE
# ==========================================================================

def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = dbcrypt.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 20000")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


@contextmanager
def db_session():
    conn = connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db() -> None:
    with db_session() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            unit TEXT NOT NULL DEFAULT 'unidad',
            description TEXT NOT NULL DEFAULT '',
            active INTEGER NOT NULL DEFAULT 1,
            yield_qty TEXT NOT NULL DEFAULT '1',
            yield_unit TEXT NOT NULL DEFAULT 'unidad',
            deleted_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            unit TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'Insumos',
            currency TEXT NOT NULL DEFAULT 'CUP',
            unit_price TEXT NOT NULL DEFAULT '0.00',
            supplier TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT '',
            effective_from TEXT NOT NULL DEFAULT '',
            effective_to TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Vigente',
            stock TEXT NOT NULL DEFAULT '0',
            min_stock TEXT NOT NULL DEFAULT '0',
            deleted_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS fichas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL REFERENCES products(id),
            version INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'Borrador',
            valid_from TEXT NOT NULL DEFAULT '',
            observations TEXT NOT NULL DEFAULT '',
            total_cost TEXT NOT NULL DEFAULT '0.00',
            yield_qty TEXT NOT NULL DEFAULT '1',
            yield_unit TEXT NOT NULL DEFAULT 'unidad',
            deleted_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(product_id, version)
        );
        CREATE TABLE IF NOT EXISTS ficha_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ficha_id INTEGER NOT NULL REFERENCES fichas(id) ON DELETE CASCADE,
            material_id INTEGER REFERENCES materials(id) ON DELETE SET NULL,
            description TEXT NOT NULL,
            quantity TEXT NOT NULL,
            unit TEXT NOT NULL,
            unit_cost TEXT NOT NULL,
            subtotal TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS controls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            ficha_id INTEGER NOT NULL REFERENCES fichas(id),
            product_id INTEGER NOT NULL REFERENCES products(id),
            period TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pendiente',
            snapshot_total TEXT NOT NULL DEFAULT '0.00',
            checked_total TEXT NOT NULL DEFAULT '0.00',
            notes TEXT NOT NULL DEFAULT '',
            validation_report TEXT NOT NULL DEFAULT '[]',
            deleted_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            checked_at TEXT NOT NULL DEFAULT '',
            UNIQUE(ficha_id, period)
        );
        CREATE TABLE IF NOT EXISTS control_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            control_id INTEGER NOT NULL REFERENCES controls(id) ON DELETE CASCADE,
            material_id INTEGER REFERENCES materials(id) ON DELETE SET NULL,
            description TEXT NOT NULL,
            quantity TEXT NOT NULL,
            unit TEXT NOT NULL,
            unit_cost TEXT NOT NULL,
            subtotal TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_fichas_product ON fichas(product_id, version DESC);
        CREATE INDEX IF NOT EXISTS idx_controls_period ON controls(period DESC);
        CREATE INDEX IF NOT EXISTS idx_products_active ON products(active);
        CREATE INDEX IF NOT EXISTS idx_materials_status ON materials(status);
        """)
        migrate_schema(conn)
        if conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
            ensure_demo_data(conn, quiet=True)


# ==========================================================================
#  MIGRACIONES DE ESQUEMA (columnas añadidas en versiones posteriores)
# ==========================================================================

# (tabla, columna, definición SQL, valor por defecto para las filas existentes)
MIGRATIONS: tuple[tuple[str, str, str, str], ...] = (
    ("materials", "category", "TEXT NOT NULL DEFAULT 'Insumos'", "Insumos"),
    ("materials", "stock", "TEXT NOT NULL DEFAULT '0'", "0"),
    ("materials", "min_stock", "TEXT NOT NULL DEFAULT '0'", "0"),
    ("materials", "deleted_at", "TEXT NOT NULL DEFAULT ''", ""),
    ("products", "yield_qty", "TEXT NOT NULL DEFAULT '1'", "1"),
    ("products", "yield_unit", "TEXT NOT NULL DEFAULT 'unidad'", "unidad"),
    ("products", "deleted_at", "TEXT NOT NULL DEFAULT ''", ""),
    ("fichas", "yield_qty", "TEXT NOT NULL DEFAULT '1'", "1"),
    ("fichas", "yield_unit", "TEXT NOT NULL DEFAULT 'unidad'", "unidad"),
    ("fichas", "deleted_at", "TEXT NOT NULL DEFAULT ''", ""),
    ("controls", "deleted_at", "TEXT NOT NULL DEFAULT ''", ""),
)


def migrate_schema(conn: sqlite3.Connection) -> list[str]:
    """Añade las columnas nuevas a bases de datos creadas por versiones anteriores."""
    applied = []
    for table, column, ddl, default in MIGRATIONS:
        existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        if not existing or column in existing:
            continue
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        applied.append(f"{table}.{column}")
    if applied:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_materials_category ON materials(category)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_materials_trash ON materials(deleted_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_products_trash ON products(deleted_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fichas_trash ON fichas(deleted_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fichas_latest ON fichas(product_id, id DESC)")
    return applied



def ensure_demo_data(conn: sqlite3.Connection, quiet: bool = False) -> dict:
    """Carga el juego de datos de demostración (idempotente: sólo por código).

    Aporta un catálogo amplio de valores del IPV —licores con precios distintos,
    insumos de comida, bebidas y servicios—, productos de Comidas y Bebidas con su
    rendimiento (comensales o copas por lote) y las fichas correspondientes, para
    poder aprender el sistema con datos reales.
    """
    import demo_data

    stamp = now_iso()
    today = date.today().isoformat()
    counts = {"materials": 0, "products": 0, "fichas": 0, "controls": 0}

    material_ids: dict[str, int] = {}
    for code, name, unit, category, price, stock, min_stock, supplier in demo_data.MATERIALS:
        row = conn.execute("SELECT id FROM materials WHERE code=?", (code,)).fetchone()
        if row:
            material_ids[code] = row[0]
            continue
        cur = conn.execute("""INSERT INTO materials
            (code,name,unit,category,currency,unit_price,supplier,source,effective_from,status,
             stock,min_stock,created_at,updated_at)
            VALUES (?,?,?,?,'CUP',?,?,?,?,'Vigente',?,?,?,?)""",
            (code, name, unit, category, price, supplier, "Catálogo de demostración", today,
             stock, min_stock, stamp, stamp))
        material_ids[code] = cur.lastrowid
        counts["materials"] += 1

    product_ids: dict[str, int] = {}
    for code, name, category, unit, description, yield_qty, yield_unit in demo_data.PRODUCTS:
        row = conn.execute("SELECT id FROM products WHERE code=?", (code,)).fetchone()
        if row:
            product_ids[code] = row[0]
            continue
        cur = conn.execute("""INSERT INTO products
            (code,name,category,unit,description,yield_qty,yield_unit,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (code, name, category, unit, description, yield_qty, yield_unit, stamp, stamp))
        product_ids[code] = cur.lastrowid
        counts["products"] += 1

    for pcode, status, yield_qty, yield_unit, lines in demo_data.RECIPES:
        product_id = product_ids.get(pcode)
        if not product_id or not lines:
            continue
        if conn.execute("SELECT 1 FROM fichas WHERE product_id=? LIMIT 1", (product_id,)).fetchone():
            continue
        items, total = [], Decimal("0.00")
        for material_code, qty_value in lines:
            material_id = material_ids.get(material_code)
            if not material_id:
                continue
            material = conn.execute("SELECT * FROM materials WHERE id=?", (material_id,)).fetchone()
            qty, cost = amount(qty_value), amount(material["unit_price"])
            subtotal = (qty * cost).quantize(CENT, rounding=ROUND_HALF_UP)
            total += subtotal
            items.append((material_id, material["name"], quantity_text(qty), material["unit"],
                          money(cost), money(subtotal)))
        cur = conn.execute("""INSERT INTO fichas
            (product_id,version,status,valid_from,observations,total_cost,yield_qty,yield_unit,created_at,updated_at)
            VALUES (?,1,?,?,?,?,?,?,?,?)""",
            (product_id, status, today, "Ficha de demostración para aprendizaje.", "0.00",
             yield_qty, yield_unit, stamp, stamp))
        ficha_id = cur.lastrowid
        for item in items:
            conn.execute("""INSERT INTO ficha_items
                (ficha_id,material_id,description,quantity,unit,unit_cost,subtotal)
                VALUES (?,?,?,?,?,?,?)""", (ficha_id, *item))
        conn.execute("UPDATE fichas SET total_cost=? WHERE id=?", (money(total), ficha_id))
        counts["fichas"] += 1

    for pcode, period, status in demo_data.CONTROLS:
        row = conn.execute("""SELECT f.id, f.product_id, f.total_cost FROM fichas f
                              JOIN products p ON p.id=f.product_id
                              WHERE p.code=? AND f.deleted_at='' ORDER BY f.id LIMIT 1""", (pcode,)).fetchone()
        if not row:
            continue
        if conn.execute("SELECT 1 FROM controls WHERE ficha_id=? AND period=?", (row["id"], period)).fetchone():
            continue
        year = period[:4]
        last = conn.execute("SELECT code FROM controls WHERE code LIKE ? ORDER BY id DESC LIMIT 1",
                            (f"IPV-{year}-%",)).fetchone()
        try:
            sequence = int(last["code"].split("-")[-1]) + 1 if last else 1
        except (ValueError, IndexError, TypeError):
            sequence = conn.execute("SELECT COALESCE(MAX(id),0)+1 FROM controls").fetchone()[0]
        cur = conn.execute("""INSERT INTO controls
            (code,ficha_id,product_id,period,status,snapshot_total,checked_total,created_at,checked_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (f"IPV-{year}-{sequence:04d}", row["id"], row["product_id"], period, status,
             row["total_cost"], row["total_cost"] if status == "Validado" else "0.00", stamp,
             stamp if status == "Validado" else ""))
        control_id = cur.lastrowid
        for item in conn.execute("SELECT * FROM ficha_items WHERE ficha_id=?", (row["id"],)).fetchall():
            conn.execute("""INSERT INTO control_items
                (control_id,material_id,description,quantity,unit,unit_cost,subtotal)
                VALUES (?,?,?,?,?,?,?)""",
                (control_id, item["material_id"], item["description"], item["quantity"],
                 item["unit"], item["unit_cost"], item["subtotal"]))
        counts["controls"] += 1

    if not quiet and any(counts.values()):
        print("  Datos de demostración: " + ", ".join(f"{v} {k}" for k, v in counts.items() if v))
    return counts


# ==========================================================================
#  DATA ACCESS
# ==========================================================================

def rowdict(row):
    return dict(row) if row is not None else None


# --------------------------------------------------------------------------
#  Rendimiento: cuántos comensales / copas sale del lote de una ficha y cuántos
#  allows el inventario actual.
# --------------------------------------------------------------------------
def yield_info(yield_qty, yield_unit, total_cost) -> dict:
    """Costo por comensal/copa de una ficha a partir de su rendimiento."""
    y = amount(yield_qty or 1)
    if y <= 0:
        y = Decimal(1)
    return {"yield_qty": quantity_text(y), "yield_unit": sanitize_text(yield_unit or "unidad", 30),
            "cost_per_serving": money(amount(total_cost) / y)}


def servings_from_stock(conn, items, yield_qty) -> tuple[int | None, str, list[dict]]:
    """Raciones/copas que permite el inventario actual (mínimo entre componentes)."""
    y = amount(yield_qty or 1)
    if y <= 0:
        y = Decimal(1)
    best: int | None = None
    limited_by = ""
    shortages: list[dict] = []
    for item in items:
        if not item.get("material_id"):
            continue
        material = conn.execute("SELECT * FROM materials WHERE id=?", (item["material_id"],)).fetchone()
        if not material:
            continue
        per = amount(item["quantity"]) / y
        item["per_serving"] = quantity_text(per)
        item["material_name"] = material["name"]
        item["material_unit"] = material["unit"]
        stock = amount(material["stock"])
        item["stock"] = quantity_text(stock)
        if per <= 0:
            continue
        possible = int(stock / per)
        if best is None or possible < best:
            best, limited_by = possible, material["name"]
        if stock < per:
            shortages.append({"material": material["name"], "code": material["code"],
                              "required": quantity_text(per), "stock": quantity_text(stock)})
    return (best if best is not None else 0), limited_by, shortages


def get_product(conn, product_id):
    return rowdict(conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone())


def list_products(conn, include_inactive=True):
    where = "" if include_inactive else " AND p.active=1"
    return [dict(r) for r in conn.execute(f"""SELECT p.*,
        (SELECT COUNT(*) FROM fichas f WHERE f.product_id=p.id AND f.deleted_at='') AS ficha_count,
        (SELECT f.status FROM fichas f WHERE f.product_id=p.id AND f.deleted_at='' ORDER BY f.id DESC LIMIT 1) AS last_status,
        (SELECT f.id FROM fichas f WHERE f.product_id=p.id AND f.deleted_at='' ORDER BY f.id DESC LIMIT 1) AS last_ficha_id,
        (SELECT f.yield_qty FROM fichas f WHERE f.product_id=p.id AND f.deleted_at='' ORDER BY f.id DESC LIMIT 1) AS last_yield_qty,
        (SELECT f.yield_unit FROM fichas f WHERE f.product_id=p.id AND f.deleted_at='' ORDER BY f.id DESC LIMIT 1) AS last_yield_unit
        FROM products p WHERE p.deleted_at=''{where}
        ORDER BY p.active DESC, p.category, p.name""").fetchall()]


def list_materials(conn, include_inactive=True, category="", q=""):
    sql = "SELECT * FROM materials WHERE deleted_at=''"
    args: list = []
    if not include_inactive:
        sql += " AND status<>'Inactivo'"
    if category:
        sql += " AND category=?"
        args.append(category)
    if q:
        sql += " AND (name LIKE ? OR code LIKE ? OR supplier LIKE ?)"
        args += [f"%{q}%"] * 3
    sql += " ORDER BY category, name"
    return [dict(r) for r in conn.execute(sql, args).fetchall()]


def material_detail(conn, material_id):
    data = rowdict(conn.execute("SELECT * FROM materials WHERE id=?", (material_id,)).fetchone())
    if not data:
        return None
    rows = conn.execute("""SELECT fi.ficha_id, fi.quantity, f.yield_qty, f.yield_unit, f.status AS ficha_status,
        p.id AS product_id, p.code AS product_code, p.name AS product_name, p.category
        FROM ficha_items fi JOIN fichas f ON f.id=fi.ficha_id JOIN products p ON p.id=f.product_id
        WHERE fi.material_id=? AND f.deleted_at='' AND p.deleted_at=''
        ORDER BY p.category, p.name""", (material_id,)).fetchall()
    used = []
    for r in rows:
        y = amount(r["yield_qty"] or 1)
        if y <= 0:
            y = Decimal(1)
        per = amount(r["quantity"]) / y
        stock = amount(data["stock"])
        used.append({**dict(r), "per_serving": quantity_text(per),
                     "servings": int(stock / per) if per > 0 else None})
    data["used_by"] = used
    data["stock_value"] = money(amount(data["stock"]) * amount(data["unit_price"]))
    data["low_stock"] = amount(data["stock"]) <= amount(data["min_stock"]) and amount(data["min_stock"]) > 0
    return data


def ficha_summary(conn, ficha_id):
    row = conn.execute("""SELECT f.*, p.code AS product_code, p.name AS product_name,
        p.category AS category, p.unit AS product_unit,
        (SELECT COUNT(*) FROM ficha_items fi WHERE fi.ficha_id=f.id) AS item_count
        FROM fichas f JOIN products p ON p.id=f.product_id WHERE f.id=?""", (ficha_id,)).fetchone()
    return rowdict(row)


def ficha_detail(conn, ficha_id):
    data = ficha_summary(conn, ficha_id)
    if not data:
        return None
    data["items"] = [dict(r) for r in conn.execute("""SELECT fi.*, m.code AS material_code,
        m.category AS material_category, m.stock AS material_stock,
        m.effective_to AS material_effective_to, m.status AS material_status
        FROM ficha_items fi LEFT JOIN materials m ON m.id=fi.material_id
        WHERE fi.ficha_id=? ORDER BY fi.id""", (ficha_id,)).fetchall()]
    servings, limited_by, shortages = servings_from_stock(conn, data["items"], data.get("yield_qty"))
    info = yield_info(data.get("yield_qty"), data.get("yield_unit"), data.get("total_cost"))
    info.update({"servings_from_stock": servings, "limited_by": limited_by or None,
                 "shortages": shortages, "stock_ok": not shortages})
    data.update(info)
    return data


def list_fichas(conn):
    rows = [dict(r) for r in conn.execute("""SELECT f.*, p.code AS product_code,
        p.name AS product_name, p.category, p.unit AS product_unit,
        (SELECT COUNT(*) FROM ficha_items fi WHERE fi.ficha_id=f.id) AS item_count,
        (SELECT COUNT(*) FROM controls c WHERE c.ficha_id=f.id) AS control_count
        FROM fichas f JOIN products p ON p.id=f.product_id
        WHERE f.deleted_at=''
        ORDER BY f.updated_at DESC, f.id DESC""").fetchall()]
    stocks = {r["id"]: amount(r["stock"]) for r in conn.execute("SELECT id, stock FROM materials")}
    for row in rows:
        y = amount(row.get("yield_qty") or 1)
        if y <= 0:
            y = Decimal(1)
        row["cost_per_serving"] = money(amount(row["total_cost"]) / y)
        items = conn.execute("SELECT material_id, quantity FROM ficha_items WHERE ficha_id=?", (row["id"],)).fetchall()
        possible = None
        for item in items:
            if not item["material_id"]:
                continue
            per = amount(item["quantity"]) / y
            if per <= 0:
                continue
            available = int(stocks.get(item["material_id"], Decimal(0)) / per)
            possible = available if possible is None else min(possible, available)
        row["servings_from_stock"] = possible
    return rows


def control_detail(conn, control_id):
    row = conn.execute("""SELECT c.*, p.code AS product_code, p.name AS product_name,
        p.category, p.unit AS product_unit, f.version AS ficha_version, f.status AS ficha_status,
        f.total_cost AS ficha_total, f.yield_qty, f.yield_unit
        FROM controls c JOIN products p ON p.id=c.product_id JOIN fichas f ON f.id=c.ficha_id
        WHERE c.id=?""", (control_id,)).fetchone()
    if not row:
        return None
    data = dict(row)
    try:
        data["validation_messages"] = json.loads(data.pop("validation_report") or "[]")
    except json.JSONDecodeError:
        data["validation_messages"] = []
    data["items"] = [dict(r) for r in conn.execute("SELECT * FROM control_items WHERE control_id=? ORDER BY id", (control_id,)).fetchall()]
    y = amount(data.get("yield_qty") or 1) or Decimal(1)
    data["cost_per_serving"] = money(amount(data["snapshot_total"]) / y)
    return data


def list_controls(conn):
    return [control_detail(conn, r[0]) for r in conn.execute(
        "SELECT id FROM controls WHERE deleted_at='' ORDER BY created_at DESC, id DESC").fetchall()]


# --------------------------------------------------------------------------
#  INVENTARIO: existencias de cada valor del IPV y rendimiento con el stock actual
# --------------------------------------------------------------------------
def inventory(conn, category="", q="", low_only=False):
    materials = list_materials(conn, category=category, q=q)
    stocks = {m["id"]: amount(m["stock"]) for m in materials}
    usage: dict[int, list[dict]] = {}
    for row in conn.execute("""SELECT fi.material_id, fi.quantity, f.id AS ficha_id, f.yield_qty, f.yield_unit,
        f.status AS ficha_status, p.id AS product_id, p.code AS product_code, p.name AS product_name,
        p.category
        FROM ficha_items fi JOIN fichas f ON f.id=fi.ficha_id JOIN products p ON p.id=f.product_id
        WHERE f.deleted_at='' AND p.deleted_at='' AND p.active=1"""):
        if row["material_id"] is None or row["material_id"] not in stocks:
            continue
        y = amount(row["yield_qty"] or 1) or Decimal(1)
        per = amount(row["quantity"]) / y
        usage.setdefault(row["material_id"], []).append({
            "ficha_id": row["ficha_id"], "product_id": row["product_id"],
            "product_code": row["product_code"], "product_name": row["product_name"],
            "category": row["category"], "ficha_status": row["ficha_status"],
            "per_serving": quantity_text(per), "yield_unit": row["yield_unit"],
            "servings": int(stocks[row["material_id"]] / per) if per > 0 else None,
        })
    items, total_value, low = [], Decimal("0.00"), 0
    for m in materials:
        stock = amount(m["stock"])
        minimum = amount(m["min_stock"])
        value = (stock * amount(m["unit_price"])).quantize(CENT, rounding=ROUND_HALF_UP)
        total_value += value
        is_low = minimum > 0 and stock <= minimum
        low += 1 if is_low else 0
        item = {**m, "stock_value": money(value), "low_stock": is_low,
                "used_by": sorted(usage.get(m["id"], []), key=lambda u: u["product_name"]),
                "usage_count": len(usage.get(m["id"], []))}
        if not low_only or is_low:
            items.append(item)
    items.sort(key=lambda i: (not i["low_stock"], i["category"], i["name"]))
    return {"items": items, "totals": {"materials": len(materials), "low_stock": low,
                                       "stock_value": money(total_value),
                                       "categories": len({m["category"] for m in materials})}}


def dashboard(conn):
    count = lambda sql: conn.execute(sql).fetchone()[0]
    recent = [dict(r) for r in conn.execute("""SELECT f.id,f.version,f.status,f.total_cost,f.updated_at,
        f.yield_qty,f.yield_unit, p.name AS product_name,p.category,p.code AS product_code
        FROM fichas f JOIN products p ON p.id=f.product_id
        WHERE f.deleted_at='' AND p.deleted_at=''
        ORDER BY f.updated_at DESC,f.id DESC LIMIT 5""").fetchall()]
    categories = [dict(r) for r in conn.execute("SELECT category,COUNT(*) AS count FROM products WHERE active=1 AND deleted_at='' GROUP BY category ORDER BY category").fetchall()]
    # Cost distribution by category
    cost_by_cat = [dict(r) for r in conn.execute("""SELECT p.category, SUM(CAST(f.total_cost AS REAL)) AS total
        FROM fichas f JOIN products p ON p.id=f.product_id
        WHERE f.deleted_at='' AND p.deleted_at=''
          AND f.id IN (SELECT MAX(id) FROM fichas WHERE deleted_at='' GROUP BY product_id)
        GROUP BY p.category ORDER BY total DESC""").fetchall()]
    # Activity timeline (last 10 operations)
    activity = [dict(r) for r in conn.execute("""
        SELECT 'ficha' as type, id, 'Ficha creada' as action, created_at as timestamp FROM fichas WHERE deleted_at=''
        UNION ALL
        SELECT 'control', id, 'Control generado', created_at FROM controls WHERE deleted_at=''
        UNION ALL
        SELECT 'product', id, 'Producto registrado', created_at FROM products WHERE deleted_at=''
        UNION ALL
        SELECT 'material', id, 'Valor del IPV registrado', created_at FROM materials WHERE deleted_at=''
        ORDER BY timestamp DESC LIMIT 10
    """).fetchall()]
    stock_value = Decimal("0.00")
    low_stock = 0
    for r in conn.execute("SELECT stock, min_stock, unit_price FROM materials WHERE deleted_at=''"):
        stock_value += amount(r["stock"]) * amount(r["unit_price"])
        if amount(r["min_stock"]) > 0 and amount(r["stock"]) <= amount(r["min_stock"]):
            low_stock += 1
    return {
        "products": count("SELECT COUNT(*) FROM products WHERE active=1 AND deleted_at=''"),
        "materials": count("SELECT COUNT(*) FROM materials WHERE deleted_at=''"),
        "fichas": count("SELECT COUNT(*) FROM fichas WHERE deleted_at=''"),
        "approved_fichas": count("SELECT COUNT(*) FROM fichas WHERE status='Aprobada' AND deleted_at=''"),
        "pending_controls": count("SELECT COUNT(*) FROM controls WHERE status='Pendiente' AND deleted_at=''"),
        "validated_controls": count("SELECT COUNT(*) FROM controls WHERE status='Validado' AND deleted_at=''"),
        "trash": count("SELECT (SELECT COUNT(*) FROM products WHERE deleted_at<>'') + "
                       "(SELECT COUNT(*) FROM materials WHERE deleted_at<>'') + "
                       "(SELECT COUNT(*) FROM fichas WHERE deleted_at<>'') + "
                       "(SELECT COUNT(*) FROM controls WHERE deleted_at<>'')"),
        "stock_value": money(stock_value),
        "low_stock": low_stock,
        "recent_fichas": recent,
        "categories": categories,
        "cost_by_category": cost_by_cat,
        "activity_timeline": activity,
    }


# --------------------------------------------------------------------------
#  PAPELERA DE RECICLAJE
# --------------------------------------------------------------------------
TRASH_TABLES = {
    "products": {"label": "Producto", "columns": ("code", "name", "category")},
    "materials": {"label": "Valor del IPV", "columns": ("code", "name", "category")},
    "fichas": {"label": "Ficha de costo", "columns": ("", "product_name", "status")},
    "controls": {"label": "Control de IPV", "columns": ("code", "product_name", "status")},
}


def list_trash(conn):
    """Elementos eliminados, listos para restaurar o borrar definitivamente."""
    queries = {
        "products": """SELECT t.id, t.code, t.name, t.category, t.deleted_at,
            (SELECT COUNT(*) FROM fichas f WHERE f.product_id=t.id AND f.deleted_at='') AS detail
            FROM products t WHERE t.deleted_at<>''""",
        "materials": "SELECT id, code, name, category, deleted_at, status AS detail FROM materials WHERE deleted_at<>''",
        "fichas": """SELECT t.id, '' AS code, p.name AS name, t.status AS detail, t.deleted_at
            FROM fichas t JOIN products p ON p.id=t.product_id WHERE t.deleted_at<>''""",
        "controls": """SELECT t.id, t.code, p.name AS name, t.status AS detail, t.deleted_at, t.period
            FROM controls t JOIN products p ON p.id=t.product_id WHERE t.deleted_at<>''""",
    }
    out = []
    for kind, meta in TRASH_TABLES.items():
        for row in conn.execute(queries[kind]).fetchall():
            out.append({"kind": kind, "kind_label": meta["label"], "id": row["id"],
                        "code": row["code"] or "", "name": row["name"],
                        "detail": str(row["detail"]) if "detail" in row.keys() else "",
                        "period": row["period"] if "period" in row.keys() else "",
                        "deleted_at": row["deleted_at"]})
    out.sort(key=lambda x: (x["deleted_at"], x["kind"]), reverse=True)
    return out



def search_all(conn, query: str, limit: int = 20):
    """Full-text search across all entities."""
    q = f"%{sanitize_text(query, 100)}%"
    results = []
    # Search products
    for r in conn.execute("SELECT id, code, name, category, 'product' as type FROM products WHERE deleted_at='' AND (name LIKE ? OR code LIKE ?) LIMIT ?", (q, q, limit)).fetchall():
        results.append(dict(r))
    # Search materials
    for r in conn.execute("SELECT id, code, name, unit, category, 'material' as type FROM materials WHERE deleted_at='' AND (name LIKE ? OR code LIKE ?) LIMIT ?", (q, q, limit)).fetchall():
        results.append(dict(r))
    # Search fichas
    for r in conn.execute("""SELECT f.id, p.code, p.name, f.version, f.status, 'ficha' as type
        FROM fichas f JOIN products p ON p.id=f.product_id
        WHERE f.deleted_at='' AND (p.name LIKE ? OR p.code LIKE ?) LIMIT ?""", (q, q, limit)).fetchall():
        results.append(dict(r))
    # Search controls
    for r in conn.execute("""SELECT c.id, c.code, p.name, c.period, c.status, 'control' as type
        FROM controls c JOIN products p ON p.id=c.product_id
        WHERE c.deleted_at='' AND (c.code LIKE ? OR p.name LIKE ?) LIMIT ?""", (q, q, limit)).fetchall():
        results.append(dict(r))
    return results[:limit]


def insert_ficha_item(conn, ficha_id, item):
    material_id = item.get("material_id")
    if material_id not in (None, ""):
        material = conn.execute("SELECT * FROM materials WHERE id=?", (int(material_id),)).fetchone()
        if not material:
            raise ValueError("El insumo seleccionado no existe.")
        description = sanitize_text(material["name"], 200)
        unit = sanitize_text(item.get("unit") or material["unit"], 30)
        unit_cost = amount(material["unit_price"])
        stored_material_id = material["id"]
    else:
        description = sanitize_text(item.get("description", ""), 200)
        unit = sanitize_text(item.get("unit", ""), 30)
        if not description or not unit:
            raise ValueError("Cada línea debe tener descripción y unidad.")
        unit_cost = amount(item.get("unit_cost"))
        stored_material_id = None
    qty = amount(item.get("quantity"))
    if qty <= 0:
        raise ValueError("La cantidad debe ser mayor que cero.")
    if unit_cost < 0:
        raise ValueError("El costo unitario no puede ser negativo.")
    subtotal = (qty * unit_cost).quantize(CENT, rounding=ROUND_HALF_UP)
    conn.execute("""INSERT INTO ficha_items
        (ficha_id,material_id,description,quantity,unit,unit_cost,subtotal)
        VALUES (?,?,?,?,?,?,?)""",
        (ficha_id, stored_material_id, description, quantity_text(qty), unit, money(unit_cost), money(subtotal)))
    return subtotal


# ==========================================================================
#  HTTP HANDLER
# ==========================================================================

class APIError(Exception):
    def __init__(self, message, status=400):
        self.message = message
        self.status = status


# Security headers applied to every response
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cache-Control": "no-store, no-cache, must-revalidate",
    "Pragma": "no-cache",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "IPV-FichasCostos/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def client_ip(self) -> str:
        forwarded = self.headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return self.client_address[0]

    def _cors_origin(self) -> str:
        origin = self.headers.get("Origin", "")
        if ALLOWED_ORIGINS == "*":
            return "*"
        allowed = [o.strip() for o in ALLOWED_ORIGINS.split(",") if o.strip()]
        if origin in allowed:
            return origin
        return allowed[0] if allowed else ""

    def _apply_security_headers(self):
        for key, value in SECURITY_HEADERS.items():
            self.send_header(key, value)
        cors = self._cors_origin()
        if cors:
            self.send_header("Access-Control-Allow-Origin", cors)
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Token")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Max-Age", "3600")
        if TLS_CERT:
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")

    def send_json(self, payload, status=200):
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self._apply_security_headers()
        self.end_headers()
        self.wfile.write(raw)

    def body_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > MAX_BODY_SIZE:
                raise APIError("La solicitud excede el tamaño máximo permitido.", 413)
            raw = self.rfile.read(length) if length else b"{}"
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                raise APIError("Se esperaba un objeto JSON.")
            return data
        except json.JSONDecodeError:
            raise APIError("JSON no válido.")

    def _check_auth(self):
        """Validate API token if configured."""
        if not API_TOKEN:
            return  # Auth disabled
        auth = self.headers.get("Authorization", "")
        token = self.headers.get("X-API-Token", "")
        provided = ""
        if auth.startswith("Bearer "):
            provided = auth[7:].strip()
        elif token:
            provided = token.strip()
        if not provided or not hmac.compare_digest(provided, API_TOKEN):
            raise APIError("Autenticación requerida.", 401)

    def do_OPTIONS(self):
        self.send_response(204)
        self._apply_security_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _pre_check(self) -> bool:
        """Rate limit + auth check. Returns True if OK, False if blocked."""
        ip = self.client_ip()
        if not check_rate_limit(ip):
            audit_log("RATE_LIMITED", client=ip)
            self.send_json({"error": "Demasiadas solicitudes. Intente más tarde."}, 429)
            return False
        try:
            self._check_auth()
        except APIError as exc:
            audit_log("AUTH_FAILED", client=ip)
            self.send_json({"error": exc.message}, exc.status)
            return False
        return True

    def do_GET(self):
        if not self._pre_check():
            return
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        qs = parse_qs(parsed.query)
        try:
            if not path.startswith("/api"):
                self.serve_static(path)
                return
            with db_session() as conn:
                if path == "/api/health":
                    result = {
                        "ok": True, "database": "SQLite", "file": DB_PATH.name,
                        "time": now_iso(), "version": "1.1.0",
                        "tls": bool(TLS_CERT),
                        "auth_required": bool(API_TOKEN),
                    }
                elif path == "/api/dashboard":
                    result = dashboard(conn)
                elif path == "/api/search":
                    q = qs.get("q", [""])[0]
                    limit = min(int(qs.get("limit", ["20"])[0]), 50)
                    if not q or len(q) < 2:
                        result = []
                    else:
                        result = search_all(conn, q, limit)
                elif path == "/api/products":
                    result = list_products(conn)
                elif path == "/api/materials":
                    result = list_materials(conn)
                elif path == "/api/inventory":
                    result = inventory(conn, category=qs.get("category", [""])[0],
                                       q=qs.get("q", [""])[0],
                                       low_only=qs.get("low", ["0"])[0] in ("1", "true", "si", "sí"))
                elif path == "/api/trash":
                    result = {"items": list_trash(conn)}
                elif path == "/api/categories":
                    result = {"materials": [r[0] for r in conn.execute(
                        "SELECT DISTINCT category FROM materials WHERE deleted_at='' ORDER BY category")],
                        "products": [r[0] for r in conn.execute(
                            "SELECT DISTINCT category FROM products WHERE deleted_at='' ORDER BY category")]}
                elif path == "/api/fichas":
                    result = list_fichas(conn)
                elif path == "/api/controls":
                    result = list_controls(conn)
                elif path.startswith("/api/fichas/"):
                    result = ficha_detail(conn, int(path.split("/")[-1]))
                    if result is None:
                        raise APIError("Ficha no encontrada.", 404)
                elif path.startswith("/api/controls/"):
                    result = control_detail(conn, int(path.split("/")[-1]))
                    if result is None:
                        raise APIError("Control no encontrado.", 404)
                elif re.fullmatch(r"/api/materials/\d+", path):
                    result = material_detail(conn, int(path.split("/")[-1]))
                    if result is None:
                        raise APIError("Valor del IPV no encontrado.", 404)
                elif re.fullmatch(r"/api/products/\d+", path):
                    product = get_product(conn, int(path.split("/")[-1]))
                    if product is None:
                        raise APIError("Producto no encontrado.", 404)
                    product["fichas"] = [dict(r) for r in conn.execute(
                        "SELECT * FROM fichas WHERE product_id=? AND deleted_at='' ORDER BY id DESC",
                        (product["id"],)).fetchall()]
                    result = product
                else:
                    raise APIError("Ruta API no encontrada.", 404)
            self.send_json(result)
        except APIError as exc:
            self.send_json({"error": exc.message}, exc.status)
        except (ValueError, TypeError):
            self.send_json({"error": "Identificador o parámetro no válido."}, 400)
        except Exception as exc:
            print("GET error:", repr(exc))
            self.send_json({"error": "Error interno del servidor."}, 500)

    def do_POST(self):
        if not self._pre_check():
            return
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        try:
            data = self.body_json()
            client = self.client_ip()
            with WRITE_LOCK, connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                if path == "/api/products":
                    result = self._create_product(conn, data)
                    status = 201
                    audit_log("CREATE_PRODUCT", f"code={data.get('code','')}", client)
                elif path == "/api/materials":
                    result = self._create_material(conn, data)
                    status = 201
                    audit_log("CREATE_MATERIAL", f"code={data.get('code','')}", client)
                elif path == "/api/fichas":
                    result = self._create_ficha(conn, data)
                    status = 201
                    audit_log("CREATE_FICHA", f"product_id={data.get('product_id','')}", client)
                elif path.startswith("/api/fichas/") and path.endswith("/approve"):
                    ficha_id = int(path.split("/")[-2])
                    result = self._approve_ficha(conn, ficha_id)
                    status = 200
                    audit_log("APPROVE_FICHA", f"id={ficha_id}", client)
                elif path == "/api/controls":
                    result = self._create_control(conn, data)
                    status = 201
                    audit_log("CREATE_CONTROL", f"ficha_id={data.get('ficha_id','')}", client)
                elif path.startswith("/api/controls/") and path.endswith("/validate"):
                    control_id = int(path.split("/")[-2])
                    result = self._validate_control(conn, control_id)
                    status = 200
                    audit_log("VALIDATE_CONTROL", f"id={control_id}", client)
                elif re.fullmatch(r"/api/materials/\d+/stock", path):
                    result = self._adjust_stock(conn, int(path.split("/")[-2]), data)
                    status = 200
                    audit_log("ADJUST_STOCK", f"id={data.get('material_id', '')}", client)
                elif re.fullmatch(r"/api/(fichas|controls)/(\d+)/restore", path):
                    kind, ident = re.fullmatch(r"/api/(fichas|controls)/(\d+)/restore", path).groups()
                    result = self._restore_from_trash(conn, kind, int(ident))
                    status = 200
                    audit_log(f"RESTORE_{kind.upper()[:-1]}", f"id={ident}", client)
                elif re.fullmatch(r"/api/trash/(\w+)/(\d+)/restore", path):
                    kind, ident = re.fullmatch(r"/api/trash/(\w+)/(\d+)/restore", path).groups()
                    result = self._restore_from_trash(conn, kind, int(ident))
                    status = 200
                    audit_log(f"RESTORE_{kind.upper()[:-1]}", f"id={ident}", client)
                elif path == "/api/trash/empty":
                    result = self._empty_trash(conn)
                    status = 200
                    audit_log("TRASH_EMPTIED", f"n={result['removed']}", client)
                elif path == "/api/demo/seed":
                    result = ensure_demo_data(conn)
                    status = 200
                    audit_log("DEMO_SEED", str(result), client)
                else:
                    raise APIError("Ruta API no encontrada.", 404)
            self.send_json(result, status)
        except APIError as exc:
            self.send_json({"error": exc.message}, exc.status)
        except sqlite3.IntegrityError as exc:
            message = "El código ya existe o el registro tiene información relacionada."
            if "UNIQUE constraint failed: controls.ficha_id, controls.period" in str(exc):
                message = "Ya existe un Control IPV para esa ficha y período."
            self.send_json({"error": message}, 409)
        except (ValueError, TypeError, KeyError) as exc:
            self.send_json({"error": str(exc) or "Datos no válidos."}, 400)
        except Exception as exc:
            print("POST error:", repr(exc))
            self.send_json({"error": "Error interno del servidor."}, 500)

    def do_PUT(self):
        if not self._pre_check():
            return
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        try:
            data = self.body_json()
            client = self.client_ip()
            with WRITE_LOCK, connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                if path.startswith("/api/fichas/"):
                    ficha_id = int(path.split("/")[-1])
                    result = self._update_ficha(conn, ficha_id, data)
                    audit_log("UPDATE_FICHA", f"id={ficha_id}", client)
                elif re.fullmatch(r"/api/materials/\d+", path):
                    material_id = int(path.split("/")[-1])
                    result = self._update_material(conn, material_id, data)
                    audit_log("UPDATE_MATERIAL", f"id={material_id} code={data.get('code','')}", client)
                elif re.fullmatch(r"/api/products/\d+", path):
                    product_id = int(path.split("/")[-1])
                    result = self._update_product(conn, product_id, data)
                    audit_log("UPDATE_PRODUCT", f"id={product_id} code={data.get('code','')}", client)
                else:
                    raise APIError("Ruta API no encontrada.", 404)
            self.send_json(result)
        except APIError as exc:
            self.send_json({"error": exc.message}, exc.status)
        except (ValueError, TypeError, KeyError) as exc:
            self.send_json({"error": str(exc) or "Datos no válidos."}, 400)
        except sqlite3.IntegrityError:
            self.send_json({"error": "No se pudo guardar: código duplicado o datos relacionados."}, 409)
        except Exception as exc:
            print("PUT error:", repr(exc))
            self.send_json({"error": "Error interno del servidor."}, 500)

    def do_DELETE(self):
        if not self._pre_check():
            return
        path = urlparse(self.path).path.rstrip("/")
        try:
            self.body_json()  # drena el cuerpo para no corromper la conexión siguiente
            client = self.client_ip()
            with WRITE_LOCK, connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                if re.fullmatch(r"/api/products/\d+", path):
                    result = self._trash_record(conn, "products", int(path.split("/")[-1]))
                    audit_log("DEACTIVATE_PRODUCT", f"id={path.split('/')[-1]}", client)
                elif re.fullmatch(r"/api/materials/\d+", path):
                    result = self._trash_record(conn, "materials", int(path.split("/")[-1]))
                    audit_log("DEACTIVATE_MATERIAL", f"id={path.split('/')[-1]}", client)
                elif re.fullmatch(r"/api/fichas/\d+", path):
                    result = self._trash_record(conn, "fichas", int(path.split("/")[-1]))
                    audit_log("DELETE_FICHA", f"id={path.split('/')[-1]}", client)
                elif re.fullmatch(r"/api/controls/\d+", path):
                    result = self._trash_record(conn, "controls", int(path.split("/")[-1]))
                    audit_log("DELETE_CONTROL", f"id={path.split('/')[-1]}", client)
                elif re.fullmatch(r"/api/trash/(\w+)/\d+", path):
                    kind, ident = re.fullmatch(r"/api/trash/(\w+)/(\d+)", path).groups()
                    result = self._purge(conn, kind, int(ident))
                    audit_log(f"PURGE_{kind.upper()[:-1]}", f"id={ident}", client)
                else:
                    raise APIError("Ruta API no encontrada.", 404)
            self.send_json(result)
        except APIError as exc:
            self.send_json({"error": exc.message}, exc.status)
        except (ValueError, TypeError):
            self.send_json({"error": "Identificador no válido."}, 400)
        except sqlite3.IntegrityError:
            self.send_json({"error": "No se pudo eliminar: el registro tiene elementos dependientes."}, 409)
        except Exception as exc:
            print("DELETE error:", repr(exc))
            self.send_json({"error": "Error interno del servidor."}, 500)

    def serve_static(self, path):
        if path == "/":
            file_path = ROOT / "web" / "index.html"
        else:
            relative = path.lstrip("/")
            # Prevent path traversal
            if ".." in relative or relative.startswith("/"):
                self.send_json({"error": "Ruta no permitida."}, 403)
                return
            file_path = (ROOT / "web" / relative).resolve()
            web_root = (ROOT / "web").resolve()
            if web_root not in file_path.parents and file_path != web_root:
                self.send_json({"error": "Ruta no permitida."}, 403)
                return
        if not file_path.is_file():
            self.send_error(404, "Archivo no encontrado")
            return
        content_type = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".ico": "image/x-icon",
            ".json": "application/json",
            ".woff2": "font/woff2",
            ".txt": "text/plain; charset=utf-8",
        }.get(file_path.suffix, "application/octet-stream")
        raw = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self._apply_security_headers()
        # Cache static assets briefly
        if file_path.suffix == ".woff2":  # las fuentes no cambian entre versiones
            self.send_header("Cache-Control", "public, max-age=2592000, immutable")
        elif file_path.suffix in (".css", ".js", ".svg", ".png"):
            self.send_header("Cache-Control", "public, max-age=300")
        else:
            self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(raw)

    # ---------- CRUD Operations ----------

    CURRENCIES = ("CUP", "MLC", "USD", "EUR")
    STATUSES = ("Vigente", "Inactivo")

    def _create_product(self, conn, data):
        code = sanitize_code(data.get("code", ""))
        name = sanitize_text(data.get("name", ""), 200)
        category = sanitize_text(data.get("category", ""), 100)
        unit = sanitize_text(data.get("unit", "unidad"), 30) or "unidad"
        if not code or not name or not category:
            raise APIError("Código, nombre y categoría son obligatorios.")
        yield_qty = amount(data.get("yield_qty", 1))
        if yield_qty <= 0:
            raise APIError("El rendimiento debe ser mayor que cero.")
        stamp = now_iso()
        cur = conn.execute("""INSERT INTO products
            (code,name,category,unit,description,yield_qty,yield_unit,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (code, name, category, unit, sanitize_text(data.get("description", ""), 1000),
             quantity_text(yield_qty), sanitize_text(data.get("yield_unit", unit), 30), stamp, stamp))
        return get_product(conn, cur.lastrowid)

    def _update_product(self, conn, product_id, data):
        current = get_product(conn, product_id)
        if not current:
            raise APIError("Producto no encontrado.", 404)
        code = sanitize_code(data.get("code", current["code"])) or current["code"]
        name = sanitize_text(data.get("name", ""), 200) or current["name"]
        category = sanitize_text(data.get("category", ""), 100) or current["category"]
        unit = sanitize_text(data.get("unit", ""), 30) or current["unit"]
        yield_qty = amount(data.get("yield_qty", current["yield_qty"]))
        if yield_qty <= 0:
            raise APIError("El rendimiento debe ser mayor que cero.")
        active = data.get("active")
        active_flag = current["active"] if active is None else (1 if active in (1, True, "1", "true", "si", "sí") else 0)
        conn.execute("""UPDATE products SET code=?,name=?,category=?,unit=?,description=?,
            yield_qty=?,yield_unit=?,active=?,updated_at=? WHERE id=?""",
            (code, name, category, unit,
             sanitize_text(data.get("description", current["description"]), 1000),
             quantity_text(yield_qty), sanitize_text(data.get("yield_unit", current["yield_unit"]), 30),
             active_flag, now_iso(), product_id))
        return get_product(conn, product_id)

    def _create_material(self, conn, data):
        code = sanitize_code(data.get("code", ""))
        name = sanitize_text(data.get("name", ""), 200)
        unit = sanitize_text(data.get("unit", ""), 30)
        if not code or not name or not unit:
            raise APIError("Código, nombre y unidad son obligatorios.")
        unit_price = amount(data.get("unit_price"))
        if unit_price < 0:
            raise APIError("El precio no puede ser negativo.")
        currency = sanitize_text(data.get("currency", "CUP"), 10) or "CUP"
        if currency not in self.CURRENCIES:
            raise APIError("Moneda no soportada.")
        stock = amount(data.get("stock", 0))
        min_stock = amount(data.get("min_stock", 0))
        if stock < 0 or min_stock < 0:
            raise APIError("Las existencias no pueden ser negativas.")
        stamp = now_iso()
        cur = conn.execute("""INSERT INTO materials
            (code,name,unit,category,currency,unit_price,supplier,source,effective_from,effective_to,
             status,stock,min_stock,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (code, name, unit, sanitize_text(data.get("category", "Insumos"), 60) or "Insumos", currency,
             money(unit_price),
             sanitize_text(data.get("supplier", ""), 200), sanitize_text(data.get("source", ""), 300),
             sanitize_text(data.get("effective_from", date.today().isoformat()), 20),
             sanitize_text(data.get("effective_to", ""), 20),
             self._clean_status(data.get("status"), "Vigente"),
             quantity_text(stock), quantity_text(min_stock), stamp, stamp))
        return material_detail(conn, cur.lastrowid)

    def _update_material(self, conn, material_id, data):
        current = conn.execute("SELECT * FROM materials WHERE id=?", (material_id,)).fetchone()
        if not current:
            raise APIError("Valor del IPV no encontrado.", 404)
        code = sanitize_code(data.get("code", current["code"])) or current["code"]
        name = sanitize_text(data.get("name", ""), 200) or current["name"]
        unit = sanitize_text(data.get("unit", ""), 30) or current["unit"]
        category = sanitize_text(data.get("category", ""), 60) or current["category"]
        unit_price = amount(data.get("unit_price", current["unit_price"]))
        if unit_price < 0:
            raise APIError("El precio no puede ser negativo.")
        currency = sanitize_text(data.get("currency", current["currency"]), 10) or "CUP"
        if currency not in self.CURRENCIES:
            raise APIError("Moneda no soportada.")
        stock = amount(data.get("stock", current["stock"]))
        min_stock = amount(data.get("min_stock", current["min_stock"]))
        if stock < 0 or min_stock < 0:
            raise APIError("Las existencias no pueden ser negativas.")
        conn.execute("""UPDATE materials SET code=?,name=?,unit=?,category=?,currency=?,unit_price=?,
            supplier=?,source=?,effective_from=?,effective_to=?,status=?,stock=?,min_stock=?,updated_at=?
            WHERE id=?""",
            (code, name, unit, category, currency, money(unit_price),
             sanitize_text(data.get("supplier", current["supplier"]), 200),
             sanitize_text(data.get("source", current["source"]), 300),
             sanitize_text(data.get("effective_from", current["effective_from"]), 20),
             sanitize_text(data.get("effective_to", current["effective_to"]), 20),
             self._clean_status(data.get("status"), current["status"]),
             quantity_text(stock), quantity_text(min_stock), now_iso(), material_id))
        return material_detail(conn, material_id)

    def _clean_status(self, value, default="Vigente") -> str:
        status = sanitize_text(value or default, 30) or default
        return status if status in self.STATUSES else default

    def _adjust_stock(self, conn, material_id, data):
        """Entrada o salida de existencias: {"delta": "+3"} o {"set": "12"}."""
        current = conn.execute("SELECT * FROM materials WHERE id=?", (material_id,)).fetchone()
        if not current:
            raise APIError("Valor del IPV no encontrado.", 404)
        stock = amount(current["stock"])
        if "set" in data and str(data.get("set")).strip() != "":
            new = amount(data.get("set"))
        else:
            new = stock + amount(data.get("delta", 0))
        if new < 0:
            raise APIError("No puede quedar menos de cero: la salida supera las existencias.", 409)
        conn.execute("UPDATE materials SET stock=?,updated_at=? WHERE id=?", (quantity_text(new), now_iso(), material_id))
        result = material_detail(conn, material_id)
        result["previous_stock"] = quantity_text(stock)
        return result

    # ---------- Papelera de reciclaje ----------

    def _trash_record(self, conn, kind, ident):
        """Envía un registro a la papelera (borrado lógico: nunca se pierde información)."""
        table = kind if kind in TRASH_TABLES else None
        if not table:
            raise APIError("Tipo de registro no válido.", 400)
        row = conn.execute(f"SELECT id FROM {table} WHERE id=?", (ident,)).fetchone()
        if not row:
            raise APIError(f"{TRASH_TABLES[table]['label']} no encontrado.", 404)
        extra = ""
        if table == "products":
            extra = ", active=0"
        elif table == "materials":
            extra = ", status='Inactivo'"
        cur = conn.execute(f"UPDATE {table} SET deleted_at=?{extra} WHERE id=?", (now_iso(), ident))
        if cur.rowcount == 0:
            raise APIError("No se pudo mover a la papelera.", 409)
        return {"ok": True, "trashed": True, "kind": kind, "id": ident}

    def _restore_from_trash(self, conn, kind, ident):
        if kind not in TRASH_TABLES:
            raise APIError("Tipo de registro no válido.", 400)
        stamp = now_iso()
        if kind == "products":
            cur = conn.execute("UPDATE products SET deleted_at='',active=1,updated_at=? WHERE id=? AND deleted_at<>''", (stamp, ident))
        elif kind == "materials":
            cur = conn.execute("UPDATE materials SET deleted_at='',status='Vigente',effective_to='',updated_at=? WHERE id=? AND deleted_at<>''", (stamp, ident))
        elif kind == "fichas":
            cur = conn.execute("UPDATE fichas SET deleted_at='',updated_at=? WHERE id=? AND deleted_at<>''", (stamp, ident))
        else:
            cur = conn.execute("UPDATE controls SET deleted_at='' WHERE id=? AND deleted_at<>''", (ident,))
        if cur.rowcount == 0:
            raise APIError("El elemento no está en la papelera.", 404)
        return {"ok": True, "restored": True, "kind": kind, "id": ident}

    def _purge_dependents(self, conn, kind, ident) -> None:
        """Borra en cascada lo que depende del registro (instantáneas y líneas)."""
        if kind == "products":
            ficha_ids = [r[0] for r in conn.execute("SELECT id FROM fichas WHERE product_id=?", (ident,))]
            if ficha_ids:
                marks = ",".join("?" * len(ficha_ids))
                control_ids = [r[0] for r in conn.execute(
                    f"SELECT id FROM controls WHERE ficha_id IN ({marks})", ficha_ids)]
                if control_ids:
                    conn.execute(f"DELETE FROM control_items WHERE control_id IN ({','.join('?' * len(control_ids))})", control_ids)
                    conn.execute(f"DELETE FROM controls WHERE id IN ({','.join('?' * len(control_ids))})", control_ids)
                conn.execute(f"DELETE FROM ficha_items WHERE ficha_id IN ({marks})", ficha_ids)
                conn.execute(f"DELETE FROM fichas WHERE id IN ({marks})", ficha_ids)
        elif kind == "fichas":
            control_ids = [r[0] for r in conn.execute("SELECT id FROM controls WHERE ficha_id=?", (ident,))]
            if control_ids:
                marks = ",".join("?" * len(control_ids))
                conn.execute(f"DELETE FROM control_items WHERE control_id IN ({marks})", control_ids)
                conn.execute(f"DELETE FROM controls WHERE id IN ({marks})", control_ids)
            conn.execute("DELETE FROM ficha_items WHERE ficha_id=?", (ident,))
        elif kind == "controls":
            conn.execute("DELETE FROM control_items WHERE control_id=?", (ident,))

    def _purge(self, conn, kind, ident):
        """Borrado definitivo desde la papelera (elimina también sus documentos derivados)."""
        if kind not in TRASH_TABLES:
            raise APIError("Tipo de registro no válido.", 400)
        row = conn.execute(f"SELECT id FROM {kind} WHERE id=? AND deleted_at<>''", (ident,)).fetchone()
        if not row:
            raise APIError("El elemento no está en la papelera.", 404)
        self._purge_dependents(conn, kind, ident)
        conn.execute(f"DELETE FROM {kind} WHERE id=?", (ident,))
        return {"ok": True, "purged": True, "kind": kind, "id": ident}

    def _empty_trash(self, conn):
        removed = {"products": 0, "materials": 0, "fichas": 0, "controls": 0}
        for kind in ("products", "fichas", "controls", "materials"):
            for row in conn.execute(f"SELECT id FROM {kind} WHERE deleted_at<>''").fetchall():
                self._purge_dependents(conn, kind, row[0])
                removed[kind] += conn.execute(f"DELETE FROM {kind} WHERE id=?", (row[0],)).rowcount
        return {"ok": True, "removed": sum(removed.values()), "by_kind": removed}


    def _create_ficha(self, conn, data):
        product_id = int(data.get("product_id"))
        product = get_product(conn, product_id)
        if not product or not product["active"]:
            raise APIError("Selecciona un producto activo.")
        items = data.get("items") or []
        if not isinstance(items, list) or not items:
            raise APIError("Añade al menos un insumo o componente.")
        if len(items) > 100:
            raise APIError("No se permiten más de 100 componentes por ficha.")
        version = conn.execute("SELECT COALESCE(MAX(version),0)+1 FROM fichas WHERE product_id=?", (product_id,)).fetchone()[0]
        yield_qty, yield_unit = self._clean_yield(data, product)
        stamp = now_iso()
        cur = conn.execute("""INSERT INTO fichas
            (product_id,version,status,valid_from,observations,total_cost,yield_qty,yield_unit,created_at,updated_at)
            VALUES (?,?,'Borrador',?,?, '0.00',?,?,?,?)""",
            (product_id, version, sanitize_text(data.get("valid_from", date.today().isoformat()), 20),
             sanitize_text(data.get("observations", ""), 1000), quantity_text(yield_qty), yield_unit, stamp, stamp))
        ficha_id = cur.lastrowid
        total = Decimal("0.00")
        for item in items:
            total += insert_ficha_item(conn, ficha_id, item)
        conn.execute("UPDATE fichas SET total_cost=? WHERE id=?", (money(total), ficha_id))
        return ficha_detail(conn, ficha_id)

    def _clean_yield(self, data, product=None):
        """Rendimiento del lote: comensales, copas, vasos… (cantidad > 0)."""
        default_qty = (product or {}).get("yield_qty") if product else None
        default_unit = (product or {}).get("yield_unit") if product else None
        try:
            qty = amount(data.get("yield_qty", default_qty or 1))
        except ValueError:
            qty = Decimal(1)
        if qty <= 0:
            qty = Decimal(1)
        unit = sanitize_text(data.get("yield_unit", default_unit or "unidad"), 30) or "unidad"
        return qty, unit

    def _update_ficha(self, conn, ficha_id, data):
        ficha = conn.execute("SELECT * FROM fichas WHERE id=?", (ficha_id,)).fetchone()
        if not ficha:
            raise APIError("Ficha no encontrada.", 404)
        if ficha["status"] != "Borrador":
            raise APIError("Solo se pueden editar fichas en estado Borrador. Crea una nueva versión.", 409)
        items = data.get("items") or []
        if not items:
            raise APIError("Añade al menos un insumo o componente.")
        if len(items) > 100:
            raise APIError("No se pueden añadir más de 100 componentes por ficha.")
        yield_qty, yield_unit = self._clean_yield(data, {"yield_qty": ficha["yield_qty"],
                                                         "yield_unit": ficha["yield_unit"]})
        conn.execute("DELETE FROM ficha_items WHERE ficha_id=?", (ficha_id,))
        total = Decimal("0.00")
        for item in items:
            total += insert_ficha_item(conn, ficha_id, item)
        conn.execute("""UPDATE fichas SET observations=?,valid_from=?,total_cost=?,yield_qty=?,yield_unit=?,
            updated_at=? WHERE id=?""",
                     (sanitize_text(data.get("observations", ficha["observations"]), 1000),
                      sanitize_text(data.get("valid_from", ficha["valid_from"]), 20), money(total),
                      quantity_text(yield_qty), yield_unit, now_iso(), ficha_id))
        return ficha_detail(conn, ficha_id)

    def _approve_ficha(self, conn, ficha_id):
        ficha = ficha_detail(conn, ficha_id)
        if not ficha:
            raise APIError("Ficha no encontrada.", 404)
        if not ficha["items"]:
            raise APIError("No se puede aprobar una ficha sin componentes.")
        for item in ficha["items"]:
            if amount(item["quantity"]) <= 0:
                raise APIError("Hay cantidades no válidas en la ficha.")
        conn.execute("UPDATE fichas SET status='Aprobada',updated_at=? WHERE id=?", (now_iso(), ficha_id))
        return ficha_detail(conn, ficha_id)

    def _create_control(self, conn, data):
        ficha_id = int(data.get("ficha_id"))
        ficha = ficha_detail(conn, ficha_id)
        if not ficha:
            raise APIError("Ficha no encontrada.", 404)
        period = sanitize_text(data.get("period", date.today().strftime("%Y-%m")), 10)
        if not period or not re.match(r'^\d{4}-\d{2}$', period):
            raise APIError("Indica el período del control en formato AAAA-MM.")
        if not ficha["items"]:
            raise APIError("No se puede crear un control desde una ficha vacía.")
        year = period[:4]
        code_prefix = f"IPV-{year}-"
        last_code = conn.execute("SELECT code FROM controls WHERE code LIKE ? ORDER BY id DESC LIMIT 1", (code_prefix + "%",)).fetchone()
        try:
            sequence = int(last_code["code"].split("-")[-1]) + 1 if last_code else 1
        except (ValueError, IndexError):
            sequence = conn.execute("SELECT COALESCE(MAX(id),0)+1 FROM controls").fetchone()[0]
        code = f"{code_prefix}{sequence:04d}"
        stamp = now_iso()
        cur = conn.execute("""INSERT INTO controls
            (code,ficha_id,product_id,period,status,snapshot_total,checked_total,notes,created_at)
            VALUES (?,?,?,?,'Pendiente',?,'0.00',?,?)""",
            (code, ficha_id, ficha["product_id"], period, ficha["total_cost"], sanitize_text(data.get("notes", ""), 1000), stamp))
        control_id = cur.lastrowid
        for item in ficha["items"]:
            conn.execute("""INSERT INTO control_items
                (control_id,material_id,description,quantity,unit,unit_cost,subtotal)
                VALUES (?,?,?,?,?,?,?)""",
                (control_id, item["material_id"], item["description"], item["quantity"], item["unit"], item["unit_cost"], item["subtotal"]))
        return control_detail(conn, control_id)

    def _validate_control(self, conn, control_id):
        control = conn.execute("SELECT * FROM controls WHERE id=?", (control_id,)).fetchone()
        if not control:
            raise APIError("Control no encontrado.", 404)
        ficha = ficha_detail(conn, control["ficha_id"])
        items = [dict(r) for r in conn.execute("SELECT * FROM control_items WHERE control_id=? ORDER BY id", (control_id,)).fetchall()]
        messages = []
        if ficha["status"] != "Aprobada":
            messages.append({"type": "error", "text": "La Ficha de Costo vinculada no está aprobada."})
        if not items:
            messages.append({"type": "error", "text": "El control no contiene líneas de detalle."})
        snapshot_sum = Decimal("0.00")
        for item in items:
            snapshot_sum += amount(item["subtotal"])
            if not str(item["description"]).strip():
                messages.append({"type": "error", "text": "Existe una línea sin descripción."})
            if amount(item["quantity"]) <= 0:
                messages.append({"type": "error", "text": f"Cantidad no válida en: {item['description']}."})
        snapshot_sum = snapshot_sum.quantize(CENT, rounding=ROUND_HALF_UP)
        if snapshot_sum != amount(control["snapshot_total"]).quantize(CENT, rounding=ROUND_HALF_UP):
            messages.append({"type": "error", "text": "La suma de las líneas no coincide con el total registrado en el control."})
        if amount(control["snapshot_total"]).quantize(CENT, rounding=ROUND_HALF_UP) != amount(ficha["total_cost"]).quantize(CENT, rounding=ROUND_HALF_UP):
            messages.append({"type": "error", "text": "El total del control no coincide con el total de la ficha vinculada."})
        if not any(m["type"] == "error" for m in messages):
            messages.append({"type": "success", "text": "El total y las líneas coinciden con la Ficha de Costo vinculada."})
            status = "Validado"
        else:
            status = "Con diferencias"
        checked_at = now_iso()
        conn.execute("UPDATE controls SET status=?,checked_total=?,validation_report=?,checked_at=? WHERE id=?",
                     (status, money(snapshot_sum), json.dumps(messages, ensure_ascii=False), checked_at, control_id))
        return control_detail(conn, control_id)


def auto_backup():
    """Create a timestamped backup of the database on startup."""
    if not DB_PATH.exists():
        return
    backup_dir = ROOT / "data" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"ipv_backup_{timestamp}.db"
    try:
        import shutil
        shutil.copy2(str(DB_PATH), str(backup_path))
        # Keep only last 10 backups
        backups = sorted(backup_dir.glob("ipv_backup_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in backups[10:]:
            old.unlink()
        print(f"  Backup: {backup_path.name}")
    except Exception as e:
        print(f"  Backup failed: {e}")


# ==========================================================================
#  MAIN
# ==========================================================================

def main():
    init_db()
    if bool(TLS_CERT) != bool(TLS_KEY):
        raise RuntimeError("Configura IPV_TLS_CERT e IPV_TLS_KEY juntos para habilitar HTTPS.")
    # Auto-backup on startup
    auto_backup()
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    scheme = "http"
    if TLS_CERT and TLS_KEY:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        # Strong cipher suites only
        context.set_ciphers("ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS")
        context.load_cert_chain(certfile=TLS_CERT, keyfile=TLS_KEY)
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
        scheme = "https"
    print(f"═══════════════════════════════════════════════════")
    print(f"  IPV · Fichas y Costos v1.0")
    print(f"  {scheme}://{HOST}:{PORT}")
    print(f"  SQLite: {DB_PATH}")
    print(f"  TLS: {'✓' if TLS_CERT else '✗'}  Auth: {'✓' if API_TOKEN else '✗'}  Rate limit: {RATE_LIMIT_MAX}/{RATE_LIMIT_WINDOW}s")
    print(f"═══════════════════════════════════════════════════")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nCerrando servidor…")
    finally:
        httpd.server_close()


# ==========================================================================
#  ADVANCED FEATURES — Statistics, Reports, Bulk Operations
# ==========================================================================

def get_statistics(conn):
    """Comprehensive statistics for analytics dashboard."""
    # Monthly ficha creation trend
    monthly_trend = [dict(r) for r in conn.execute("""
        SELECT strftime('%Y-%m', created_at) as month, COUNT(*) as count
        FROM fichas
        WHERE created_at >= date('now', '-12 months')
        GROUP BY month
        ORDER BY month DESC
        LIMIT 12
    """).fetchall()]
    
    # Top 5 most expensive products
    top_expensive = [dict(r) for r in conn.execute("""
        SELECT p.name, p.code, f.total_cost, f.version
        FROM fichas f
        JOIN products p ON p.id = f.product_id
        WHERE f.id IN (SELECT MAX(id) FROM fichas GROUP BY product_id)
        ORDER BY CAST(f.total_cost AS REAL) DESC
        LIMIT 5
    """).fetchall()]
    
    # Status distribution
    status_dist = [dict(r) for r in conn.execute("""
        SELECT status, COUNT(*) as count
        FROM fichas
        GROUP BY status
    """).fetchall()]
    
    # Average cost per category
    avg_by_category = [dict(r) for r in conn.execute("""
        SELECT p.category, AVG(CAST(f.total_cost AS REAL)) as avg_cost
        FROM fichas f
        JOIN products p ON p.id = f.product_id
        WHERE f.id IN (SELECT MAX(id) FROM fichas GROUP BY product_id)
        GROUP BY p.category
    """).fetchall()]
    
    return {
        "monthly_trend": monthly_trend,
        "top_expensive": top_expensive,
        "status_distribution": status_dist,
        "avg_cost_by_category": avg_by_category,
    }


def export_database_backup():
    """Create a downloadable backup of the database."""
    import shutil
    import tempfile
    backup_dir = ROOT / "data" / "exports"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"ipv_export_{timestamp}.db"
    try:
        shutil.copy2(str(DB_PATH), str(backup_path))
        return {
            "success": True,
            "filename": backup_path.name,
            "size": backup_path.stat().st_size,
            "path": str(backup_path),
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_audit_log(limit=50):
    """Retrieve recent audit log entries."""
    # In a production system, this would read from a dedicated audit table
    # For now, we'll return a placeholder structure
    return {
        "entries": [],
        "message": "Audit log endpoint ready. Implement persistent logging to populate entries."
    }


def bulk_update_prices(conn, updates):
    """Bulk update material prices with validation."""
    results = []
    for update in updates:
        try:
            material_id = int(update.get("id"))
            new_price = amount(update.get("price"))
            if new_price < 0:
                results.append({"id": material_id, "success": False, "error": "Precio negativo"})
                continue
            conn.execute(
                "UPDATE materials SET unit_price=?, updated_at=? WHERE id=?",
                (money(new_price), now_iso(), material_id)
            )
            results.append({"id": material_id, "success": True})
        except Exception as e:
            results.append({"id": update.get("id"), "success": False, "error": str(e)})
    return results


def generate_report(conn, report_type, filters=None):
    """Generate different types of reports."""
    filters = filters or {}
    
    if report_type == "fichas_summary":
        data = [dict(r) for r in conn.execute("""
            SELECT p.name as product, p.category, f.version, f.status, 
                   f.total_cost, f.created_at, f.updated_at
            FROM fichas f
            JOIN products p ON p.id = f.product_id
            ORDER BY f.updated_at DESC
        """).fetchall()]
        return {"type": "fichas_summary", "data": data, "count": len(data)}
    
    elif report_type == "materials_inventory":
        data = [dict(r) for r in conn.execute("""
            SELECT code, name, category, unit, unit_price, currency, stock, min_stock, supplier,
                   source, effective_from, status
            FROM materials WHERE deleted_at=''
            ORDER BY category, name
        """).fetchall()]
        return {"type": "materials_inventory", "data": data, "count": len(data)}
    
    elif report_type == "controls_pending":
        data = [dict(r) for r in conn.execute("""
            SELECT c.code, c.period, c.status, c.snapshot_total,
                   p.name as product, f.version as ficha_version
            FROM controls c
            JOIN products p ON p.id = c.product_id
            JOIN fichas f ON f.id = c.ficha_id
            WHERE c.status IN ('Pendiente', 'Con diferencias')
            ORDER BY c.created_at DESC
        """).fetchall()]
        return {"type": "controls_pending", "data": data, "count": len(data)}
    
    return {"error": "Tipo de reporte no válido"}


# Add new API endpoints to Handler
def handle_advanced_endpoints(self, path, conn=None):
    """Handle advanced API endpoints."""
    if path == "/api/statistics":
        with db_session() as c:
            return get_statistics(c)
    elif path == "/api/backup":
        return export_database_backup()
    elif path == "/api/audit":
        return get_audit_log()
    elif path.startswith("/api/report/"):
        report_type = path.split("/")[-1]
        with db_session() as c:
            return generate_report(c, report_type)
    return None

# Monkey patch the Handler to add new endpoints
original_do_get = Handler.do_GET
def enhanced_do_GET(self):
    parsed = urlparse(self.path)
    path = parsed.path.rstrip("/") or "/"
    
    # Try advanced endpoints first
    if path in ["/api/statistics", "/api/backup", "/api/audit"] or path.startswith("/api/report/"):
        if not self._pre_check():
            return
        try:
            result = handle_advanced_endpoints(self, path)
            if result is not None:
                self.send_json(result)
                return
        except Exception as e:
            print("Advanced endpoint error:", repr(e)); self.send_json({"error": "Error interno del servidor."}, 500)
            return
    
    # Fall back to original handler
    original_do_get(self)

Handler.do_GET = enhanced_do_GET

# Add bulk update to POST handler
original_do_post = Handler.do_POST
def enhanced_do_POST(self):
    parsed = urlparse(self.path)
    path = parsed.path.rstrip("/")
    
    if path == "/api/materials/bulk-update":
        if not self._pre_check():
            return
        try:
            data = self.body_json()
            updates = data.get("updates", [])
            with WRITE_LOCK, connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                result = bulk_update_prices(conn, updates)
                conn.commit()
                audit_log("BULK_UPDATE", f"count={len(updates)}", self.client_ip())
            self.send_json({"results": result})
            return
        except Exception as e:
            print("Advanced endpoint error:", repr(e)); self.send_json({"error": "Error interno del servidor."}, 500)
            return
    
    # Fall back to original handler
    original_do_post(self)

Handler.do_POST = enhanced_do_POST


# ==========================================================================
#  ENTERPRISE — JWT, auditoría persistente, rate limiting granular, API v1,
#  tiempo real (SSE), backups programados y notificaciones
# ==========================================================================
import enterprise  # noqa: E402

enterprise.install(sys.modules[__name__])

import licencia  # noqa: E402  — licencias por período (keygen/keygen.py)

licencia.install(sys.modules[__name__])

if __name__ == "__main__":
    main()
