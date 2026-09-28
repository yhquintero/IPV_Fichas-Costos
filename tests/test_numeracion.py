"""Pruebas de la columna «Id» (numeración de los ítems).

Cada listado —web, exportaciones CSV y aplicación Android— numera sus filas de
1 a N delante del resto de las columnas, de modo que el último número diga
cuántos ítems hay.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
KOTLIN = ROOT / "android" / "app" / "src" / "main" / "java" / "cu" / "ipvcostos" / "app" / "MainActivity.kt"


class ColumnaIdWebTest(unittest.TestCase):
    """La web numera todas las tablas."""

    @classmethod
    def setUpClass(cls):
        cls.app = (WEB / "app.js").read_text(encoding="utf-8")
        cls.enterprise = (WEB / "enterprise.js").read_text(encoding="utf-8")
        cls.css = (WEB / "styles.css").read_text(encoding="utf-8")

    def test_ayudantes_definidos(self):
        self.assertIn("function idTh()", self.app)
        self.assertIn("function idTd(i, realId)", self.app)
        self.assertIn("function countPill(", self.app)
        self.assertIn('class="row-id-h"', self.app)
        self.assertIn('class="row-id"', self.app)

    def test_toda_cabecera_empieza_por_id(self):
        for nombre, fuente in (("app.js", self.app), ("enterprise.js", self.enterprise)):
            cabeceras = re.findall(r"<thead>\s*<tr>\s*(.{0,12})", fuente)
            self.assertTrue(cabeceras, f"{nombre}: no se encontró ninguna tabla")
            for pos, inicio in enumerate(cabeceras, 1):
                self.assertTrue(
                    inicio.startswith("${idTh()}"),
                    f"{nombre}: la tabla #{pos} no empieza por la columna Id ({inicio!r})",
                )

    def test_cada_cabecera_tiene_su_celda(self):
        for nombre, fuente in (("app.js", self.app), ("enterprise.js", self.enterprise)):
            cabeceras = fuente.count("${idTh()}")
            celdas = len(re.findall(r"\$\{idTd\(", fuente))
            self.assertGreaterEqual(celdas, cabeceras, f"{nombre}: faltan celdas de Id")

    def test_listados_sin_tabla_tambien_se_numeran(self):
        self.assertIn('class="trash-index"', self.app)   # papelera
        self.assertIn('class="line-num"', self.app)      # componentes de una ficha

    def test_contadores_en_las_barras_de_herramientas(self):
        for etiqueta in ("'productos'", "'valores'", "'ítems'", "'fichas'", "'controles'", "'elementos'"):
            self.assertIn(f"countPill(rows.length, ", self.app)
            self.assertIn(etiqueta, self.app, f"falta el contador de {etiqueta}")

    def test_csv_exporta_el_id(self):
        cabeceras = re.findall(r"rows = \[\[([^\]]+)\]", self.app)
        self.assertEqual(len(cabeceras), 5, "se esperaban cinco exportaciones CSV")
        for cab in cabeceras:
            self.assertTrue(cab.startswith("'Id'"), f"CSV sin columna Id: {cab[:60]}")

    def test_estilos_de_la_columna(self):
        self.assertIn(".row-id", self.css)
        self.assertIn(".count-pill", self.css)
        self.assertIn(".trash-index", self.css)
        self.assertIn(".line-num", self.css)


class ColumnaIdAndroidTest(unittest.TestCase):
    """La aplicación móvil numera las tarjetas igual que la web."""

    @classmethod
    def setUpClass(cls):
        cls.src = KOTLIN.read_text(encoding="utf-8")

    def test_card_admite_indice(self):
        self.assertIn("private fun card(title: String, subtitle: String, index: Int = 0)", self.src)
        self.assertIn('label(if (index > 0) "$index.  $title" else title', self.src)

    def test_todas_las_tarjetas_llevan_id(self):
        lineas = self.src.splitlines()
        llamadas = 0
        for n, linea in enumerate(lineas):
            if "card(" not in linea or "private fun card(" in linea:
                continue
            llamadas += 1
            sentencia = linea
            if linea.rstrip().endswith(","):
                sentencia += lineas[n + 1]
            self.assertIn("i + 1", sentencia, f"card() sin Id en la línea {n + 1}")
        self.assertGreaterEqual(llamadas, 7, "faltan listados por numerar")

    def test_contador_de_items(self):
        self.assertIn("private fun addCount(parent: LinearLayout, total: Int, label: String)", self.src)
        for etiqueta in ('"productos"', '"valores"', '"fichas"', '"ítems"', '"controles"', '"elementos"'):
            self.assertIn(f"addCount(content, ", self.src)
            self.assertIn(etiqueta, self.src, f"falta el contador de {etiqueta}")


if __name__ == "__main__":
    unittest.main()
