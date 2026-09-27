#!/usr/bin/env python3
"""IPV / Fichas de Costo demo API. Uses only Python's standard library + SQLite."""
from __future__ import annotations

import json
import os
import sqlite3
import ssl
import threading
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("IPV_DB_PATH", ROOT / "data" / "ipv.db")).resolve()
HOST = os.environ.get("IPV_HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", os.environ.get("IPV_PORT", "8000")))
TLS_CERT = os.environ.get("IPV_TLS_CERT", "").strip()
TLS_KEY = os.environ.get("IPV_TLS_KEY", "").strip()
CENT = Decimal("0.01")
WRITE_LOCK = threading.RLock()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 20000")
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
        """)
        if conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
            seed_demo(conn)


def seed_demo(conn: sqlite3.Connection) -> None:
    stamp = now_iso()
    material_rows = [
        ("INS-001", "Ron (precio demostrativo)", "L", "820.00", "Proveedor de muestra", "Factura de ejemplo"),
        ("INS-002", "Limón", "kg", "210.00", "Proveedor de muestra", "Factura de ejemplo"),
        ("INS-003", "Azúcar", "kg", "95.00", "Proveedor de muestra", "Factura de ejemplo"),
        ("INS-004", "Hierbabuena", "kg", "600.00", "Proveedor de muestra", "Factura de ejemplo"),
        ("INS-005", "Agua con gas", "L", "85.00", "Proveedor de muestra", "Factura de ejemplo"),
        ("INS-006", "Mango", "kg", "180.00", "Proveedor de muestra", "Factura de ejemplo"),
        ("INS-007", "Arroz", "kg", "130.00", "Proveedor de muestra", "Factura de ejemplo"),
        ("INS-008", "Frijol negro", "kg", "220.00", "Proveedor de muestra", "Factura de ejemplo"),
        ("INS-009", "Pollo", "kg", "490.00", "Proveedor de muestra", "Factura de ejemplo"),
        ("INS-010", "Aceite", "L", "480.00", "Proveedor de muestra", "Factura de ejemplo"),
        ("INS-011", "Sal", "kg", "70.00", "Proveedor de muestra", "Factura de ejemplo"),
        ("INS-012", "Mano de obra", "hora", "220.00", "Tarifa de ejemplo", "Referencia de muestra"),
    ]
    material_ids = {}
    for code, name, unit, price, supplier, source in material_rows:
        cur = conn.execute("""INSERT INTO materials
            (code,name,unit,currency,unit_price,supplier,source,effective_from,status,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (code, name, unit, "CUP", price, supplier, source, date.today().isoformat(), "Vigente", stamp, stamp))
        material_ids[code] = cur.lastrowid

    products = [
        ("BEB-001", "Mojito clásico", "Bebidas", "copa", "Receta demostrativa por porción."),
        ("BEB-002", "Jugo natural de mango", "Bebidas", "vaso", "Receta demostrativa por vaso."),
        ("COM-001", "Arroz congrí", "Comidas", "ración", "Receta demostrativa por ración."),
        ("COM-002", "Pollo asado", "Comidas", "ración", "Receta demostrativa por ración."),
        ("SER-001", "Servicio de salón", "Servicios", "hora", "Ejemplo de servicio por hora."),
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
            (product_id, status, date.today().isoformat(), "Valores y cálculos ficticios para probar la aplicación.", stamp, stamp))
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

    create_seed_control(conn, ficha_ids["BEB-001"], "2026-09", "Validado", "IPV-2026-0001")
    create_seed_control(conn, ficha_ids["COM-001"], "2026-09", "Pendiente", "IPV-2026-0002")


def create_seed_control(conn, ficha_id: int, period: str, status: str, code: str) -> None:
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
        p.name AS product_name,p.category FROM fichas f JOIN products p ON p.id=f.product_id
        ORDER BY f.updated_at DESC,f.id DESC LIMIT 5""").fetchall()]
    categories = [dict(r) for r in conn.execute("SELECT category,COUNT(*) AS count FROM products WHERE active=1 GROUP BY category ORDER BY category").fetchall()]
    return {
        "products": count("SELECT COUNT(*) FROM products WHERE active=1"),
        "materials": count("SELECT COUNT(*) FROM materials"),
        "fichas": count("SELECT COUNT(*) FROM fichas"),
        "approved_fichas": count("SELECT COUNT(*) FROM fichas WHERE status='Aprobada'"),
        "pending_controls": count("SELECT COUNT(*) FROM controls WHERE status='Pendiente'"),
        "validated_controls": count("SELECT COUNT(*) FROM controls WHERE status='Validado'"),
        "recent_fichas": recent,
        "categories": categories,
    }


def insert_ficha_item(conn, ficha_id, item):
    material_id = item.get("material_id")
    if material_id not in (None, ""):
        material = conn.execute("SELECT * FROM materials WHERE id=?", (int(material_id),)).fetchone()
        if not material:
            raise ValueError("El insumo seleccionado no existe.")
        description = material["name"]
        unit = item.get("unit") or material["unit"]
        unit_cost = amount(material["unit_price"])
        stored_material_id = material["id"]
    else:
        description = str(item.get("description", "")).strip()
        unit = str(item.get("unit", "")).strip()
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


class APIError(Exception):
    def __init__(self, message, status=400):
        self.message = message
        self.status = status


class Handler(BaseHTTPRequestHandler):
    server_version = "IPVSQLiteDemo/1.0"

    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def send_json(self, payload, status=200):
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.end_headers()
        self.wfile.write(raw)

    def body_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 1_000_000:
                raise APIError("La solicitud es demasiado grande.", 413)
            raw = self.rfile.read(length) if length else b"{}"
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                raise APIError("Se esperaba un objeto JSON.")
            return data
        except json.JSONDecodeError:
            raise APIError("JSON no válido.")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, PATCH, DELETE, OPTIONS")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        try:
            if not path.startswith("/api"):
                self.serve_static(path)
                return
            with db_session() as conn:
                if path == "/api/health":
                    result = {"ok": True, "database": "SQLite", "file": DB_PATH.name, "time": now_iso()}
                elif path == "/api/dashboard":
                    result = dashboard(conn)
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
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        try:
            data = self.body_json()
            with WRITE_LOCK, connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                if path == "/api/products":
                    result = self.create_product(conn, data)
                    status = 201
                elif path == "/api/materials":
                    result = self.create_material(conn, data)
                    status = 201
                elif path == "/api/fichas":
                    result = self.create_ficha(conn, data)
                    status = 201
                elif path.startswith("/api/fichas/") and path.endswith("/approve"):
                    ficha_id = int(path.split("/")[-2])
                    result = self.approve_ficha(conn, ficha_id)
                    status = 200
                elif path == "/api/controls":
                    result = self.create_control(conn, data)
                    status = 201
                elif path.startswith("/api/controls/") and path.endswith("/validate"):
                    control_id = int(path.split("/")[-2])
                    result = self.validate_control(conn, control_id)
                    status = 200
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
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        try:
            data = self.body_json()
            with WRITE_LOCK, connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                if path.startswith("/api/fichas/"):
                    ficha_id = int(path.split("/")[-1])
                    result = self.update_ficha(conn, ficha_id, data)
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
        path = urlparse(self.path).path.rstrip("/")
        try:
            with WRITE_LOCK, connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                if path.startswith("/api/products/"):
                    product_id = int(path.split("/")[-1])
                    cur = conn.execute("UPDATE products SET active=0,updated_at=? WHERE id=?", (now_iso(), product_id))
                    if cur.rowcount == 0:
                        raise APIError("Producto no encontrado.", 404)
                    result = {"ok": True}
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
            file_path = (ROOT / "web" / relative).resolve()
            web_root = (ROOT / "web").resolve()
            if web_root not in file_path.parents and file_path != web_root:
                self.send_json({"error": "Ruta no permitida."}, 403)
                return
        if not file_path.is_file():
            self.send_error(404, "Archivo no encontrado")
            return
        content_type = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "application/javascript; charset=utf-8", ".svg": "image/svg+xml"}.get(file_path.suffix, "application/octet-stream")
        raw = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(raw)

    def create_product(self, conn, data):
        code = str(data.get("code", "")).strip().upper()
        name = str(data.get("name", "")).strip()
        category = str(data.get("category", "")).strip()
        unit = str(data.get("unit", "unidad")).strip() or "unidad"
        if not code or not name or not category:
            raise APIError("Código, nombre y categoría son obligatorios.")
        stamp = now_iso()
        cur = conn.execute("""INSERT INTO products(code,name,category,unit,description,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?)""", (code, name, category, unit, str(data.get("description", "")).strip(), stamp, stamp))
        return get_product(conn, cur.lastrowid)

    def create_material(self, conn, data):
        code = str(data.get("code", "")).strip().upper()
        name = str(data.get("name", "")).strip()
        unit = str(data.get("unit", "")).strip()
        if not code or not name or not unit:
            raise APIError("Código, nombre y unidad son obligatorios.")
        unit_price = amount(data.get("unit_price"))
        if unit_price < 0:
            raise APIError("El precio no puede ser negativo.")
        stamp = now_iso()
        cur = conn.execute("""INSERT INTO materials
            (code,name,unit,currency,unit_price,supplier,source,effective_from,effective_to,status,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (code, name, unit, str(data.get("currency", "CUP")).strip() or "CUP", money(unit_price),
             str(data.get("supplier", "")).strip(), str(data.get("source", "")).strip(),
             str(data.get("effective_from", date.today().isoformat())), str(data.get("effective_to", "")),
             str(data.get("status", "Vigente")), stamp, stamp))
        return dict(conn.execute("SELECT * FROM materials WHERE id=?", (cur.lastrowid,)).fetchone())

    def create_ficha(self, conn, data):
        product_id = int(data.get("product_id"))
        product = get_product(conn, product_id)
        if not product or not product["active"]:
            raise APIError("Selecciona un producto activo.")
        items = data.get("items") or []
        if not isinstance(items, list) or not items:
            raise APIError("Añade al menos un insumo o componente.")
        version = conn.execute("SELECT COALESCE(MAX(version),0)+1 FROM fichas WHERE product_id=?", (product_id,)).fetchone()[0]
        stamp = now_iso()
        cur = conn.execute("""INSERT INTO fichas
            (product_id,version,status,valid_from,observations,total_cost,created_at,updated_at)
            VALUES (?,?,'Borrador',?,?, '0.00',?,?)""",
            (product_id, version, str(data.get("valid_from", date.today().isoformat())),
             str(data.get("observations", "")).strip(), stamp, stamp))
        ficha_id = cur.lastrowid
        total = Decimal("0.00")
        for item in items:
            total += insert_ficha_item(conn, ficha_id, item)
        conn.execute("UPDATE fichas SET total_cost=? WHERE id=?", (money(total), ficha_id))
        return ficha_detail(conn, ficha_id)

    def update_ficha(self, conn, ficha_id, data):
        ficha = conn.execute("SELECT * FROM fichas WHERE id=?", (ficha_id,)).fetchone()
        if not ficha:
            raise APIError("Ficha no encontrada.", 404)
        if ficha["status"] != "Borrador":
            raise APIError("Solo se pueden editar fichas en estado Borrador. Crea una nueva versión.", 409)
        items = data.get("items") or []
        if not items:
            raise APIError("Añade al menos un insumo o componente.")
        conn.execute("DELETE FROM ficha_items WHERE ficha_id=?", (ficha_id,))
        total = Decimal("0.00")
        for item in items:
            total += insert_ficha_item(conn, ficha_id, item)
        conn.execute("UPDATE fichas SET observations=?,valid_from=?,total_cost=?,updated_at=? WHERE id=?",
                     (str(data.get("observations", ficha["observations"])).strip(),
                      str(data.get("valid_from", ficha["valid_from"])), money(total), now_iso(), ficha_id))
        return ficha_detail(conn, ficha_id)

    def approve_ficha(self, conn, ficha_id):
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

    def create_control(self, conn, data):
        ficha_id = int(data.get("ficha_id"))
        ficha = ficha_detail(conn, ficha_id)
        if not ficha:
            raise APIError("Ficha no encontrada.", 404)
        period = str(data.get("period", date.today().strftime("%Y-%m"))).strip()
        if not period:
            raise APIError("Indica el período del control.")
        if not ficha["items"]:
            raise APIError("No se puede crear un control desde una ficha vacía.")
        year = period[:4] if len(period) >= 4 and period[:4].isdigit() else str(date.today().year)
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
            (code, ficha_id, ficha["product_id"], period, ficha["total_cost"], str(data.get("notes", "")).strip(), stamp))
        control_id = cur.lastrowid
        for item in ficha["items"]:
            conn.execute("""INSERT INTO control_items
                (control_id,material_id,description,quantity,unit,unit_cost,subtotal)
                VALUES (?,?,?,?,?,?,?)""",
                (control_id, item["material_id"], item["description"], item["quantity"], item["unit"], item["unit_cost"], item["subtotal"]))
        return control_detail(conn, control_id)

    def validate_control(self, conn, control_id):
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


def main():
    init_db()
    if bool(TLS_CERT) != bool(TLS_KEY):
        raise RuntimeError("Configura IPV_TLS_CERT e IPV_TLS_KEY juntos para habilitar HTTPS.")
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    scheme = "http"
    if TLS_CERT and TLS_KEY:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(certfile=TLS_CERT, keyfile=TLS_KEY)
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
        scheme = "https"
    print(f"IPV Fichas y Costos disponible en {scheme}://{HOST}:{PORT}")
    print(f"SQLite: {DB_PATH}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nCerrando servidor…")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
