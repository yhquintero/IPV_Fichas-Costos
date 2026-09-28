"""CRUD de valores del IPV, inventario, rendimiento y papelera."""
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import server


class CrudAndInventoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        server.DB_PATH = Path(cls.temp_dir.name) / "crud.db"
        server.init_db()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=2)
        cls.temp_dir.cleanup()

    def request(self, method, path, body=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.base + path, data=data,
                                     headers={"Content-Type": "application/json"}, method=method)
        try:
            with urllib.request.urlopen(req) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def test_demo_catalog_is_seeded(self):
        status, materials = self.request("GET", "/api/materials")
        self.assertEqual(status, 200)
        self.assertGreaterEqual(len(materials), 100)
        cats = {m["category"] for m in materials}
        self.assertIn("Licores", cats)
        status, products = self.request("GET", "/api/products")
        self.assertGreaterEqual(len(products), 20)
        self.assertTrue(any(p["category"] == "Comidas" for p in products))
        self.assertTrue(any(p["category"] == "Bebidas" for p in products))

    def test_material_crud_and_stock(self):
        status, created = self.request("POST", "/api/materials", {
            "code": "LIC-TEST", "name": "Ron de prueba", "unit": "L",
            "category": "Licores", "unit_price": "1500", "stock": "10", "min_stock": "2",
        })
        self.assertEqual(status, 201, created)
        ident = created["id"]
        self.assertEqual(created["stock"], "10")
        self.assertEqual(created["category"], "Licores")

        status, updated = self.request("PUT", f"/api/materials/{ident}", {
            "name": "Ron de prueba añejo", "unit_price": "1800", "stock": "8",
        })
        self.assertEqual(status, 200, updated)
        self.assertEqual(updated["name"], "Ron de prueba añejo")
        self.assertEqual(updated["unit_price"], "1800.00")

        status, stock = self.request("POST", f"/api/materials/{ident}/stock", {"delta": "-3"})
        self.assertEqual(status, 200, stock)
        self.assertEqual(stock["stock"], "5")

        status, err = self.request("POST", f"/api/materials/{ident}/stock", {"delta": "-99"})
        self.assertEqual(status, 409)

        status, detail = self.request("GET", f"/api/materials/{ident}")
        self.assertEqual(status, 200)
        self.assertIn("used_by", detail)
        self.assertIn("stock_value", detail)

        status, _ = self.request("DELETE", f"/api/materials/{ident}")
        self.assertEqual(status, 200)
        mats = {m["id"] for m in self.request("GET", "/api/materials")[1]}
        self.assertNotIn(ident, mats)
        trash = self.request("GET", "/api/trash")[1]["items"]
        self.assertTrue(any(t["id"] == ident and t["kind"] == "materials" for t in trash))

        status, restored = self.request("POST", f"/api/trash/materials/{ident}/restore", {})
        self.assertEqual(status, 200, restored)
        mats = {m["id"]: m for m in self.request("GET", "/api/materials")[1]}
        self.assertEqual(mats[ident]["status"], "Vigente")

        self.request("DELETE", f"/api/materials/{ident}")
        status, purged = self.request("DELETE", f"/api/trash/materials/{ident}")
        self.assertEqual(status, 200, purged)
        trash = self.request("GET", "/api/trash")[1]["items"]
        self.assertFalse(any(t["id"] == ident and t["kind"] == "materials" for t in trash))

    def test_ficha_yield_and_servings_from_stock(self):
        product = self.request("POST", "/api/products", {
            "code": "COM-TEST", "name": "Plato de prueba", "category": "Comidas",
            "unit": "ración", "yield_qty": "10", "yield_unit": "comensales",
        })[1]
        material = self.request("POST", "/api/materials", {
            "code": "INS-TEST", "name": "Arroz de prueba", "unit": "kg",
            "category": "Granos y básicos", "unit_price": "100", "stock": "5",
        })[1]
        status, ficha = self.request("POST", "/api/fichas", {
            "product_id": product["id"], "yield_qty": "10", "yield_unit": "comensales",
            "items": [{"material_id": material["id"], "quantity": "2"}],
        })
        self.assertEqual(status, 201, ficha)
        self.assertEqual(ficha["total_cost"], "200.00")
        self.assertEqual(ficha["yield_qty"], "10")
        self.assertEqual(ficha["cost_per_serving"], "20.00")
        # 5 kg / (2 kg / 10 comensales) = 25 comensales
        self.assertEqual(ficha["servings_from_stock"], 25)

        status, listed = self.request("GET", "/api/fichas")
        self.assertEqual(status, 200)
        row = next(f for f in listed if f["id"] == ficha["id"])
        self.assertEqual(row["cost_per_serving"], "20.00")
        self.assertEqual(row["servings_from_stock"], 25)

    def test_inventory_and_demo_seed_idempotent(self):
        status, inv = self.request("GET", "/api/inventory")
        self.assertEqual(status, 200)
        self.assertIn("totals", inv)
        self.assertGreaterEqual(inv["totals"]["materials"], 100)
        self.assertTrue(any("used_by" in item for item in inv["items"]))

        status, first = self.request("POST", "/api/demo/seed", {})
        self.assertEqual(status, 200)
        self.assertEqual(first["materials"], 0)
        self.assertEqual(first["products"], 0)

    def test_product_update_and_trash(self):
        product = self.request("POST", "/api/products", {
            "code": "BEB-TEST", "name": "Cóctel de prueba", "category": "Bebidas",
            "yield_qty": "12", "yield_unit": "copas",
        })[1]
        status, updated = self.request("PUT", f"/api/products/{product['id']}", {
            "name": "Cóctel especial", "yield_qty": "15",
        })
        self.assertEqual(status, 200)
        self.assertEqual(updated["name"], "Cóctel especial")
        self.assertEqual(updated["yield_qty"], "15")
        status, _ = self.request("DELETE", f"/api/products/{product['id']}")
        self.assertEqual(status, 200)
        status, _ = self.request("POST", f"/api/products/{product['id']}/restore", {})
        self.assertEqual(status, 200)
        products = {p["id"]: p for p in self.request("GET", "/api/products")[1]}
        self.assertEqual(products[product["id"]]["active"], 1)
