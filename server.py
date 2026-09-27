#!/usr/bin/env python3
"""IPV · Fichas y Costos — Servidor de aplicación para red local.

Publica la API JSON y el cliente web del sistema de gestión de costos sobre
HTTP o HTTPS, con persistencia en SQLite y trazabilidad de cada operación.
Se implementa únicamente con la biblioteca estándar de Python.

Autor: Ing. Yosvany Hernández Quintero
"""
from __future__ import annotations

import argparse
import gzip
import json
import logging
import os
import platform
import re
import socket
import sqlite3
import ssl
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import parse_qs, unquote, urlparse

# --------------------------------------------------------------------------- #
# Identidad de la aplicación
# --------------------------------------------------------------------------- #
APP_NAME = "IPV · Fichas y Costos"
APP_VERSION = "2.0.0"
APP_RELEASE = "2026-09-27"
APP_AUTHOR = "Ing. Yosvany Hernández Quintero"
APP_ROLE = "Diseño, desarrollo e implementación"
APP_DESCRIPTION = (
    "Plataforma para el catálogo de productos y servicios, el registro de valores de "
    "referencia del IPV, las Fichas de Costo versionadas y los Controles de IPV con "
    "trazabilidad completa de cada operación."
)
DATA_NOTICE = (
    "Los importes precargados son datos de ejemplo para la configuración inicial. "
    "Reemplácelos por los valores y documentos oficiales de su entidad."
)

# --------------------------------------------------------------------------- #
# Configuración (variables de entorno y argumentos de línea de comandos)
# --------------------------------------------------------------------------- #
ROOT = Path(__file__).resolve().parent
WEB_ROOT = (ROOT / "web").resolve()


def _env_path(name: str, default: Path) -> Path:
    return Path(os.environ.get(name, default)).expanduser().resolve()


DB_PATH = _env_path("IPV_DB_PATH", ROOT / "data" / "ipv.db")
BACKUP_DIR = _env_path("IPV_BACKUP_DIR", DB_PATH.parent / "backups")
HOST = os.environ.get("IPV_HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", os.environ.get("IPV_PORT", "8000")))
TLS_CERT = os.environ.get("IPV_TLS_CERT", "").strip()
TLS_KEY = os.environ.get("IPV_TLS_KEY", "").strip()
DEFAULT_OPERATOR = os.environ.get("IPV_OPERATOR", "Operador local").strip() or "Operador local"
MAX_BODY_BYTES = int(os.environ.get("IPV_MAX_BODY_BYTES", "2000000"))
CENT = Decimal("0.01")
MONEY_QUANT = Decimal("0.01")
QUANTITY_QUANT = Decimal("0.000001")
WRITE_LOCK = threading.RLock()
STARTED_AT = time.time()
LOG = logging.getLogger("ipv")

FICHA_STATES = ("Borrador", "Aprobada")
CONTROL_STATES = ("Pendiente", "Validado", "Con diferencias")
MATERIAL_STATES = ("Vigente", "Suspendido", "Descontinuado")
MATERIAL_KINDS = ("Insumo", "Materia prima", "Mano de obra", "Servicio", "Gasto indirecto", "Otros")
PRODUCT_UNITS = ("unidad", "ración", "porción", "vaso", "copa", "botella", "plato", "hora", "servicio", "kg", "L")


# --------------------------------------------------------------------------- #
# Utilidades de formato y validación
# --------------------------------------------------------------------------- #
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today_iso() -> str:
    return date.today().isoformat()


def display_datetime(value: str | None) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return str(value)


def amount(value: Any, default: str = "0") -> Decimal:
    """Convierte un valor a Decimal validando que sea finito y numérico."""
    if value is None or value == "":
        value = default
    try:
        result = Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, ValueError, AttributeError):
        raise ValueError("Importe o cantidad no válido.")
    if not result.is_finite():
        raise ValueError("Importe o cantidad no válido.")
    return result


def money(value: Any) -> str:
    return str(amount(value).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP))


def quantity_text(value: Any) -> str:
    text = format(amount(value).quantize(QUANTITY_QUANT, rounding=ROUND_HALF_UP).normalize(), "f")
    return "0" if text in ("-0", "") else text


def money_number(value: Any) -> float:
    """Versión numérica para agregados estadísticos (gráficos del tablero)."""
    return float(amount(value).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP))


def clean_text(value: Any, label: str, *, max_length: int = 400, required: bool = False) -> str:
    text = "" if value is None else str(value).replace("\x00", "").strip()
    if len(text) > max_length:
        raise APIError(f"{label}: se superó la longitud máxima de {max_length} caracteres.")
    if required and not text:
        raise APIError(f"{label} es obligatorio.")
    return text


def clean_int(value: Any, label: str, *, minimum: int | None = None) -> int:
    try:
        result = int(str(value).strip())
    except (TypeError, ValueError):
        raise APIError(f"{label} no es válido.")
    if minimum is not None and result < minimum:
        raise APIError(f"{label} no es válido.")
    return result


def clean_date(value: Any, label: str) -> str:
    text = clean_text(value, label, max_length=10)
    if not text:
        return ""
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        raise APIError(f"{label} debe tener el formato AAAA-MM-DD.")


def clean_period(value: Any, label: str = "El período") -> str:
    text = clean_text(value, label, max_length=7)
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", text or ""):
        raise APIError(f"{label} debe tener el formato AAAA-MM (por ejemplo 2026-09).")
    return text


def clean_choice(value: Any, label: str, options: Iterable[str], *, default: str = "") -> str:
    text = clean_text(value, label, max_length=60) or default
    if text not in tuple(options):
        raise APIError(f"{label} debe ser uno de: {', '.join(options)}.")
    return text


def day_delta(value: str, reference: date | None = None) -> int | None:
    """Días entre la fecha indicada y la referencia (positivo = futuro)."""
    if not value:
        return None
    try:
        target = date.fromisoformat(value)
    except ValueError:
        return None
    return (target - (reference or date.today())).days


class APIError(Exception):
    """Error controlado que se devuelve al cliente con un mensaje claro."""

    def __init__(self, message: str, status: int = 400, code: str = "solicitud_invalida") -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


# --------------------------------------------------------------------------- #
# Bases de datos
# --------------------------------------------------------------------------- #
SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    unit TEXT NOT NULL DEFAULT 'unidad',
    description TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'Insumo',
    unit TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'CUP',
    unit_price TEXT NOT NULL DEFAULT '0.00',
    supplier TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    effective_from TEXT NOT NULL DEFAULT '',
    effective_to TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'Vigente',
    notes TEXT NOT NULL DEFAULT '',
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
    prepared_by TEXT NOT NULL DEFAULT '',
    approved_by TEXT NOT NULL DEFAULT '',
    approved_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(product_id, version)
);
CREATE TABLE IF NOT EXISTS ficha_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ficha_id INTEGER NOT NULL REFERENCES fichas(id) ON DELETE CASCADE,
    material_id INTEGER REFERENCES materials(id) ON DELETE SET NULL,
    description TEXT NOT NULL,
    unit TEXT NOT NULL,
    quantity TEXT NOT NULL,
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
    created_by TEXT NOT NULL DEFAULT '',
    checked_by TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    checked_at TEXT NOT NULL DEFAULT '',
    UNIQUE(ficha_id, period)
);
CREATE TABLE IF NOT EXISTS control_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    control_id INTEGER NOT NULL REFERENCES controls(id) ON DELETE CASCADE,
    material_id INTEGER REFERENCES materials(id) ON DELETE SET NULL,
    description TEXT NOT NULL,
    unit TEXT NOT NULL,
    quantity TEXT NOT NULL,
    unit_cost TEXT NOT NULL,
    subtotal TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL,
    entity TEXT NOT NULL,
    entity_id INTEGER,
    summary TEXT NOT NULL DEFAULT '',
    details TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_fichas_product ON fichas(product_id, version DESC);
CREATE INDEX IF NOT EXISTS idx_controls_period ON controls(period DESC);
CREATE INDEX IF NOT EXISTS idx_controls_ficha ON controls(ficha_id);
CREATE INDEX IF NOT EXISTS idx_audit_at ON audit_log(at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity, entity_id);
CREATE INDEX IF NOT EXISTS idx_items_material ON ficha_items(material_id);
"""

# Columnas añadidas después de la primera versión del esquema (bases existentes).
MIGRATIONS: tuple[tuple[str, str, str], ...] = (
    ("materials", "kind", "TEXT NOT NULL DEFAULT 'Insumo'"),
    ("materials", "notes", "TEXT NOT NULL DEFAULT ''"),
    ("fichas", "prepared_by", "TEXT NOT NULL DEFAULT ''"),
    ("fichas", "approved_by", "TEXT NOT NULL DEFAULT ''"),
    ("fichas", "approved_at", "TEXT NOT NULL DEFAULT ''"),
    ("controls", "created_by", "TEXT NOT NULL DEFAULT ''"),
    ("controls", "checked_by", "TEXT NOT NULL DEFAULT ''"),
)


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=25)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 25000")
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
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        for table, column, ddl in MIGRATIONS:
            ensure_column(conn, table, column, ddl)
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (2, now_iso()),
        )
        if conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
            seed_demo(conn)


def ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


# --------------------------------------------------------------------------- #
# Datos iniciales
# --------------------------------------------------------------------------- #
def seed_demo(conn: sqlite3.Connection) -> None:
    stamp = now_iso()
    materials = [
        ("INS-001", "Ron añejo", "Insumo", "L", "820.00", "Almacén central", "Acta de valoración inicial"),
        ("INS-002", "Limón criollo", "Insumo", "kg", "210.00", "Mercado agropecuario", "Acta de valoración inicial"),
        ("INS-003", "Azúcar refino", "Insumo", "kg", "95.00", "Almacén central", "Acta de valoración inicial"),
        ("INS-004", "Hierbabuena", "Insumo", "kg", "600.00", "Mercado agropecuario", "Acta de valoración inicial"),
        ("INS-005", "Agua gaseada", "Insumo", "L", "85.00", "Almacén central", "Acta de valoración inicial"),
        ("INS-006", "Mango", "Insumo", "kg", "180.00", "Mercado agropecuario", "Acta de valoración inicial"),
        ("INS-007", "Arroz", "Insumo", "kg", "130.00", "Almacén central", "Acta de valoración inicial"),
        ("INS-008", "Frijol negro", "Insumo", "kg", "220.00", "Almacén central", "Acta de valoración inicial"),
        ("INS-009", "Pollo", "Insumo", "kg", "490.00", "Almacén central", "Acta de valoración inicial"),
        ("INS-010", "Aceite vegetal", "Insumo", "L", "480.00", "Almacén central", "Acta de valoración inicial"),
        ("INS-011", "Sal", "Insumo", "kg", "70.00", "Almacén central", "Acta de valoración inicial"),
        ("INS-012", "Mano de obra directa", "Mano de obra", "hora", "220.00", "Nómina", "Tarifa aprobada"),
    ]
    material_ids: dict[str, int] = {}
    for code, name, kind, unit, price, supplier, source in materials:
        cur = conn.execute(
            """INSERT INTO materials
               (code,name,kind,unit,currency,unit_price,supplier,source,effective_from,effective_to,
                status,notes,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (code, name, kind, unit, "CUP", price, supplier, source, today_iso(), "", "Vigente", "", stamp, stamp),
        )
        material_ids[code] = int(cur.lastrowid)

    products = [
        ("BEB-001", "Mojito clásico", "Bebidas", "copa", "Coctel elaborado en barra."),
        ("BEB-002", "Jugo natural de mango", "Bebidas", "vaso", "Jugo natural por vaso de 300 ml."),
        ("COM-001", "Arroz congrí", "Comidas", "ración", "Ración individual de acompañante."),
        ("COM-002", "Pollo asado", "Comidas", "ración", "Ración individual con guarnición."),
        ("SER-001", "Servicio de salón", "Servicios", "hora", "Atención de salón por hora de servicio."),
    ]
    product_ids: dict[str, int] = {}
    for code, name, category, unit, description in products:
        cur = conn.execute(
            """INSERT INTO products (code,name,category,unit,description,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?)""",
            (code, name, category, unit, description, stamp, stamp),
        )
        product_ids[code] = int(cur.lastrowid)

    recipes = [
        ("BEB-001", "Aprobada", [("INS-001", "0.05"), ("INS-002", "0.03"), ("INS-003", "0.02"),
                                 ("INS-004", "0.005"), ("INS-005", "0.12")]),
        ("BEB-002", "Aprobada", [("INS-006", "0.25"), ("INS-003", "0.02")]),
        ("COM-001", "Aprobada", [("INS-007", "0.12"), ("INS-008", "0.04"), ("INS-010", "0.01"),
                                 ("INS-011", "0.002")]),
        ("COM-002", "Borrador", [("INS-009", "0.25"), ("INS-010", "0.01"), ("INS-011", "0.002")]),
        ("SER-001", "Aprobada", [("INS-012", "0.5")]),
    ]
    ficha_ids: dict[str, int] = {}
    for pcode, status, lines in recipes:
        product_id = product_ids[pcode]
        approved_at = stamp if status == "Aprobada" else ""
        cur = conn.execute(
            """INSERT INTO fichas
               (product_id,version,status,valid_from,observations,total_cost,prepared_by,approved_by,
                approved_at,created_at,updated_at)
               VALUES (?,1,?,?,?, '0.00',?,?,?,?,?)""",
            (product_id, status, today_iso(), "Ficha inicial del producto o servicio.",
             DEFAULT_OPERATOR, "Dirección de la unidad" if status == "Aprobada" else "", approved_at, stamp, stamp),
        )
        ficha_id = int(cur.lastrowid)
        total = Decimal("0.00")
        for material_code, qty_value in lines:
            material = conn.execute("SELECT * FROM materials WHERE id=?", (material_ids[material_code],)).fetchone()
            assert material is not None
            quantity = amount(qty_value)
            unit_cost = amount(material["unit_price"])
            subtotal = (quantity * unit_cost).quantize(CENT, rounding=ROUND_HALF_UP)
            total += subtotal
            conn.execute(
                """INSERT INTO ficha_items (ficha_id,material_id,description,unit,quantity,unit_cost,subtotal)
                   VALUES (?,?,?,?,?,?,?)""",
                (ficha_id, material["id"], material["name"], material["unit"],
                 quantity_text(quantity), money(unit_cost), money(subtotal)),
            )
        conn.execute("UPDATE fichas SET total_cost=? WHERE id=?", (money(total), ficha_id))
        record_audit(conn, "crear", "ficha", ficha_id, f"Ficha v1 creada para {pcode}.", actor=DEFAULT_OPERATOR)
        ficha_ids[pcode] = ficha_id

    create_seed_control(conn, ficha_ids["BEB-001"], "2026-09", "Validado", "IPV-2026-0001")
    create_seed_control(conn, ficha_ids["COM-001"], "2026-09", "Pendiente", "IPV-2026-0002")
    record_audit(conn, "sistema", "sistema", None,
                 "Base de datos inicializada con el conjunto de datos de ejemplo.", actor="Sistema")


def create_seed_control(conn: sqlite3.Connection, ficha_id: int, period: str, status: str, code: str) -> None:
    stamp = now_iso()
    ficha = conn.execute("SELECT * FROM fichas WHERE id=?", (ficha_id,)).fetchone()
    cur = conn.execute(
        """INSERT INTO controls
           (code,ficha_id,product_id,period,status,snapshot_total,checked_total,notes,created_by,
            checked_by,created_at,checked_at)
           VALUES (?,?,?,?,?,?,?,'',?,?,?,?)""",
        (code, ficha_id, ficha["product_id"], period, status, ficha["total_cost"], ficha["total_cost"],
         DEFAULT_OPERATOR, "Dirección de la unidad" if status == "Validado" else "", stamp,
         stamp if status == "Validado" else ""),
    )
    for item in conn.execute("SELECT * FROM ficha_items WHERE ficha_id=? ORDER BY id", (ficha_id,)).fetchall():
        conn.execute(
            """INSERT INTO control_items (control_id,material_id,description,unit,quantity,unit_cost,subtotal)
               VALUES (?,?,?,?,?,?,?)""",
            (cur.lastrowid, item["material_id"], item["description"], item["unit"],
             item["quantity"], item["unit_cost"], item["subtotal"]),
        )
    if status == "Validado":
        # El control de ejemplo se valida con el mismo procedimiento que la interfaz,
        # de modo que su informe coincida con el de un control real.
        validate_control(conn, int(cur.lastrowid), {"checked_by": "Dirección de la unidad"}, DEFAULT_OPERATOR)


# --------------------------------------------------------------------------- #
# Bitácora (auditoría)
# --------------------------------------------------------------------------- #
def record_audit(conn: sqlite3.Connection, action: str, entity: str, entity_id: int | None, summary: str,
                 details: dict[str, Any] | None = None, actor: str | None = None) -> None:
    actor = (actor or DEFAULT_OPERATOR).strip() or DEFAULT_OPERATOR
    conn.execute(
        """INSERT INTO audit_log (at,actor,action,entity,entity_id,summary,details)
           VALUES (?,?,?,?,?,?,?)""",
        (now_iso(), actor, action, entity, entity_id, summary,
         json.dumps(details or {}, ensure_ascii=False, default=str)),
    )
    LOG.info("auditoría %s %s#%s · %s · %s", action, entity, entity_id, actor, summary)


def list_audit(conn: sqlite3.Connection, *, limit: int = 120, entity: str = "", entity_id: int | None = None,
               query: str = "") -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if entity:
        clauses.append("entity = ?")
        params.append(entity)
    if entity_id is not None:
        clauses.append("entity_id = ?")
        params.append(entity_id)
    if query:
        clauses.append("(summary LIKE ? OR actor LIKE ? OR action LIKE ?)")
        params.extend([f"%{query}%"] * 3)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM audit_log {where} ORDER BY at DESC, id DESC LIMIT ?", (*params, max(1, min(limit, 500)))
    ).fetchall()
    return [dict(row) for row in rows]


# --------------------------------------------------------------------------- #
# Consultas de dominio
# --------------------------------------------------------------------------- #
def rowdict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def effective_material(row: sqlite3.Row | dict[str, Any]) -> str:
    """Estado operativo del valor: Vigente, Por vencer, Vencido, Suspendido o Descontinuado."""
    status = str(row["status"])
    if status in ("Suspendido", "Descontinuado"):
        return status
    remaining = day_delta(str(row["effective_to"])) if row["effective_to"] else None
    if remaining is not None and remaining < 0:
        return "Vencido"
    if remaining is not None and remaining <= 30:
        return "Por vencer"
    return "Vigente"


def material_view(row: sqlite3.Row | dict[str, Any], usage: int = 0) -> dict[str, Any]:
    data = dict(row)
    data["state"] = effective_material(data)
    data["expires_in_days"] = day_delta(str(data["effective_to"])) if data["effective_to"] else None
    data["usage_count"] = usage
    return data


def list_products(conn: sqlite3.Connection, *, query: str = "", category: str = "", status: str = "") -> list[dict]:
    rows = conn.execute(
        """SELECT p.*,
                  (SELECT COUNT(*) FROM fichas f WHERE f.product_id=p.id) AS ficha_count,
                  (SELECT COUNT(*) FROM fichas f WHERE f.product_id=p.id AND f.status='Aprobada')
                      AS approved_count,
                  (SELECT f.version FROM fichas f WHERE f.product_id=p.id ORDER BY f.version DESC LIMIT 1)
                      AS latest_version,
                  (SELECT f.status FROM fichas f WHERE f.product_id=p.id ORDER BY f.version DESC LIMIT 1)
                      AS latest_status,
                  (SELECT f.total_cost FROM fichas f WHERE f.product_id=p.id ORDER BY f.version DESC LIMIT 1)
                      AS latest_total,
                  (SELECT f.updated_at FROM fichas f WHERE f.product_id=p.id ORDER BY f.version DESC LIMIT 1)
                      AS latest_updated_at
           FROM products p
           ORDER BY p.active DESC, p.category, p.name"""
    ).fetchall()
    data = [dict(row) for row in rows]
    text = query.strip().lower()
    if text:
        data = [row for row in data
                if text in f"{row['code']} {row['name']} {row['category']} {row['description']}".lower()]
    if category:
        data = [row for row in data if row["category"] == category]
    if status == "activos":
        data = [row for row in data if row["active"]]
    elif status == "inactivos":
        data = [row for row in data if not row["active"]]
    return data


def get_product(conn: sqlite3.Connection, product_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """SELECT p.*,
                  (SELECT COUNT(*) FROM fichas f WHERE f.product_id=p.id) AS ficha_count
           FROM products p WHERE p.id=?""",
        (product_id,),
    ).fetchone()
    return rowdict(row)


def list_materials(conn: sqlite3.Connection, *, query: str = "", kind: str = "", state: str = "") -> list[dict]:
    usage = {row["material_id"]: row["total"] for row in conn.execute(
        "SELECT material_id, COUNT(*) AS total FROM ficha_items WHERE material_id IS NOT NULL GROUP BY material_id"
    )}
    rows = conn.execute("SELECT * FROM materials ORDER BY name").fetchall()
    data = [material_view(row, usage.get(row["id"], 0)) for row in rows]
    text = query.strip().lower()
    if text:
        data = [row for row in data
                if text in f"{row['code']} {row['name']} {row['supplier']} {row['source']} {row['kind']}".lower()]
    if kind:
        data = [row for row in data if row["kind"] == kind]
    if state:
        data = [row for row in data if row["state"] == state]
    return data


def get_material(conn: sqlite3.Connection, material_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM materials WHERE id=?", (material_id,)).fetchone()
    return rowdict(row)


def material_detail(conn: sqlite3.Connection, material_id: int) -> dict[str, Any] | None:
    """Valor del IPV con su estado operativo y el número de fichas que lo utilizan."""
    row = conn.execute("SELECT * FROM materials WHERE id=?", (material_id,)).fetchone()
    if row is None:
        return None
    usage = conn.execute("SELECT COUNT(*) FROM ficha_items WHERE material_id=?", (material_id,)).fetchone()[0]
    return material_view(row, int(usage))


def ficha_summary(conn: sqlite3.Connection, ficha_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """SELECT f.*, p.code AS product_code, p.name AS product_name, p.category AS category,
                  p.unit AS product_unit, p.active AS product_active,
                  (SELECT COUNT(*) FROM ficha_items fi WHERE fi.ficha_id=f.id) AS item_count,
                  (SELECT COUNT(*) FROM fichas x WHERE x.product_id=f.product_id) AS version_count,
                  (SELECT COUNT(*) FROM controls c WHERE c.ficha_id=f.id) AS control_count
           FROM fichas f JOIN products p ON p.id=f.product_id WHERE f.id=?""",
        (ficha_id,),
    ).fetchone()
    data = rowdict(row)
    if data:
        data["document_code"] = f"FC-{data['product_code']}-v{data['version']}"
    return data


def ficha_detail(conn: sqlite3.Connection, ficha_id: int) -> dict[str, Any] | None:
    data = ficha_summary(conn, ficha_id)
    if not data:
        return None
    items = conn.execute(
        """SELECT fi.*, m.code AS material_code, m.kind AS material_kind, m.status AS material_status,
                  m.effective_to AS material_effective_to, m.unit_price AS current_unit_price
           FROM ficha_items fi LEFT JOIN materials m ON m.id=fi.material_id
           WHERE fi.ficha_id=? ORDER BY fi.id""",
        (ficha_id,),
    ).fetchall()
    total = amount(data["total_cost"])
    data["items"] = []
    for row in items:
        item = dict(row)
        item["subtotal"] = money(item["subtotal"])
        share = (amount(item["subtotal"]) / total * 100) if total else Decimal("0")
        item["share_percent"] = float(share.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
        item["price_changed"] = bool(
            item["current_unit_price"] is not None and amount(item["current_unit_price"]) != amount(item["unit_cost"])
        )
        data["items"].append(item)
    data["versions"] = [dict(row) for row in conn.execute(
        """SELECT id, version, status, total_cost, valid_from, approved_by, approved_at, updated_at
           FROM fichas WHERE product_id=? ORDER BY version DESC""",
        (data["product_id"],),
    ).fetchall()]
    data["controls"] = [dict(row) for row in conn.execute(
        "SELECT id, code, period, status, snapshot_total, checked_total, checked_at FROM controls "
        "WHERE ficha_id=? ORDER BY period DESC, id DESC",
        (ficha_id,),
    ).fetchall()]
    data["audit"] = list_audit(conn, limit=25, entity="ficha", entity_id=ficha_id)
    return data


def list_fichas(conn: sqlite3.Connection, *, query: str = "", status: str = "", product_id: int | None = None,
                category: str = "") -> list[dict]:
    rows = conn.execute(
        """SELECT f.*, p.code AS product_code, p.name AS product_name, p.category AS category,
                  p.unit AS product_unit, p.active AS product_active,
                  (SELECT COUNT(*) FROM ficha_items fi WHERE fi.ficha_id=f.id) AS item_count,
                  (SELECT COUNT(*) FROM controls c WHERE c.ficha_id=f.id) AS control_count,
                  (SELECT c.status FROM controls c WHERE c.ficha_id=f.id ORDER BY c.id DESC LIMIT 1)
                      AS last_control_status
           FROM fichas f JOIN products p ON p.id=f.product_id
           ORDER BY f.updated_at DESC, f.id DESC"""
    ).fetchall()
    data = []
    for row in rows:
        item = dict(row)
        item["document_code"] = f"FC-{item['product_code']}-v{item['version']}"
        data.append(item)
    text = query.strip().lower()
    if text:
        data = [row for row in data
                if text in f"{row['document_code']} {row['product_name']} {row['product_code']} "
                           f"{row['category']} {row['status']} {row['observations']}".lower()]
    if status:
        data = [row for row in data if row["status"] == status]
    if category:
        data = [row for row in data if row["category"] == category]
    if product_id is not None:
        data = [row for row in data if row["product_id"] == product_id]
    return data


def control_detail(conn: sqlite3.Connection, control_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """SELECT c.*, p.code AS product_code, p.name AS product_name, p.category, p.unit AS product_unit,
                  f.version AS ficha_version, f.status AS ficha_status, f.total_cost AS ficha_total,
                  f.valid_from AS ficha_valid_from, f.approved_by AS ficha_approved_by
           FROM controls c
           JOIN products p ON p.id=c.product_id
           JOIN fichas f ON f.id=c.ficha_id
           WHERE c.id=?""",
        (control_id,),
    ).fetchone()
    if not row:
        return None
    data = dict(row)
    try:
        messages = json.loads(data.pop("validation_report") or "[]")
    except json.JSONDecodeError:
        messages = []
    data["validation_report"] = messages
    data["validation_messages"] = messages  # compatibilidad con clientes anteriores
    data["ok"] = data["status"] == "Validado"
    data["document_code"] = f"CT-{data['code']}"
    items = conn.execute("SELECT * FROM control_items WHERE control_id=? ORDER BY id", (control_id,)).fetchall()
    total = amount(data["snapshot_total"])
    data["items"] = []
    for item in items:
        entry = dict(item)
        share = (amount(entry["subtotal"]) / total * 100) if total else Decimal("0")
        entry["share_percent"] = float(share.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
        data["items"].append(entry)
    data["audit"] = list_audit(conn, limit=20, entity="control", entity_id=control_id)
    return data


def list_controls(conn: sqlite3.Connection, *, query: str = "", status: str = "", period: str = "") -> list[dict]:
    ids = [row["id"] for row in conn.execute("SELECT id FROM controls ORDER BY created_at DESC, id DESC")]
    data = [control_detail(conn, control_id) for control_id in ids]
    result = [item for item in data if item]
    text = query.strip().lower()
    if text:
        result = [row for row in result
                  if text in f"{row['code']} {row['product_name']} {row['product_code']} {row['status']} "
                             f"{row['period']} {row['notes']}".lower()]
    if status:
        result = [row for row in result if row["status"] == status]
    if period:
        result = [row for row in result if row["period"] == period]
    return result


def catalogue_totals(conn: sqlite3.Connection) -> dict[str, Any]:
    scalar = lambda sql, *args: conn.execute(sql, args).fetchone()[0]  # noqa: E731
    return {
        "products": scalar("SELECT COUNT(*) FROM products"),
        "active_products": scalar("SELECT COUNT(*) FROM products WHERE active=1"),
        "materials": scalar("SELECT COUNT(*) FROM materials"),
        "fichas": scalar("SELECT COUNT(*) FROM fichas"),
        "approved_fichas": scalar("SELECT COUNT(*) FROM fichas WHERE status='Aprobada'"),
        "draft_fichas": scalar("SELECT COUNT(*) FROM fichas WHERE status='Borrador'"),
        "controls": scalar("SELECT COUNT(*) FROM controls"),
        "pending_controls": scalar("SELECT COUNT(*) FROM controls WHERE status='Pendiente'"),
        "validated_controls": scalar("SELECT COUNT(*) FROM controls WHERE status='Validado'"),
        "controls_with_differences": scalar("SELECT COUNT(*) FROM controls WHERE status='Con diferencias'"),
        "audit_events": scalar("SELECT COUNT(*) FROM audit_log"),
    }


def monthly_trend(conn: sqlite3.Connection, months: int = 6) -> dict[str, Any]:
    """Fichas y controles registrados por mes, para el gráfico del tablero."""
    today = date.today()
    buckets: list[str] = []
    year, month = today.year, today.month
    for _ in range(months):
        buckets.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    buckets.reverse()
    fichas = {row["period"]: row["total"] for row in conn.execute(
        "SELECT substr(created_at,1,7) AS period, COUNT(*) AS total FROM fichas "
        "GROUP BY period")}
    controls = {row["period"]: row["total"] for row in conn.execute(
        "SELECT substr(created_at,1,7) AS period, COUNT(*) AS total FROM controls GROUP BY period")}
    return {
        "periods": buckets,
        "fichas": [fichas.get(period, 0) for period in buckets],
        "controls": [controls.get(period, 0) for period in buckets],
    }


def dashboard(conn: sqlite3.Connection) -> dict[str, Any]:
    totals = catalogue_totals(conn)
    categories = conn.execute(
        """SELECT p.category,
                  COUNT(DISTINCT p.id) AS products,
                  (SELECT COUNT(*) FROM fichas f JOIN products p2 ON p2.id=f.product_id
                    WHERE p2.category=p.category) AS fichas,
                  (SELECT AVG(CAST(f.total_cost AS REAL)) FROM fichas f JOIN products p3 ON p3.id=f.product_id
                    WHERE p3.category=p.category AND f.status='Aprobada') AS average_cost
           FROM products p WHERE p.active=1 GROUP BY p.category ORDER BY p.category"""
    ).fetchall()
    category_rows = []
    for row in categories:
        item = dict(row)
        item["average_cost"] = money(item["average_cost"] or 0)
        category_rows.append(item)
    recent_fichas = [dict(row) for row in conn.execute(
        """SELECT f.id, f.version, f.status, f.total_cost, f.updated_at, f.valid_from,
                  p.name AS product_name, p.code AS product_code, p.category
           FROM fichas f JOIN products p ON p.id=f.product_id
           ORDER BY f.updated_at DESC, f.id DESC LIMIT 6"""
    ).fetchall()]
    recent_controls = list_controls(conn)[:5]
    materials = list_materials(conn)
    expired = [row for row in materials if row["state"] == "Vencido"]
    expiring = [row for row in materials if row["state"] == "Por vencer"]
    without_ficha = conn.execute(
        "SELECT COUNT(*) FROM products p WHERE p.active=1 AND NOT EXISTS "
        "(SELECT 1 FROM fichas f WHERE f.product_id=p.id)"
    ).fetchone()[0]
    approved_total = conn.execute(
        "SELECT COALESCE(SUM(CAST(total_cost AS REAL)), 0) FROM fichas WHERE status='Aprobada'"
    ).fetchone()[0]
    average_cost = conn.execute(
        "SELECT COALESCE(AVG(CAST(total_cost AS REAL)), 0) FROM fichas WHERE status='Aprobada'"
    ).fetchone()[0]

    alerts: list[dict[str, Any]] = []
    if totals["controls_with_differences"]:
        alerts.append({
            "severity": "critical",
            "title": "Controles con diferencias",
            "detail": "Existen controles cuya validación detectó diferencias que requieren revisión.",
            "count": totals["controls_with_differences"],
            "view": "controls",
        })
    if totals["pending_controls"]:
        alerts.append({
            "severity": "warning",
            "title": "Controles pendientes de validación",
            "detail": "Hay controles creados que aún no se han validado contra su ficha de costo.",
            "count": totals["pending_controls"],
            "view": "controls",
        })
    if expired:
        alerts.append({
            "severity": "warning",
            "title": "Valores de referencia vencidos",
            "detail": "Valores del IPV cuya vigencia terminó y deben actualizarse o suspenderse.",
            "count": len(expired),
            "view": "materials",
        })
    if expiring:
        alerts.append({
            "severity": "info",
            "title": "Valores próximos a vencer",
            "detail": "Valores del IPV que pierden vigencia en los próximos 30 días.",
            "count": len(expiring),
            "view": "materials",
        })
    if without_ficha:
        alerts.append({
            "severity": "info",
            "title": "Productos sin ficha de costo",
            "detail": "Productos o servicios activos que todavía no tienen una Ficha de Costo asociada.",
            "count": without_ficha,
            "view": "products",
        })

    return {
        "kpis": {
            **totals,
            "catalogue_value": money(sum(amount(row["unit_price"]) for row in materials) if materials else 0),
            "average_ficha_cost": money(average_cost),
            "approved_cost_total": money(approved_total),
            "materials_expired": len(expired),
            "materials_expiring": len(expiring),
            "products_without_ficha": without_ficha,
            "approval_rate": round(totals["approved_fichas"] / totals["fichas"] * 100, 1) if totals["fichas"] else 0.0,
        },
        "products": totals["active_products"],
        "materials": totals["materials"],
        "fichas": totals["fichas"],
        "approved_fichas": totals["approved_fichas"],
        "pending_controls": totals["pending_controls"],
        "validated_controls": totals["validated_controls"],
        "categories": category_rows,
        "trend": monthly_trend(conn),
        "alerts": alerts,
        "recent_fichas": recent_fichas,
        "recent_controls": recent_controls,
        "activity": list_audit(conn, limit=8),
    }


def global_search(conn: sqlite3.Connection, query: str) -> dict[str, Any]:
    text = query.strip().lower()
    if len(text) < 2:
        return {"products": [], "materials": [], "fichas": [], "controls": [], "query": query}
    products = [row for row in list_products(conn) if
                text in f"{row['code']} {row['name']} {row['category']} {row['description']}".lower()][:6]
    materials = [row for row in list_materials(conn) if
                 text in f"{row['code']} {row['name']} {row['supplier']} {row['source']}".lower()][:6]
    fichas = [row for row in list_fichas(conn) if
              text in f"{row['document_code']} {row['product_name']} {row['product_code']} "
                      f"{row['category']} {row['status']}".lower()][:6]
    controls = [row for row in list_controls(conn) if
                text in f"{row['code']} {row['product_name']} {row['product_code']} "
                        f"{row['status']} {row['period']}".lower()][:6]
    return {"query": query, "products": products, "materials": materials, "fichas": fichas, "controls": controls}


# --------------------------------------------------------------------------- #
# Operaciones de escritura
# --------------------------------------------------------------------------- #
def create_product(conn: sqlite3.Connection, data: dict[str, Any], actor: str) -> dict[str, Any]:
    code = clean_text(data.get("code"), "El código", max_length=40, required=True).upper()
    name = clean_text(data.get("name"), "El nombre", max_length=160, required=True)
    category = clean_text(data.get("category"), "La categoría", max_length=80, required=True)
    unit = clean_text(data.get("unit"), "La unidad de salida", max_length=40) or "unidad"
    description = clean_text(data.get("description"), "La descripción", max_length=600)
    stamp = now_iso()
    cur = conn.execute(
        """INSERT INTO products (code,name,category,unit,description,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?)""",
        (code, name, category, unit, description, stamp, stamp),
    )
    product_id = int(cur.lastrowid)
    record_audit(conn, "crear", "producto", product_id, f"Producto {code} · {name} incorporado al catálogo.",
                 {"category": category, "unit": unit}, actor)
    return get_product(conn, product_id) or {}


def update_product(conn: sqlite3.Connection, product_id: int, data: dict[str, Any], actor: str) -> dict[str, Any]:
    product = get_product(conn, product_id)
    if not product:
        raise APIError("Producto no encontrado.", 404, "no_encontrado")
    code = clean_text(data.get("code", product["code"]), "El código", max_length=40, required=True).upper()
    name = clean_text(data.get("name", product["name"]), "El nombre", max_length=160, required=True)
    category = clean_text(data.get("category", product["category"]), "La categoría", max_length=80, required=True)
    unit = clean_text(data.get("unit", product["unit"]), "La unidad de salida", max_length=40) or "unidad"
    description = clean_text(data.get("description", product["description"]), "La descripción", max_length=600)
    conn.execute(
        "UPDATE products SET code=?,name=?,category=?,unit=?,description=?,updated_at=? WHERE id=?",
        (code, name, category, unit, description, now_iso(), product_id),
    )
    record_audit(conn, "actualizar", "producto", product_id, f"Producto {code} actualizado.",
                 {"category": category, "unit": unit}, actor)
    return get_product(conn, product_id) or {}


def set_product_active(conn: sqlite3.Connection, product_id: int, active: bool, actor: str) -> dict[str, Any]:
    product = get_product(conn, product_id)
    if not product:
        raise APIError("Producto no encontrado.", 404, "no_encontrado")
    conn.execute("UPDATE products SET active=?, updated_at=? WHERE id=?",
                 (1 if active else 0, now_iso(), product_id))
    record_audit(conn, "activar" if active else "desactivar", "producto", product_id,
                 f"Producto {product['code']} {'reactivado' if active else 'desactivado'} "
                 f"(los documentos históricos se conservan).", None, actor)
    return get_product(conn, product_id) or {}


def create_material(conn: sqlite3.Connection, data: dict[str, Any], actor: str) -> dict[str, Any]:
    code = clean_text(data.get("code"), "El código", max_length=40, required=True).upper()
    name = clean_text(data.get("name"), "El nombre", max_length=160, required=True)
    unit = clean_text(data.get("unit"), "La unidad", max_length=40, required=True)
    kind = clean_choice(data.get("kind"), "El tipo de valor", MATERIAL_KINDS, default="Insumo")
    currency = clean_text(data.get("currency", "CUP"), "La moneda", max_length=10).upper() or "CUP"
    unit_price = amount(data.get("unit_price"))
    if unit_price < 0:
        raise APIError("El precio unitario no puede ser negativo.")
    effective_from = clean_date(data.get("effective_from") or today_iso(), "La fecha de vigencia inicial")
    effective_to = clean_date(data.get("effective_to"), "La fecha de vigencia final")
    if effective_from and effective_to and effective_to < effective_from:
        raise APIError("La fecha final de vigencia no puede ser anterior a la inicial.")
    status = clean_choice(data.get("status"), "El estado", MATERIAL_STATES, default="Vigente")
    stamp = now_iso()
    cur = conn.execute(
        """INSERT INTO materials
           (code,name,kind,unit,currency,unit_price,supplier,source,effective_from,effective_to,status,
            notes,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (code, name, kind, unit, currency, money(unit_price),
         clean_text(data.get("supplier"), "El proveedor o fuente", max_length=160),
         clean_text(data.get("source"), "El documento de respaldo", max_length=200),
         effective_from, effective_to, status,
         clean_text(data.get("notes"), "Las notas", max_length=600), stamp, stamp),
    )
    material_id = int(cur.lastrowid)
    record_audit(conn, "crear", "valor", material_id,
                 f"Valor {code} · {name} registrado a {money(unit_price)} {currency}/{unit}.",
                 {"kind": kind, "effective_from": effective_from, "effective_to": effective_to}, actor)
    return material_detail(conn, material_id) or {}


def update_material(conn: sqlite3.Connection, material_id: int, data: dict[str, Any], actor: str) -> dict[str, Any]:
    material = get_material(conn, material_id)
    if not material:
        raise APIError("Valor del IPV no encontrado.", 404, "no_encontrado")
    code = clean_text(data.get("code", material["code"]), "El código", max_length=40, required=True).upper()
    name = clean_text(data.get("name", material["name"]), "El nombre", max_length=160, required=True)
    unit = clean_text(data.get("unit", material["unit"]), "La unidad", max_length=40, required=True)
    kind = clean_choice(data.get("kind", material["kind"]), "El tipo de valor", MATERIAL_KINDS, default="Insumo")
    currency = clean_text(data.get("currency", material["currency"]), "La moneda", max_length=10).upper() or "CUP"
    unit_price = amount(data.get("unit_price", material["unit_price"]))
    if unit_price < 0:
        raise APIError("El precio unitario no puede ser negativo.")
    effective_from = clean_date(data.get("effective_from", material["effective_from"]), "La vigencia inicial")
    effective_to = clean_date(data.get("effective_to", material["effective_to"]), "La vigencia final")
    if effective_from and effective_to and effective_to < effective_from:
        raise APIError("La fecha final de vigencia no puede ser anterior a la inicial.")
    status = clean_choice(data.get("status", material["status"]), "El estado", MATERIAL_STATES, default="Vigente")
    price_changed = amount(material["unit_price"]) != unit_price
    conn.execute(
        """UPDATE materials SET code=?,name=?,kind=?,unit=?,currency=?,unit_price=?,supplier=?,source=?,
                  effective_from=?,effective_to=?,status=?,notes=?,updated_at=? WHERE id=?""",
        (code, name, kind, unit, currency, money(unit_price),
         clean_text(data.get("supplier", material["supplier"]), "El proveedor o fuente", max_length=160),
         clean_text(data.get("source", material["source"]), "El documento de respaldo", max_length=200),
         effective_from, effective_to, status,
         clean_text(data.get("notes", material["notes"]), "Las notas", max_length=600),
         now_iso(), material_id),
    )
    summary = f"Valor {code} actualizado."
    if price_changed:
        summary += f" Precio: {money(material['unit_price'])} → {money(unit_price)} {currency}."
    record_audit(conn, "actualizar", "valor", material_id, summary,
                 {"price_before": str(material["unit_price"]), "price_after": money(unit_price)}, actor)
    return material_detail(conn, material_id) or {}


def build_ficha_item(conn: sqlite3.Connection, item: dict[str, Any]) -> tuple:
    """Normaliza una línea de ficha: o bien referencia un valor del IPV o es un componente libre."""
    material_id = item.get("material_id")
    if material_id not in (None, "", "null"):
        material = get_material(conn, clean_int(material_id, "El insumo seleccionado", minimum=1))
        if not material:
            raise APIError("El insumo o valor seleccionado no existe.", 404, "no_encontrado")
        description = material["name"]
        unit = clean_text(item.get("unit"), "La unidad", max_length=40) or material["unit"]
        unit_cost = amount(item.get("unit_cost", material["unit_price"]))
        stored_material_id: int | None = int(material["id"])
    else:
        description = clean_text(item.get("description"), "La descripción del componente", max_length=200,
                                 required=True)
        unit = clean_text(item.get("unit"), "La unidad del componente", max_length=40, required=True)
        unit_cost = amount(item.get("unit_cost"))
        stored_material_id = None
    quantity = amount(item.get("quantity"))
    if quantity <= 0:
        raise APIError(f"La cantidad de «{description}» debe ser mayor que cero.")
    if unit_cost < 0:
        raise APIError(f"El costo unitario de «{description}» no puede ser negativo.")
    subtotal = (quantity * unit_cost).quantize(CENT, rounding=ROUND_HALF_UP)
    return (stored_material_id, description, unit, quantity_text(quantity), money(unit_cost), money(subtotal), subtotal)


def replace_ficha_items(conn: sqlite3.Connection, ficha_id: int, items: list[dict[str, Any]]) -> Decimal:
    conn.execute("DELETE FROM ficha_items WHERE ficha_id=?", (ficha_id,))
    total = Decimal("0.00")
    for item in items:
        row = build_ficha_item(conn, item)
        conn.execute(
            """INSERT INTO ficha_items (ficha_id,material_id,description,unit,quantity,unit_cost,subtotal)
               VALUES (?,?,?,?,?,?,?)""",
            (ficha_id, row[0], row[1], row[2], row[3], row[4], row[5]),
        )
        total += row[6]
    return total.quantize(CENT, rounding=ROUND_HALF_UP)


def create_ficha(conn: sqlite3.Connection, data: dict[str, Any], actor: str) -> dict[str, Any]:
    product_id = clean_int(data.get("product_id"), "El producto seleccionado", minimum=1)
    product = get_product(conn, product_id)
    if not product or not product["active"]:
        raise APIError("Seleccione un producto o servicio activo del catálogo.")
    items = data.get("items") or []
    if not isinstance(items, list) or not items:
        raise APIError("Añada al menos un componente a la ficha de costo.")
    version = int(conn.execute("SELECT COALESCE(MAX(version),0)+1 FROM fichas WHERE product_id=?",
                               (product_id,)).fetchone()[0])
    stamp = now_iso()
    cur = conn.execute(
        """INSERT INTO fichas (product_id,version,status,valid_from,observations,total_cost,prepared_by,
                               created_at,updated_at)
           VALUES (?,?,'Borrador',?,?,'0.00',?,?,?)""",
        (product_id, version, clean_date(data.get("valid_from") or today_iso(), "La fecha de vigencia"),
         clean_text(data.get("observations"), "Las observaciones", max_length=1000), actor, stamp, stamp),
    )
    ficha_id = int(cur.lastrowid)
    total = replace_ficha_items(conn, ficha_id, items)
    conn.execute("UPDATE fichas SET total_cost=? WHERE id=?", (money(total), ficha_id))
    record_audit(conn, "crear", "ficha", ficha_id,
                 f"Ficha de costo v{version} creada para {product['code']} · {product['name']} "
                 f"con {len(items)} componente(s).",
                 {"total": money(total), "product_code": product["code"]}, actor)
    return ficha_detail(conn, ficha_id) or {}


def update_ficha(conn: sqlite3.Connection, ficha_id: int, data: dict[str, Any], actor: str) -> dict[str, Any]:
    ficha = ficha_summary(conn, ficha_id)
    if not ficha:
        raise APIError("Ficha de costo no encontrada.", 404, "no_encontrado")
    if ficha["status"] != "Borrador":
        raise APIError("Solo se editan fichas en estado Borrador. Cree una nueva versión para registrar cambios.", 409,
                       "estado_invalido")
    items = data.get("items") or []
    if not isinstance(items, list) or not items:
        raise APIError("Añada al menos un componente a la ficha de costo.")
    total = replace_ficha_items(conn, ficha_id, items)
    conn.execute(
        "UPDATE fichas SET observations=?,valid_from=?,total_cost=?,updated_at=? WHERE id=?",
        (clean_text(data.get("observations", ficha["observations"]), "Las observaciones", max_length=1000),
         clean_date(data.get("valid_from", ficha["valid_from"]), "La fecha de vigencia"),
         money(total), now_iso(), ficha_id),
    )
    record_audit(conn, "actualizar", "ficha", ficha_id,
                 f"Borrador v{ficha['version']} actualizado: {len(items)} componente(s), total {money(total)}.",
                 {"total_before": str(ficha["total_cost"]), "total_after": money(total)}, actor)
    return ficha_detail(conn, ficha_id) or {}


def approve_ficha(conn: sqlite3.Connection, ficha_id: int, data: dict[str, Any], actor: str) -> dict[str, Any]:
    ficha = ficha_detail(conn, ficha_id)
    if not ficha:
        raise APIError("Ficha de costo no encontrada.", 404, "no_encontrado")
    if ficha["status"] == "Aprobada":
        raise APIError("La ficha ya está aprobada.", 409, "estado_invalido")
    if not ficha["items"]:
        raise APIError("No se puede aprobar una ficha sin componentes.")
    zero_cost = [item["description"] for item in ficha["items"] if amount(item["subtotal"]) <= 0]
    if zero_cost:
        raise APIError("Revise los componentes sin importe: " + ", ".join(zero_cost[:3]) + ".")
    approved_by = clean_text(data.get("approved_by") or actor, "El responsable de la aprobación", max_length=120)
    stamp = now_iso()
    conn.execute(
        "UPDATE fichas SET status='Aprobada',approved_by=?,approved_at=?,updated_at=? WHERE id=?",
        (approved_by, stamp, stamp, ficha_id),
    )
    record_audit(conn, "aprobar", "ficha", ficha_id,
                 f"Ficha {ficha['document_code']} aprobada por {approved_by}. Total {ficha['total_cost']}.",
                 {"approved_by": approved_by}, actor)
    return ficha_detail(conn, ficha_id) or {}


def reopen_ficha(conn: sqlite3.Connection, ficha_id: int, data: dict[str, Any], actor: str) -> dict[str, Any]:
    ficha = ficha_summary(conn, ficha_id)
    if not ficha:
        raise APIError("Ficha de costo no encontrada.", 404, "no_encontrado")
    if ficha["status"] != "Aprobada":
        raise APIError("Solo se pueden reabrir fichas aprobadas.", 409, "estado_invalido")
    validated = conn.execute("SELECT COUNT(*) FROM controls WHERE ficha_id=? AND status='Validado'",
                             (ficha_id,)).fetchone()[0]
    if validated:
        raise APIError("La ficha tiene controles validados. Cree una nueva versión para conservar la trazabilidad.",
                       409, "estado_invalido")
    reason = clean_text(data.get("reason"), "El motivo de la reapertura", max_length=300, required=True)
    conn.execute("UPDATE fichas SET status='Borrador',approved_by='',approved_at='',updated_at=? WHERE id=?",
                 (now_iso(), ficha_id))
    record_audit(conn, "reabrir", "ficha", ficha_id,
                 f"Ficha {ficha['document_code']} devuelta a borrador. Motivo: {reason}.", {"reason": reason}, actor)
    return ficha_detail(conn, ficha_id) or {}


def duplicate_ficha(conn: sqlite3.Connection, ficha_id: int, data: dict[str, Any], actor: str) -> dict[str, Any]:
    ficha = ficha_detail(conn, ficha_id)
    if not ficha:
        raise APIError("Ficha de costo no encontrada.", 404, "no_encontrado")
    version = int(conn.execute("SELECT COALESCE(MAX(version),0)+1 FROM fichas WHERE product_id=?",
                               (ficha["product_id"],)).fetchone()[0])
    stamp = now_iso()
    notes = clean_text(data.get("observations"), "Las observaciones", max_length=1000) or (
        f"Nueva versión creada a partir de la ficha v{ficha['version']}.")
    cur = conn.execute(
        """INSERT INTO fichas (product_id,version,status,valid_from,observations,total_cost,prepared_by,
                               created_at,updated_at)
           VALUES (?,?,'Borrador',?,?,?,?,?,?)""",
        (ficha["product_id"], version, clean_date(data.get("valid_from") or today_iso(), "La fecha de vigencia"),
         notes, ficha["total_cost"], actor, stamp, stamp),
    )
    new_id = int(cur.lastrowid)
    for item in ficha["items"]:
        conn.execute(
            """INSERT INTO ficha_items (ficha_id,material_id,description,unit,quantity,unit_cost,subtotal)
               VALUES (?,?,?,?,?,?,?)""",
            (new_id, item["material_id"], item["description"], item["unit"], item["quantity"],
             item["unit_cost"], item["subtotal"]),
        )
    record_audit(conn, "versionar", "ficha", new_id,
                 f"Ficha v{version} creada como copia de la v{ficha['version']} de {ficha['product_code']}.",
                 {"source_ficha": ficha_id}, actor)
    return ficha_detail(conn, new_id) or {}


def refresh_ficha_prices(conn: sqlite3.Connection, ficha_id: int, actor: str) -> dict[str, Any]:
    """Actualiza un borrador con los precios vigentes del catálogo de valores."""
    ficha = ficha_detail(conn, ficha_id)
    if not ficha:
        raise APIError("Ficha de costo no encontrada.", 404, "no_encontrado")
    if ficha["status"] != "Borrador":
        raise APIError("Solo se actualizan precios en fichas en estado Borrador.", 409, "estado_invalido")
    total = Decimal("0.00")
    updated = 0
    for item in ficha["items"]:
        if item["material_id"] is None:
            continue
        material = get_material(conn, int(item["material_id"]))
        if not material:
            continue
        current = amount(material["unit_price"])
        if current != amount(item["unit_cost"]):
            updated += 1
        quantity = amount(item["quantity"])
        subtotal = (quantity * current).quantize(CENT, rounding=ROUND_HALF_UP)
        conn.execute("UPDATE ficha_items SET description=?,unit=?,unit_cost=?,subtotal=? WHERE id=?",
                     (material["name"], material["unit"], money(current), money(subtotal), item["id"]))
        total += subtotal
    conn.execute("UPDATE fichas SET total_cost=?,updated_at=? WHERE id=?",
                 (money(total.quantize(CENT, rounding=ROUND_HALF_UP)), now_iso(), ficha_id))
    record_audit(conn, "recalcular", "ficha", ficha_id,
                 f"Precios del borrador v{ficha['version']} actualizados desde el catálogo "
                 f"({updated} línea(s) con cambios). Nuevo total {money(total)}.",
                 {"lines_changed": updated}, actor)
    return ficha_detail(conn, ficha_id) or {}


def create_control(conn: sqlite3.Connection, data: dict[str, Any], actor: str) -> dict[str, Any]:
    ficha_id = clean_int(data.get("ficha_id"), "La ficha de costo", minimum=1)
    ficha = ficha_detail(conn, ficha_id)
    if not ficha:
        raise APIError("Ficha de costo no encontrada.", 404, "no_encontrado")
    if ficha["status"] != "Aprobada":
        raise APIError("Solo se generan controles desde fichas aprobadas.")
    if not ficha["items"]:
        raise APIError("No se puede crear un control desde una ficha sin componentes.")
    period = clean_period(data.get("period") or date.today().strftime("%Y-%m"))
    year = period[:4]
    prefix = f"IPV-{year}-"
    last = conn.execute("SELECT code FROM controls WHERE code LIKE ? ORDER BY code DESC LIMIT 1",
                        (prefix + "%",)).fetchone()
    try:
        sequence = int(str(last["code"]).split("-")[-1]) + 1 if last else 1
    except (ValueError, IndexError):
        sequence = int(conn.execute("SELECT COALESCE(MAX(id),0)+1 FROM controls").fetchone()[0])
    code = f"{prefix}{sequence:04d}"
    stamp = now_iso()
    cur = conn.execute(
        """INSERT INTO controls (code,ficha_id,product_id,period,status,snapshot_total,checked_total,notes,
                                 created_by,created_at)
           VALUES (?,?,?,?,'Pendiente',?,'0.00',?,?,?)""",
        (code, ficha_id, ficha["product_id"], period, ficha["total_cost"],
         clean_text(data.get("notes"), "Las observaciones", max_length=1000), actor, stamp),
    )
    control_id = int(cur.lastrowid)
    for item in ficha["items"]:
        conn.execute(
            """INSERT INTO control_items (control_id,material_id,description,unit,quantity,unit_cost,subtotal)
               VALUES (?,?,?,?,?,?,?)""",
            (control_id, item["material_id"], item["description"], item["unit"], item["quantity"],
             item["unit_cost"], item["subtotal"]),
        )
    record_audit(conn, "crear", "control", control_id,
                 f"Control {code} generado desde la ficha {ficha['document_code']} para el período {period}.",
                 {"period": period, "snapshot_total": ficha["total_cost"]}, actor)
    return control_detail(conn, control_id) or {}


def update_control(conn: sqlite3.Connection, control_id: int, data: dict[str, Any], actor: str) -> dict[str, Any]:
    control = conn.execute("SELECT * FROM controls WHERE id=?", (control_id,)).fetchone()
    if not control:
        raise APIError("Control de IPV no encontrado.", 404, "no_encontrado")
    notes = clean_text(data.get("notes", control["notes"]), "Las observaciones", max_length=1000)
    conn.execute("UPDATE controls SET notes=? WHERE id=?", (notes, control_id))
    record_audit(conn, "actualizar", "control", control_id, f"Observaciones del control {control['code']} "
                 "actualizadas.", None, actor)
    return control_detail(conn, control_id) or {}


def validate_control(conn: sqlite3.Connection, control_id: int, data: dict[str, Any], actor: str) -> dict[str, Any]:
    control = conn.execute("SELECT * FROM controls WHERE id=?", (control_id,)).fetchone()
    if not control:
        raise APIError("Control de IPV no encontrado.", 404, "no_encontrado")
    ficha = ficha_detail(conn, int(control["ficha_id"]))
    if not ficha:
        raise APIError("La ficha vinculada al control no existe.", 409, "estado_invalido")
    items = [dict(row) for row in conn.execute(
        "SELECT * FROM control_items WHERE control_id=? ORDER BY id", (control_id,)).fetchall()]

    report: list[dict[str, Any]] = []

    def add(level: str, text: str, check: str, expected: Any = None, actual: Any = None) -> None:
        entry: dict[str, Any] = {
            "type": {"ok": "success", "warning": "warning", "error": "error"}[level],
            "level": level,
            "text": text,
            "check": check,
        }
        if expected is not None:
            entry["expected"] = str(expected)
        if actual is not None:
            entry["actual"] = str(actual)
        report.append(entry)

    if ficha["status"] != "Aprobada":
        add("error", "La Ficha de Costo vinculada no está en estado Aprobada.", "Estado de la ficha",
            "Aprobada", ficha["status"])
    else:
        add("ok", f"Ficha vinculada {ficha['document_code']} aprobada por "
                  f"{ficha['approved_by'] or 'responsable no registrado'}.", "Estado de la ficha")

    if not items:
        add("error", "El control no contiene líneas de detalle.", "Detalle del control", "Con líneas", "Vacío")

    computed = Decimal("0.00")
    for item in items:
        description = str(item["description"]).strip()
        if not description:
            add("error", "Existe una línea sin descripción.", "Integridad del detalle")
            continue
        quantity = amount(item["quantity"])
        unit_cost = amount(item["unit_cost"])
        subtotal = amount(item["subtotal"])
        if quantity <= 0:
            add("error", f"Cantidad no válida en «{description}».", "Cantidad mayor que cero", "> 0", quantity)
        if unit_cost < 0:
            add("error", f"Costo unitario negativo en «{description}».", "Costo unitario no negativo")
        expected_subtotal = (quantity * unit_cost).quantize(CENT, rounding=ROUND_HALF_UP)
        if expected_subtotal != subtotal.quantize(CENT, rounding=ROUND_HALF_UP):
            add("error", f"El subtotal de «{description}» no coincide con cantidad × costo unitario.",
                "Subtotal de la línea", money(expected_subtotal), money(subtotal))
        computed += subtotal

    computed = computed.quantize(CENT, rounding=ROUND_HALF_UP)
    snapshot = amount(control["snapshot_total"]).quantize(CENT, rounding=ROUND_HALF_UP)
    if computed != snapshot:
        add("error", "La suma de las líneas no coincide con el total registrado en el control.",
            "Cuadre del control", money(snapshot), money(computed))
    else:
        add("ok", f"La suma de las líneas coincide con el total del control ({money(snapshot)}).", "Cuadre del control")

    ficha_total = amount(ficha["total_cost"]).quantize(CENT, rounding=ROUND_HALF_UP)
    if snapshot != ficha_total:
        add("error", "El total del control no coincide con el total de la ficha vinculada.",
            "Conciliación con la ficha", money(ficha_total), money(snapshot))
    else:
        add("ok", "El total del control coincide con la Ficha de Costo vinculada.", "Conciliación con la ficha")

    # Observaciones informativas: vigencia de los valores y variaciones de precios.
    for item in items:
        if item["material_id"] is None:
            continue
        material = get_material(conn, int(item["material_id"]))
        if not material:
            continue
        state = effective_material(material)
        if state in ("Vencido", "Suspendido", "Descontinuado"):
            add("warning", f"El valor «{material['name']}» está en estado {state}.",
                "Vigencia de los valores", "Vigente", state)
        current = amount(material["unit_price"])
        if current != amount(item["unit_cost"]):
            add("warning", f"El valor «{material['name']}» cambió desde la instantánea: "
                           f"{money(item['unit_cost'])} → {money(current)}.",
                "Variación de precios", money(current), money(item["unit_cost"]))

    errors = [entry for entry in report if entry["level"] == "error"]
    warnings = [entry for entry in report if entry["level"] == "warning"]
    if not errors:
        summary = "El control cuadra con la Ficha de Costo vinculada."
        if warnings:
            summary += f" Se registraron {len(warnings)} observación(es) informativa(s)."
        add("ok", summary, "Resultado de la validación")

    status = "Validado" if not errors else "Con diferencias"
    checked_by = clean_text(data.get("checked_by") or actor, "El responsable de la validación", max_length=120)
    checked_at = now_iso()
    conn.execute(
        """UPDATE controls SET status=?,checked_total=?,validation_report=?,checked_by=?,checked_at=?,
                  notes=? WHERE id=?""",
        (status, money(computed), json.dumps(report, ensure_ascii=False), checked_by, checked_at,
         clean_text(data.get("notes", control["notes"]), "Las observaciones", max_length=1000), control_id),
    )
    record_audit(conn, "validar", "control", control_id,
                 f"Control {control['code']} validado por {checked_by}: {status} "
                 f"({len(errors)} error(es), {len(warnings)} observación(es)).",
                 {"status": status, "errors": len(errors), "warnings": len(warnings)}, actor)
    return control_detail(conn, control_id) or {}


def build_backup(conn: sqlite3.Connection) -> dict[str, Any]:
    tables = ("products", "materials", "fichas", "ficha_items", "controls", "control_items", "audit_log")
    payload = {
        "application": APP_NAME,
        "version": APP_VERSION,
        "generated_at": now_iso(),
        "author": APP_AUTHOR,
        "database": DB_PATH.name,
        "tables": {table: [dict(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY id")] for table in tables},
        "counts": catalogue_totals(conn),
    }
    return payload


def write_backup_file(payload: dict[str, Any]) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = BACKUP_DIR / f"ipv-respaldo-{stamp}.json"
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return target


RESTORE_COLUMNS: dict[str, tuple[str, ...]] = {
    "products": ("id", "code", "name", "category", "unit", "description", "active", "created_at", "updated_at"),
    "materials": ("id", "code", "name", "kind", "unit", "currency", "unit_price", "supplier", "source",
                  "effective_from", "effective_to", "status", "notes", "created_at", "updated_at"),
    "fichas": ("id", "product_id", "version", "status", "valid_from", "observations", "total_cost", "prepared_by",
               "approved_by", "approved_at", "created_at", "updated_at"),
    "ficha_items": ("id", "ficha_id", "material_id", "description", "unit", "quantity", "unit_cost", "subtotal"),
    "controls": ("id", "code", "ficha_id", "product_id", "period", "status", "snapshot_total", "checked_total",
                 "notes", "validation_report", "created_by", "checked_by", "created_at", "checked_at"),
    "control_items": ("id", "control_id", "material_id", "description", "unit", "quantity", "unit_cost", "subtotal"),
    "audit_log": ("id", "at", "actor", "action", "entity", "entity_id", "summary", "details"),
}
RESTORE_ORDER = ("products", "materials", "fichas", "ficha_items", "controls", "control_items", "audit_log")


def restore_backup(conn: sqlite3.Connection, payload: dict[str, Any], actor: str) -> dict[str, Any]:
    tables = payload.get("tables")
    if not isinstance(tables, dict):
        raise APIError("El respaldo no tiene el formato esperado (falta la clave «tables»).")
    missing = [name for name in RESTORE_ORDER if not isinstance(tables.get(name), list) and name != "audit_log"]
    if missing:
        raise APIError("El respaldo está incompleto: faltan " + ", ".join(missing) + ".")
    for name in RESTORE_ORDER:
        rows = tables.get(name, [])
        if not isinstance(rows, list) or len(rows) > 100000:
            raise APIError(f"El respaldo contiene un número no válido de registros en «{name}».")
    safety = write_backup_file(build_backup(conn))
    try:
        conn.execute("DELETE FROM control_items")
        conn.execute("DELETE FROM controls")
        conn.execute("DELETE FROM ficha_items")
        conn.execute("DELETE FROM fichas")
        conn.execute("DELETE FROM materials")
        conn.execute("DELETE FROM products")
        conn.execute("DELETE FROM audit_log")
        restored: dict[str, int] = {}
        for name in RESTORE_ORDER:
            columns = RESTORE_COLUMNS[name]
            inserted = 0
            for row in tables.get(name, []):
                if not isinstance(row, dict):
                    continue
                values = [row.get(column) if column != "details" else json.dumps(row.get(column) or {},
                                                                               ensure_ascii=False)
                          for column in columns]
                if name == "materials" and not values[columns.index("kind")]:
                    values[columns.index("kind")] = "Insumo"
                placeholders = ",".join("?" for _ in columns)
                conn.execute(f"INSERT INTO {name} ({','.join(columns)}) VALUES ({placeholders})", values)
                inserted += 1
            restored[name] = inserted
        for name in RESTORE_ORDER:
            maximum = conn.execute(f"SELECT COALESCE(MAX(id),0) FROM {name}").fetchone()[0]
            conn.execute("DELETE FROM sqlite_sequence WHERE name=?", (name,))
            if maximum:
                conn.execute("INSERT INTO sqlite_sequence(name,seq) VALUES (?,?)", (name, maximum))
    except sqlite3.Error as exc:
        raise APIError(f"No se pudo restaurar el respaldo: {exc}", 400, "respaldo_invalido")
    record_audit(conn, "restaurar", "sistema", None,
                 f"Respaldo restaurado desde {safety.name}. Registros: "
                 + ", ".join(f"{name}={total}" for name, total in restored.items()),
                 {"safety_backup": safety.name, "restored": restored}, actor)
    return {"ok": True, "restored": restored, "safety_backup": safety.name}


# --------------------------------------------------------------------------- #
# Información del sistema
# --------------------------------------------------------------------------- #
def certificate_info() -> dict[str, Any]:
    info: dict[str, Any] = {"enabled": bool(TLS_CERT and TLS_KEY), "file": Path(TLS_CERT).name if TLS_CERT else ""}
    if not info["enabled"]:
        return info
    try:  # metadatos opcionales del certificado (API privada estable en CPython)
        decoded = ssl._ssl._test_decode_cert(TLS_CERT)  # type: ignore[attr-defined]
        subject = decoded.get("subject", ())
        common_name = next((value for group in subject for key, value in group if key == "commonName"), "")
        info["subject"] = common_name
        info["not_after"] = decoded.get("notAfter", "")
    except Exception:  # pragma: no cover - depende de la plataforma
        pass
    return info


def database_info(conn: sqlite3.Connection, *, deep: bool = False) -> dict[str, Any]:
    info: dict[str, Any] = {
        "engine": "SQLite",
        "version": sqlite3.sqlite_version,
        "file": DB_PATH.name,
        "path": str(DB_PATH),
        "journal_mode": str(conn.execute("PRAGMA journal_mode").fetchone()[0]).upper(),
        "size_bytes": DB_PATH.stat().st_size if DB_PATH.exists() else 0,
        "counts": catalogue_totals(conn),
    }
    if deep:
        info["integrity"] = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        info["foreign_keys"] = len(conn.execute("PRAGMA foreign_key_check").fetchall())
    return info


def server_info() -> dict[str, Any]:
    return {
        "host": HOST,
        "port": PORT,
        "python": platform.python_version(),
        "platform": f"{platform.system()} {platform.release()}",
        "started_at": datetime.fromtimestamp(STARTED_AT, tz=timezone.utc).isoformat(timespec="seconds"),
        "uptime_seconds": int(time.time() - STARTED_AT),
        "operator_default": DEFAULT_OPERATOR,
        "backup_dir": str(BACKUP_DIR),
    }


def local_ipv4_addresses() -> list[str]:
    addresses: set[str] = set()
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("10.255.255.255", 1))
            addresses.add(probe.getsockname()[0])
        finally:
            probe.close()
    except OSError:
        pass
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            addresses.add(item[4][0])
    except OSError:
        pass
    return sorted(address for address in addresses if not address.startswith(("127.", "169.254.")))


# --------------------------------------------------------------------------- #
# Enrutado de la API
# --------------------------------------------------------------------------- #
@dataclass
class RequestContext:
    request_id: str
    method: str
    path: str
    query: dict[str, str]
    params: dict[str, str] = field(default_factory=dict)
    body: dict[str, Any] = field(default_factory=dict)
    actor: str = DEFAULT_OPERATOR
    conn: sqlite3.Connection | None = None
    client_ip: str = ""
    handler: Any = None

    def q(self, name: str, default: str = "") -> str:
        return str(self.query.get(name, default) or default).strip()

    def q_int(self, name: str) -> int | None:
        raw = self.q(name)
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError:
            raise APIError(f"El parámetro «{name}» debe ser numérico.")


@dataclass(frozen=True)
class Route:
    method: str
    pattern: re.Pattern[str]
    handler: Callable[[RequestContext], Any]
    write: bool = False
    description: str = ""


def route(method: str, path: str, *, write: bool = False, description: str = "") -> Callable:
    def decorator(func: Callable[[RequestContext], Any]) -> Callable[[RequestContext], Any]:
        ROUTES.append(Route(method.upper(), re.compile(f"^{path}$"), func, write, description))
        return func
    return decorator


ROUTES: list[Route] = []


@route("GET", "/api/health", description="Estado del servicio y de la base de datos")
def api_health(ctx: RequestContext) -> dict[str, Any]:
    deep = ctx.q("deep") in ("1", "true", "yes")
    payload = {
        "ok": True,
        "status": "operativo",
        "database": "SQLite",
        "file": DB_PATH.name,
        "time": now_iso(),
        "version": APP_VERSION,
        "uptime_seconds": int(time.time() - STARTED_AT),
        "scheme": ctx.handler.current_scheme(),
        "tls": certificate_info()["enabled"],
    }
    if deep:
        payload["integrity"] = str(ctx.conn.execute("PRAGMA integrity_check").fetchone()[0])  # type: ignore[union-attr]
        payload["orphans"] = len(ctx.conn.execute("PRAGMA foreign_key_check").fetchall())  # type: ignore[union-attr]
        payload["journal_mode"] = str(ctx.conn.execute("PRAGMA journal_mode").fetchone()[0]).upper()  # type: ignore
    return payload


@route("GET", "/api/meta", description="Identidad de la aplicación, servidor y base de datos")
def api_meta(ctx: RequestContext) -> dict[str, Any]:
    deep = ctx.q("deep") in ("1", "true", "yes")
    handler = ctx.handler
    return {
        "application": {
            "name": APP_NAME,
            "version": APP_VERSION,
            "release": APP_RELEASE,
            "description": APP_DESCRIPTION,
            "author": APP_AUTHOR,
            "author_role": APP_ROLE,
            "notice": DATA_NOTICE,
            "url": f"{handler.current_scheme()}://{handler.host_header()}:{handler.server_port}",
        },
        "server": {**server_info(), "scheme": handler.current_scheme(), "port": handler.server_port},
        "database": database_info(ctx.conn, deep=deep),  # type: ignore[arg-type]
        "tls": certificate_info(),
        "capabilities": [
            "Catálogo de productos y servicios con versionado de fichas",
            "Registro de valores del IPV con vigencia y procedencia",
            "Control de precios: variaciones detectadas en la validación",
            "Bitácora de auditoría de todas las operaciones",
            "Exportación a CSV y respaldo/restauración en JSON",
            "API JSON compartida con el cliente Android",
        ],
    }


@route("GET", "/api/dashboard", description="Indicadores, alertas y actividad reciente")
def api_dashboard(ctx: RequestContext) -> dict[str, Any]:
    return dashboard(ctx.conn)  # type: ignore[arg-type]


@route("GET", "/api/products", description="Catálogo de productos y servicios")
def api_products(ctx: RequestContext) -> list[dict]:
    return list_products(ctx.conn, query=ctx.q("search"), category=ctx.q("category"), status=ctx.q("status"))  # type: ignore


@route("POST", "/api/products", write=True, description="Registrar un producto o servicio")
def api_create_product(ctx: RequestContext) -> tuple[dict, int]:
    return create_product(ctx.conn, ctx.body, ctx.actor), 201  # type: ignore[arg-type]


@route("GET", r"/api/products/(?P<product_id>\d+)", description="Detalle de un producto")
def api_product(ctx: RequestContext) -> dict[str, Any]:
    product_id = int(ctx.params["product_id"])
    product = get_product(ctx.conn, product_id)  # type: ignore[arg-type]
    if not product:
        raise APIError("Producto no encontrado.", 404, "no_encontrado")
    product["fichas"] = list_fichas(ctx.conn, product_id=product_id)  # type: ignore[arg-type]
    product["audit"] = list_audit(ctx.conn, limit=20, entity="producto", entity_id=product_id)  # type: ignore
    return product


@route("PUT", r"/api/products/(?P<product_id>\d+)", write=True, description="Actualizar un producto")
def api_update_product(ctx: RequestContext) -> dict[str, Any]:
    return update_product(ctx.conn, int(ctx.params["product_id"]), ctx.body, ctx.actor)  # type: ignore[arg-type]


@route("PATCH", r"/api/products/(?P<product_id>\d+)", write=True, description="Activar o desactivar un producto")
def api_patch_product(ctx: RequestContext) -> dict[str, Any]:
    if "active" not in ctx.body:
        return update_product(ctx.conn, int(ctx.params["product_id"]), ctx.body, ctx.actor)  # type: ignore[arg-type]
    return set_product_active(ctx.conn, int(ctx.params["product_id"]), bool(ctx.body.get("active")), ctx.actor)  # type: ignore


@route("DELETE", r"/api/products/(?P<product_id>\d+)", write=True, description="Desactivar un producto")
def api_delete_product(ctx: RequestContext) -> dict[str, Any]:
    set_product_active(ctx.conn, int(ctx.params["product_id"]), False, ctx.actor)  # type: ignore[arg-type]
    return {"ok": True}


@route("GET", "/api/materials", description="Valores de referencia del IPV")
def api_materials(ctx: RequestContext) -> list[dict]:
    return list_materials(ctx.conn, query=ctx.q("search"), kind=ctx.q("kind"), state=ctx.q("state"))  # type: ignore


@route("POST", "/api/materials", write=True, description="Registrar un valor del IPV")
def api_create_material(ctx: RequestContext) -> tuple[dict, int]:
    return create_material(ctx.conn, ctx.body, ctx.actor), 201  # type: ignore[arg-type]


@route("PUT", r"/api/materials/(?P<material_id>\d+)", write=True, description="Actualizar un valor del IPV")
def api_update_material(ctx: RequestContext) -> dict[str, Any]:
    return update_material(ctx.conn, int(ctx.params["material_id"]), ctx.body, ctx.actor)  # type: ignore[arg-type]


@route("GET", "/api/fichas", description="Fichas de costo")
def api_fichas(ctx: RequestContext) -> list[dict]:
    return list_fichas(ctx.conn, query=ctx.q("search"), status=ctx.q("status"),  # type: ignore[arg-type]
                       product_id=ctx.q_int("product_id"), category=ctx.q("category"))


@route("POST", "/api/fichas", write=True, description="Crear una ficha de costo")
def api_create_ficha(ctx: RequestContext) -> tuple[dict, int]:
    return create_ficha(ctx.conn, ctx.body, ctx.actor), 201  # type: ignore[arg-type]


@route("GET", r"/api/fichas/(?P<ficha_id>\d+)", description="Detalle de una ficha de costo")
def api_ficha(ctx: RequestContext) -> dict[str, Any]:
    detail = ficha_detail(ctx.conn, int(ctx.params["ficha_id"]))  # type: ignore[arg-type]
    if not detail:
        raise APIError("Ficha de costo no encontrada.", 404, "no_encontrado")
    return detail


@route("PUT", r"/api/fichas/(?P<ficha_id>\d+)", write=True, description="Actualizar un borrador de ficha")
def api_update_ficha(ctx: RequestContext) -> dict[str, Any]:
    return update_ficha(ctx.conn, int(ctx.params["ficha_id"]), ctx.body, ctx.actor)  # type: ignore[arg-type]


@route("POST", r"/api/fichas/(?P<ficha_id>\d+)/approve", write=True, description="Aprobar una ficha de costo")
def api_approve_ficha(ctx: RequestContext) -> dict[str, Any]:
    return approve_ficha(ctx.conn, int(ctx.params["ficha_id"]), ctx.body, ctx.actor)  # type: ignore[arg-type]


@route("POST", r"/api/fichas/(?P<ficha_id>\d+)/reopen", write=True, description="Reabrir una ficha aprobada")
def api_reopen_ficha(ctx: RequestContext) -> dict[str, Any]:
    return reopen_ficha(ctx.conn, int(ctx.params["ficha_id"]), ctx.body, ctx.actor)  # type: ignore[arg-type]


@route("POST", r"/api/fichas/(?P<ficha_id>\d+)/duplicate", write=True, description="Crear una nueva versión")
def api_duplicate_ficha(ctx: RequestContext) -> tuple[dict, int]:
    return duplicate_ficha(ctx.conn, int(ctx.params["ficha_id"]), ctx.body, ctx.actor), 201  # type: ignore


@route("POST", r"/api/fichas/(?P<ficha_id>\d+)/refresh-prices", write=True,
       description="Actualizar precios del borrador desde el catálogo")
def api_refresh_ficha(ctx: RequestContext) -> dict[str, Any]:
    return refresh_ficha_prices(ctx.conn, int(ctx.params["ficha_id"]), ctx.actor)  # type: ignore[arg-type]


@route("GET", "/api/controls", description="Controles de IPV")
def api_controls(ctx: RequestContext) -> list[dict]:
    return list_controls(ctx.conn, query=ctx.q("search"), status=ctx.q("status"), period=ctx.q("period"))  # type: ignore


@route("POST", "/api/controls", write=True, description="Generar un control de IPV")
def api_create_control(ctx: RequestContext) -> tuple[dict, int]:
    return create_control(ctx.conn, ctx.body, ctx.actor), 201  # type: ignore[arg-type]


@route("GET", r"/api/controls/(?P<control_id>\d+)", description="Detalle de un control de IPV")
def api_control(ctx: RequestContext) -> dict[str, Any]:
    detail = control_detail(ctx.conn, int(ctx.params["control_id"]))  # type: ignore[arg-type]
    if not detail:
        raise APIError("Control de IPV no encontrado.", 404, "no_encontrado")
    return detail


@route("PATCH", r"/api/controls/(?P<control_id>\d+)", write=True, description="Actualizar un control")
def api_update_control(ctx: RequestContext) -> dict[str, Any]:
    return update_control(ctx.conn, int(ctx.params["control_id"]), ctx.body, ctx.actor)  # type: ignore[arg-type]


@route("POST", r"/api/controls/(?P<control_id>\d+)/validate", write=True, description="Validar un control de IPV")
def api_validate_control(ctx: RequestContext) -> dict[str, Any]:
    return validate_control(ctx.conn, int(ctx.params["control_id"]), ctx.body, ctx.actor)  # type: ignore[arg-type]


@route("GET", "/api/audit", description="Bitácora de auditoría")
def api_audit(ctx: RequestContext) -> list[dict]:
    return list_audit(ctx.conn, limit=ctx.q_int("limit") or 120, entity=ctx.q("entity"),  # type: ignore[arg-type]
                      entity_id=ctx.q_int("entity_id"), query=ctx.q("search"))


@route("GET", "/api/search", description="Búsqueda global")
def api_search(ctx: RequestContext) -> dict[str, Any]:
    return global_search(ctx.conn, ctx.q("q"))  # type: ignore[arg-type]


@route("GET", "/api/backup", description="Respaldo completo en JSON")
def api_backup(ctx: RequestContext) -> dict[str, Any]:
    return build_backup(ctx.conn)  # type: ignore[arg-type]


@route("POST", "/api/restore", write=True, description="Restaurar un respaldo JSON")
def api_restore(ctx: RequestContext) -> dict[str, Any]:
    if str(ctx.body.get("confirm", "")).strip().upper() != "REEMPLAZAR":
        raise APIError("Confirme la restauración enviando «confirm» con el valor REEMPLAZAR.")
    return restore_backup(ctx.conn, ctx.body, ctx.actor)  # type: ignore[arg-type]


@route("GET", "/api/routes", description="Catálogo de rutas disponibles")
def api_routes(ctx: RequestContext) -> list[dict[str, str]]:
    return [{"method": item.method, "path": item.pattern.pattern.replace("^", "").replace("$", ""),
             "description": item.description} for item in ROUTES]


# --------------------------------------------------------------------------- #
# Servidor HTTP
# --------------------------------------------------------------------------- #
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".mjs": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".webmanifest": "application/manifest+json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".txt": "text/plain; charset=utf-8",
    ".map": "application/json; charset=utf-8",
}
COMPRESSIBLE = {".html", ".css", ".js", ".mjs", ".json", ".svg", ".webmanifest", ".txt", ".map"}
SECURITY_HEADERS = (
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "no-referrer"),
    ("Permissions-Policy", "geolocation=(), camera=(), microphone=(), payment=()"),
    ("Cross-Origin-Opener-Policy", "same-origin"),
)
CSP = ("default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
       "script-src 'self'; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; "
       "form-action 'self'")


class Handler(BaseHTTPRequestHandler):
    server_version = f"IPV/{APP_VERSION}"
    sys_version = ""
    protocol_version = "HTTP/1.1"
    timeout = 60

    # -- utilidades -------------------------------------------------------- #
    @property
    def server_port(self) -> int:
        try:
            return int(self.server.server_address[1])
        except (AttributeError, IndexError, TypeError):  # pragma: no cover
            return PORT

    def host_header(self) -> str:
        header = self.headers.get("Host", "") or ""
        return header.split(":")[0] if header else (local_ipv4_addresses() or ["localhost"])[0]

    def current_scheme(self) -> str:
        override = os.environ.get("IPV_SCHEME", "").strip()
        if override:
            return override
        return "https" if isinstance(getattr(self, "connection", None), ssl.SSLSocket) else "http"

    def log_message(self, fmt: str, *args: Any) -> None:  # pragma: no cover - ruido de red
        LOG.debug("%s - %s", self.address_string(), fmt % args)

    def log_error(self, fmt: str, *args: Any) -> None:  # pragma: no cover
        LOG.warning("%s - %s", self.address_string(), fmt % args)

    # -- respuestas -------------------------------------------------------- #
    def _head(self, status: int, content_type: str, length: int, extra: list[tuple[str, str]] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("X-Request-Id", getattr(self, "request_id", "-"))
        for key, value in SECURITY_HEADERS:
            self.send_header(key, value)
        for key, value in (extra or []):
            self.send_header(key, value)
        self.end_headers()

    def send_payload(self, content_type: str, raw: bytes, status: int = 200, *,
                     extra: list[tuple[str, str]] | None = None, compressible: bool = False) -> None:
        body = raw
        headers = list(extra or [])
        if compressible and len(raw) > 700 and "gzip" in self.headers.get("Accept-Encoding", "").lower():
            body = gzip.compress(raw, compresslevel=6)
            headers.append(("Content-Encoding", "gzip"))
        headers.append(("Vary", "Accept-Encoding"))
        self._head(status, content_type, len(body), headers)
        if self.command != "HEAD":
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):  # pragma: no cover
                LOG.debug("Cliente desconectado durante la respuesta %s", self.path)

    def send_json(self, payload: Any, status: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
        self.send_payload("application/json; charset=utf-8", raw, status,
                          extra=[("Cache-Control", "no-store"),
                                 ("Access-Control-Allow-Origin", "*"),
                                 ("Access-Control-Allow-Headers", "Content-Type, Authorization, X-IPV-Operator"),
                                 ("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")],
                          compressible=True)

    def send_error_json(self, message: str, status: int = 400, code: str = "error") -> None:
        self.send_json({"error": message, "code": code, "request_id": getattr(self, "request_id", "-")}, status)

    # -- lectura del cuerpo ----------------------------------------------- #
    def read_body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
        except ValueError:
            raise APIError("La longitud de la solicitud no es válida.")
        if length > MAX_BODY_BYTES:
            raise APIError("La solicitud supera el tamaño máximo permitido.", 413, "solicitud_muy_grande")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise APIError("El cuerpo de la solicitud no es JSON válido.")
        if not isinstance(data, dict):
            raise APIError("Se esperaba un objeto JSON en el cuerpo de la solicitud.")
        return data

    # -- verbos HTTP ------------------------------------------------------ #
    def do_OPTIONS(self) -> None:  # noqa: N802
        self._head(204, "text/plain; charset=utf-8", 0,
                   [("Access-Control-Allow-Origin", "*"),
                    ("Access-Control-Allow-Headers", "Content-Type, Authorization, X-IPV-Operator"),
                    ("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS"),
                    ("Access-Control-Max-Age", "600")])

    def do_GET(self) -> None:  # noqa: N802
        self.dispatch("GET")

    def do_HEAD(self) -> None:  # noqa: N802
        self.dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self.dispatch("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self.dispatch("PUT")

    def do_PATCH(self) -> None:  # noqa: N802
        self.dispatch("PATCH")

    def do_DELETE(self) -> None:  # noqa: N802
        self.dispatch("DELETE")

    # -- despacho --------------------------------------------------------- #
    def dispatch(self, method: str) -> None:
        started = time.perf_counter()
        self.request_id = uuid.uuid4().hex[:12]
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if len(path) > 1:
            path = path.rstrip("/") or "/"
        query = {key: values[0] for key, values in parse_qs(parsed.query, keep_blank_values=True).items()}
        status = 500
        try:
            if not path.startswith("/api"):
                if method != "GET":
                    self.send_error_json("Método no permitido para este recurso.", 405, "metodo_no_permitido")
                    status = 405
                else:
                    status = self.serve_static(path)
                return
            method_mismatch = False
            for item in ROUTES:
                match = item.pattern.match(path)
                if not match:
                    continue
                if item.method != method:
                    method_mismatch = True
                    continue
                context = RequestContext(
                    request_id=self.request_id,
                    method=method,
                    path=path,
                    query=query,
                    params=match.groupdict(),
                    actor=(self.headers.get("X-IPV-Operator") or DEFAULT_OPERATOR).strip()[:120] or DEFAULT_OPERATOR,
                    client_ip=self.client_address[0] if self.client_address else "",
                    handler=self,
                )
                if item.write:
                    context.body = self.read_body()
                    with WRITE_LOCK:
                        conn = connect()
                        try:
                            conn.execute("BEGIN IMMEDIATE")
                            context.conn = conn
                            result = item.handler(context)
                            conn.commit()
                        except Exception:
                            conn.rollback()
                            raise
                        finally:
                            conn.close()
                else:
                    context.body = self.read_body() if method in ("POST", "PUT", "PATCH") else {}
                    conn = connect()
                    try:
                        context.conn = conn
                        result = item.handler(context)
                    finally:
                        conn.close()
                payload, code = result if isinstance(result, tuple) else (result, 200)
                self.send_json(payload, code)
                status = code
                LOG.info("%s %s → %s en %.0f ms · %s", method, path, code,
                         (time.perf_counter() - started) * 1000, item.description)
                return
            if method_mismatch:
                self.send_error_json(f"El método {method} no está permitido para este recurso.", 405,
                                     "metodo_no_permitido")
                status = 405
                return
            # Ruta de API no registrada: 404 consistente.
            self.send_error_json("Recurso no encontrado.", 404, "no_encontrado")
            status = 404
        except APIError as exc:
            status = exc.status
            self.send_error_json(exc.message, exc.status, exc.code)
        except sqlite3.IntegrityError as exc:
            status = 409
            message = "El registro duplica un código existente o infringe una restricción de integridad."
            if "controls.ficha_id, controls.period" in str(exc):
                message = "Ya existe un Control de IPV para esa ficha y período."
            elif "products.code" in str(exc):
                message = "Ya existe un producto con ese código."
            elif "materials.code" in str(exc):
                message = "Ya existe un valor del IPV con ese código."
            self.send_error_json(message, status, "conflicto")
        except (ValueError, TypeError, KeyError) as exc:
            status = 400
            self.send_error_json(str(exc) or "Datos no válidos.", status, "datos_invalidos")
        except (BrokenPipeError, ConnectionResetError):  # pragma: no cover
            LOG.debug("Conexión interrumpida en %s %s", method, path)
        except Exception as exc:  # pragma: no cover - salvaguarda
            status = 500
            LOG.exception("Error no controlado en %s %s: %r", method, path, exc)
            self.send_error_json("Error interno del servidor. Consulte el registro del servicio.", status, "error_interno")
        finally:
            if status >= 400 and path.startswith("/api"):
                LOG.warning("%s %s → %s", method, path, status)

    # -- archivos estáticos ----------------------------------------------- #
    def resolve_static(self, path: str) -> Path | None:
        if path in ("/", "/index.html"):
            return WEB_ROOT / "index.html"
        relative = path.lstrip("/")
        candidate = (WEB_ROOT / relative).resolve()
        if WEB_ROOT not in candidate.parents and candidate != WEB_ROOT:
            return None
        if candidate.is_file():
            return candidate
        # Navegación de la aplicación (rutas limpias): devuelve la interfaz.
        if "." not in Path(relative).name and (WEB_ROOT / "index.html").is_file():
            return WEB_ROOT / "index.html"
        return None

    def serve_static(self, path: str) -> int:
        file_path = self.resolve_static(path)
        if file_path is None:
            self.send_error_json(
                "El recurso solicitado no existe. La interfaz web se sirve en «/» y la API en «/api».", 404,
                "no_encontrado")
            return 404
        try:
            stat = file_path.stat()
            raw = file_path.read_bytes()
        except OSError:
            self.send_error_json("No se pudo leer el recurso solicitado.", 500, "error_lectura")
            return 500
        etag = f'W/"{stat.st_mtime_ns:x}-{stat.st_size:x}"'
        if self.headers.get("If-None-Match") == etag:
            self._head(304, "text/plain; charset=utf-8", 0, [("ETag", etag), ("Cache-Control", "no-cache")])
            return 304
        content_type = CONTENT_TYPES.get(file_path.suffix.lower(), "application/octet-stream")
        extra = [("ETag", etag), ("Cache-Control", "no-cache, must-revalidate")]
        if file_path.suffix.lower() == ".html":
            extra.append(("Content-Security-Policy", CSP))
        if self.current_scheme() == "https":
            extra.append(("Strict-Transport-Security", "max-age=86400"))
        self.send_payload(content_type, raw, 200, extra=extra,
                          compressible=file_path.suffix.lower() in COMPRESSIBLE)
        return 200


class ApplicationServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


# --------------------------------------------------------------------------- #
# Arranque
# --------------------------------------------------------------------------- #
def print_banner(scheme: str) -> None:
    addresses = local_ipv4_addresses()
    hostname = socket.gethostname()
    line = "─" * 66
    print(line)
    print(f"  {APP_NAME}  ·  versión {APP_VERSION}")
    print(f"  {APP_AUTHOR}")
    print(line)
    print(f"  Interfaz web:        {scheme}://{hostname}:{PORT}/")
    print(f"  En esta PC:          {scheme}://localhost:{PORT}/")
    for address in addresses:
        print(f"  Desde la red:        {scheme}://{address}:{PORT}/")
    print(f"  Base de datos:       {DB_PATH}")
    print(f"  Respaldos:           {BACKUP_DIR}")
    print(f"  Bitácora:            {LOG.level and logging.getLevelName(LOG.level)}")
    print(line)
    print("  Detenga el servicio con Ctrl+C.")
    print(line)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="server.py",
        description=f"{APP_NAME} · servidor de aplicación para red local ({APP_AUTHOR}).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--host", default=HOST, help="Dirección de escucha.")
    parser.add_argument("--port", type=int, default=PORT, help="Puerto TCP.")
    parser.add_argument("--db", default=str(DB_PATH), help="Ruta del archivo SQLite.")
    parser.add_argument("--cert", default=TLS_CERT, help="Certificado PEM para habilitar HTTPS.")
    parser.add_argument("--key", default=TLS_KEY, help="Clave privada PEM del certificado.")
    parser.add_argument("--operator", default=DEFAULT_OPERATOR, help="Operador registrado en la bitácora.")
    parser.add_argument("--log-level", default=os.environ.get("IPV_LOG_LEVEL", "INFO"),
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Nivel de detalle del registro.")
    parser.add_argument("--check", action="store_true",
                        help="Verifica la configuración, la base de datos y el certificado sin iniciar el servicio.")
    return parser.parse_args(argv)


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s · %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main(argv: list[str] | None = None) -> int:
    global DB_PATH, BACKUP_DIR, HOST, PORT, TLS_CERT, TLS_KEY, DEFAULT_OPERATOR
    args = parse_args(argv)
    configure_logging(args.log_level)
    DB_PATH = Path(args.db).expanduser().resolve()
    BACKUP_DIR = Path(os.environ.get("IPV_BACKUP_DIR", DB_PATH.parent / "backups")).resolve()
    HOST, PORT = args.host, args.port
    TLS_CERT, TLS_KEY = (args.cert or "").strip(), (args.key or "").strip()
    DEFAULT_OPERATOR = (args.operator or "Operador local").strip() or "Operador local"

    if bool(TLS_CERT) != bool(TLS_KEY):
        LOG.error("Debe indicar el certificado y la clave privada juntos para habilitar HTTPS.")
        return 2
    for candidate in (TLS_CERT, TLS_KEY):
        if candidate and not Path(candidate).is_file():
            LOG.error("No se encontró el archivo %s", candidate)
            return 2

    init_db()
    if args.check:
        with db_session() as conn:
            info = database_info(conn, deep=True)
        print(f"{APP_NAME} {APP_VERSION} · {APP_AUTHOR}")
        print(f"Base de datos: {info['path']} ({info['size_bytes']} bytes, integridad: {info['integrity']})")
        print(f"Registros: {info['counts']}")
        print(f"HTTPS: {'habilitado' if TLS_CERT else 'deshabilitado'}")
        return 0

    httpd = ApplicationServer((HOST, PORT), Handler)
    scheme = "http"
    if TLS_CERT and TLS_KEY:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(certfile=TLS_CERT, keyfile=TLS_KEY)
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
        scheme = "https"
    LOG.info("%s v%s iniciado en %s://%s:%s", APP_NAME, APP_VERSION, scheme, HOST, PORT)
    print_banner(scheme)
    try:
        httpd.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("\nDeteniendo el servicio…")
    finally:
        httpd.server_close()
        LOG.info("Servicio detenido.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
