"""Provisiona el servidor aislado del E2E con una licencia propia efímera."""
import json
import os
import urllib.error
import urllib.request

BASE = os.environ.get("IPV_E2E_BASE_URL", "http://127.0.0.1:8011")
EMAIL = os.environ["IPV_ADMIN_EMAIL"]
PASSWORD = os.environ["IPV_ADMIN_PASSWORD"]
SIGNING_PASSWORD = "E2E-clave-firma-solo-CI-2026"


def request(method, path, payload=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"{method} {path} respondió {exc.code}: {detail}") from exc


def main():
    status, login = request("POST", "/api/auth/login", {"email": EMAIL, "password": PASSWORD})
    assert status == 200 and login.get("access_token"), "No se pudo iniciar la sesión temporal de E2E."
    token = login["access_token"]
    status, initialized = request("POST", "/api/keygen/init", {
        "passphrase": SIGNING_PASSWORD, "whatsapp": "", "force": False,
    }, token)
    assert status == 200 and initialized.get("configured"), "No se pudo crear la clave efímera del E2E."
    status, info = request("GET", "/api/keygen/status", token=token)
    code = info.get("license", {}).get("request_code")
    assert status == 200 and code, "No se obtuvo el código de solicitud del servidor de E2E."
    status, issued = request("POST", "/api/keygen/emit", {
        "user": "Servidor E2E", "code": code, "plan": "1A", "passphrase": SIGNING_PASSWORD,
    }, token)
    assert status == 200 and issued.get("license"), "No se pudo emitir la licencia propia efímera."
    status, activation = request("POST", "/api/license", {"license": issued["license"]}, token)
    assert status == 200 and activation.get("valid"), "No se pudo activar la licencia temporal del servidor."
    print("Servidor E2E inicializado con clave y licencia efímeras.")


if __name__ == "__main__":
    main()
