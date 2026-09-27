import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import server


class ApiWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        server.DB_PATH = Path(cls.temp_dir.name) / "workflow.db"
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

    def test_product_to_ficha_to_validated_control(self):
        status, product = self.request("POST", "/api/products", {
            "code": "TEST-01", "name": "Producto de prueba", "category": "Bebidas", "unit": "copa"
        })
        self.assertEqual(status, 201)

        status, material = self.request("POST", "/api/materials", {
            "code": "TEST-INS-01", "name": "Insumo de prueba", "unit": "kg", "unit_price": "12.50"
        })
        self.assertEqual(status, 201)

        status, ficha = self.request("POST", "/api/fichas", {
            "product_id": product["id"], "valid_from": "2026-09-27",
            "items": [{"material_id": material["id"], "quantity": "2"}]
        })
        self.assertEqual(status, 201)
        self.assertEqual(ficha["total_cost"], "25.00")
        self.assertEqual(ficha["status"], "Borrador")

        status, ficha = self.request("POST", f"/api/fichas/{ficha['id']}/approve", {})
        self.assertEqual(status, 200)
        self.assertEqual(ficha["status"], "Aprobada")

        status, control = self.request("POST", "/api/controls", {
            "ficha_id": ficha["id"], "period": "2026-09"
        })
        self.assertEqual(status, 201)
        self.assertEqual(control["snapshot_total"], "25.00")

        status, control = self.request("POST", f"/api/controls/{control['id']}/validate", {})
        self.assertEqual(status, 200)
        self.assertEqual(control["status"], "Validado")
        self.assertEqual(control["checked_total"], "25.00")

    def test_health_reports_sqlite(self):
        status, response = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(response["database"], "SQLite")


if __name__ == "__main__":
    unittest.main()
