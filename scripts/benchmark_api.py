#!/usr/bin/env python3
"""Benchmark reproducible y aislado de endpoints HTTP con dataset sintético.

    python scripts/benchmark_api.py --rows 500 --iterations 25

Mide API local en memoria de prueba, no carga real ni producción. Requiere solo
la biblioteca estándar de Python. No replica datos ni cambia la base del proyecto.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import platform
import secrets
import statistics
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from contextlib import redirect_stdout
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Importar el servidor emite mensajes de diagnóstico; mantener stdout limpio para JSON.
with redirect_stdout(io.StringIO()):
    import auth  # noqa: E402
    import server  # noqa: E402


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def request(base: str, path: str, token: str = "") -> tuple[int, bytes]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(base + path, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def _run(rows: int, iterations: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="ipv-benchmark-") as temp:
        temp_path = Path(temp)
        old_db, old_root = server.DB_PATH, server.ROOT
        old_secret, old_enabled = auth.JWT_SECRET, auth.JWT_ENABLED
        httpd = None
        server.DB_PATH, server.ROOT = temp_path / "benchmark.db", temp_path
        auth.JWT_SECRET = secrets.token_urlsafe(48)
        auth.JWT_ENABLED = True
        server.Handler.log_message = lambda *_args, **_kwargs: None
        try:
            server.init_db()
            stamp = server.now_iso()
            with server.connect() as conn:
                conn.executemany(
                    "INSERT INTO products(code,name,category,unit,description,active,yield_qty,yield_unit,created_at,updated_at) "
                    "VALUES(?,?,?,'unidad','',1,'1','unidad',?,?)",
                    [(f"BM-{index:06d}", f"Producto de prueba {index}", "Benchmark", stamp, stamp)
                     for index in range(rows)],
                )
                auth.create_user(conn, {"email": "benchmark@ipv.local", "name": "Benchmark", "role": "admin",
                                        "password": "Bench#Local-2026"}, server.now_iso)

            httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{httpd.server_port}"
            deadline = time.monotonic() + 15
            while True:
                status, _ = request(base, "/api/health")
                if status == 200:
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError("El servidor local de benchmark no quedó listo.")
                time.sleep(0.05)

            login_data = json.dumps({"email": "benchmark@ipv.local", "password": "Bench#Local-2026"}).encode()
            login_req = urllib.request.Request(base + "/api/auth/login", data=login_data,
                                               headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(login_req, timeout=20) as response:
                token = json.loads(response.read())["access_token"]

            samples = {"GET /api/health": [], "GET /api/products": [], "GET /api/dashboard": []}
            payload_bytes = {name: 0 for name in samples}
            endpoints = [("GET /api/health", "/api/health", ""),
                         ("GET /api/products", "/api/products", token),
                         ("GET /api/dashboard", "/api/dashboard", token)]
            for _ in range(iterations):
                for label, path, bearer in endpoints:
                    started = time.perf_counter()
                    status, body = request(base, path, bearer)
                    elapsed = (time.perf_counter() - started) * 1000
                    if status != 200:
                        raise RuntimeError(f"{label} devolvió HTTP {status}: {body[:200]!r}")
                    samples[label].append(elapsed)
                    payload_bytes[label] = len(body)

            return {
                "fecha_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "tipo": "benchmark sintético local; no representa producción",
                "revision_git": subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                                               capture_output=True, text=True, check=False).stdout.strip() or "desconocida",
                "entorno": {"python": platform.python_version(), "sistema": platform.platform(),
                            "cpu_logicas": os.cpu_count(), "host": "loopback", "cifrado_db": bool(server.dbcrypt.ENABLED)},
                "dataset": {"productos": rows, "iteraciones_por_endpoint": iterations},
                "resultados": {
                    name: {"p50_ms": round(statistics.median(values), 3),
                           "p95_ms": round(percentile(values, 0.95), 3),
                           "payload_ultima_muestra_bytes": payload_bytes[name]}
                    for name, values in samples.items()
                },
                "advertencia": "No comparar con otros equipos o tamaños de datos sin conservar método y versión.",
            }
        finally:
            if httpd is not None:
                httpd.shutdown()
                httpd.server_close()
            auth.JWT_SECRET, auth.JWT_ENABLED = old_secret, old_enabled
            server.DB_PATH, server.ROOT = old_db, old_root


def run(rows: int, iterations: int) -> dict:
    with redirect_stdout(io.StringIO()):
        return _run(rows, iterations)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=500, help="productos sintéticos (1–10000)")
    parser.add_argument("--iterations", type=int, default=20, help="muestras por endpoint (1–35)")
    args = parser.parse_args()
    if not 1 <= args.rows <= 10000 or not 1 <= args.iterations <= 35:
        parser.error("--rows debe estar entre 1 y 10000 y --iterations entre 1 y 35")
    try:
        print(json.dumps(run(args.rows, args.iterations), ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"resultado": "FALLO", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
