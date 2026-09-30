"""
IPV Fichas y Costos - Roles del sistema (solo librería estándar).
Autor: Ing. Yosvany Hernández Quintero

Mismo esquema de roles que el repositorio «inventario» (Cuadres, Inventarios),
compartido por la aplicación IPV (web y Android) y por el Keygen Web:

  ADMINISTRADOR  control total: usuarios, licencias, copias de seguridad y auditoría.
  JEFE           dirige el negocio y al equipo; no puede tocar a los administradores.
  ECONOMICO      costos y finanzas: precios, fichas y controles; tasas de cambio.
  ALMACENERO     existencias y valores del IPV, sin ver los costos de las fichas.

Los permisos por módulo de cada rol están en `permisos.py` (y se pueden ajustar
por usuario); las capacidades del Keygen Web están en `CAPACIDADES_KEYGEN`.
"""
from __future__ import annotations

ADMINISTRADOR = "ADMINISTRADOR"
JEFE = "JEFE"
ECONOMICO = "ECONOMICO"
ALMACENERO = "ALMACENERO"

ROLES = (ADMINISTRADOR, JEFE, ECONOMICO, ALMACENERO)
# Igual que `ADMINS` en inventario: los dos roles que dirigen el sistema
ADMINS = frozenset({ADMINISTRADOR, JEFE})

LABELS = {
    ADMINISTRADOR: "Administrador",
    JEFE: "Jefe",
    ECONOMICO: "Económico",
    ALMACENERO: "Almacenero",
}

DESCRIPTIONS = {
    ADMINISTRADOR: "Control total: usuarios, licencias, copias de seguridad y auditoría.",
    JEFE: "Dirige el negocio y al equipo (no gestiona administradores). Ve y edita todo.",
    ECONOMICO: "Costos y finanzas: precios, fichas y controles. No modifica existencias.",
    ALMACENERO: "Existencias y valores del IPV. No ve los costos de las fichas ni los controles.",
}

# Roles de versiones anteriores (admin / editor / viewer) y su equivalente al migrar.
# `editor` y `viewer` pasan a ALMACENERO (el rol sin funciones de administración)
# y conservan exactamente los permisos que tenían: nadie gana privilegios al actualizar.
LEGACY_ROLES = {"admin": ADMINISTRADOR, "editor": ALMACENERO, "viewer": ALMACENERO}

# Quién puede usar cada grupo de rutas administrativas del servidor IPV
ROUTE_ROLES = {
    "/api/users": frozenset({ADMINISTRADOR, JEFE}),
    "/api/backup": frozenset({ADMINISTRADOR, JEFE}),
    "/api/audit": frozenset({ADMINISTRADOR, JEFE, ECONOMICO}),
    "/api/keygen": frozenset({ADMINISTRADOR}),
}


def is_valid(role) -> bool:
    return role in ROLES


def label(role: str) -> str:
    return LABELS.get(role, str(role))


def catalog() -> list[dict]:
    """Catálogo para los clientes (web y Android): identificador, nombre y descripción."""
    return [{"id": r, "label": LABELS[r], "description": DESCRIPTIONS[r],
             "admin": r in ADMINS} for r in ROLES]


def can_manage(actor_role: str, target_role: str) -> bool:
    """¿Puede `actor_role` administrar (crear, cambiar, desactivar) cuentas de `target_role`?

    El ADMINISTRADOR gestiona a todos; el JEFE solo a los roles que no son administrativos
    (ni puede ascender a nadie a ADMINISTRADOR).
    """
    if actor_role == ADMINISTRADOR:
        return target_role in ROLES
    if actor_role == JEFE:
        return target_role in (ECONOMICO, ALMACENERO)
    return False


# ---------------------------------------------------------------------------
#  Keygen Web: qué puede hacer cada rol sobre las licencias
# ---------------------------------------------------------------------------
CAPACIDADES_KEYGEN = {
    #                        emitir  historial  precios  anular  exportar  usuarios  clave  tasas  auditoría
    ADMINISTRADOR: {"emit", "history_all", "prices", "revoke", "export", "users", "keys", "rates", "audit"},
    JEFE:          {"emit", "history_all", "prices", "revoke", "export", "users", "rates", "audit"},
    ECONOMICO:     {"history_all", "prices", "export", "rates", "audit"},
    ALMACENERO:    {"emit", "history_own"},
}

KEYGEN_DESCRIPTIONS = {
    ADMINISTRADOR: "Todo: usuarios, clave de firma, emitir, anular, exportar y auditoría.",
    JEFE: "Emite, anula y consulta todo el historial; gestiona usuarios (no administradores).",
    ECONOMICO: "Consulta el historial completo con precios, exporta y fija las tasas. No emite.",
    ALMACENERO: "Operador: emite licencias y consulta solo las que él mismo creó (sin precios).",
}


def keygen_caps(role: str) -> set[str]:
    return set(CAPACIDADES_KEYGEN.get(role, ()))


def keygen_can(role: str, capability: str) -> bool:
    return capability in CAPACIDADES_KEYGEN.get(role, ())


def keygen_catalog() -> list[dict]:
    return [{"id": r, "label": LABELS[r], "description": KEYGEN_DESCRIPTIONS[r],
             "capabilities": sorted(CAPACIDADES_KEYGEN[r])} for r in ROLES]
