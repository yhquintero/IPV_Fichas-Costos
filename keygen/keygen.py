#!/usr/bin/env python3
"""IPV Keygen — emisión de licencias por período para IPV Web y IPV Android.

Uso (en el equipo del proveedor, NUNCA en el del cliente):

    python keygen/keygen.py                     # interfaz gráfica
    python keygen/keygen.py init --whatsapp 5355555555
    python keygen/keygen.py emitir --usuario "Juan Pérez" --codigo IPVW-XXXXX-... --plan 1M
    python keygen/keygen.py verificar --licencia IPV1....
    python keygen/keygen.py precios

Alternativa integrada: el **Creador de Licencias** de la aplicación web (creador_licencias.py,
menú «Creador de Licencias», solo administradores) usa este mismo módulo, por lo que comparten
clave_privada.json, tasas.json y registro_licencias.csv; puede alternar entre ambos.

`init` crea la clave de firma (cifrada con su contraseña) y escribe la clave pública y
su número de WhatsApp en licencia.py (servidor) y en License.kt (Android). Después hay
que volver a distribuir el servidor y recompilar el APK.

Ing. Yosvany Hernández Quintero
"""
from __future__ import annotations

import argparse
import csv
import getpass
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
import licencia as L

KEY_FILE = HERE / "clave_privada.json"
LEDGER = HERE / "registro_licencias.csv"
RATES_FILE = HERE / "tasas.json"
KOTLIN = ROOT / "android/app/src/main/java/cu/ipvcostos/app/License.kt"
PBKDF2_ITER = 600_000
DEFAULT_RATES = {"USD": 740.00, "EUR": 840.00, "MLC": 467.12, "CAD": 477.29, "MXN": 52.34,
                 "ZELLE": 718.22, "CLA": 675.64}


# ------------------------------------------------------------ clave privada ----
def _derive(passphrase: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", passphrase.encode(), salt, PBKDF2_ITER)


def save_private_key(d: int, passphrase: str, path: Path = KEY_FILE) -> None:
    salt = secrets.token_bytes(16)
    key = _derive(passphrase, salt)
    stream = hmac.new(key, b"ipv-keygen-enc" + salt, hashlib.sha256).digest()
    ct = bytes(a ^ b for a, b in zip(d.to_bytes(32, "big"), stream))
    tag = hmac.new(key, b"ipv-keygen-mac" + salt + ct, hashlib.sha256).hexdigest()
    doc = {"v": 1, "kdf": "pbkdf2-sha256", "iter": PBKDF2_ITER, "salt": salt.hex(), "ct": ct.hex(),
           "tag": tag, "public": L.public_from_private(d), "created": time.strftime("%Y-%m-%d %H:%M")}
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def load_private_key(passphrase: str, path: Path = KEY_FILE) -> int:
    if not path.exists():
        raise SystemExit("No existe la clave de firma. Ejecute primero:  python keygen/keygen.py init")
    doc = json.loads(path.read_text(encoding="utf-8"))
    salt, ct = bytes.fromhex(doc["salt"]), bytes.fromhex(doc["ct"])
    key = hashlib.pbkdf2_hmac("sha256", passphrase.encode(), salt, int(doc["iter"]))
    tag = hmac.new(key, b"ipv-keygen-mac" + salt + ct, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(tag, doc["tag"]):
        raise ValueError("Contraseña incorrecta.")
    stream = hmac.new(key, b"ipv-keygen-enc" + salt, hashlib.sha256).digest()
    d = int.from_bytes(bytes(a ^ b for a, b in zip(ct, stream)), "big")
    if L.public_from_private(d) != doc["public"]:
        raise ValueError("El archivo de clave está dañado.")
    return d


def ask_passphrase(confirm: bool = False) -> str:
    env = os.environ.get("IPV_KEYGEN_PASS")
    if env:
        return env
    pw = getpass.getpass("Contraseña de la clave de firma: ")
    if confirm:
        if len(pw) < 10:
            raise SystemExit("Use al menos 10 caracteres.")
        if getpass.getpass("Repita la contraseña: ") != pw:
            raise SystemExit("Las contraseñas no coinciden.")
    return pw


# ------------------------------------------------------------ precios ---------
def rates() -> dict:
    try:
        return {**DEFAULT_RATES, **json.loads(RATES_FILE.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return dict(DEFAULT_RATES)


def price_usd(app: str, plan: str) -> int:
    return L.PLANS[plan][2] if app == L.APP_WEB else L.PLANS[plan][3]


def fmt_cup(v: float) -> str:
    """Formato monetario unificado: $ 3,163,138.00 (miles con coma, decimales con punto)."""
    return f"$ {v:,.2f}"


def price_line(app: str, plan: str) -> str:
    usd, r = price_usd(app, plan), rates()
    cup = usd * r["USD"]
    return (f"{usd} USD = {fmt_cup(cup)} CUP  |  {cup / r['EUR']:.2f} EUR  |  {cup / r['ZELLE']:.2f} Zelle  |  "
            f"{cup / r['MLC']:.2f} MLC  |  {cup / r['CLA']:.2f} CLA")


# ------------------------------------------------------------ operaciones -----
def patch_public_key(pub_hex: str, whatsapp: str) -> list[str]:
    changed = []
    py = ROOT / "licencia.py"
    s = py.read_text(encoding="utf-8")
    s = re.sub(r'^PUBLIC_KEY_HEX = ".*"$', f'PUBLIC_KEY_HEX = "{pub_hex}"', s, count=1, flags=re.MULTILINE)
    s = re.sub(r'^WHATSAPP_NUMBER = ".*"$', f'WHATSAPP_NUMBER = "{whatsapp}"', s, count=1, flags=re.MULTILINE)
    py.write_text(s, encoding="utf-8")
    changed.append(str(py.relative_to(ROOT)))
    if KOTLIN.exists():
        k = KOTLIN.read_text(encoding="utf-8")
        k = re.sub(r'const val PUBLIC_KEY_B64 = ".*"', f'const val PUBLIC_KEY_B64 = "{L.spki_der_b64(pub_hex)}"', k, count=1)
        k = re.sub(r'const val WHATSAPP_NUMBER = ".*"', f'const val WHATSAPP_NUMBER = "{whatsapp}"', k, count=1)
        KOTLIN.write_text(k, encoding="utf-8")
        changed.append(str(KOTLIN.relative_to(ROOT)))
    return changed


def clean_phone(num: str) -> str:
    digits = re.sub(r"\D", "", num or "")
    if digits and not 8 <= len(digits) <= 15:
        raise SystemExit("Número de WhatsApp no válido. Formato internacional sin '+': 5355555555")
    return digits


def emit(d: int, user: str, code: str, plan: str) -> tuple[str, str]:
    token = L.issue(d, user, code, plan)
    data = L.decode(token, L.public_from_private(d))
    new_file = not LEDGER.exists()
    with LEDGER.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if new_file:
            w.writerow(["fecha", "serie", "usuario", "app", "plan", "vence", "codigo_solicitud", "precio_usd", "precio_cup"])
        usd = price_usd(data["app"], plan)
        w.writerow([time.strftime("%Y-%m-%d %H:%M"), data["sn"], data["usr"], data["app"], plan,
                    time.strftime("%Y-%m-%d", time.localtime(data["exp"])), code.upper(), usd, round(usd * rates()["USD"])])
    return token, whatsapp_reply(data, token)


def whatsapp_reply(data: dict, token: str) -> str:
    vence = time.strftime("%d/%m/%Y", time.localtime(data["exp"]))
    return (f"✅ *Licencia IPV Fichas de Costo*\n"
            f"Usuario: {data['usr']}\n"
            f"Aplicación: {L.APP_NAMES[data['app']]}\n"
            f"Plan: {L.PLANS[data['plan']][0]} — vence el {vence}\n"
            f"Serie: {data['sn']}\n\n"
            f"Copie la licencia completa y péguela en *Activar licencia*:\n\n{token}")


def describe(token: str, pub: str) -> str:
    data = L.decode(token, pub)
    return (f"Firma válida ✔\nUsuario: {data['usr']}\nApp: {L.APP_NAMES[data['app']]}\n"
            f"Dispositivo: {data['dev']}\nPlan: {L.PLANS[data['plan']][0]}\n"
            f"Emitida: {time.strftime('%d/%m/%Y %H:%M', time.localtime(data['iat']))}\n"
            f"Vence: {time.strftime('%d/%m/%Y %H:%M', time.localtime(data['exp']))}\nSerie: {data['sn']}")


def current_public() -> str:
    if KEY_FILE.exists():
        return json.loads(KEY_FILE.read_text(encoding="utf-8"))["public"]
    return L.PUBLIC_KEY_HEX


# ------------------------------------------------------------ CLI -------------
def cmd_init(args) -> None:
    if KEY_FILE.exists() and not args.force:
        raise SystemExit("Ya existe una clave. Usar --force invalida TODAS las licencias emitidas.")
    phone = clean_phone(args.whatsapp)
    pw = ask_passphrase(confirm=True)
    d, pub = L.generate_keypair()
    save_private_key(d, pw)
    files = patch_public_key(pub, phone)
    print("Clave de firma creada:", KEY_FILE)
    print("Clave pública escrita en:", ", ".join(files))
    print("\n⚠ Haga una copia de keygen/clave_privada.json y de su contraseña en un lugar seguro.")
    print("  Sin ellas no podrá renovar licencias; con ellas cualquiera podría emitirlas.")
    print("⚠ Vuelva a distribuir el servidor y recompile el APK para que usen la nueva clave.")


def cmd_emit(args) -> None:
    d = load_private_key(ask_passphrase())
    _token, reply = emit(d, args.usuario, args.codigo, args.plan.upper())
    app = L.parse_request_code(args.codigo)[0]
    print(reply)
    print("\nPrecio:", price_line(app, args.plan.upper()))


def cmd_verify(args) -> None:
    print(describe(args.licencia, current_public()))


def cmd_prices(_args) -> None:
    r = rates()
    print("Tasas (CUP): " + ", ".join(f"1 {k} = {v}" for k, v in r.items()))
    for app in (L.APP_WEB, L.APP_ANDROID):
        print(f"\n{L.APP_NAMES[app]}")
        for plan, (name, days, *_rest) in L.PLANS.items():
            print(f"  {plan}  {name:<9} ({days:>3} días): {price_line(app, plan)}")


# ------------------------------------------------------------ GUI -------------
def run_gui() -> None:
    import tkinter as tk
    from tkinter import messagebox, simpledialog, ttk

    root = tk.Tk()
    root.title("IPV Keygen — Licencias")
    root.geometry("760x640")
    root.configure(bg="#0f172a")
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", background="#0f172a", foreground="#e2e8f0", font=("Segoe UI", 10))
    style.configure("TEntry", fieldbackground="#1e293b", foreground="#f8fafc")
    style.configure("TCombobox", fieldbackground="#1e293b", foreground="#f8fafc")
    style.configure("Accent.TButton", background="#10b981", foreground="#052e16", font=("Segoe UI", 10, "bold"))
    style.configure("TButton", background="#6366f1", foreground="white")
    state = {"d": None}

    frm = ttk.Frame(root, padding=16)
    frm.pack(fill="both", expand=True)
    tk.Label(frm, text="🔑 IPV Keygen", bg="#0f172a", fg="#34d399", font=("Segoe UI", 18, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
    tk.Label(frm, text="Emisión de licencias por período · Ing. Yosvany Hernández Quintero", bg="#0f172a",
             fg="#94a3b8").grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 12))

    user_var, code_var, plan_var = tk.StringVar(), tk.StringVar(), tk.StringVar(value="1M — 1 Mes")
    price_var = tk.StringVar(value="")
    ttk.Label(frm, text="Usuario:").grid(row=2, column=0, sticky="w")
    ttk.Entry(frm, textvariable=user_var, width=60).grid(row=2, column=1, sticky="we", pady=4)
    ttk.Label(frm, text="ID Dispositivo (código):").grid(row=3, column=0, sticky="w")
    ttk.Entry(frm, textvariable=code_var, width=60).grid(row=3, column=1, sticky="we", pady=4)
    ttk.Label(frm, text="Plan:").grid(row=4, column=0, sticky="w")
    plans = [f"{k} — {v[0]}" for k, v in L.PLANS.items()]
    ttk.Combobox(frm, textvariable=plan_var, values=plans, state="readonly", width=20).grid(row=4, column=1, sticky="w", pady=4)
    tk.Label(frm, textvariable=price_var, bg="#0f172a", fg="#fbbf24", wraplength=700, justify="left").grid(row=5, column=0, columnspan=2, sticky="w", pady=6)
    out = tk.Text(frm, height=16, bg="#1e293b", fg="#f8fafc", insertbackground="white", wrap="word", relief="flat")
    out.grid(row=7, column=0, columnspan=2, sticky="nsew", pady=8)
    frm.columnconfigure(1, weight=1)
    frm.rowconfigure(7, weight=1)

    def update_price(*_a):
        try:
            app = L.parse_request_code(code_var.get())[0]
            price_var.set(f"{L.APP_NAMES[app]} · {price_line(app, plan_var.get()[:2])}")
        except ValueError:
            price_var.set("Pegue el código de solicitud recibido por WhatsApp (IPVW-… para PC, IPVA-… para móvil).")

    code_var.trace_add("write", update_price)
    plan_var.trace_add("write", update_price)
    update_price()

    def key() -> int | None:
        if state["d"] is None:
            pw = simpledialog.askstring("Clave de firma", "Contraseña de la clave de firma:", show="•", parent=root)
            if not pw:
                return None
            try:
                state["d"] = load_private_key(pw)
            except (ValueError, SystemExit) as exc:
                messagebox.showerror("Keygen", str(exc))
                return None
        return state["d"]

    def generate():
        d = key()
        if d is None:
            return
        try:
            _token, reply = emit(d, user_var.get(), code_var.get(), plan_var.get()[:2])
        except ValueError as exc:
            messagebox.showerror("Keygen", str(exc))
            return
        out.delete("1.0", "end")
        out.insert("1.0", reply)
        root.clipboard_clear()
        root.clipboard_append(reply)
        messagebox.showinfo("Keygen", "Licencia generada y copiada al portapapeles.\nPéguela en WhatsApp.")

    def verify_clip():
        try:
            messagebox.showinfo("Verificar", describe(root.clipboard_get(), current_public()))
        except (ValueError, tk.TclError) as exc:
            messagebox.showerror("Verificar", str(exc))

    bar = ttk.Frame(frm)
    bar.grid(row=6, column=0, columnspan=2, sticky="w")
    ttk.Button(bar, text="Generar licencia", style="Accent.TButton", command=generate).pack(side="left", padx=(0, 8))
    ttk.Button(bar, text="Verificar licencia del portapapeles", command=verify_clip).pack(side="left")
    if not KEY_FILE.exists():
        messagebox.showwarning("Keygen", "Aún no hay clave de firma. Ejecute:\npython keygen/keygen.py init --whatsapp 53XXXXXXXX")
    root.mainloop()


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="IPV Keygen — licencias por período")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("init", help="crear la clave de firma")
    p.add_argument("--whatsapp", default="", help="número para solicitudes, p. ej. 5355555555")
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("emitir", help="emitir una licencia")
    p.add_argument("--usuario", required=True)
    p.add_argument("--codigo", required=True, help="código de solicitud IPVW-/IPVA-")
    p.add_argument("--plan", required=True, choices=[k for k in L.PLANS] + [k.lower() for k in L.PLANS])
    p = sub.add_parser("verificar", help="comprobar una licencia")
    p.add_argument("--licencia", required=True)
    sub.add_parser("precios", help="tabla de precios en USD/CUP")
    args = ap.parse_args(argv)
    try:
        {"init": cmd_init, "emitir": cmd_emit, "verificar": cmd_verify, "precios": cmd_prices}.get(
            args.cmd, lambda _a: run_gui())(args)
    except ValueError as exc:
        raise SystemExit(f"Error: {exc}") from exc


if __name__ == "__main__":
    main()
