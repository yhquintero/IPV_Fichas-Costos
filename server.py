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
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            unit TEXT NOT NULL,
            currency TEXT NOT NULL DEFAULT 'CUP',
            unit_price TEXT NOT NULL DEFAULT '0.00',
            supplier TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT '',
            effective_from TEXT NOT NULL DEFAULT '',
            effective_to TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Vigente',
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
        if conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
            seed_data(conn)


def seed_data(conn: sqlite3.Connection) -> None:
    stamp = now_iso()
    material_rows = [
        ("INS-001", "Ron", "L", "820.00", "Proveedor registrado", "Lista de precios vigente"),
        ("INS-002", "Limón", "kg", "210.00", "Proveedor registrado", "Lista de precios vigente"),
        ("INS-003", "Azúcar", "kg", "95.00", "Proveedor registrado", "Lista de precios vigente"),
        ("INS-004", "Hierbabuena", "kg", "600.00", "Proveedor registrado", "Lista de precios vigente"),
        ("INS-005", "Agua con gas", "L", "85.00", "Proveedor registrado", "Lista de precios vigente"),
        ("INS-006", "Mango", "kg", "180.00", "Proveedor registrado", "Lista de precios vigente"),
        ("INS-007", "Arroz", "kg", "130.00", "Proveedor registrado", "Lista de precios vigente"),
        ("INS-008", "Frijol negro", "kg", "220.00", "Proveedor registrado", "Lista de precios vigente"),
        ("INS-009", "Pollo", "kg", "490.00", "Proveedor registrado", "Lista de precios vigente"),
        ("INS-010", "Aceite", "L", "480.00", "Proveedor registrado", "Lista de precios vigente"),
        ("INS-011", "Sal", "kg", "70.00", "Proveedor registrado", "Lista de precios vigente"),
        ("INS-012", "Mano de obra", "hora", "220.00", "Tarifa interna", "Referencia oficial"),
    ]
    material_ids = {}
    for code, name, unit, price, supplier, source in material_rows:
        cur = conn.execute("""INSERT INTO materials
            (code,name,unit,currency,unit_price,supplier,source,effective_from,status,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (code, name, unit, "CUP", price, supplier, source, date.today().isoformat(), "Vigente", stamp, stamp))
        material_ids[code] = cur.lastrowid

    products = [
        ("BEB-001", "Mojito clásico", "Bebidas", "copa", "Receta estándar por porción."),
        ("BEB-002", "Jugo natural de mango", "Bebidas", "vaso", "Receta estándar por vaso."),
        ("COM-001", "Arroz congrí", "Comidas", "ración", "Receta estándar por ración."),
        ("COM-002", "Pollo asado", "Comidas", "ración", "Receta estándar por ración."),
        ("SER-001", "Servicio de salón", "Servicios", "hora", "Servicio de atención por hora."),
    ]
    product_ids = {}
    for code, name, category, unit, description in products:
        cur = conn.execute("""INSERT INTO products
            (code,name,category,unit,description,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?)""", (code, name, category, unit, description, stamp, stamp))
        product_ids[code] = cur.lastrowid

    recipes = [
        ("BEB-001", "Aprobada", [("INS-001", "0.05"), ("INS-002", "0.03"), ("INS-003", "0.02"), ("INS-004", "0.005"), ("INS-005", "0.12")]),
        ("BEB-002", "Aprobada", [("INS-006", "0.25"), ("INS-003", "0.02")]),
        ("COM-001", "Aprobada", [("INS-007", "0.12"), ("INS-008", "0.04"), ("INS-010", "0.01"), ("INS-011", "0.002")]),
        ("COM-002", "Borrador", [("INS-009", "0.25"), ("INS-010", "0.01"), ("INS-011", "0.002")]),
        ("SER-001", "Aprobada", [("INS-012", "0.5")]),
    ]
    ficha_ids = {}
    for pcode, status, lines in recipes:
        product_id = product_ids[pcode]
        cur = conn.execute("""INSERT INTO fichas
            (product_id,version,status,valid_from,observations,total_cost,created_at,updated_at)
            VALUES (?,1,?,?,?, '0.00',?,?)""",
            (product_id, status, date.today().isoformat(), "Ficha de costo inicial del producto.", stamp, stamp))
        ficha_id = cur.lastrowid
        total = Decimal("0.00")
        for material_code, qty_value in lines:
            m = conn.execute("SELECT * FROM materials WHERE id=?", (material_ids[material_code],)).fetchone()
            qty = amount(qty_value)
            cost = amount(m["unit_price"])
            subtotal = (qty * cost).quantize(CENT, rounding=ROUND_HALF_UP)
            total += subtotal
            conn.execute("""INSERT INTO ficha_items
                (ficha_id,material_id,description,quantity,unit,unit_cost,subtotal)
                VALUES (?,?,?,?,?,?,?)""",
                (ficha_id, m["id"], m["name"], quantity_text(qty), m["unit"], money(cost), money(subtotal)))
        conn.execute("UPDATE fichas SET total_cost=? WHERE id=?", (money(total), ficha_id))
        ficha_ids[pcode] = ficha_id

    _create_seed_control(conn, ficha_ids["BEB-001"], "2026-09", "Validado", "IPV-2026-0001")
    _create_seed_control(conn, ficha_ids["COM-001"], "2026-09", "Pendiente", "IPV-2026-0002")


def _create_seed_control(conn, ficha_id: int, period: str, status: str, code: str) -> None:
    stamp = now_iso()
    ficha = conn.execute("SELECT * FROM fichas WHERE id=?", (ficha_id,)).fetchone()
    cur = conn.execute("""INSERT INTO controls
        (code,ficha_id,product_id,period,status,snapshot_total,checked_total,created_at,checked_at)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (code, ficha_id, ficha["product_id"], period, status, ficha["total_cost"], ficha["total_cost"], stamp,
         stamp if status == "Validado" else ""))
    control_id = cur.lastrowid
    for item in conn.execute("SELECT * FROM ficha_items WHERE ficha_id=?", (ficha_id,)).fetchall():
        conn.execute("""INSERT INTO control_items
            (control_id,material_id,description,quantity,unit,unit_cost,subtotal)
            VALUES (?,?,?,?,?,?,?)""",
            (control_id, item["material_id"], item["description"], item["quantity"], item["unit"], item["unit_cost"], item["subtotal"]))


# ==========================================================================
#  DATA ACCESS
# ==========================================================================

def rowdict(row):
    return dict(row) if row is not None else None


def get_product(conn, product_id):
    return rowdict(conn.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone())


def list_products(conn):
    return [dict(r) for r in conn.execute("""SELECT p.*,
        (SELECT COUNT(*) FROM fichas f WHERE f.product_id=p.id) AS ficha_count
        FROM products p ORDER BY p.active DESC, p.category, p.name""").fetchall()]


def list_materials(conn):
    return [dict(r) for r in conn.execute("SELECT * FROM materials ORDER BY name").fetchall()]


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
        m.effective_to AS material_effective_to, m.status AS material_status
        FROM ficha_items fi LEFT JOIN materials m ON m.id=fi.material_id
        WHERE fi.ficha_id=? ORDER BY fi.id""", (ficha_id,)).fetchall()]
    return data


def list_fichas(conn):
    return [dict(r) for r in conn.execute("""SELECT f.*, p.code AS product_code,
        p.name AS product_name, p.category, p.unit AS product_unit,
        (SELECT COUNT(*) FROM ficha_items fi WHERE fi.ficha_id=f.id) AS item_count,
        (SELECT COUNT(*) FROM controls c WHERE c.ficha_id=f.id) AS control_count
        FROM fichas f JOIN products p ON p.id=f.product_id
        ORDER BY f.updated_at DESC, f.id DESC""").fetchall()]


def control_detail(conn, control_id):
    row = conn.execute("""SELECT c.*, p.code AS product_code, p.name AS product_name,
        p.category, p.unit AS product_unit, f.version AS ficha_version, f.status AS ficha_status,
        f.total_cost AS ficha_total
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
    return data


def list_controls(conn):
    return [control_detail(conn, r[0]) for r in conn.execute("SELECT id FROM controls ORDER BY created_at DESC, id DESC").fetchall()]


def dashboard(conn):
    count = lambda sql: conn.execute(sql).fetchone()[0]
    recent = [dict(r) for r in conn.execute("""SELECT f.id,f.version,f.status,f.total_cost,f.updated_at,
        p.name AS product_name,p.category,p.code AS product_code FROM fichas f JOIN products p ON p.id=f.product_id
        ORDER BY f.updated_at DESC,f.id DESC LIMIT 5""").fetchall()]
    categories = [dict(r) for r in conn.execute("SELECT category,COUNT(*) AS count FROM products WHERE active=1 GROUP BY category ORDER BY category").fetchall()]
    # Cost distribution by category
    cost_by_cat = [dict(r) for r in conn.execute("""SELECT p.category, SUM(CAST(f.total_cost AS REAL)) AS total
        FROM fichas f JOIN products p ON p.id=f.product_id
        WHERE f.id IN (SELECT MAX(id) FROM fichas GROUP BY product_id)
        GROUP BY p.category ORDER BY total DESC""").fetchall()]
    # Activity timeline (last 10 operations)
    activity = [dict(r) for r in conn.execute("""
        SELECT 'ficha' as type, id, 'Ficha creada' as action, created_at as timestamp FROM fichas
        UNION ALL
        SELECT 'control', id, 'Control generado', created_at FROM controls
        UNION ALL
        SELECT 'product', id, 'Producto registrado', created_at FROM products
        ORDER BY timestamp DESC LIMIT 10
    """).fetchall()]
    return {
        "products": count("SELECT COUNT(*) FROM products WHERE active=1"),
        "materials": count("SELECT COUNT(*) FROM materials"),
        "fichas": count("SELECT COUNT(*) FROM fichas"),
        "approved_fichas": count("SELECT COUNT(*) FROM fichas WHERE status='Aprobada'"),
        "pending_controls": count("SELECT COUNT(*) FROM controls WHERE status='Pendiente'"),
        "validated_controls": count("SELECT COUNT(*) FROM controls WHERE status='Validado'"),
        "recent_fichas": recent,
        "categories": categories,
        "cost_by_category": cost_by_cat,
        "activity_timeline": activity,
    }


def search_all(conn, query: str, limit: int = 20):
    """Full-text search across all entities."""
    q = f"%{sanitize_text(query, 100)}%"
    results = []
    # Search products
    for r in conn.execute("SELECT id, code, name, category, 'product' as type FROM products WHERE name LIKE ? OR code LIKE ? LIMIT ?", (q, q, limit)).fetchall():
        results.append(dict(r))
    # Search materials
    for r in conn.execute("SELECT id, code, name, unit, 'material' as type FROM materials WHERE name LIKE ? OR code LIKE ? LIMIT ?", (q, q, limit)).fetchall():
        results.append(dict(r))
    # Search fichas
    for r in conn.execute("""SELECT f.id, p.code, p.name, f.version, f.status, 'ficha' as type
        FROM fichas f JOIN products p ON p.id=f.product_id WHERE p.name LIKE ? OR p.code LIKE ? LIMIT ?""", (q, q, limit)).fetchall():
        results.append(dict(r))
    # Search controls
    for r in conn.execute("""SELECT c.id, c.code, p.name, c.period, c.status, 'control' as type
        FROM controls c JOIN products p ON p.id=c.product_id WHERE c.code LIKE ? OR p.name LIKE ? LIMIT ?""", (q, q, limit)).fetchall():
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
                        "time": now_iso(), "version": "1.0.0",
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
            client = self.client_ip()
            with WRITE_LOCK, connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                if path.startswith("/api/products/"):
                    product_id = int(path.split("/")[-1])
                    cur = conn.execute("UPDATE products SET active=0,updated_at=? WHERE id=?", (now_iso(), product_id))
                    if cur.rowcount == 0:
                        raise APIError("Producto no encontrado.", 404)
                    result = {"ok": True}
                    audit_log("DEACTIVATE_PRODUCT", f"id={product_id}", client)
                else:
                    raise APIError("Ruta API no encontrada.", 404)
            self.send_json(result)
        except APIError as exc:
            self.send_json({"error": exc.message}, exc.status)
        except (ValueError, TypeError):
            self.send_json({"error": "Identificador no válido."}, 400)
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

    def _create_product(self, conn, data):
        code = sanitize_code(data.get("code", ""))
        name = sanitize_text(data.get("name", ""), 200)
        category = sanitize_text(data.get("category", ""), 100)
        unit = sanitize_text(data.get("unit", "unidad"), 30) or "unidad"
        if not code or not name or not category:
            raise APIError("Código, nombre y categoría son obligatorios.")
        stamp = now_iso()
        cur = conn.execute("""INSERT INTO products(code,name,category,unit,description,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?)""", (code, name, category, unit, sanitize_text(data.get("description", ""), 1000), stamp, stamp))
        return get_product(conn, cur.lastrowid)

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
        if currency not in ("CUP", "MLC", "USD", "EUR"):
            raise APIError("Moneda no soportada.")
        stamp = now_iso()
        cur = conn.execute("""INSERT INTO materials
            (code,name,unit,currency,unit_price,supplier,source,effective_from,effective_to,status,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (code, name, unit, currency, money(unit_price),
             sanitize_text(data.get("supplier", ""), 200), sanitize_text(data.get("source", ""), 300),
             sanitize_text(data.get("effective_from", date.today().isoformat()), 20),
             sanitize_text(data.get("effective_to", ""), 20),
             sanitize_text(data.get("status", "Vigente"), 30), stamp, stamp))
        return dict(conn.execute("SELECT * FROM materials WHERE id=?", (cur.lastrowid,)).fetchone())

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
        stamp = now_iso()
        cur = conn.execute("""INSERT INTO fichas
            (product_id,version,status,valid_from,observations,total_cost,created_at,updated_at)
            VALUES (?,?,'Borrador',?,?, '0.00',?,?)""",
            (product_id, version, sanitize_text(data.get("valid_from", date.today().isoformat()), 20),
             sanitize_text(data.get("observations", ""), 1000), stamp, stamp))
        ficha_id = cur.lastrowid
        total = Decimal("0.00")
        for item in items:
            total += insert_ficha_item(conn, ficha_id, item)
        conn.execute("UPDATE fichas SET total_cost=? WHERE id=?", (money(total), ficha_id))
        return ficha_detail(conn, ficha_id)

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
            raise APIError("No se permiten más de 100 componentes por ficha.")
        conn.execute("DELETE FROM ficha_items WHERE ficha_id=?", (ficha_id,))
        total = Decimal("0.00")
        for item in items:
            total += insert_ficha_item(conn, ficha_id, item)
        conn.execute("UPDATE fichas SET observations=?,valid_from=?,total_cost=?,updated_at=? WHERE id=?",
                     (sanitize_text(data.get("observations", ficha["observations"]), 1000),
                      sanitize_text(data.get("valid_from", ficha["valid_from"]), 20), money(total), now_iso(), ficha_id))
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
            SELECT code, name, unit, unit_price, currency, supplier, 
                   source, effective_from, status
            FROM materials
            ORDER BY name
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
