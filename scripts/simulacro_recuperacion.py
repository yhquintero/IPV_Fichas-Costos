#!/usr/bin/env python3
"""Simulacro seguro de recuperación sobre una base TEMPORAL con datos sintéticos.

Uso:
    python scripts/simulacro_recuperacion.py
    IPV_DB_KEY='clave-temporal-de-prueba-larga' python scripts/simulacro_recuperacion.py

No lee ni modifica la base de datos real, no conserva archivos al finalizar y no
replica a destinos externos. Las cifras son del entorno de prueba, no un SLA.
"""
from __future__ import annotations

import io
import json
import shutil
import sys
import tempfile
import time
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

with redirect_stdout(io.StringIO()):
    import dbcrypt  # noqa: E402
    import offsite  # noqa: E402
    import server  # noqa: E402


def _drill() -> dict:
    with tempfile.TemporaryDirectory(prefix="ipv-drill-") as temp:
        temp_root = Path(temp)
        source_db = temp_root / "source.db"
        original_db_path, original_root = server.DB_PATH, server.ROOT
        server.DB_PATH, server.ROOT = source_db, temp_root
        # Desactivar toda replicación externa durante el simulacro sintético.
        patches = [
            mock.patch.object(offsite, "MIRROR_DIRS", []),
            mock.patch.object(offsite, "S3_ENDPOINT", ""),
            mock.patch.object(offsite, "S3_BUCKET", ""),
            mock.patch.object(offsite, "S3_ACCESS_KEY", ""),
            mock.patch.object(offsite, "S3_SECRET_KEY", ""),
        ]
        started = time.perf_counter()
        try:
            for patcher in patches:
                patcher.start()
            server.init_db()
            created = datetime.now(timezone.utc).isoformat(timespec="microseconds")
            with server.connect() as conn:
                conn.execute("CREATE TABLE IF NOT EXISTS recovery_drill ("
                             "id INTEGER PRIMARY KEY, value TEXT NOT NULL, created_at TEXT NOT NULL)")
                conn.execute("INSERT INTO recovery_drill(id,value,created_at) VALUES(1,'incluido',?)", (created,))

            info = server.auto_backup()
            if not info or info.get("error"):
                raise RuntimeError(f"No se pudo crear/verificar backup: {(info or {}).get('error', 'sin resultado')}")
            backup = temp_root / "data" / "backups" / info["filename"]
            if not backup.is_file():
                raise RuntimeError("No apareció el archivo de backup esperado.")
            backup_completed = time.perf_counter()

            # Simular una transacción confirmada después del último backup y una
            # incidencia inmediata: esta transacción debe faltar en la recuperación.
            with server.connect() as conn:
                conn.execute("INSERT INTO recovery_drill(id,value,created_at) VALUES(2,'posterior-al-backup',?)",
                             (datetime.now(timezone.utc).isoformat(timespec="microseconds"),))
            incident = time.perf_counter()

            restore_path = temp_root / "restored.db"
            restore_started = time.perf_counter()
            shutil.copy2(backup, restore_path)
            restored = dbcrypt.connect(restore_path)
            try:
                check = restored.execute("PRAGMA integrity_check").fetchone()
                if not check or str(check[0]).lower() != "ok":
                    raise RuntimeError("La base restaurada no pasó integrity_check.")
                rows = restored.execute("SELECT id,value FROM recovery_drill ORDER BY id").fetchall()
                if [(row[0], row[1]) for row in rows] != [(1, "incluido")]:
                    raise RuntimeError(f"Contenido restaurado inesperado: {rows!r}")
            finally:
                restored.close()
            finished = time.perf_counter()

            return {
                "simulacro": "solo datos sintéticos; directorio temporal eliminado al finalizar",
                "cifrado_sqlcipher": bool(dbcrypt.ENABLED),
                "resultado": "OK",
                "backup_bytes": backup.stat().st_size,
                "integrity_check": "ok",
                "dato_previo_recuperado": True,
                "escritura_posterior_no_recuperada_como_se_esperaba": True,
                "escrituras_perdidas_simuladas": 1,
                "rpo_segundos_simulado": round(incident - backup_completed, 6),
                "rto_segundos_simulado": round(finished - incident, 6),
                "tiempo_total_segundos": round(finished - started, 6),
                "advertencia": "Métricas de prueba sintética en este equipo; no son un SLA ni describen producción.",
            }
        finally:
            for patcher in reversed(patches):
                patcher.stop()
            server.DB_PATH, server.ROOT = original_db_path, original_root


def drill() -> dict:
    with redirect_stdout(io.StringIO()):
        return _drill()


if __name__ == "__main__":
    try:
        print(json.dumps(drill(), ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps({"resultado": "FALLO", "error": str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(1)
