"""Sistema de Seguridad por Usuarios: permisos finos por módulo.

Cubre la entrada única «Valores del IPV» (pestañas Valores e Inventario):
quién puede abrirla, quién puede modificarla y quién puede ver los precios.
"""
import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import auth
import dbcrypt
import permisos
import rate_limiter
import server

ADMIN = ("jefe@ipv.cu", "Admin#2026seguro")
EDITOR = ("editor@ipv.cu", "Editor#2026seguro")
LECTOR = ("lector@ipv.cu", "Lector#2026seguro")
ALMACEN = ("almacen@ipv.cu", "Almacen#2026seguro")


def ajustes_almacen() -> dict:
    """Almacén: solo Valores del IPV, con existencias pero sin precios."""
    sin_acceso = {m: {"view": False, "edit": False, "costs": False} for m in permisos.MODULES}
    sin_acceso["materials"] = {"view": True, "edit": True, "costs": False}
    return sin_acceso


class PermisosAPITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        server.DB_PATH = Path(cls.temp_dir.name) / "permisos.db"
        server.init_db()
        auth.JWT_SECRET = "permisos-test-" + "z" * 32
        auth.JWT_ENABLED = True
        with server.connect() as conn:
            for email, nombre, rol, clave in (
                (ADMIN[0], "Jefe", "admin", ADMIN[1]),
                (EDITOR[0], "Editor", "editor", EDITOR[1]),
                (LECTOR[0], "Lector", "viewer", LECTOR[1]),
                (ALMACEN[0], "Almacén", "editor", ALMACEN[1]),
            ):
                auth.create_user(conn, {"email": email, "name": nombre, "role": rol,
                                        "password": clave}, server.now_iso)
            uid = conn.execute("SELECT id FROM users WHERE email=?", (ALMACEN[0],)).fetchone()[0]
            permisos.set_permissions(conn, uid, "editor", ajustes_almacen(), server.now_iso)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_port}"

    @classmethod
    def tearDownClass(cls):
        auth.JWT_ENABLED = False
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=2)
        cls.temp_dir.cleanup()

    def setUp(self):
        rate_limiter._hits.clear()

    def req(self, method, path, body=None, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(r) as resp:
                return resp.status, json.loads(resp.read()), dict(resp.headers)
        except urllib.error.HTTPError as err:
            raw = err.read()
            try:
                return err.code, json.loads(raw), dict(err.headers)
            except json.JSONDecodeError:
                return err.code, {"raw": raw.decode(errors="replace")}, dict(err.headers)

    def login(self, email, password):
        status, data = self.req("POST", "/api/auth/login", {"email": email, "password": password})[:2]
        self.assertEqual(status, 200, data)
        return data

    def token(self, cuenta):
        return self.login(*cuenta)["access_token"]

    def user_id(self, email):
        with server.connect() as conn:
            return conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()[0]

    # ---------------- Permisos por defecto según el rol ----------------
    def test_login_devuelve_permisos_por_modulo(self):
        lector = self.login(*LECTOR)
        self.assertEqual(lector["permissions"]["materials"], {"view": True, "edit": False, "costs": False})
        self.assertTrue(lector["permissions"]["fichas"]["view"])
        editor = self.login(*EDITOR)
        self.assertEqual(editor["permissions"]["materials"], {"view": True, "edit": True, "costs": True})
        jefe = self.login(*ADMIN)
        self.assertTrue(all(p["edit"] for p in jefe["permissions"].values()))
        # /api/auth/me repite los permisos para que la web adapte el menú
        status, me = self.req("GET", "/api/auth/me", token=lector["access_token"])[:2]
        self.assertEqual(status, 200)
        self.assertFalse(me["permissions"]["materials"]["costs"])
        self.assertEqual(me["user"]["permissions"], me["permissions"])

    def test_admin_no_puede_ser_limitado(self):
        jefe = self.token(ADMIN)
        status, err = self.req("PUT", f"/api/users/{self.user_id(ADMIN[0])}",
                               {"permissions": {"materials": {"view": False}}}, token=jefe)[:2]
        self.assertEqual(status, 400)
        self.assertIn("administradores", err["error"].lower())
        # Y sigue viendo los precios aunque alguien escriba la fila a mano
        with server.connect() as conn:
            conn.execute("INSERT OR REPLACE INTO user_permissions(user_id,module,can_view,can_edit,can_costs) "
                         "VALUES(?, 'materials', 0, 0, 0)", (self.user_id(ADMIN[0]),))
        status, materials = self.req("GET", "/api/materials", token=jefe)[:2]
        self.assertEqual(status, 200)
        self.assertIsNotNone(materials[0]["unit_price"])

    # ---------------- Consulta sin costos: el servidor no los envía ----------------
    def test_lector_ve_inventario_sin_precios(self):
        lector = self.token(LECTOR)
        status, inv = self.req("GET", "/api/inventory", token=lector)[:2]
        self.assertEqual(status, 200)
        self.assertGreater(len(inv["items"]), 0)
        self.assertTrue(inv["costs_hidden"])
        self.assertIsNone(inv["totals"]["stock_value"])
        for item in inv["items"]:
            self.assertIsNone(item["unit_price"], item["name"])
            self.assertIsNone(item["stock_value"], item["name"])
            self.assertIsNotNone(item["stock"])       # las existencias sí se ven
            self.assertIn("used_by", item)             # y las recetas que lo usan
        status, materials = self.req("GET", "/api/materials", token=lector)[:2]
        self.assertTrue(all(m["unit_price"] is None for m in materials))
        status, detalle = self.req("GET", f"/api/materials/{materials[0]['id']}", token=lector)[:2]
        self.assertEqual(status, 200)
        self.assertIsNone(detalle["unit_price"])
        self.assertIsNone(detalle["stock_value"])
        status, panel = self.req("GET", "/api/dashboard", token=lector)[:2]
        self.assertIsNone(panel["stock_value"])
        status, reporte = self.req("GET", "/api/report/materials_inventory", token=lector)[:2]
        self.assertEqual(status, 200)
        self.assertTrue(all(r["unit_price"] is None for r in reporte["data"]))

    def test_editor_si_recibe_precios(self):
        editor = self.token(EDITOR)
        status, inv = self.req("GET", "/api/inventory", token=editor)[:2]
        self.assertEqual(status, 200)
        self.assertNotIn("costs_hidden", inv)
        self.assertIsNotNone(inv["totals"]["stock_value"])
        self.assertTrue(all(m["unit_price"] is not None for m in inv["items"]))
        status, materials = self.req("GET", "/api/materials", token=editor)[:2]
        self.assertTrue(all(m["unit_price"] is not None for m in materials))

    def test_lector_no_modifica_valores_ni_existencias(self):
        lector = self.token(LECTOR)
        self.assertEqual(self.req("POST", "/api/materials", {"code": "X-1", "name": "X", "unit": "kg",
                                                             "category": "Insumos", "unit_price": "5"},
                                  token=lector)[0], 403)
        self.assertEqual(self.req("POST", "/api/materials/1/stock", {"set": "9"}, token=lector)[0], 403)
        self.assertEqual(self.req("PUT", "/api/materials/1", {"name": "Otro"}, token=lector)[0], 403)
        self.assertEqual(self.req("DELETE", "/api/materials/1", {}, token=lector)[0], 403)

    # ---------------- Ajustes por usuario, con efecto inmediato ----------------
    def test_admin_quita_edicion_y_costos_a_un_editor(self):
        jefe = self.token(ADMIN)
        editor_token = self.token(EDITOR)  # sesión abierta antes del cambio
        uid = self.user_id(EDITOR[0])
        status, guardado = self.req("PUT", f"/api/users/{uid}",
                                    {"permissions": {"materials": {"view": True, "edit": False, "costs": False}}},
                                    token=jefe)[:2]
        self.assertEqual(status, 200, guardado)
        self.assertFalse(guardado["permissions"]["materials"]["edit"])
        # Sin volver a iniciar sesión: el editor ya no ve precios ni puede escribir
        status, materials = self.req("GET", "/api/materials", token=editor_token)[:2]
        self.assertEqual(status, 200)
        self.assertTrue(all(m["unit_price"] is None for m in materials))
        status, err = self.req("POST", "/api/materials/1/stock", {"set": "9"}, token=editor_token)[:2]
        self.assertEqual(status, 403)
        self.assertEqual(err["permission_denied"], "materials.edit")
        self.assertIn("permiso", err["error"].lower())
        # La lista de usuarios informa de los permisos efectivos
        usuarios = self.req("GET", "/api/users", token=jefe)[1]
        editor = next(u for u in usuarios if u["id"] == uid)
        self.assertFalse(editor["permissions"]["materials"]["edit"])
        # Restablecer según el rol devuelve la edición y los precios
        status, _ = self.req("PUT", f"/api/users/{uid}", {"reset_permissions": True}, token=jefe)[:2]
        self.assertEqual(status, 200)
        status, materials = self.req("GET", "/api/materials", token=editor_token)[:2]
        self.assertTrue(all(m["unit_price"] is not None for m in materials))
        status, _ = self.req("POST", "/api/materials/1/stock", {"set": "9"}, token=editor_token)[:2]
        self.assertEqual(status, 200)
        # Auditoría del cambio de permisos y de los accesos denegados
        eventos = self.req("GET", "/api/audit?action=UPDATE_USER_PERMISSIONS&limit=20", token=jefe)[1]
        self.assertGreaterEqual(eventos["total"], 1)
        denegados = self.req("GET", "/api/audit?action=PERMISSION_DENIED&limit=20", token=jefe)[1]
        self.assertGreaterEqual(denegados["total"], 1)
        self.assertIn("materials.edit", denegados["entries"][0]["details"])

    def test_sin_permiso_de_vista_desaparece_la_entrada(self):
        jefe = self.token(ADMIN)
        uid = self.user_id(EDITOR[0])
        self.req("PUT", f"/api/users/{uid}", {"permissions": {"materials": {"view": False}}}, token=jefe)
        editor = self.token(EDITOR)
        for ruta in ("/api/materials", "/api/inventory", "/api/materials/1", "/api/report/materials_inventory"):
            status, err = self.req("GET", ruta, token=editor)[:2]
            self.assertEqual(status, 403, ruta)
            self.assertIn("permiso", err["error"].lower())
        # Ni la búsqueda global ni la papelera revelan los valores del IPV
        resultados = self.req("GET", "/api/search?q=ron&limit=20", token=editor)[1]
        self.assertFalse(any(r["type"] == "material" for r in resultados))
        papelera = self.req("GET", "/api/trash", token=editor)[1]
        self.assertFalse(any(t["kind"] == "materials" for t in papelera["items"]))
        categorias = self.req("GET", "/api/categories", token=editor)[1]
        self.assertNotIn("materials", categorias)
        self.assertIn("products", categorias)
        self.req("PUT", f"/api/users/{uid}", {"reset_permissions": True}, token=jefe)

    def test_usuario_de_almacen_solo_entra_a_valores_del_ipv(self):
        almacen = self.token(ALMACEN)
        self.assertEqual(self.req("GET", "/api/products", token=almacen)[0], 403)
        self.assertEqual(self.req("GET", "/api/fichas", token=almacen)[0], 403)
        self.assertEqual(self.req("GET", "/api/controls", token=almacen)[0], 403)
        status, materials = self.req("GET", "/api/materials", token=almacen)[:2]
        self.assertEqual(status, 200)
        self.assertTrue(all(m["unit_price"] is None for m in materials))
        # Puede mover existencias, que es su trabajo, sin ver el dinero
        status, movido = self.req("POST", "/api/materials/1/stock", {"set": "12"}, token=almacen)[:2]
        self.assertEqual(status, 200, movido)
        self.assertEqual(movido["stock"], "12")
        self.assertIsNone(movido.get("unit_price"))
        # Los datos de prueba escriben en varios apartados: se rechazan
        status, err = self.req("POST", "/api/demo/seed", {}, token=almacen)[:2]
        self.assertEqual(status, 403)
        self.assertIn("edición", err["error"])
        self.assertTrue(err["permission_denied"].startswith("seed:"))

    def test_almacen_no_puede_escribir_precios_ni_moneda(self):
        almacen, jefe = self.token(ALMACEN), self.token(ADMIN)
        base = {"code": "SEC-ALM-001", "name": "Prueba de existencias", "unit": "kg",
                "category": "Insumos", "stock": "3"}
        try:
            for field, value in (("unit_price", "10"), ("currency", "USD")):
                status, _ = self.req("POST", "/api/materials", {**base, field: value}, token=almacen)[:2]
                self.assertEqual(status, 403, field)
            status, material = self.req("POST", "/api/materials", base, token=almacen)[:2]
            self.assertEqual(status, 201, material)
            ident = material["id"]
            self.assertIsNone(material["unit_price"])
            for field, value in (("unit_price", "25"), ("currency", "EUR")):
                status, _ = self.req("PUT", f"/api/materials/{ident}", {field: value}, token=almacen)[:2]
                self.assertEqual(status, 403, field)
            status, _ = self.req("PUT", f"/api/materials/{ident}", {"name": "Nueva etiqueta"}, token=almacen)[:2]
            self.assertEqual(status, 200)
            status, denied = self.req("POST", "/api/materials/bulk-update",
                                      {"updates": [{"id": ident, "unit_price": "99"}]}, token=almacen)[:2]
            self.assertEqual(status, 403, denied)
            self.assertEqual(denied["permission_denied"], "materials.costs")
            updated = self.req("GET", f"/api/materials/{ident}", token=jefe)[1]
            self.assertEqual(updated["name"], "Nueva etiqueta")
            self.assertEqual(float(updated["unit_price"]), 0)
        finally:
            with server.connect() as conn:
                row = conn.execute("SELECT id FROM materials WHERE code=?", (base["code"],)).fetchone()
            if row:
                self.req("DELETE", f"/api/materials/{row['id']}", token=jefe)
                self.req("DELETE", f"/api/trash/materials/{row['id']}", token=jefe)

    def test_papelera_requiere_permiso_propio_y_de_cada_modulo(self):
        jefe, editor = self.token(ADMIN), self.token(EDITOR)
        uid = self.user_id(EDITOR[0])
        code = "SEC-TRASH-001"
        try:
            status, material = self.req("POST", "/api/materials",
                                        {"code": code, "name": "Temporal", "unit": "kg", "category": "Insumos",
                                         "unit_price": "7"}, token=jefe)[:2]
            self.assertEqual(status, 201, material)
            ident = material["id"]
            self.assertEqual(self.req("DELETE", f"/api/materials/{ident}", token=jefe)[0], 200)
            self.req("PUT", f"/api/users/{uid}", {"permissions": {"trash": {"edit": False}}}, token=jefe)
            for method, route in (("POST", f"/api/trash/materials/{ident}/restore"),
                                  ("DELETE", f"/api/trash/materials/{ident}"),
                                  ("POST", "/api/trash/empty")):
                status, denied = self.req(method, route, {}, token=editor)[:2]
                self.assertEqual(status, 403, route)
                self.assertEqual(denied["permission_denied"], "trash.edit")
            for kind in ("fichas", "controls"):
                status, denied = self.req("POST", f"/api/{kind}/987654/restore", {}, token=editor)[:2]
                self.assertEqual(status, 403)
                self.assertEqual(denied["permission_denied"], "trash.edit")
            self.req("PUT", f"/api/users/{uid}", {"permissions": {"trash": {"edit": True},
                                                   "materials": {"edit": False}}}, token=jefe)
            for method, route in (("POST", f"/api/trash/materials/{ident}/restore"),
                                  ("DELETE", f"/api/trash/materials/{ident}"),
                                  ("POST", "/api/trash/empty")):
                status, denied = self.req(method, route, {}, token=editor)[:2]
                self.assertEqual(status, 403, route)
                self.assertEqual(denied["permission_denied"], "materials.edit")
            self.req("PUT", f"/api/users/{uid}", {"permissions": {"materials": {"edit": True},
                                                   "controls": {"edit": False}}}, token=jefe)
            status, denied = self.req("POST", "/api/trash/empty", {}, token=editor)[:2]
            self.assertEqual(status, 403)
            self.assertEqual(denied["permission_denied"], "controls.edit")
            self.assertEqual(self.req("POST", f"/api/trash/materials/{ident}/restore", {}, token=editor)[0], 200)
        finally:
            self.req("PUT", f"/api/users/{uid}", {"reset_permissions": True}, token=jefe)
            with server.connect() as conn:
                row = conn.execute("SELECT id FROM materials WHERE code=?", (code,)).fetchone()
            if row:
                self.req("DELETE", f"/api/materials/{row['id']}", token=jefe)
                self.req("DELETE", f"/api/trash/materials/{row['id']}", token=jefe)

    def test_sembrar_datos_requiere_controles(self):
        jefe, editor = self.token(ADMIN), self.token(EDITOR)
        uid = self.user_id(EDITOR[0])
        try:
            self.req("PUT", f"/api/users/{uid}", {"permissions": {"controls": {"edit": False}}}, token=jefe)
            status, denied = self.req("POST", "/api/demo/seed", {}, token=editor)[:2]
            self.assertEqual(status, 403)
            self.assertIn("controls", denied["permission_denied"])
            self.req("PUT", f"/api/users/{uid}", {"permissions": {"controls": {"edit": True},
                                                   "materials": {"costs": False}}}, token=jefe)
            status, denied = self.req("POST", "/api/demo/seed", {}, token=editor)[:2]
            self.assertEqual(status, 403)
            self.assertEqual(denied["permission_denied"], "materials.costs")
        finally:
            self.req("PUT", f"/api/users/{uid}", {"reset_permissions": True}, token=jefe)

    def test_linea_libre_no_permitida_sin_costos_de_fichas(self):
        jefe, editor = self.token(ADMIN), self.token(EDITOR)
        uid = self.user_id(EDITOR[0])
        products = self.req("GET", "/api/products", token=jefe)[1]
        try:
            self.req("PUT", f"/api/users/{uid}", {"permissions": {"fichas": {"costs": False}}}, token=jefe)
            body = {"product_id": products[0]["id"], "items": [
                {"description": "Libre", "unit": "kg", "quantity": "1", "unit_cost": "999"}]}
            status, denied = self.req("POST", "/api/fichas", body, token=editor)[:2]
            self.assertEqual(status, 403, denied)
            self.assertIn("costos", denied["error"])
        finally:
            self.req("PUT", f"/api/users/{uid}", {"reset_permissions": True}, token=jefe)

    def test_resumen_recortado_por_modulo(self):
        """El resumen mezcla apartados: cada usuario ve solo lo que puede consultar."""
        almacen = self.token(ALMACEN)
        status, d = self.req("GET", "/api/dashboard", token=almacen)[:2]
        self.assertEqual(status, 200, d)
        for campo in ("products", "fichas", "approved_fichas", "pending_controls"):
            self.assertIsNone(d[campo], campo)
        self.assertEqual(d["recent_fichas"], [])
        self.assertEqual(d["categories"], [])
        self.assertEqual(d["cost_by_category"], [])
        self.assertIsNone(d["stock_value"])          # valores del IPV sin permiso `costs`
        self.assertIsInstance(d["materials"], int)   # su apartado sí aparece
        tipos = {a["type"] for a in d["activity_timeline"]}
        self.assertFalse(tipos & {"product", "ficha", "control"}, tipos)  # nada de otros apartados
        self.assertEqual(self.req("GET", "/api/statistics", token=almacen)[0], 403)
        self.assertEqual(self.req("GET", "/api/report/fichas_summary", token=almacen)[0], 403)

    def test_resumen_del_lector_oculta_solo_el_dinero_de_valores(self):
        d = self.req("GET", "/api/dashboard", token=self.token(LECTOR))[1]
        self.assertIsNone(d["stock_value"])
        self.assertTrue(d["costs_hidden"])
        self.assertIsInstance(d["products"], int)
        self.assertIsInstance(d["low_stock"], int)   # las existencias no son información económica
        # Las fichas y sus costos sí los puede consultar el rol de consulta
        self.assertTrue(d["recent_fichas"])
        self.assertTrue(all(f["total_cost"] is not None for f in d["recent_fichas"]))
        estadisticas = self.req("GET", "/api/statistics", token=self.token(LECTOR))[1]
        self.assertTrue(estadisticas["top_expensive"][0]["total_cost"])

    def test_sin_costos_en_fichas_se_ocultan_sus_importes(self):
        jefe = self.token(ADMIN)
        uid = self.user_id(EDITOR[0])
        self.req("PUT", f"/api/users/{uid}", {"permissions": {"fichas": {"costs": False}}}, token=jefe)
        editor = self.token(EDITOR)
        fichas = self.req("GET", "/api/fichas", token=editor)[1]
        self.assertTrue(fichas)
        self.assertTrue(all(f["total_cost"] is None for f in fichas))
        detalle = self.req("GET", f"/api/fichas/{fichas[0]['id']}", token=editor)[1]
        self.assertIsNone(detalle["total_cost"])
        self.assertTrue(all(i["subtotal"] is None and i["unit_cost"] is None for i in detalle["items"]))
        d = self.req("GET", "/api/dashboard", token=editor)[1]
        self.assertEqual(d["cost_by_category"], [])
        self.assertTrue(all(f["total_cost"] is None for f in d["recent_fichas"]))
        estadisticas = self.req("GET", "/api/statistics", token=editor)[1]
        self.assertTrue(all(t["total_cost"] is None for t in estadisticas["top_expensive"]))
        self.assertTrue(all(a["avg_cost"] is None for a in estadisticas["avg_cost_by_category"]))
        self.req("PUT", f"/api/users/{uid}", {"reset_permissions": True}, token=jefe)

    def test_usuario_nuevo_con_permisos_de_almacen(self):
        jefe = self.token(ADMIN)
        status, creado = self.req("POST", "/api/users", {
            "email": "nuevo@ipv.cu", "name": "Nuevo", "role": "editor", "password": "Nuevo#2026seguro",
            "permissions": {"materials": {"view": True, "edit": True, "costs": False},
                            "products": {"view": False}},
        }, token=jefe)[:2]
        self.assertEqual(status, 201, creado)
        self.assertFalse(creado["permissions"]["materials"]["costs"])
        self.assertFalse(creado["permissions"]["products"]["view"])
        token_nuevo = self.login("nuevo@ipv.cu", "Nuevo#2026seguro")["access_token"]
        self.assertEqual(self.req("GET", "/api/products", token=token_nuevo)[0], 403)
        self.assertEqual(self.req("GET", "/api/inventory", token=token_nuevo)[0], 200)


class PermisosUnitTest(unittest.TestCase):
    """Reglas de rutas y normalización, sin levantar el servidor."""

    def setUp(self):
        # dbcrypt.connect: con IPV_DB_KEY la conexión y `sqlite3.Row` son las de SQLCipher
        self.conn = dbcrypt.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, role TEXT);
                                   INSERT INTO users(id,email,role) VALUES(7,'u@ipv.cu','editor');""")
        permisos.init_permissions(self.conn)

    def test_reglas_por_ruta_y_metodo(self):
        casos = [
            ("/api/materials", "GET", ("materials", "view")),
            ("/api/materials", "POST", ("materials", "edit")),
            ("/api/materials/3", "PUT", ("materials", "edit")),
            ("/api/materials/3", "DELETE", ("materials", "edit")),
            ("/api/materials/3/stock", "POST", ("materials", "edit")),
            ("/api/materials/bulk-update", "POST", ("materials", "edit")),
            ("/api/inventory", "GET", ("materials", "view")),
            ("/api/report/materials_inventory", "GET", ("materials", "view")),
            ("/api/trash/materials/4/restore", "POST", ("materials", "edit")),
            ("/api/trash/materials/4", "DELETE", ("materials", "edit")),
            ("/api/trash", "GET", ("trash", "view")),
            ("/api/trash/empty", "POST", ("trash", "edit")),
            ("/api/products", "GET", ("products", "view")),
            ("/api/fichas/2/approve", "POST", ("fichas", "edit")),
            ("/api/statistics", "GET", ("fichas", "view")),
            ("/api/auth/login", "POST", None),
            ("/api/users", "GET", None),          # lo rige la lista de administradores
            ("/api/health", "GET", None),
            ("/api/materials", "OPTIONS", None),
        ]
        for ruta, metodo, esperado in casos:
            self.assertEqual(permisos.rule_for(ruta, metodo), esperado, f"{metodo} {ruta}")

    def test_editar_y_costos_implican_ver(self):
        permisos.set_permissions(self.conn, 7, "editor",
                                 {"materials": {"view": False, "edit": True, "costs": True}}, server.now_iso)
        self.assertEqual(permisos.effective(self.conn, 7, "editor")["materials"],
                         {"view": False, "edit": False, "costs": False})

    def test_modulos_y_permisos_desconocidos_se_rechazan(self):
        with self.assertRaises(permisos.PermisoError):
            permisos.set_permissions(self.conn, 7, "editor", {"inventario": {"view": True}}, server.now_iso)
        with self.assertRaises(permisos.PermisoError):
            permisos.set_permissions(self.conn, 7, "editor", {"materials": {"borrar": True}}, server.now_iso)
        with self.assertRaises(permisos.PermisoError):
            permisos.set_permissions(self.conn, 7, "admin", {"materials": {"view": True}}, server.now_iso)

    def test_filtrado_de_respuestas(self):
        sin_session = {"materials": [{"id": 1, "unit_price": "10.00"}]}
        self.assertEqual(permisos.filter_response("/api/materials", sin_session, None), sin_session)
        usuario = {"permissions": permisos.defaults_for("viewer")}
        filtrado = permisos.filter_response("/api/materials", [{"id": 1, "unit_price": "10.00", "stock": "3"}], usuario)
        self.assertIsNone(filtrado[0]["unit_price"])
        self.assertEqual(filtrado[0]["stock"], "3")
        self.assertTrue(filtrado[0]["costs_hidden"])
        # Los mensajes de error nunca se modifican
        error = {"error": "No encontrado", "status": 404}
        self.assertEqual(permisos.filter_response("/api/materials/1", error, usuario), error)
        # Búsqueda y papelera: solo los apartados con permiso de vista
        busca = permisos.filter_response("/api/search", [{"type": "material", "id": 1},
                                                         {"type": "ficha", "id": 2}],
                                         {"permissions": {"materials": {"view": False}, "fichas": {"view": True}}})
        self.assertEqual([r["type"] for r in busca], ["ficha"])

    def test_filtrado_del_resumen_por_modulo(self):
        perms = {"products": {"view": False, "edit": False, "costs": False},
                 "fichas": {"view": True, "edit": False, "costs": False},
                 "controls": {"view": True, "edit": False, "costs": True},
                 "materials": {"view": True, "edit": True, "costs": False},
                 "trash": {"view": True, "edit": False, "costs": True}}
        resumen = {"products": 3, "fichas": 5, "approved_fichas": 2, "pending_controls": 1,
                   "materials": 9, "low_stock": 2, "stock_value": "100.00",
                   "recent_fichas": [{"id": 1, "total_cost": "50.00", "status": "Aprobada"}],
                   "categories": [{"category": "Comida", "count": 3}],
                   "cost_by_category": [{"category": "Comida", "total": 50.0}],
                   "activity_timeline": [{"type": "material"}, {"type": "product"}, {"type": "ficha"}]}
        salida = permisos.filter_response("/api/dashboard", resumen, {"permissions": perms})
        self.assertIsNone(salida["products"])
        self.assertIsNone(salida["stock_value"])
        self.assertTrue(salida["costs_hidden"])
        self.assertEqual(salida["categories"], [])
        self.assertEqual(salida["cost_by_category"], [])
        self.assertIsNone(salida["recent_fichas"][0]["total_cost"])
        self.assertEqual(salida["recent_fichas"][0]["status"], "Aprobada")
        self.assertEqual([a["type"] for a in salida["activity_timeline"]], ["material", "ficha"])
        self.assertEqual(salida["fichas"], 5)
        self.assertEqual(salida["materials"], 9)
        # Sin permiso de vista sobre fichas desaparece el panel completo
        sin_fichas = dict(perms, fichas={"view": False, "edit": False, "costs": False})
        salida2 = permisos.filter_response("/api/dashboard", resumen, {"permissions": sin_fichas})
        self.assertEqual(salida2["recent_fichas"], [])
        self.assertIsNone(salida2["fichas"])
        self.assertIsNone(salida2["approved_fichas"])
        # El resumen intacto cuando no hay sesión (servidor abierto)
        self.assertEqual(permisos.filter_response("/api/dashboard", resumen, None), resumen)

    def test_ocultacion_de_importes_en_fichas_y_controles(self):
        sin_costos = {"fichas": {"view": True, "edit": False, "costs": False},
                      "controls": {"view": True, "edit": False, "costs": False}}
        ficha = {"id": 1, "total_cost": "50.00", "version": 2,
                 "items": [{"description": "Ron", "unit_cost": "25.00", "subtotal": "50.00", "quantity": "2"}]}
        salida = permisos.filter_response("/api/fichas/1", ficha, {"permissions": sin_costos})
        self.assertIsNone(salida["total_cost"])
        self.assertIsNone(salida["items"][0]["unit_cost"])
        self.assertIsNone(salida["items"][0]["subtotal"])
        self.assertEqual(salida["items"][0]["description"], "Ron")
        self.assertEqual(salida["version"], 2)
        self.assertTrue(salida["costs_hidden"])
        control = {"code": "C-1", "snapshot_total": "10.00", "checked_total": "10.00", "status": "Validado"}
        oculto = permisos.filter_response("/api/controls/1", control, {"permissions": sin_costos})
        self.assertIsNone(oculto["snapshot_total"])
        self.assertIsNone(oculto["checked_total"])
        self.assertEqual(oculto["status"], "Validado")
        # Con costos permitidos no se toca nada
        con_costos = {"fichas": {"view": True, "edit": True, "costs": True},
                      "controls": {"view": True, "edit": True, "costs": True}}
        self.assertEqual(permisos.filter_response("/api/fichas/1", ficha, {"permissions": con_costos}), ficha)
        # Reportes y analítica siguen el mismo criterio
        reporte = {"type": "fichas_summary", "data": [{"product": "Daiquirí", "total_cost": "30.00"}]}
        self.assertIsNone(permisos.filter_response("/api/report/fichas_summary", reporte,
                                                   {"permissions": sin_costos})["data"][0]["total_cost"])
        estadisticas = {"top_expensive": [{"name": "Daiquirí", "total_cost": "30.00"}],
                        "avg_cost_by_category": [{"category": "Bebidas", "avg_cost": 30.0}]}
        filtradas = permisos.filter_response("/api/statistics", estadisticas, {"permissions": sin_costos})
        self.assertIsNone(filtradas["top_expensive"][0]["total_cost"])
        self.assertIsNone(filtradas["avg_cost_by_category"][0]["avg_cost"])

    def test_mensaje_de_denegacion(self):
        self.assertIn("Valores del IPV e Inventario", permisos.denial_message("materials", "view"))
        self.assertIn("modificar", permisos.denial_message("materials", "edit"))


if __name__ == "__main__":
    unittest.main()
