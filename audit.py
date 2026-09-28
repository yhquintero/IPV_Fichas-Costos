"""
IPV Fichas y Costos - Auditoría persistente en SQLite (solo librería estándar).
Autor: Ing. Yosvany Hernández Quintero
"""
from __future__ import annotations

import hashlib
import hmac
import os
import queue
import sqlite3

import dbcrypt
import threading

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    action TEXT NOT NULL,
    client TEXT NOT NULL DEFAULT '',
    user_email TEXT NOT NULL DEFAULT '',
    details TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);
"""

# Clave de la cadena de integridad: sin ella no se pueden recalcular los sellos
_KEY = (os.environ.get("IPV_AUDIT_KEY") or os.environ.get("IPV_JWT_SECRET") or "ipv-audit-local").encode()
GENESIS = "0" * 64


def _seal(prev: str, row) -> str:
    material = "|".join([prev, *[str(v) for v in row]]).encode("utf-8")
    return hmac.new(_KEY, material, hashlib.sha256).hexdigest()


_db_path = None
_local = threading.local()
_queue: queue.Queue = queue.Queue(maxsize=10000)
_writer = None


def _writer_loop() -> None:
    """Hilo único escritor: las transacciones de negocio nunca esperan por la auditoría."""
    while True:
        path, row = _queue.get()
        for attempt in range(20):
            try:
                with dbcrypt.connect(path, timeout=10) as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    last = conn.execute("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
                    prev = (last[0] if last else "") or GENESIS
                    conn.execute("INSERT INTO audit_log(timestamp,action,client,user_email,details,prev_hash,hash) "
                                 "VALUES(?,?,?,?,?,?,?)", (*row, prev, _seal(prev, row)))
                break
            except sqlite3.OperationalError as exc:
                if attempt == 19:
                    print("Auditoría no registrada:", exc)
                threading.Event().wait(0.05 * (attempt + 1))
        _queue.task_done()


def init_audit(db_path) -> None:
    global _db_path, _writer
    _db_path = str(db_path)
    with dbcrypt.connect(_db_path) as conn:
        conn.executescript(SCHEMA)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(audit_log)")}
        for col in ("prev_hash", "hash"):
            if col not in cols:
                conn.execute(f"ALTER TABLE audit_log ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")
    if _writer is None:
        _writer = threading.Thread(target=_writer_loop, daemon=True, name="audit-writer")
        _writer.start()


def flush() -> None:
    _queue.join()


def set_current_user(email: str) -> None:
    _local.user = email or ""


def record(ts: str, action: str, details: str = "", client: str = "") -> None:
    """Guarda el evento sin interrumpir nunca la operación principal."""
    if not _db_path:
        return
    row = (ts, action[:80], client[:64], getattr(_local, "user", "")[:200], details[:1000])
    try:
        _queue.put_nowait((_db_path, row))
    except queue.Full:
        print("Cola de auditoría llena; evento descartado:", action)


def query(limit: int = 50, offset: int = 0, action: str = "", search: str = "") -> dict:
    flush()
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    sql, params = " FROM audit_log WHERE 1=1", []
    if action:
        sql += " AND action=?"
        params.append(action)
    if search:
        sql += " AND (details LIKE ? OR client LIKE ? OR user_email LIKE ?)"
        like = f"%{search}%"
        params += [like, like, like]
    with dbcrypt.connect(_db_path) as conn:
        conn.row_factory = sqlite3.Row
        total = conn.execute("SELECT COUNT(*)" + sql, params).fetchone()[0]
        rows = conn.execute("SELECT *" + sql + " ORDER BY id DESC LIMIT ? OFFSET ?", params + [limit, offset]).fetchall()
        actions = [r[0] for r in conn.execute("SELECT DISTINCT action FROM audit_log ORDER BY action")]
    return {"entries": [dict(r) for r in rows], "total": total, "limit": limit, "offset": offset, "actions": actions}


def verify_chain() -> dict:
    """Recorre toda la cadena y detecta filas modificadas, insertadas o eliminadas."""
    flush()
    with dbcrypt.connect(_db_path) as conn:
        rows = conn.execute("SELECT id,timestamp,action,client,user_email,details,prev_hash,hash "
                            "FROM audit_log ORDER BY id").fetchall()
    prev, checked, legacy = GENESIS, 0, 0
    for r in rows:
        if not r[7]:  # eventos anteriores a la activación de la cadena
            legacy += 1
            continue
        expected = _seal(prev, r[1:6])
        if r[6] != prev or not hmac.compare_digest(r[7], expected):
            return {"valid": False, "broken_at": r[0], "checked": checked, "legacy": legacy,
                    "message": f"Integridad comprometida en el evento #{r[0]}."}
        prev, checked = r[7], checked + 1
    return {"valid": True, "checked": checked, "legacy": legacy,
            "message": f"Cadena íntegra: {checked} eventos verificados."}
