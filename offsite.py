"""
IPV Fichas y Costos - Réplica de copias de seguridad fuera del equipo.
Autor: Ing. Yosvany Hernández Quintero

Destinos (se pueden combinar):
  · IPV_BACKUP_MIRROR_DIRS   Carpetas separadas por ';' (disco USB, carpeta de red
                             \\\\servidor\\copias, NAS…). Se copia, se verifica el SHA-256
                             y se aplica la retención IPV_BACKUP_MIRROR_KEEP.
  · IPV_BACKUP_S3_*          Almacenamiento compatible con S3 (AWS, MinIO, Backblaze B2,
                             Wasabi…). Firma AWS Signature V4 implementada con la librería
                             estándar; se envía x-amz-content-sha256 para que el servidor
                             verifique la integridad.

Con IPV_DB_KEY las copias ya salen cifradas (SQLCipher). Sin ella, se avisa en el
registro: una copia en claro fuera del equipo expone todos los datos.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import shutil
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CHUNK = 1024 * 1024


def _env_list(name: str) -> list[str]:
    return [p.strip() for p in os.environ.get(name, "").split(";") if p.strip()]


MIRROR_DIRS = _env_list("IPV_BACKUP_MIRROR_DIRS")
MIRROR_KEEP = int(os.environ.get("IPV_BACKUP_MIRROR_KEEP", "30") or 30)
S3_ENDPOINT = os.environ.get("IPV_BACKUP_S3_ENDPOINT", "").strip().rstrip("/")   # https://s3.us-east-1.amazonaws.com
S3_BUCKET = os.environ.get("IPV_BACKUP_S3_BUCKET", "").strip()
S3_PREFIX = os.environ.get("IPV_BACKUP_S3_PREFIX", "ipv-fichas-costos/").strip()
S3_REGION = os.environ.get("IPV_BACKUP_S3_REGION", "us-east-1").strip()
S3_ACCESS_KEY = os.environ.get("IPV_BACKUP_S3_ACCESS_KEY", "").strip()
S3_SECRET_KEY = os.environ.get("IPV_BACKUP_S3_SECRET_KEY", "").strip()

_state_lock = threading.Lock()
LAST: dict = {"time": None, "file": None, "results": []}


class OffsiteError(Exception):
    pass


def configured() -> bool:
    return bool(MIRROR_DIRS or s3_configured())


def s3_configured() -> bool:
    return bool(S3_ENDPOINT and S3_BUCKET and S3_ACCESS_KEY and S3_SECRET_KEY)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
#  Carpetas espejo
# ---------------------------------------------------------------------------
def copy_to_dir(src: Path, target_dir: Path, expected_sha: str, keep: int | None = None) -> dict:
    keep = MIRROR_KEEP if keep is None else keep
    target_dir.mkdir(parents=True, exist_ok=True)
    final = target_dir / src.name
    partial = target_dir / (src.name + ".partial")
    shutil.copyfile(src, partial)  # copia completa antes de hacerla visible
    if sha256_file(partial) != expected_sha:
        partial.unlink(missing_ok=True)
        raise OffsiteError(f"La copia en {target_dir} no coincide (SHA-256).")
    os.replace(partial, final)
    (target_dir / (src.name + ".sha256")).write_text(f"{expected_sha}  {src.name}\n", encoding="ascii")
    # Retención por nombre (ipv_backup_AAAAMMDD_HHMMSS.db ordena cronológicamente)
    prefix = src.name.rsplit("_", 2)[0]
    olds = sorted(target_dir.glob(f"{prefix}_*.db"), key=lambda p: p.name, reverse=True)
    for old in olds[keep:]:
        old.unlink(missing_ok=True)
        (target_dir / (old.name + ".sha256")).unlink(missing_ok=True)
    return {"target": str(target_dir), "ok": True}


# ---------------------------------------------------------------------------
#  S3 (AWS Signature Version 4)
# ---------------------------------------------------------------------------
def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def sign_v4(method: str, url: str, headers: dict, payload_sha: str, region: str, access_key: str,
            secret_key: str, now: datetime | None = None, service: str = "s3") -> dict:
    """Devuelve las cabeceras firmadas (Authorization, x-amz-date, x-amz-content-sha256)."""
    now = now or datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    day = now.strftime("%Y%m%d")
    parts = urllib.parse.urlsplit(url)
    signed = {k.lower(): str(v).strip() for k, v in headers.items()}
    signed["host"] = parts.netloc
    signed["x-amz-date"] = amz_date
    signed["x-amz-content-sha256"] = payload_sha
    names = sorted(signed)
    canonical_query = "&".join(
        f"{urllib.parse.quote(k, safe='-_.~')}={urllib.parse.quote(v, safe='-_.~')}"
        for k, v in sorted(urllib.parse.parse_qsl(parts.query, keep_blank_values=True)))
    canonical = "\n".join([
        method, urllib.parse.quote(parts.path or "/", safe="/-_.~"), canonical_query,
        "".join(f"{n}:{signed[n]}\n" for n in names), ";".join(names), payload_sha])
    scope = f"{day}/{region}/{service}/aws4_request"
    to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
    key = _hmac(_hmac(_hmac(_hmac(f"AWS4{secret_key}".encode(), day), region), service), "aws4_request")
    signature = hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()
    out = {k: v for k, v in signed.items() if k != "host"}
    out["authorization"] = (f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
                            f"SignedHeaders={';'.join(names)}, Signature={signature}")
    return out


def upload_s3(src: Path, sha: str, timeout: int = 300) -> dict:
    key = f"{S3_PREFIX}{src.name}"
    url = f"{S3_ENDPOINT}/{S3_BUCKET}/{urllib.parse.quote(key, safe='/-_.~')}"  # estilo path (válido en MinIO/AWS)
    if not url.lower().startswith("https://") and not os.environ.get("IPV_BACKUP_S3_ALLOW_HTTP"):
        raise OffsiteError("El destino S3 debe usar HTTPS.")
    headers = sign_v4("PUT", url, {"content-type": "application/octet-stream",
                                   "x-amz-meta-sha256": sha}, sha, S3_REGION, S3_ACCESS_KEY, S3_SECRET_KEY)
    size = src.stat().st_size
    with open(src, "rb") as body:
        req = urllib.request.Request(url, data=body, method="PUT",
                                     headers={**headers, "content-length": str(size)})
        try:
            # El esquema se valida arriba (solo https, salvo IPV_BACKUP_S3_ALLOW_HTTP explícito)
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
                if resp.status not in (200, 201):
                    raise OffsiteError(f"S3 respondió {resp.status}.")
        except urllib.error.HTTPError as exc:
            raise OffsiteError(f"S3 rechazó la subida ({exc.code}): {exc.read()[:200]!r}") from exc
        except urllib.error.URLError as exc:
            raise OffsiteError(f"No se pudo conectar con S3: {exc.reason}") from exc
    return {"target": f"s3://{S3_BUCKET}/{key}", "ok": True}


# ---------------------------------------------------------------------------
#  Orquestación
# ---------------------------------------------------------------------------
def replicate(src, encrypted: bool) -> dict:
    """Replica `src` en todos los destinos. Nunca lanza: devuelve el resultado por destino."""
    src = Path(src)
    results = []
    if configured():
        try:
            sha = sha256_file(src)
        except OSError as exc:
            results.append({"target": "origen", "ok": False, "error": f"No se pudo leer {src.name}: {exc}"})
            with _state_lock:
                LAST.update({"time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                             "file": src.name, "results": results})
            return {"file": src.name, "results": results}
        if not encrypted:
            print("  ⚠ Réplica externa de un backup SIN cifrar: defina IPV_DB_KEY para proteger las copias.")
        for folder in MIRROR_DIRS:
            try:
                results.append(copy_to_dir(src, Path(folder), sha))
            except (OSError, OffsiteError) as exc:
                results.append({"target": folder, "ok": False, "error": str(exc)})
        if s3_configured():
            try:
                results.append(upload_s3(src, sha))
            except (OSError, OffsiteError) as exc:
                results.append({"target": f"s3://{S3_BUCKET}", "ok": False, "error": str(exc)})
    with _state_lock:
        LAST.update({"time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     "file": src.name, "results": results})
    return {"file": src.name, "results": results}


def status() -> dict:
    with _state_lock:
        last = dict(LAST)
    return {"configured": configured(), "mirror_dirs": len(MIRROR_DIRS), "s3": s3_configured(),
            "last": last}
