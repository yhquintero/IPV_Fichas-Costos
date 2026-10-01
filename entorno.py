"""IPV · Fichas y Costos — Carga del archivo `.env` en el entorno del proceso.
Autor: Ing. Yosvany Hernández Quintero

¿Por qué existe este módulo?
---------------------------
Hasta ahora solo `iniciar-https.ps1` leía el archivo `.env`: arrancar el servidor
a mano (`python server.py`) dejaba el proceso **sin** `IPV_JWT_SECRET`, sin
certificado TLS y, por tanto, sin HTTPS y sin inicio de sesión, sin ningún aviso
claro. Este módulo cierra ese hueco: `server.py` carga `.env` al arrancar, igual
en Windows, Linux o macOS.

Reglas (intencionadamente conservadoras):
  · Las variables que ya existen en el entorno **mandan**: `.env` nunca las pisa,
    así el script de PowerShell, Docker o un `set`/`export` manual siguen ganando.
  · Formato admitido:  CLAVE=valor,  con `#` para comentarios y comillas opcionales.
  · Se admite el prefijo `export ` para que el mismo archivo sirva en un shell.
  · Si el archivo no existe no pasa nada: el servidor usa sus valores por defecto.

Solo usa la librería estándar.
"""
from __future__ import annotations

import os
from pathlib import Path

__all__ = ["parse_env", "cargar"]

RAIZ = Path(__file__).resolve().parent


def parse_env(texto: str) -> dict[str, str]:
    """Convierte el contenido de un `.env` en un diccionario.

    Ignora líneas vacías y comentarios, admite `export CLAVE=valor` y retira las
    comillas simples o dobles que envuelven el valor.
    """
    valores: dict[str, str] = {}
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        if linea.startswith("export "):
            linea = linea[len("export "):].lstrip()
        clave, _, valor = linea.partition("=")
        clave = clave.strip()
        if not clave:
            continue
        valor = valor.strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
            valor = valor[1:-1]
        valores[clave] = valor
    return valores


def cargar(ruta: str | os.PathLike | None = None, *, sobrescribir: bool = False) -> dict[str, str]:
    """Carga `.env` en `os.environ` y devuelve lo que se aplicó.

    `sobrescribir=False` (por defecto) respeta lo que ya hubiera en el entorno.
    """
    archivo = Path(ruta) if ruta is not None else Path(os.environ.get("IPV_ENV_FILE", RAIZ / ".env"))
    try:
        if not archivo.is_file():
            return {}
        texto = archivo.read_text(encoding="utf-8-sig")
    except OSError:
        # Un `.env` ilegible no debe impedir el arranque: se continúa con el entorno actual.
        return {}

    aplicados: dict[str, str] = {}
    for clave, valor in parse_env(texto).items():
        if sobrescribir or not os.environ.get(clave):
            os.environ[clave] = valor
            aplicados[clave] = valor
    return aplicados
