#!/usr/bin/env python3
"""IPV Keygen — emisión de licencias por período para IPV Web y IPV Android.

Uso (en el equipo del proveedor, NUNCA en el del cliente):

    python keygen/keygen.py                     # Keygen Web: abre http://127.0.0.1:8500 en el navegador
    python keygen/keygen.py web --port 8500     # lo mismo, eligiendo dirección y puerto
    python keygen/keygen.py gui                 # ventana de escritorio (Tk)
    python keygen/keygen.py init --whatsapp 5355555555
    python keygen/keygen.py emitir --usuario "Juan Pérez" --codigo IPVW-XXXXX-... --plan 1M
    python keygen/keygen.py verificar --licencia IPV1....
    python keygen/keygen.py historial [--csv salida.csv] [--importar]
    python keygen/keygen.py precios

El **Keygen Web** (keygen/webapp.py) es la forma visual de emitir licencias y controlar su
historial completo: entrada con usuario, contraseña y 2FA, roles (ADMINISTRADOR, JEFE,
ECONOMICO, ALMACENERO), panel, historial con filtros, anulaciones, pagos y exportación.
Todas las formas de emitir (Web, CLI, ventana de escritorio y el Creador integrado en la app)
comparten clave_privada.json, tasas.json y el historial keygen/licencias.db (SQLite).

`init` crea la clave de firma (cifrada con su contraseña) y escribe la clave pública y
su número de WhatsApp en licencia.py (servidor) y en License.kt (Android). Después hay
que volver a distribuir el servidor y recompilar el APK.

Ing. Yosvany Hernández Quintero
"""
from __future__ import annotations

import argparse
import csv
import getpass
from decimal import Decimal, InvalidOperation
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

try:  # como paquete (servidor, pruebas) o ejecutado como script (python keygen/keygen.py)
    from keygen import historial as H
except ImportError:  # pragma: no cover - depende de cómo se ejecute
    import historial as H

KEY_FILE = HERE / "clave_privada.json"
LEDGER = HERE / "registro_licencias.csv"   # registro antiguo: solo se importa al historial SQLite
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


def price_usd(app: str, plan: str, custom_price: str | int | float | Decimal | None = None) -> int | float:
    if plan == "PX":
        if custom_price is None:
            raise ValueError("Indique el precio acordado en USD para el período personalizado.")
        try:
            amount = Decimal(str(custom_price).strip().replace(",", "."))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("El precio personalizado debe ser un importe válido en USD.") from exc
        if not amount.is_finite() or amount < 0:
            raise ValueError("El precio personalizado debe ser finito y no negativo.")
        return float(amount.quantize(Decimal("0.01")))
    if custom_price is not None:
        raise ValueError("El precio manual solo se admite con el plan personalizado PX.")
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


def import_legacy(conn=None) -> dict:
    """Importa el registro antiguo (registro_licencias.csv) al historial SQLite, sin duplicar."""
    if not LEDGER.exists():
        return {"imported": 0, "skipped": 0, "invalid": 0, "found": False}
    text = LEDGER.read_text(encoding="utf-8-sig")
    own, close = H._own(conn)
    try:
        with H.LOCK:
            result = H.import_legacy_csv(own, text)
            if close:
                own.commit()
        return {**result, "found": True}
    finally:
        if close:
            own.close()


def emit(d: int, user: str, code: str, plan: str, start_date: str | None = None,
         end_date: str | None = None, custom_price: str | int | float | Decimal | None = None, *,
         contact: str = "", notes: str = "", created_by: str = "", paid: bool = False,
         pay_method: str = "", renewed_from: str = "", source: str = "cli", conn=None) -> tuple[str, str]:
    """Firma una licencia y la registra en el historial (keygen/licencias.db).

    Si el historial no se puede escribir la licencia NO se entrega: nunca sale una licencia
    sin su registro.
    """
    token = L.issue(d, user, code, plan, start_date=start_date, end_date=end_date)
    data = L.decode(token, L.public_from_private(d))
    usd = price_usd(data["app"], plan, custom_price)
    rate = rates()["USD"]
    H.record_issue(token=token, data=data, request_code=code, price_usd=usd, price_cup=round(usd * rate),
                   usd_rate=rate, created_by=created_by, contact=contact, notes=notes, paid=paid,
                   pay_method=pay_method, renewed_from=renewed_from, source=source, conn=conn)
    return token, whatsapp_reply(data, token)


def whatsapp_reply(data: dict, token: str) -> str:
    vence = data.get("end_date") or time.strftime("%d/%m/%Y", time.localtime(data["exp"]))
    period = f"\nVigencia: {data['start_date']} hasta {data['end_date']} (UTC)" if data["plan"] == "PX" else ""
    return (f"✅ *Licencia IPV Fichas de Costo*\n"
            f"Usuario: {data['usr']}\n"
            f"Aplicación: {L.APP_NAMES[data['app']]}\n"
            f"Plan: {L.PLANS[data['plan']][0]}{period} — vence el {vence}\n"
            f"Serie: {data['sn']}\n\n"
            f"Copie la licencia completa y péguela en *Activar licencia*:\n\n{token}")


def describe(token: str, pub: str) -> str:
    data = L.decode(token, pub)
    period = (f"\nVigencia: {data['start_date']} hasta {data['end_date']} (UTC)" if data["plan"] == "PX" else "")
    return (f"Firma válida ✔\nUsuario: {data['usr']}\nApp: {L.APP_NAMES[data['app']]}\n"
            f"Dispositivo: {data['dev']}\nPlan: {L.PLANS[data['plan']][0]}{period}\n"
            f"Emitida: {time.strftime('%d/%m/%Y %H:%M', time.localtime(data['iat']))}\n"
            f"Vence: {data.get('end_date') or time.strftime('%d/%m/%Y %H:%M', time.localtime(data['exp']))}\nSerie: {data['sn']}")


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


def operator_name() -> str:
    """Quién emite desde la consola o la ventana de escritorio (queda en el historial)."""
    try:
        return os.environ.get("IPV_KEYGEN_USER") or getpass.getuser()
    except (KeyError, OSError):  # contenedores sin entrada de usuario
        return "consola"


def cmd_emit(args) -> None:
    d = load_private_key(ask_passphrase())
    plan = args.plan.upper()
    _token, reply = emit(d, args.usuario, args.codigo, plan, args.desde, args.hasta, args.precio_usd,
                         contact=args.contacto or "", notes=args.notas or "", paid=args.pagada,
                         pay_method=args.metodo_pago or "", renewed_from=args.renueva or "",
                         created_by=operator_name(), source="cli")
    app = L.parse_request_code(args.codigo)[0]
    print(reply)
    if plan == "PX":
        print(f"\nPrecio acordado: {price_usd(app, plan, args.precio_usd)} USD = "
              f"{fmt_cup(float(price_usd(app, plan, args.precio_usd)) * rates()['USD'])} CUP")
    else:
        print("\nPrecio:", price_line(app, plan))


def cmd_verify(args) -> None:
    print(describe(args.licencia, current_public()))


def cmd_historial(args) -> None:
    conn = H.connect()
    try:
        H.init(conn)
        if args.importar:
            with conn:
                res = import_legacy(conn)
            print("Registro antiguo:", "no encontrado" if not res["found"] else
                  f"{res['imported']} importadas, {res['skipped']} ya estaban, {res['invalid']} no válidas")
        filtros = {"q": args.buscar or "", "state": args.estado or "", "plan": args.plan or ""}
        if args.csv:
            Path(args.csv).write_text(H.export_csv(conn, filtros), encoding="utf-8")
            print("Historial exportado a", args.csv)
            return
        page = H.query(conn, {**filtros, "limit": 200})
        print(f"{'Serie':<9} {'Emitida':<11} {'Cliente':<28} {'App':<4} {'Plan':<4} {'Estado':<11} {'Vence':<11} USD")
        for it in page["items"]:
            vence = it["valid_until"] or time.strftime("%Y-%m-%d", time.gmtime(it["expires_at"]))
            print(f"{it['serial']:<9} {it['created_at'][:10]:<11} {it['customer'][:27]:<28} {it['app']:<4} "
                  f"{it['plan']:<4} {it['state_label']:<11} {vence:<11} {it['price_usd']:g}")
        print(f"\n{page['total']} licencia(s)" + (" (se muestran las 200 más recientes; use --csv para todas)"
                                                  if page["total"] > 200 else ""))
    finally:
        conn.close()


def cmd_web(args) -> None:
    try:
        from keygen import webapp
    except ImportError:  # pragma: no cover - ejecutado como script
        import webapp
    webapp.serve(host=args.host, port=args.port, open_browser=not args.no_navegador)


def cmd_gui(_args) -> None:
    run_gui()


def cmd_prices(_args) -> None:
    r = rates()
    print("Tasas (CUP): " + ", ".join(f"1 {k} = {v}" for k, v in r.items()))
    for app in (L.APP_WEB, L.APP_ANDROID):
        print(f"\n{L.APP_NAMES[app]}")
        for plan, (name, days, *_rest) in L.PLANS.items():
            if plan == "PX":
                print(f"  {plan}  {name}: precio acordado manualmente por el proveedor")
            else:
                print(f"  {plan}  {name:<9} ({days:>3} días): {price_line(app, plan)}")


# ------------------------------------------------------------ GUI -------------
def run_gui() -> None:
    import tkinter as tk
    from tkinter import messagebox, simpledialog, ttk

    root = tk.Tk()
    root.title("IPV Keygen — Licencias")
    root.geometry("820x740")
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
    start_var, end_var, custom_price_var = tk.StringVar(), tk.StringVar(), tk.StringVar()
    price_var = tk.StringVar(value="")
    ttk.Label(frm, text="Usuario:").grid(row=2, column=0, sticky="w")
    ttk.Entry(frm, textvariable=user_var, width=60).grid(row=2, column=1, sticky="we", pady=4)
    ttk.Label(frm, text="ID Dispositivo (código):").grid(row=3, column=0, sticky="w")
    ttk.Entry(frm, textvariable=code_var, width=60).grid(row=3, column=1, sticky="we", pady=4)
    ttk.Label(frm, text="Plan:").grid(row=4, column=0, sticky="w")
    plans = [f"{k} — {v[0]}" for k, v in L.PLANS.items()]
    ttk.Combobox(frm, textvariable=plan_var, values=plans, state="readonly", width=28).grid(row=4, column=1, sticky="w", pady=4)
    ttk.Label(frm, text="Desde / Hasta / USD (solo PX):").grid(row=5, column=0, sticky="w")
    date_fields = ttk.Frame(frm)
    date_fields.grid(row=5, column=1, sticky="w", pady=4)
    for label_text, variable, width in (("Desde · AAAA-MM-DD", start_var, 13),
                                        ("Hasta · AAAA-MM-DD", end_var, 13),
                                        ("Precio USD", custom_price_var, 10)):
        cell = ttk.Frame(date_fields)
        cell.pack(side="left", padx=(0, 7))
        ttk.Label(cell, text=label_text).pack(anchor="w")
        ttk.Entry(cell, textvariable=variable, width=width).pack(anchor="w")
    tk.Label(frm, textvariable=price_var, bg="#0f172a", fg="#fbbf24", wraplength=700, justify="left").grid(row=6, column=0, columnspan=2, sticky="w", pady=6)
    out = tk.Text(frm, height=16, bg="#1e293b", fg="#f8fafc", insertbackground="white", wrap="word", relief="flat")
    out.grid(row=8, column=0, columnspan=2, sticky="nsew", pady=8)
    frm.columnconfigure(1, weight=1)
    frm.rowconfigure(8, weight=1)

    def update_price(*_a):
        try:
            app = L.parse_request_code(code_var.get())[0]
            selected_plan = plan_var.get()[:2]
            if selected_plan == "PX":
                price = custom_price_var.get().strip() or "—"
                period = f"{start_var.get() or 'AAAA-MM-DD'} hasta {end_var.get() or 'AAAA-MM-DD'}"
                price_var.set(f"{L.APP_NAMES[app]} · período {period} UTC · precio acordado {price} USD")
            else:
                price_var.set(f"{L.APP_NAMES[app]} · {price_line(app, selected_plan)}")
        except ValueError:
            price_var.set("Pegue el código de solicitud recibido por WhatsApp (IPVW-… para PC, IPVA-… para móvil).")

    code_var.trace_add("write", update_price)
    plan_var.trace_add("write", update_price)
    start_var.trace_add("write", update_price)
    end_var.trace_add("write", update_price)
    custom_price_var.trace_add("write", update_price)
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
            selected_plan = plan_var.get()[:2]
            custom = selected_plan == "PX"
            _token, reply = emit(d, user_var.get(), code_var.get(), selected_plan,
                                 (start_var.get().strip() or None) if custom else None,
                                 (end_var.get().strip() or None) if custom else None,
                                 (custom_price_var.get().strip() or None) if custom else None,
                                 created_by=operator_name(), source="gui")
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
    p.add_argument("--desde", help="inicio inclusivo AAAA-MM-DD (obligatorio para PX; UTC)")
    p.add_argument("--hasta", help="fin inclusivo AAAA-MM-DD (obligatorio para PX; UTC)")
    p.add_argument("--precio-usd", help="precio acordado manualmente para PX")
    p.add_argument("--contacto", help="teléfono o correo del cliente (queda en el historial)")
    p.add_argument("--notas", help="notas internas (quedan en el historial)")
    p.add_argument("--pagada", action="store_true", help="marcar la licencia como cobrada")
    p.add_argument("--metodo-pago", help="efectivo, transferencia, Zelle…")
    p.add_argument("--renueva", help="serie de la licencia que esta renueva")
    p = sub.add_parser("verificar", help="comprobar una licencia")
    p.add_argument("--licencia", required=True)
    sub.add_parser("precios", help="tabla de precios en USD/CUP")
    p = sub.add_parser("web", help="Keygen Web: panel visual con historial, roles y 2FA (por defecto)")
    p.add_argument("--host", default="127.0.0.1", help="dirección de escucha (por defecto solo este equipo)")
    p.add_argument("--port", type=int, default=8500)
    p.add_argument("--no-navegador", action="store_true", help="no abrir el navegador automáticamente")
    sub.add_parser("gui", help="ventana de escritorio (Tk)")
    p = sub.add_parser("historial", help="consultar, exportar o importar el historial de licencias")
    p.add_argument("--buscar", help="texto: cliente, serie, código…")
    p.add_argument("--estado", choices=list(H.STATES))
    p.add_argument("--plan", choices=[k for k in L.PLANS] + [k.lower() for k in L.PLANS])
    p.add_argument("--csv", help="guardar el historial en este archivo CSV")
    p.add_argument("--importar", action="store_true", help="importar antes registro_licencias.csv")
    args = ap.parse_args(argv)
    try:
        if args.cmd is None:  # sin argumentos: el Keygen Web
            return cmd_web(argparse.Namespace(host="127.0.0.1", port=8500, no_navegador=False))
        {"init": cmd_init, "emitir": cmd_emit, "verificar": cmd_verify, "precios": cmd_prices,
         "web": cmd_web, "gui": cmd_gui, "historial": cmd_historial}[args.cmd](args)
    except ValueError as exc:
        raise SystemExit(f"Error: {exc}") from exc


if __name__ == "__main__":
    main()
