"""
IPV Fichas y Costos - Rate limiting granular por endpoint (ventana deslizante, en memoria).
Autor: Ing. Yosvany Hernández Quintero
"""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque

# (máximo de solicitudes, ventana en segundos)
PROFILES = {
    "auth": (5, 60),       # login / refresh: anti fuerza bruta
    "export": (10, 300),   # backups y reportes
    "bulk": (10, 60),      # operaciones masivas
    "write": (60, 60),     # POST/PUT/DELETE
    "read": (300, 60),     # GET
}
# Multiplicador de los límites (p. ej. 50 para el escaneo OWASP ZAP en CI). Nunca menor que 1.
_SCALE = max(1.0, float(os.environ.get("IPV_RATE_LIMIT_SCALE", "1") or 1))
PROFILES = {k: (max(1, int(n * _SCALE)), w) for k, (n, w) in PROFILES.items()}

_lock = threading.Lock()
_hits: dict[str, deque] = defaultdict(deque)


def profile_for(method: str, path: str) -> str:
    if path.startswith(("/api/auth/login", "/api/auth/refresh",
                        "/api/auth/maintenance-login", "/api/auth/maintenance-refresh")):
        return "auth"
    if path in ("/api/backup",) or path.startswith("/api/report/"):
        return "export"
    if path.endswith("/bulk-update"):
        return "bulk"
    return "read" if method in ("GET", "HEAD") else "write"


def check(client: str, method: str, path: str) -> tuple[bool, int, int, int]:
    """Devuelve (permitido, límite, restantes, segundos_para_reset)."""
    name = profile_for(method, path)
    limit, window = PROFILES[name]
    key = f"{name}:{client}"
    now = time.monotonic()
    with _lock:
        q = _hits[key]
        while q and q[0] <= now - window:
            q.popleft()
        if len(q) >= limit:
            return False, limit, 0, int(window - (now - q[0])) + 1
        q.append(now)
        return True, limit, limit - len(q), window
