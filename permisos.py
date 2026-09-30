"""
IPV Fichas y Costos - Sistema de Seguridad por Usuarios (solo librería estándar).
Autor: Ing. Yosvany Hernández Quintero

Permisos finos por módulo, aplicados a las dos pestañas de la entrada
«Valores del IPV» (Valores e Inventario) y al resto de apartados del sistema:

  * view  — puede abrir el apartado y consultar sus datos
  * edit  — puede crear, modificar, ajustar existencias, restaurar y enviar a la papelera
  * costs — puede ver y administrar precios, importes y valores en dinero (se ocultan del API y de la web)

Los permisos efectivos salen del rol (admin / editor / viewer) y se ajustan por
usuario en la tabla `user_permissions`. El administrador los cambia desde
Web → Usuarios → 🔐 Permisos y tienen efecto inmediato: se leen en cada petición,
así que no hace falta cerrar sesiones ni volver a iniciar.

Reglas de seguridad:
  * Los administradores conservan siempre todos los permisos (no se pueden
    bloquear a sí mismos ni quedar fuera del sistema).
  * `edit` y `costs` implican `view`: sin acceso al apartado no hay nada que
    editar ni que valorar.
  * Los importes se filtran en la respuesta del servidor, no solo en la web:
    un usuario sin `costs` nunca recibe los precios por mucho que inspeccione
    las peticiones.
"""
from __future__ import annotations

import re
import sqlite3

# ---------------------------------------------------------------------------
#  Módulos y permisos
# ---------------------------------------------------------------------------
# «materials» es la entrada única «Valores del IPV» con sus dos pestañas:
# Valores (referencias y precios) e Inventario (existencias y rendimiento).
MODULES = {
    "materials": "Valores del IPV e Inventario",
    "products": "Productos y servicios",
    "fichas": "Fichas de costo",
    "controls": "Controles de IPV",
    "trash": "Papelera de reciclaje",
}
PERMS = ("view", "edit", "costs")
PERM_LABELS = {"view": "Ver", "edit": "Editar", "costs": "Ver costos"}

# Campos con información económica que se ocultan sin el permiso `costs`
MONEY_FIELDS = ("unit_price", "stock_value", "total_value")
# Importes propios de fichas, controles y analítica (mismo criterio, otro módulo)
COST_FIELDS = ("total_cost", "unit_cost", "subtotal", "snapshot_total", "checked_total",
               "avg_cost", "cost_per_serving", "ficha_total")

SCHEMA = """
CREATE TABLE IF NOT EXISTS user_permissions (
    user_id INTEGER NOT NULL,
    module TEXT NOT NULL,
    can_view INTEGER NOT NULL DEFAULT 1,
    can_edit INTEGER NOT NULL DEFAULT 0,
    can_costs INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (user_id, module)
);
"""


class PermisoError(Exception):
    """Permiso mal definido o no permitido (se traduce a un error HTTP)."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def _perms(view: bool = True, edit: bool = False, costs: bool = True) -> dict:
    return {"view": bool(view), "edit": bool(edit and view), "costs": bool(costs and view)}


def defaults_for(role: str) -> dict:
    """Permisos que hereda un usuario de su rol (base del sistema)."""
    completo = {m: _perms(True, True, True) for m in MODULES}
    if role in ("admin", "editor"):
        return completo
    # Consulta: ve todo, no modifica nada y no ve los precios de los valores del IPV
    lectura = {m: _perms(True, False, True) for m in MODULES}
    lectura["materials"] = _perms(True, False, False)
    return lectura


# ---------------------------------------------------------------------------
#  Esquema y permisos efectivos
# ---------------------------------------------------------------------------
def init_permissions(conn) -> None:
    conn.executescript(SCHEMA)
    # Borra ajustes huérfanos de usuarios que ya no existen
    conn.execute("DELETE FROM user_permissions WHERE user_id NOT IN (SELECT id FROM users)")


def effective(conn, user_id, role: str) -> dict:
    """Permisos efectivos: los del rol, con los ajustes guardados para el usuario."""
    perms = defaults_for(role)
    if role == "admin" or not user_id:
        return perms  # el administrador siempre tiene acceso completo
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return perms
    try:
        rows = conn.execute("SELECT module, can_view, can_edit, can_costs FROM user_permissions "
                            "WHERE user_id=?", (uid,)).fetchall()
    except sqlite3.Error:
        # Base de datos anterior al sistema de permisos (sin la tabla): se aplica el rol.
        # `dbcrypt` unifica las clases de excepción, así que sirve con SQLite y con SQLCipher.
        return perms
    for row in rows:
        module = row["module"] if hasattr(row, "keys") else row[0]
        if module not in perms:
            continue
        values = (row["can_view"], row["can_edit"], row["can_costs"]) if hasattr(row, "keys") else row[1:4]
        perms[module] = _perms(bool(values[0]), bool(values[1]), bool(values[2]))
    return perms


def can(perms, module: str, perm: str) -> bool:
    """¿Tiene este usuario el permiso indicado? Sin permisos (modo abierto) se permite."""
    if not perms:
        return True
    if module not in MODULES:
        return True
    return bool(perms.get(module, {}).get(perm))


def set_permissions(conn, user_id, role: str, data, now_iso) -> dict:
    """Guarda los permisos por módulo de un usuario y devuelve los efectivos.

    Se puede enviar solo lo que cambia: los permisos ausentes conservan el valor
    del rol (así `{"fichas": {"costs": false}}` quita los importes sin cerrar el
    apartado). `edit` y `costs` siempre se descuentan de `view`.
    """
    if role == "admin":
        raise PermisoError("Los administradores siempre tienen todos los permisos; "
                           "cámbiele el rol si necesita limitarlo.")
    if not isinstance(data, dict) or not data:
        raise PermisoError("Indique los permisos por módulo, por ejemplo "
                           "{\"materials\": {\"view\": true, \"edit\": false, \"costs\": false}}.")
    desconocidos = sorted(k for k in data if k not in MODULES)
    if desconocidos:
        raise PermisoError(f"Módulos no válidos: {', '.join(desconocidos)}.")
    base = defaults_for(role)
    for module, perms in data.items():
        if not isinstance(perms, dict):
            raise PermisoError(f"Los permisos de «{MODULES[module]}» deben ser un objeto.")
        mal = sorted(p for p in perms if p not in PERMS)
        if mal:
            raise PermisoError(f"Permisos no válidos en «{MODULES[module]}»: {', '.join(mal)}.")
        hereda = base[module]
        limpio = _perms(bool(perms.get("view", hereda["view"])),
                        bool(perms.get("edit", hereda["edit"])),
                        bool(perms.get("costs", hereda["costs"])))
        conn.execute("""INSERT INTO user_permissions(user_id,module,can_view,can_edit,can_costs,updated_at)
                        VALUES(?,?,?,?,?,?)
                        ON CONFLICT(user_id,module) DO UPDATE SET
                          can_view=excluded.can_view, can_edit=excluded.can_edit,
                          can_costs=excluded.can_costs, updated_at=excluded.updated_at""",
                     (int(user_id), module, 1 if limpio["view"] else 0, 1 if limpio["edit"] else 0,
                      1 if limpio["costs"] else 0, now_iso()))
    return effective(conn, user_id, role)


def reset_permissions(conn, user_id) -> None:
    """Deja al usuario con los permisos de su rol (borra los ajustes)."""
    conn.execute("DELETE FROM user_permissions WHERE user_id=?", (int(user_id),))


# ---------------------------------------------------------------------------
#  Qué permiso exige cada ruta del API
# ---------------------------------------------------------------------------
_TRASH_ITEM = re.compile(r"^/api/trash/(materials|products|fichas|controls)/\d+(/restore)?$")
_REPORT_MODULE = {"materials_inventory": "materials", "fichas_summary": "fichas", "controls_pending": "controls"}


def rule_for(path: str, method: str):
    """Devuelve (módulo, permiso) exigidos por la ruta, o None si no aplica.

    La lectura pide `view`; cualquier escritura (POST/PUT/DELETE/PATCH) pide `edit`.
    Restaurar o purgar desde la papelera exige permiso sobre el módulo del registro.
    """
    method = (method or "GET").upper()
    if method in ("OPTIONS", "HEAD"):
        return None
    permiso = "view" if method == "GET" else "edit"

    basura = _TRASH_ITEM.match(path)
    if basura:
        return (basura.group(1), "edit")  # restaurar o purgar modifica el módulo
    if path == "/api/trash/empty":
        return ("trash", "edit")
    if path == "/api/trash":
        return ("trash", permiso)
    if path.startswith("/api/materials") or path.startswith("/api/inventory"):
        return ("materials", permiso)
    if path.startswith("/api/products"):
        return ("products", permiso)
    if path.startswith("/api/fichas"):
        return ("fichas", permiso)
    if path.startswith("/api/controls"):
        return ("controls", permiso)
    if path.startswith("/api/report/"):
        modulo = _REPORT_MODULE.get(path.rsplit("/", 1)[-1])
        return (modulo, permiso) if modulo else None
    if path == "/api/statistics":
        return ("fichas", permiso)  # analítica de costos de las fichas
    if path == "/api/demo/seed":
        return ("materials", "edit")  # escribe en valores, productos, fichas y controles
    return None


def denial_message(module: str, perm: str) -> str:
    nombre = MODULES.get(module, module)
    if perm == "edit":
        return f"Su usuario no tiene permiso para modificar «{nombre}»."
    if perm == "costs":
        return f"Su usuario no tiene permiso para administrar costos de «{nombre}»."
    return f"Su usuario no tiene permiso para consultar «{nombre}»."


def seed_requires() -> tuple:
    """Módulos que deben poder editarse para cargar los datos de prueba."""
    return ("products", "materials", "fichas", "controls")


# ---------------------------------------------------------------------------
#  Filtrado de respuestas: menos privilegios, menos datos
# ---------------------------------------------------------------------------
def _ocultar_importes(row: dict) -> dict:
    for field in MONEY_FIELDS:
        if field in row:
            row[field] = None
    row["costs_hidden"] = True
    return row


def _ocultar_campos(payload, campos):
    """Pone a None los importes de `campos` en dicts y listas anidadas."""
    if isinstance(payload, dict):
        salida = {}
        for k, v in payload.items():
            salida[k] = None if k in campos else _ocultar_campos(v, campos)
        if any(k in payload for k in campos):
            salida["costs_hidden"] = True
        return salida
    if isinstance(payload, list):
        return [_ocultar_campos(v, campos) for v in payload]
    return payload


# Apartados del resumen que alimenta cada módulo (el resto se oculta sin `view`)
DASHBOARD_FIELDS = {
    "products": ("products",),
    "fichas": ("fichas", "approved_fichas"),
    "controls": ("pending_controls", "validated_controls"),
    "materials": ("materials", "low_stock"),
}
_ACTIVITY_MODULE = {"ficha": "fichas", "control": "controls", "product": "products", "material": "materials"}


def _filtrar_dashboard(payload: dict, perms, costos_materials: bool) -> dict:
    """El resumen mezcla datos de todos los apartados: se recorta módulo a módulo."""
    salida = dict(payload)
    if not costos_materials and "stock_value" in salida:
        salida["stock_value"] = None
        salida["costs_hidden"] = True
    for modulo, campos in DASHBOARD_FIELDS.items():
        if can(perms, modulo, "view"):
            continue
        for campo in campos:
            if campo in salida:
                salida[campo] = None
    # Fichas recientes y distribución de costos: solo con permiso sobre fichas
    if not can(perms, "fichas", "view"):
        salida["recent_fichas"] = []
        salida["cost_by_category"] = []
    elif not can(perms, "fichas", "costs"):
        salida = _ocultar_campos(salida, ("total_cost",))
        salida["cost_by_category"] = []
    if not can(perms, "products", "view"):
        salida["categories"] = []
    if isinstance(salida.get("activity_timeline"), list):
        salida["activity_timeline"] = [a for a in salida["activity_timeline"]
                                       if can(perms, _ACTIVITY_MODULE.get(str(a.get("type")), ""), "view")]
    return salida


def _ve_costos(perms, module: str = "materials") -> bool:
    return can(perms, module, "costs")


def filter_response(path: str, payload, user):
    """Recorta la respuesta del API según los permisos del usuario autenticado.

    Se aplica en `Handler.send_json`, así que cubre todas las rutas (también las
    avanzadas y las versionadas /api/v1/...) sin tocar cada manejador.
    """
    perms = (user or {}).get("permissions")
    if not perms or payload is None:
        return payload
    if isinstance(payload, dict) and "error" in payload:
        return payload  # los mensajes de error no llevan datos del módulo
    costos = _ve_costos(perms)

    # Valores del IPV: lista, detalle, altas/bajas y existencias sin precios ni importes
    if path.startswith("/api/materials"):
        if isinstance(payload, dict) and not can(perms, "fichas", "view"):
            payload = {**payload, "used_by": [], "usage_count": 0}
        if not costos:
            if isinstance(payload, list):
                return [_ocultar_importes(dict(m)) if isinstance(m, dict) else m for m in payload]
            if isinstance(payload, dict) and any(f in payload for f in MONEY_FIELDS):
                return _ocultar_importes(dict(payload))
        return payload
    if path.startswith("/api/inventory") and isinstance(payload, dict):
        if not can(perms, "fichas", "view"):
            payload = {**payload, "items": [{**m, "used_by": [], "usage_count": 0}
                                             for m in payload.get("items", [])]}
        if not costos:
            salida = dict(payload)
            salida["items"] = [_ocultar_importes(dict(m)) for m in payload.get("items", [])]
            totales = dict(payload.get("totals", {}))
            for field in MONEY_FIELDS:
                if field in totales:
                    totales[field] = None
            salida["totals"] = totales
            salida["costs_hidden"] = True
            return salida
    if path == "/api/report/materials_inventory" and isinstance(payload, dict) and not costos:
        salida = dict(payload)
        salida["data"] = [_ocultar_importes(dict(r)) for r in payload.get("data", [])]
        salida["costs_hidden"] = True
        return salida
    # El detalle de productos contiene fichas de otro módulo: no dar acceso
    # indirecto a sus costos (ni a sus metadatos si no puede ver fichas).
    if path.startswith("/api/products"):
        if isinstance(payload, dict) and "fichas" in payload:
            payload = dict(payload)
            payload["fichas"] = payload["fichas"] if can(perms, "fichas", "view") else []
            if not can(perms, "fichas", "costs"):
                payload["fichas"] = _ocultar_campos(payload["fichas"], COST_FIELDS)
        elif isinstance(payload, list) and not can(perms, "fichas", "view"):
            payload = [{**p, **{k: None for k in ("ficha_count", "last_status", "last_ficha_id",
                                                  "last_yield_qty", "last_yield_unit") if k in p}} for p in payload]
        return payload
    # Resumen: cada tarjeta y panel depende del módulo que la alimenta
    if path == "/api/dashboard" and isinstance(payload, dict):
        return _filtrar_dashboard(payload, perms, costos)
    # Fichas, controles, analítica y reportes: importes según el permiso `costs` del módulo
    if path == "/api/statistics" or path.startswith("/api/report/fichas"):
        if not can(perms, "fichas", "costs"):
            return _ocultar_campos(payload, COST_FIELDS)
    elif path.startswith("/api/fichas"):
        if not can(perms, "fichas", "costs"):
            return _ocultar_campos(payload, COST_FIELDS)
    elif path.startswith("/api/controls") or path.startswith("/api/report/controls"):
        if not can(perms, "controls", "costs"):
            return _ocultar_campos(payload, COST_FIELDS)
    # Búsqueda global y papelera: solo los apartados que el usuario puede ver
    if path == "/api/search" and isinstance(payload, list):
        tipo_modulo = {"product": "products", "material": "materials", "ficha": "fichas", "control": "controls"}
        return [r for r in payload if can(perms, tipo_modulo.get(str(r.get("type")), ""), "view")]
    if path == "/api/trash" and isinstance(payload, dict) and isinstance(payload.get("items"), list):
        salida = dict(payload)
        salida["items"] = [t for t in payload["items"] if can(perms, str(t.get("kind")), "view")]
        return salida
    if path == "/api/categories" and isinstance(payload, dict):
        return {k: v for k, v in payload.items() if can(perms, k, "view")}
    return payload
