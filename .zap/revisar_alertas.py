#!/usr/bin/env python3
"""Revisa el informe JSON de OWASP ZAP y decide si la CI debe fallar.

Uso:  python .zap/revisar_alertas.py report_json.json [etiqueta]

Reglas:
  * Cada alerta se anota en el job (::error:: o ::notice::) para poder verla sin
    descargar el artefacto.
  * Falla si aparece una alerta de riesgo **medio o alto** que no esté marcada
    como IGNORE ni como WARN en `.zap/rules.tsv`.
  * Las alertas informativas y de riesgo bajo solo se anotan: un escaneo pasivo
    siempre produce ruido (comentarios del código, cabeceras `Sec-Fetch-*` que
    envía el propio escáner, etc.).
"""
from __future__ import annotations

import json
import pathlib
import sys

RULES = pathlib.Path(__file__.rsplit("/", 1)[0] + "/rules.tsv")
NIVEL = {0: "Informativa", 1: "Baja", 2: "Media", 3: "Alta"}


def acciones() -> dict[str, str]:
    """{id de regla: IGNORE|WARN|FAIL} leído de rules.tsv."""
    acc: dict[str, str] = {}
    if not RULES.is_file():
        return acc
    for linea in RULES.read_text(encoding="utf-8").splitlines():
        if not linea.strip() or linea.lstrip().startswith("#"):
            continue
        partes = linea.split("\t")
        if len(partes) >= 2:
            acc[partes[0].strip()] = partes[1].strip().upper()
    return acc


def main() -> int:
    ruta = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "report_json.json")
    etiqueta = sys.argv[2] if len(sys.argv) > 2 else "ZAP"
    if not ruta.is_file():
        print(f"::notice::{etiqueta}: no se generó {ruta} (¿falló el escaneo antes de tiempo?)")
        return 0

    acc = acciones()
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    bloqueantes: list[str] = []
    total = 0

    for sitio in datos.get("site", []):
        for alerta in sitio.get("alerts", []):
            total += 1
            rid = str(alerta.get("pluginid", "?"))
            riesgo = int(alerta.get("riskcode", "0") or 0)
            accion = acc.get(rid, "")
            urls = ", ".join(i.get("uri", "") for i in alerta.get("instances", [])[:3])
            resumen = (f"[{rid}] {NIVEL.get(riesgo, '?')} · {alerta.get('alert')} · "
                       f"{alerta.get('count')} caso(s) · {urls}")
            if riesgo >= 2 and accion not in ("IGNORE", "WARN"):
                bloqueantes.append(resumen)
                print(f"::error::{etiqueta}: {resumen}")
            else:
                print(f"::notice::{etiqueta}: {resumen}{' · aceptada en rules.tsv' if accion else ''}")

    print(f"{etiqueta}: {total} alerta(s), {len(bloqueantes)} bloqueante(s).")
    if bloqueantes:
        print(f"::error::{etiqueta}: hay {len(bloqueantes)} alerta(s) de riesgo medio o alto sin justificar "
              f"en .zap/rules.tsv")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
