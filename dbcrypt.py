"""
IPV Fichas y Costos - Cifrado de la base de datos en reposo (SQLCipher, AES-256).
Autor: Ing. Yosvany Hernández Quintero

Activación
----------
1. Instalar el motor:      pip install sqlcipher3-wheels     (Windows)
                           pip install sqlcipher3-binary     (Linux / Docker)
2. Definir la clave:       IPV_DB_KEY=<frase larga>   o   IPV_DB_KEY_FILE=<ruta a archivo>
3. Cifrar la BD existente: python dbcrypt.py encrypt
   (se conserva una copia en claro con sufijo .plain-<fecha>.bak que debe
   guardarse fuera del equipo o borrarse de forma segura)

Sin IPV_DB_KEY todo funciona igual que antes (SQLite estándar). Si hay clave
pero falta el motor, o la BD sigue en claro, el servidor NO arranca: nunca se
degrada en silencio a almacenamiento sin cifrar.

Comandos:  python dbcrypt.py status | encrypt | decrypt <destino> | rekey
"""
from __future__ import annotations

import functools
import hashlib
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

PLAIN_HEADER = b"SQLite format 3\x00"
MIN_KEY_LEN = 16

try:  # sqlcipher3-binary y sqlcipher3-wheels exponen el mismo módulo
    import sqlcipher3 as _cipher  # type: ignore
except ImportError:  # pragma: no cover - depende de la instalación
    _cipher = None


class CryptoConfigError(RuntimeError):
    """Configuración de cifrado inválida: el servidor no debe arrancar."""


def _load_key() -> str:
    key = os.environ.get("IPV_DB_KEY", "")
    key_file = os.environ.get("IPV_DB_KEY_FILE", "").strip()
    if not key and key_file:
        try:
            key = Path(key_file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise CryptoConfigError(f"No se pudo leer IPV_DB_KEY_FILE: {exc}") from exc
    return key


KEY = _load_key()
ENABLED = bool(KEY)


KDF_SALT = b"IPV-Fichas-Costos/dbcrypt/v1"
KDF_ITERATIONS = 310_000


@functools.lru_cache(maxsize=8)
def _quote(key: str) -> str:
    """Deriva la clave AES-256 UNA sola vez (PBKDF2-HMAC-SHA512) y la entrega a
    SQLCipher como clave binaria. Así cada conexión nueva no repite el KDF de
    SQLCipher (≈100 ms), algo crítico porque el servidor abre una por petición."""
    raw = hashlib.pbkdf2_hmac("sha512", key.encode("utf-8"), KDF_SALT, KDF_ITERATIONS, dklen=32)
    return f"\"x'{raw.hex()}'\""


def _install_compat() -> None:
    """Hace que `sqlite3.Row` y las excepciones `sqlite3.*` usadas en todo el
    proyecto correspondan a las de SQLCipher (mismo API DB-API 2.0)."""
    for name in ("Row", "Error", "DatabaseError", "IntegrityError", "OperationalError",
                 "ProgrammingError", "InterfaceError", "NotSupportedError", "DataError"):
        setattr(sqlite3, name, getattr(_cipher, name))


if ENABLED and _cipher is not None:
    _install_compat()


def is_plaintext(path) -> bool:
    try:
        with open(path, "rb") as fh:
            return fh.read(16) == PLAIN_HEADER
    except FileNotFoundError:
        return False


def validate() -> None:
    """Se llama al arrancar. Lanza CryptoConfigError si la configuración es insegura."""
    if not ENABLED:
        return
    if _cipher is None:
        raise CryptoConfigError("IPV_DB_KEY está definida pero falta el motor SQLCipher. "
                                "Instale: pip install sqlcipher3-wheels (Windows) o sqlcipher3-binary (Linux).")
    if len(KEY) < MIN_KEY_LEN:
        raise CryptoConfigError(f"IPV_DB_KEY debe tener al menos {MIN_KEY_LEN} caracteres.")


def connect(path, timeout: float = 20, key: str | None = None):
    """Conexión SQLite o SQLCipher según la configuración."""
    key = KEY if key is None else key
    if not key:
        return sqlite3.connect(str(path), timeout=timeout)
    validate()
    conn = _cipher.connect(str(path), timeout=timeout)
    conn.execute(f"PRAGMA key = {_quote(key)}")
    try:
        conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
    except _cipher.DatabaseError as exc:
        conn.close()
        if is_plaintext(path):
            raise CryptoConfigError("La base de datos está SIN cifrar. Ejecute: python dbcrypt.py encrypt") from exc
        raise CryptoConfigError("Clave de base de datos incorrecta (IPV_DB_KEY).") from exc
    return conn


def check_database(path) -> None:
    """Verificación de arranque: motor disponible, clave correcta y archivo cifrado."""
    validate()
    if ENABLED:
        _install_compat()
        if is_plaintext(path):
            raise CryptoConfigError(f"'{path}' está SIN cifrar. Ejecute: python dbcrypt.py encrypt")
        if Path(path).exists():
            connect(path).close()


def status(path) -> dict:
    path = Path(path)
    return {
        "encryption_configured": ENABLED,
        "engine_available": _cipher is not None,
        "engine_version": _cipher_version(),
        "file_exists": path.exists(),
        "file_encrypted": path.exists() and not is_plaintext(path),
    }


def _cipher_version() -> str:
    if _cipher is None:
        return ""
    conn = _cipher.connect(":memory:")
    try:
        row = conn.execute("PRAGMA cipher_version").fetchone()
        return row[0] if row else ""
    finally:
        conn.close()


def _wal_checkpoint(path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()


def encrypt_file(path, key: str | None = None) -> Path:
    """Cifra en el sitio una BD en claro. Devuelve la ruta de la copia en claro."""
    key = KEY if key is None else key
    path = Path(path)
    if not key or _cipher is None:
        raise CryptoConfigError("Se necesita IPV_DB_KEY y el motor SQLCipher.")
    if not is_plaintext(path):
        raise CryptoConfigError("La base de datos no existe o ya está cifrada.")
    _wal_checkpoint(path)
    tmp = path.with_suffix(path.suffix + ".enc-tmp")
    tmp.unlink(missing_ok=True)
    conn = _cipher.connect(str(path))
    try:
        # sin PRAGMA key: el origen se abre en claro
        conn.execute(f"ATTACH DATABASE ? AS enc KEY {_quote(key)}", (str(tmp),))
        conn.execute("SELECT sqlcipher_export('enc')")
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        conn.execute(f"PRAGMA enc.user_version = {int(version)}")
        conn.execute("DETACH DATABASE enc")
    finally:
        conn.close()
    connect(tmp, key=key).close()  # verificación antes de sustituir
    backup = path.with_name(f"{path.name}.plain-{datetime.now():%Y%m%d_%H%M%S}.bak")
    path.rename(backup)
    for extra in ("-wal", "-shm"):
        Path(str(path) + extra).unlink(missing_ok=True)
    tmp.rename(path)
    return backup


def decrypt_to(path, target, key: str | None = None) -> None:
    """Exporta una copia en claro (para migrar o soporte). Úsese con cuidado."""
    key = KEY if key is None else key
    target = Path(target)
    if target.exists():
        raise CryptoConfigError("El destino ya existe.")
    conn = connect(path, key=key)
    try:
        conn.execute("ATTACH DATABASE ? AS plain KEY ''", (str(target),))
        conn.execute("SELECT sqlcipher_export('plain')")
        conn.execute("DETACH DATABASE plain")
    finally:
        conn.close()


def rekey(path, new_key: str, key: str | None = None) -> None:
    if len(new_key) < MIN_KEY_LEN:
        raise CryptoConfigError(f"La nueva clave debe tener al menos {MIN_KEY_LEN} caracteres.")
    conn = connect(path, key=key)
    try:
        conn.execute(f"PRAGMA rekey = {_quote(new_key)}")
    finally:
        conn.close()


def _main(argv) -> int:  # pragma: no cover - CLI
    import getpass
    import json

    root = Path(__file__).resolve().parent
    db = Path(os.environ.get("IPV_DB_PATH", root / "data" / "ipv.db"))
    cmd = argv[1] if len(argv) > 1 else "status"
    try:
        if cmd == "status":
            print(json.dumps(status(db), indent=2, ensure_ascii=False))
        elif cmd == "encrypt":
            backup = encrypt_file(db)
            print(f"✓ Base de datos cifrada: {db}")
            print(f"⚠ Copia en claro: {backup}\n  Guárdela fuera del equipo o bórrela de forma segura.")
        elif cmd == "decrypt" and len(argv) > 2:
            decrypt_to(db, argv[2])
            print(f"✓ Copia SIN cifrar creada en {argv[2]}. Protéjala.")
        elif cmd == "rekey":
            new = getpass.getpass("Nueva clave: ")
            if new != getpass.getpass("Repita la nueva clave: "):
                print("Las claves no coinciden."); return 1
            rekey(db, new)
            print("✓ Clave cambiada. Actualice IPV_DB_KEY antes de reiniciar el servidor.")
        else:
            print(__doc__); return 1
    except CryptoConfigError as exc:
        print(f"✗ {exc}"); return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(_main(sys.argv))
