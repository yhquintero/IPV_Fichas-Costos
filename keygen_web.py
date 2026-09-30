#!/usr/bin/env python3
"""IPV Keygen Web — lanzador.

    python keygen_web.py                       # abre http://127.0.0.1:8500 en el navegador
    python keygen_web.py --port 8600 --no-navegador
    python keygen_web.py --restablecer-clave USUARIO [--sin-2fa]     # recuperar el acceso desde la consola

Emisión visual de licencias para IPV Web e IPV Android, con historial completo, roles
(ADMINISTRADOR, JEFE, ECONOMICO, ALMACENERO), usuario + contraseña + 2FA y auditoría.
Ejecútelo solo en el equipo del proveedor, nunca en el del cliente.
Guía completa: docs/keygen-web.md

Ing. Yosvany Hernández Quintero
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from keygen import webapp  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="IPV Keygen Web — licencias de IPV Web e IPV Android")
    ap.add_argument("--host", default="127.0.0.1", help="dirección de escucha (por defecto solo este equipo)")
    ap.add_argument("--port", type=int, default=webapp.DEFAULT_PORT)
    ap.add_argument("--no-navegador", action="store_true", help="no abrir el navegador automáticamente")
    ap.add_argument("--restablecer-clave", metavar="USUARIO",
                    help="fija una nueva contraseña para USUARIO (recuperación con acceso al equipo) y sale")
    ap.add_argument("--sin-2fa", action="store_true",
                    help="junto a --restablecer-clave: desactiva también su verificación en dos pasos")
    args = ap.parse_args(argv)
    if args.restablecer_clave:
        password = getpass.getpass("Nueva contraseña: ")
        if getpass.getpass("Repita la contraseña: ") != password:
            print("Las contraseñas no coinciden.", file=sys.stderr)
            return 1
        try:
            print(webapp.reset_password(args.restablecer_clave, password, args.sin_2fa))
        except Exception as exc:  # contraseña débil (AuthError) o usuario inexistente (ValueError)
            print(f"Error: {getattr(exc, 'message', exc)}", file=sys.stderr)
            return 1
        return 0
    webapp.serve(args.host, args.port, open_browser=not args.no_navegador)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
