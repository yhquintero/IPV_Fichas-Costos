"""IPV · Fichas y Costos — Juego de datos de demostración (contenido puro).

Catálogo amplio de valores del IPV, productos, recetas y existencias pensado para
aprender el sistema: comidas con su número de comensales, bebidas con licores de
distinto precio y control de inventario.

Todo se inserta de forma **idempotente** (por código), de modo que puede aplicarse
varias veces sobre la misma base de datos sin duplicar nada.

Autor: Ing. Yosvany Hernández Quintero
"""
from __future__ import annotations

# --------------------------------------------------------------------------- #
#  VALORES DEL IPV  (código, nombre, unidad, categoría, precio, stock, mínimo, proveedor)
# --------------------------------------------------------------------------- #
MATERIALS: list[tuple[str, str, str, str, str, str, str, str]] = [
    # ── Licores ──────────────────────────────────────────────────────────────
    ("LIC-001", "Ron Habana 7 años", "L", "Licores", "4200.00", "6", "2", "Bodega La Row"),
    ("LIC-002", "Ron Matusalem", "L", "Licores", "3600.00", "9", "3", "Bodega La Row"),
    ("LIC-003", "Ron Flor de Caña 7", "L", "Licores", "2650.00", "12", "4", "Distribuidora Nacional"),
    ("LIC-004", "Ron Flor de Caña 5", "L", "Licores", "1980.00", "10", "3", "Distribuidora Nacional"),
    ("LIC-005", "Ron Havana Club 3 años", "L", "Licores", "2450.00", "8", "3", "Bodega La Row"),
    ("LIC-006", "Ron Havana Club 7 años", "L", "Licores", "5400.00", "4", "2", "Bodega La Row"),
    ("LIC-007", "Ron añejo 3 años", "L", "Licores", "1560.00", "18", "6", "Distribuidora Nacional"),
    ("LIC-008", "Ron blanco", "L", "Licores", "1180.00", "14", "5", "Distribuidora Nacional"),
    ("LIC-009", "Ron dorado", "L", "Licores", "1320.00", "12", "4", "Distribuidora Nacional"),
    ("LIC-010", "Ron con miel", "L", "Licores", "980.00", "11", "4", "Distribuidora Nacional"),
    ("LIC-011", "Ron sabor coco", "L", "Licores", "920.00", "9", "3", "Distribuidora Nacional"),
    ("LIC-012", "Ron sabor naranja", "L", "Licores", "860.00", "9", "3", "Distribuidora Nacional"),
    ("LIC-013", "Ron sabor menta", "L", "Licores", "840.00", "8", "3", "Distribuidora Nacional"),
    ("LIC-014", "Brandy Centauro", "L", "Licores", "3350.00", "5", "2", "Bodega La Row"),
    ("LIC-015", "Vodka Moskovsky", "L", "Licores", "2400.00", "7", "2", "Bodega La Row"),
    ("LIC-016", "Gin Beefeater", "L", "Licores", "3600.00", "5", "2", "Bodega La Row"),
    ("LIC-017", "Tequila Olmeca Silver", "L", "Licores", "3450.00", "6", "2", "Distribuidora Nacional"),
    ("LIC-018", "Coñac Hennessy V.S.O.P", "L", "Licores", "9800.00", "3", "1", "Bodega La Row"),
    ("LIC-019", "Whisky Etiqueta Negra", "L", "Licores", "5200.00", "5", "2", "Bodega La Row"),
    ("LIC-020", "Singani", "L", "Licores", "3100.00", "4", "1", "Distribuidora Nacional"),
    ("LIC-021", "Crema de licor", "L", "Licores", "1250.00", "6", "2", "Distribuidora Nacional"),
    ("LIC-022", "Licor de cacao", "L", "Licores", "1450.00", "5", "2", "Distribuidora Nacional"),
    ("LIC-023", "Licor de café", "L", "Licores", "1180.00", "5", "2", "Distribuidora Nacional"),
    ("LIC-024", "Aguardiente de caña", "L", "Licores", "520.00", "20", "8", "Destilería local"),
    # ── Cervezas y vinos ─────────────────────────────────────────────────────
    ("CER-001", "Cerveza pilsener 330 ml", "unidad", "Cervezas", "180.00", "120", "48", "Cervecería Nacional"),
    ("CER-002", "Cerveza lager 500 ml", "unidad", "Cervezas", "120.00", "80", "36", "Cervecería Nacional"),
    ("CER-003", "Cerveza sin alcohol 330 ml", "unidad", "Cervezas", "160.00", "60", "24", "Cervecería Nacional"),
    ("CER-004", "Cerveza artesanal IPA 330 ml", "unidad", "Cervezas", "320.00", "36", "12", "Cerveza Artesanal"),
    ("VIN-001", "Vino tinto selección 750 ml", "unidad", "Vinos", "480.00", "30", "12", "Distribuidora Nacional"),
    ("VIN-002", "Vino blanco selección 750 ml", "unidad", "Vinos", "460.00", "24", "10", "Distribuidora Nacional"),
    ("VIN-003", "Vino rosado 750 ml", "unidad", "Vinos", "430.00", "18", "8", "Distribuidora Nacional"),
    ("VIN-004", "Espumoso 750 ml", "unidad", "Vinos", "520.00", "20", "8", "Distribuidora Nacional"),
    # ── Bebidas sin alcohol ──────────────────────────────────────────────────
    ("BEB-001", "Agua con gas", "L", "Bebidas sin alcohol", "85.00", "60", "24", "Distribuidora Nacional"),
    ("BEB-002", "Agua purificada", "L", "Bebidas sin alcohol", "45.00", "180", "60", "Empresa de Aguas"),
    ("BEB-003", "Jugo de mango", "L", "Bebidas sin alcohol", "60.00", "40", "15", "Producción propia"),
    ("BEB-004", "Jugo de piña", "L", "Bebidas sin alcohol", "58.00", "36", "15", "Producción propia"),
    ("BEB-005", "Jugo de naranja", "L", "Bebidas sin alcohol", "55.00", "42", "15", "Producción propia"),
    ("BEB-006", "Jugo de fresa", "L", "Bebidas sin alcohol", "62.00", "30", "12", "Producción propia"),
    ("BEB-007", "Refresco de cola", "L", "Bebidas sin alcohol", "60.00", "45", "18", "Distribuidora Nacional"),
    ("BEB-008", "Refresco de naranja", "L", "Bebidas sin alcohol", "58.00", "40", "18", "Distribuidora Nacional"),
    ("BEB-009", "Limonada", "L", "Bebidas sin alcohol", "55.00", "25", "10", "Producción propia"),
    ("BEB-010", "Té frío", "L", "Bebidas sin alcohol", "45.00", "35", "12", "Producción propia"),
    ("BEB-011", "Agua de coco", "L", "Bebidas sin alcohol", "90.00", "20", "8", "Mercado del Puerto"),
    ("BEB-012", "Jugo de tomate", "L", "Bebidas sin alcohol", "50.00", "18", "8", "Producción propia"),
    ("BEB-013", "Malteada de fresa", "unidad", "Bebidas sin alcohol", "120.00", "25", "10", "Producción propia"),
    ("BEB-014", "Agua de naranja natural", "L", "Bebidas sin alcohol", "70.00", "22", "8", "Producción propia"),
    # ── Cafés y tés ──────────────────────────────────────────────────────────
    ("CAF-001", "Café espresso (dosis)", "unidad", "Cafés y tés", "35.00", "300", "100", "Tostadores de Cuba"),
    ("CAF-002", "Café filtrado (dosis)", "unidad", "Cafés y tés", "30.00", "280", "100", "Tostadores de Cuba"),
    ("CAF-003", "Café latte", "unidad", "Cafés y tés", "55.00", "120", "40", "Producción propia"),
    ("CAF-004", "Capuchino", "unidad", "Cafés y tés", "60.00", "110", "40", "Producción propia"),
    ("CAF-005", "Chocolate caliente", "unidad", "Cafés y tés", "65.00", "90", "30", "Producción propia"),
    ("CAF-006", "Té verde (dosis)", "unidad", "Cafés y tés", "25.00", "200", "60", "Distribuidora Nacional"),
    ("CAF-007", "Té negro (dosis)", "unidad", "Cafés y tés", "25.00", "200", "60", "Distribuidora Nacional"),
    ("CAF-008", "Matcha latte", "unidad", "Cafés y tés", "70.00", "60", "20", "Producción propia"),
    # ── Granos y básicos ─────────────────────────────────────────────────────
    ("INS-001", "Arroz", "kg", "Granos y básicos", "130.00", "80", "25", "Almacén central"),
    ("INS-002", "Frijol negro", "kg", "Granos y básicos", "220.00", "45", "15", "Almacén central"),
    ("INS-003", "Frijol rojo", "kg", "Granos y básicos", "210.00", "38", "12", "Almacén central"),
    ("INS-004", "Maíz", "kg", "Granos y básicos", "105.00", "40", "12", "Almacén central"),
    ("INS-005", "Aceite", "L", "Granos y básicos", "480.00", "30", "10", "Almacén central"),
    ("INS-006", "Aceite de oliva", "L", "Granos y básicos", "950.00", "12", "4", "Distribuidora Nacional"),
    ("INS-007", "Azúcar", "kg", "Granos y básicos", "95.00", "70", "25", "Almacén central"),
    ("INS-008", "Sal", "kg", "Granos y básicos", "70.00", "55", "20", "Almacén central"),
    ("INS-009", "Harina de trigo", "kg", "Granos y básicos", "60.00", "90", "30", "Almacén central"),
    ("INS-010", "Manteca", "kg", "Granos y básicos", "380.00", "18", "6", "Almacén central"),
    ("INS-011", "Vinagre", "L", "Granos y básicos", "130.00", "16", "6", "Almacén central"),
    ("INS-012", "Vino tinto para cocinar", "L", "Granos y básicos", "260.00", "10", "4", "Almacén central"),
    # ── Condimentos y salsas ─────────────────────────────────────────────────
    ("CON-001", "Salsa de tomate", "kg", "Condimentos", "150.00", "22", "8", "Almacén central"),
    ("CON-002", "Ketchup", "kg", "Condimentos", "190.00", "12", "4", "Almacén central"),
    ("CON-003", "Mayonesa", "kg", "Condimentos", "210.00", "14", "5", "Almacén central"),
    ("CON-004", "Mostaza", "kg", "Condimentos", "180.00", "9", "3", "Almacén central"),
    ("CON-005", "Salsa oriental", "L", "Condimentos", "250.00", "11", "4", "Almacén central"),
    ("CON-006", "Salsa de ajo", "kg", "Condimentos", "230.00", "8", "3", "Almacén central"),
    ("CON-007", "Salsa barbecue", "L", "Condimentos", "260.00", "10", "4", "Almacén central"),
    ("CON-008", "Pimentón de la Vera", "kg", "Condimentos", "440.00", "4", "1", "Distribuidora Nacional"),
    ("CON-009", "Comino molido", "kg", "Condimentos", "300.00", "6", "2", "Almacén central"),
    ("CON-010", "Pimienta negra", "kg", "Condimentos", "900.00", "2", "1", "Distribuidora Nacional"),
    ("CON-011", "Ajo en polvo", "kg", "Condimentos", "460.00", "3", "1", "Almacén central"),
    ("CON-012", "Orégano", "kg", "Condimentos", "380.00", "3", "1", "Almacén central"),
    ("CON-013", "Canela molida", "kg", "Condimentos", "320.00", "3", "1", "Almacén central"),
    # ── Vegetales ────────────────────────────────────────────────────────────
    ("VEG-001", "Cebolla", "kg", "Vegetales", "90.00", "35", "12", "Mercado central"),
    ("VEG-002", "Ajo", "kg", "Vegetales", "210.00", "12", "4", "Mercado central"),
    ("VEG-003", "Pimiento rojo", "kg", "Vegetales", "140.00", "18", "6", "Mercado central"),
    ("VEG-004", "Tomate perita", "kg", "Vegetales", "130.00", "30", "10", "Mercado central"),
    ("VEG-005", "Zanahoria", "kg", "Vegetales", "85.00", "26", "9", "Mercado central"),
    ("VEG-006", "Papa", "kg", "Vegetales", "75.00", "90", "30", "Mercado central"),
    ("VEG-007", "Boniato", "kg", "Vegetales", "70.00", "60", "20", "Mercado central"),
    ("VEG-008", "Plátano macho", "kg", "Vegetales", "130.00", "34", "12", "Mercado central"),
    ("VEG-009", "Yuca", "kg", "Vegetales", "95.00", "28", "10", "Mercado central"),
    ("VEG-010", "Calabaza", "kg", "Vegetales", "60.00", "40", "12", "Mercado central"),
    ("VEG-011", "Lechuga", "kg", "Vegetales", "55.00", "12", "4", "Mercado central"),
    ("VEG-012", "Aji dulce", "kg", "Vegetales", "190.00", "9", "3", "Mercado central"),
    ("VEG-013", "Cilantro", "kg", "Hierbas", "240.00", "6", "2", "Mercado central"),
    ("VEG-014", "Perejil", "kg", "Hierbas", "200.00", "5", "2", "Mercado central"),
    ("VEG-015", "Menta fresca", "kg", "Hierbas", "180.00", "4", "1", "Mercado central"),
    ("VEG-016", "Hierbabuena", "kg", "Hierbas", "600.00", "2", "1", "Mercado central"),
    ("VEG-017", "Romero", "kg", "Hierbas", "420.00", "2", "1", "Mercado central"),
    # ── Frutas ───────────────────────────────────────────────────────────────
    ("FRU-001", "Mango", "kg", "Frutas", "180.00", "32", "12", "Mercado central"),
    ("FRU-002", "Piña", "kg", "Frutas", "160.00", "24", "8", "Mercado central"),
    ("FRU-003", "Plátano", "kg", "Frutas", "130.00", "28", "10", "Mercado central"),
    ("FRU-004", "Naranja", "kg", "Frutas", "95.00", "40", "15", "Mercado central"),
    ("FRU-005", "Limón", "kg", "Frutas", "210.00", "18", "6", "Mercado central"),
    ("FRU-006", "Fresa", "kg", "Frutas", "380.00", "8", "3", "Mercado central"),
    ("FRU-007", "Guayaba", "kg", "Frutas", "120.00", "16", "6", "Mercado central"),
    ("FRU-008", "Papaya", "kg", "Frutas", "145.00", "20", "8", "Mercado central"),
    ("FRU-009", "Coco", "kg", "Frutas", "190.00", "12", "4", "Mercado central"),
    ("FRU-010", "Pera", "kg", "Frutas", "150.00", "14", "5", "Mercado central"),
    ("FRU-011", "Uva", "kg", "Frutas", "220.00", "10", "4", "Mercado central"),
    # ── Carnes y aves ────────────────────────────────────────────────────────
    ("CAR-001", "Cerdo (pulpa)", "kg", "Carnes", "620.00", "26", "10", "Matadero provincial"),
    ("CAR-002", "Res molida", "kg", "Carnes", "780.00", "18", "7", "Matadero provincial"),
    ("CAR-003", "Chuletón de res", "kg", "Carnes", "1250.00", "12", "5", "Matadero provincial"),
    ("CAR-004", "Patas de res", "kg", "Carnes", "540.00", "16", "6", "Matadero provincial"),
    ("CAR-005", "Hígado de res", "kg", "Carnes", "380.00", "8", "3", "Matadero provincial"),
    ("CAR-006", "Chorizo", "kg", "Carnes", "720.00", "9", "3", "Matadero provincial"),
    ("CAR-007", "Jamón serrano", "kg", "Carnes", "950.00", "6", "2", "Distribuidora Nacional"),
    ("CAR-008", "Tocino", "kg", "Carnes", "880.00", "7", "3", "Distribuidora Nacional"),
    ("AVE-001", "Pollo entero", "kg", "Aves", "520.00", "45", "15", "Avícola Nacional"),
    ("AVE-002", "Pechuga de pollo", "kg", "Aves", "560.00", "30", "10", "Avícola Nacional"),
    ("AVE-003", "Muslo de pollo", "kg", "Aves", "470.00", "38", "12", "Avícola Nacional"),
    ("AVE-004", "Alas de pollo", "kg", "Aves", "430.00", "22", "8", "Avícola Nacional"),
    # ── Pescados y mariscos ──────────────────────────────────────────────────
    ("PES-001", "Pescado blanco", "kg", "Pescados", "780.00", "14", "5", "Pescadería del Puerto"),
    ("PES-002", "Lubina", "kg", "Pescados", "1450.00", "8", "3", "Pescadería del Puerto"),
    ("PES-003", "Salmón", "kg", "Pescados", "1680.00", "6", "2", "Pescadería del Puerto"),
    ("PES-004", "Atún fresco", "kg", "Pescados", "1250.00", "9", "3", "Pescadería del Puerto"),
    ("PES-005", "Dorado", "kg", "Pescados", "1120.00", "10", "3", "Pescadería del Puerto"),
    ("MAR-001", "Camarón", "kg", "Mariscos", "1650.00", "7", "2", "Pescadería del Puerto"),
    ("MAR-002", "Langosta", "kg", "Mariscos", "2400.00", "4", "1", "Pescadería del Puerto"),
    ("MAR-003", "Cangrejo", "kg", "Mariscos", "1900.00", "5", "2", "Pescadería del Puerto"),
    # ── Lácteos y panadería ──────────────────────────────────────────────────
    ("LAC-001", "Leche entera", "L", "Lácteos", "65.00", "60", "20", "Lácteos Nacionales"),
    ("LAC-002", "Leche condensada", "kg", "Lácteos", "110.00", "18", "6", "Lácteos Nacionales"),
    ("LAC-003", "Queso crema", "kg", "Lácteos", "180.00", "12", "4", "Lácteos Nacionales"),
    ("LAC-004", "Queso cheddar", "kg", "Lácteos", "480.00", "7", "2", "Lácteos Nacionales"),
    ("LAC-005", "Mantequilla", "kg", "Lácteos", "420.00", "9", "3", "Lácteos Nacionales"),
    ("LAC-006", "Crema de leche", "L", "Lácteos", "210.00", "14", "5", "Lácteos Nacionales"),
    ("LAC-007", "Yogur natural", "unidad", "Lácteos", "90.00", "40", "15", "Lácteos Nacionales"),
    ("LAC-008", "Huevo", "unidad", "Lácteos", "55.00", "240", "80", "Avícola Nacional"),
    ("PAN-001", "Pan blanco", "kg", "Panadería", "60.00", "35", "12", "Panadería El Molino"),
    ("PAN-002", "Pan integral", "kg", "Panadería", "70.00", "22", "8", "Panadería El Molino"),
    ("PAN-003", "Baguette", "unidad", "Panadería", "85.00", "30", "12", "Panadería El Molino"),
    ("PAN-004", "Croissant", "unidad", "Panadería", "120.00", "24", "10", "Panadería El Molino"),
    ("PAN-005", "Tostón", "kg", "Panadería", "90.00", "16", "6", "Panadería El Molino"),
    # ── Servicios ────────────────────────────────────────────────────────────
    ("SRV-001", "Mano de obra general", "hora", "Servicios", "220.00", "500", "0", "Tarifa interna"),
    ("SRV-002", "Cocinero", "hora", "Servicios", "280.00", "400", "0", "Tarifa interna"),
    ("SRV-003", "Mesero", "hora", "Servicios", "200.00", "300", "0", "Tarifa interna"),
    ("SRV-004", "Barman", "hora", "Servicios", "300.00", "200", "0", "Tarifa interna"),
    ("SRV-005", "Limpieza", "hora", "Servicios", "180.00", "200", "0", "Tarifa interna"),
    ("SRV-006", "Alquiler del local", "día", "Servicios", "45000.00", "30", "0", "Contrato vigente"),
    ("SRV-007", "Energía eléctrica", "kWh", "Servicios", "320.00", "1200", "0", "Factura mes"),
    ("SRV-008", "Agua potable", "m³", "Servicios", "180.00", "300", "0", "Factura mes"),
    ("SRV-009", "Mantenimiento de equipos", "servicio", "Servicios", "950.00", "20", "0", "Proveedor técnico"),
    ("SRV-010", "Servicio de sala y música", "hora", "Servicios", "180.00", "0", "0", "Contrato vigente"),
]

# --------------------------------------------------------------------------- #
#  PRODUCTOS  (código, nombre, categoría, unidad, descripción, rendimiento, unidad de rend.)
# --------------------------------------------------------------------------- #
PRODUCTS: list[tuple[str, str, str, str, str, str, str]] = [
    # Comidas — el rendimiento indica cuántos comensales salen del lote
    ("COM-001", "Arroz congrí", "Comidas", "ración", "Arroz con frijol y carne de cerdo.", "20", "comensales"),
    ("COM-002", "Pollo asado con arroz", "Comidas", "ración", "Pollo asado con guarnición de arroz blanco.", "15", "comensales"),
    ("COM-003", "Ropa vieja", "Comidas", "ración", "Carne deshebrada en salsa de tomate.", "18", "comensales"),
    ("COM-004", "Picadillo con arroz", "Comidas", "ración", "Carne molida guisada con verduras.", "20", "comensales"),
    ("COM-005", "Potaje de frijoles negros", "Comidas", "ración", "Frijoles negros con cerdo y boniato.", "25", "comensales"),
    ("COM-006", "Arroz con pollo", "Comidas", "ración", "Arroz con pollo guisado.", "20", "comensales"),
    ("COM-007", "Chicharrón de cerdo", "Comidas", "ración", "Chicharrón crujiente con patacón.", "12", "comensales"),
    ("COM-008", "Pernil de cerdo asado", "Comidas", "ración", "Pernil asado con salsa oriental.", "16", "comensales"),
    ("COM-009", "Sopa de pollo", "Comidas", "ración", "Sopa casera con pollo y verduras.", "20", "comensales"),
    ("COM-010", "Crema de calabaza", "Comidas", "ración", "Crema de calabaza con crema de leche.", "18", "comensales"),
    ("COM-011", "Bistec de res a la plancha", "Comidas", "ración", "Bistec de res con papas y huevo.", "10", "comensales"),
    ("COM-012", "Lubina al horno", "Comidas", "ración", "Lubina al horno con verduras.", "12", "comensales"),
    ("COM-013", "Paella de camarones", "Comidas", "ración", "Arroz con camarones y condimentos.", "14", "comensales"),
    ("COM-014", "Pastel de carne", "Comidas", "ración", "Pastel de carne con masa quebrada.", "12", "comensales"),
    # Bebidas
    ("BEB-001", "Mojito clásico", "Bebidas", "copa", "Ron Havana Club, menta, lima y agua con gas.", "20", "copas"),
    ("BEB-002", "Cuba libre", "Bebidas", "copa", "Ron, refresco de cola y lima.", "20", "copas"),
    ("BEB-003", "Daiquiri de fresa", "Bebidas", "copa", "Ron, fresa, azúcar y limón.", "15", "copas"),
    ("BEB-004", "Daiquiri de mango", "Bebidas", "copa", "Ron, mango y limón.", "15", "copas"),
    ("BEB-005", "Piña colada", "Bebidas", "copa", "Ron, piña, coco y crema.", "12", "copas"),
    ("BEB-006", "Gin & Tonic", "Bebidas", "copa", "Gin, agua tónica y hielo.", "15", "copas"),
    ("BEB-007", "Tequila sunrise", "Bebidas", "copa", "Tequila, zumo de naranja y grenadina.", "12", "copas"),
    ("BEB-008", "Ron añejo solo", "Bebidas", "copa", "Copa de ron añejo con hielo.", "20", "copas"),
    ("BEB-009", "Whisky con hielo", "Bebidas", "copa", "Whisky con hielo y agua mineral.", "20", "copas"),
    ("BEB-010", "Sangría de frutas", "Bebidas", "copa", "Sangria con vino tinto y frutas.", "10", "copas"),
    ("BEB-011", "Jugo de mango natural", "Bebidas", "vaso", "Jugo natural de mango por vaso.", "20", "vasos"),
    ("BEB-012", "Limonada de menta", "Bebidas", "vaso", "Limonada con menta fresca y hielo.", "20", "vasos"),
    ("BEB-013", "Café expreso", "Bebidas", "taza", "Café espreso de grano.", "30", "tazas"),
    ("BEB-014", "Capuchino", "Bebidas", "taza", "Espreso con leche vaporizada.", "20", "tazas"),
    ("BEB-015", "Cerveza pilsener", "Bebidas", "botella", "Cerveza pilsener helada.", "24", "botellas"),
    ("BEB-016", "Cerveza artesanal IPA", "Bebidas", "botella", "Cerveza artesanal de Malta.", "12", "botellas"),
    ("BEB-017", "Vino tinto de la casa", "Bebidas", "copa", "Copa de vino tinto selección.", "10", "copas"),
    ("SER-001", "Servicio de salón", "Servicios", "hora", "Atención de mesa por hora.", "1", "servicio"),
    ("SER-002", "Catering por persona", "Servicios", "persona", "Servicio completo de banquete.", "50", "comensales"),
]

# --------------------------------------------------------------------------- #
#  RECETAS  (código de producto, estado, rendimiento, unidad, [(código material, cantidad)])
#  Las cantidades son para TODO el lote: por eso el rendimiento indica comensales/copas.
# --------------------------------------------------------------------------- #
RECIPES: list[tuple[str, str, str, str, list[tuple[str, str]]]] = [
    ("COM-001", "Aprobada", "20", "comensales", [
        ("INS-001", "3.0"), ("INS-002", "0.8"), ("CAR-001", "2.5"), ("INS-005", "0.3"),
        ("INS-007", "0.2"), ("INS-008", "0.1"), ("CON-001", "0.6"), ("VEG-001", "0.5"),
        ("VEG-004", "1.2"), ("CON-009", "0.05"), ("SRV-002", "2.0")]),
    ("COM-002", "Aprobada", "15", "comensales", [
        ("AVE-001", "4.5"), ("INS-001", "2.0"), ("INS-005", "0.2"), ("CON-006", "0.15"),
        ("CON-007", "0.2"), ("VEG-002", "0.15"), ("VEG-001", "0.4"), ("INS-008", "0.06"),
        ("VEG-003", "0.3"), ("SRV-002", "2.5")]),
    ("COM-003", "Aprobada", "18", "comensales", [
        ("CAR-001", "3.0"), ("CON-001", "1.5"), ("VEG-004", "2.0"), ("VEG-001", "0.6"),
        ("CON-013", "0.04"), ("CON-010", "0.02"), ("INS-005", "0.25"), ("INS-007", "0.15"),
        ("INS-011", "0.1"), ("SRV-002", "2.0")]),
    ("COM-004", "Aprobada", "20", "comensales", [
        ("CAR-002", "2.6"), ("INS-001", "3.0"), ("VEG-001", "0.7"), ("VEG-004", "1.8"),
        ("VEG-003", "0.5"), ("CON-009", "0.06"), ("CON-011", "0.03"), ("INS-005", "0.25"),
        ("INS-008", "0.1"), ("SRV-002", "2.0")]),
    ("COM-005", "Aprobada", "25", "comensales", [
        ("INS-002", "3.0"), ("CAR-001", "1.8"), ("VEG-007", "2.0"), ("VEG-001", "0.6"),
        ("INS-005", "0.3"), ("CON-006", "0.1"), ("CON-012", "0.03"), ("INS-008", "0.15"),
        ("PAN-002", "0.5"), ("SRV-002", "1.5")]),
    ("COM-006", "Aprobada", "20", "comensales", [
        ("AVE-003", "4.0"), ("INS-001", "3.2"), ("VEG-001", "0.6"), ("VEG-004", "1.5"),
        ("CON-012", "0.03"), ("CON-009", "0.04"), ("INS-005", "0.2"), ("INS-008", "0.12"),
        ("SRV-002", "2.2")]),
    ("COM-007", "Borrador", "12", "comensales", [
        ("CAR-001", "2.4"), ("INS-005", "0.8"), ("VEG-006", "2.0"), ("INS-008", "0.15"),
        ("VEG-002", "0.1"), ("INS-010", "0.3"), ("CON-011", "0.02"), ("SRV-002", "1.8")]),
    ("COM-008", "Aprobada", "16", "comensales", [
        ("CAR-001", "4.0"), ("CON-005", "0.5"), ("CON-006", "0.2"), ("VEG-006", "2.5"),
        ("VEG-001", "0.5"), ("CON-007", "0.3"), ("INS-005", "0.3"), ("INS-007", "0.2"),
        ("SRV-002", "3.0")]),
    ("COM-009", "Aprobada", "20", "comensales", [
        ("AVE-002", "2.5"), ("INS-001", "0.8"), ("VEG-009", "1.0"), ("VEG-004", "1.2"),
        ("VEG-001", "0.5"), ("VEG-002", "0.08"), ("INS-005", "0.1"), ("SRV-002", "1.5")]),
    ("COM-010", "Aprobada", "18", "comensales", [
        ("VEG-010", "3.0"), ("LAC-006", "0.6"), ("VEG-001", "0.4"), ("VEG-005", "0.5"),
        ("INS-010", "0.15"), ("INS-008", "0.08"), ("CON-006", "0.1"), ("SRV-002", "1.2")]),
    ("COM-011", "Borrador", "10", "comensales", [
        ("CAR-003", "2.0"), ("VEG-006", "2.5"), ("INS-005", "0.4"), ("LAC-008", "10"),
        ("VEG-003", "0.3"), ("INS-008", "0.1"), ("SRV-002", "1.6")]),
    ("COM-012", "Aprobada", "12", "comensales", [
        ("PES-002", "3.0"), ("VEG-006", "1.5"), ("VEG-003", "0.4"), ("VEG-001", "0.3"),
        ("INS-006", "0.2"), ("INS-008", "0.08"), ("CON-012", "0.02"), ("SRV-002", "1.8")]),
    ("COM-013", "Aprobada", "14", "comensales", [
        ("MAR-001", "1.8"), ("INS-001", "2.4"), ("PES-004", "0.8"), ("CON-005", "0.15"),
        ("CON-007", "0.12"), ("VEG-003", "0.4"), ("CON-013", "0.03"), ("INS-005", "0.25"),
        ("INS-008", "0.1"), ("SRV-002", "2.2")]),
    ("COM-014", "Aprobada", "12", "comensales", [
        ("CAR-002", "1.8"), ("INS-009", "1.5"), ("LAC-005", "0.3"), ("INS-010", "0.25"),
        ("VEG-001", "0.4"), ("VEG-004", "1.0"), ("INS-005", "0.15"), ("INS-008", "0.08"),
        ("SRV-002", "1.8")]),
    ("BEB-001", "Aprobada", "20", "copas", [
        ("LIC-005", "1.0"), ("VEG-015", "0.08"), ("FRU-005", "0.15"), ("BEB-001", "2.4"),
        ("INS-007", "0.2"), ("BEB-002", "0.6"), ("SRV-004", "1.0")]),
    ("BEB-002", "Aprobada", "20", "copas", [
        ("LIC-007", "1.0"), ("BEB-007", "2.0"), ("FRU-005", "0.15"), ("BEB-002", "0.8"),
        ("SRV-004", "1.0")]),
    ("BEB-003", "Aprobada", "15", "copas", [
        ("LIC-004", "0.75"), ("FRU-006", "0.6"), ("INS-007", "0.15"), ("FRU-005", "0.12"),
        ("BEB-002", "0.5"), ("SRV-004", "0.8")]),
    ("BEB-004", "Aprobada", "15", "copas", [
        ("LIC-004", "0.75"), ("FRU-001", "0.9"), ("FRU-005", "0.12"), ("INS-007", "0.1"),
        ("BEB-002", "0.5"), ("SRV-004", "0.8")]),
    ("BEB-005", "Aprobada", "12", "copas", [
        ("LIC-002", "0.6"), ("FRU-002", "0.9"), ("FRU-009", "0.35"), ("LAC-006", "0.3"),
        ("BEB-002", "0.4"), ("SRV-004", "0.8")]),
    ("BEB-006", "Aprobada", "15", "copas", [
        ("LIC-016", "0.75"), ("BEB-001", "2.2"), ("FRU-005", "0.1"), ("BEB-002", "0.4"),
        ("SRV-004", "0.8")]),
    ("BEB-007", "Aprobada", "12", "copas", [
        ("LIC-017", "0.6"), ("BEB-005", "1.2"), ("LIC-021", "0.1"), ("BEB-002", "0.4"),
        ("SRV-004", "0.8")]),
    ("BEB-008", "Aprobada", "20", "copas", [
        ("LIC-002", "0.9"), ("BEB-002", "0.5"), ("INS-007", "0.05"), ("SRV-004", "0.6")]),
    ("BEB-009", "Aprobada", "20", "copas", [
        ("LIC-019", "0.9"), ("BEB-002", "0.5"), ("INS-007", "0.05"), ("SRV-004", "0.6")]),
    ("BEB-010", "Aprobada", "10", "copas", [
        ("VIN-001", "0.75"), ("FRU-001", "0.4"), ("FRU-004", "0.3"), ("BEB-002", "0.5"),
        ("INS-007", "0.1"), ("SRV-004", "0.8")]),
    ("BEB-011", "Aprobada", "20", "vasos", [
        ("FRU-001", "5.0"), ("INS-007", "0.4"), ("BEB-002", "1.5"), ("LAC-002", "0.2"),
        ("SRV-003", "1.2")]),
    ("BEB-012", "Aprobada", "20", "vasos", [
        ("FRU-005", "0.6"), ("VEG-015", "0.05"), ("INS-007", "0.5"), ("BEB-002", "4.0"),
        ("SRV-003", "1.0")]),
    ("BEB-013", "Aprobada", "30", "tazas", [
        ("CAF-001", "30"), ("INS-007", "0.2"), ("BEB-002", "0.6"), ("SRV-003", "2.0")]),
    ("BEB-014", "Aprobada", "20", "tazas", [
        ("CAF-001", "20"), ("LAC-001", "1.2"), ("INS-007", "0.15"), ("LAC-006", "0.1"),
        ("BEB-002", "0.5"), ("SRV-003", "1.8")]),
    ("BEB-015", "Aprobada", "24", "botellas", [
        ("CER-001", "24"), ("PAN-005", "0.5"), ("INS-007", "0.1"), ("SRV-005", "0.5")]),
    ("BEB-016", "Aprobada", "12", "botellas", [
        ("CER-004", "12"), ("PAN-004", "0.5"), ("INS-007", "0.1"), ("SRV-005", "0.5")]),
    ("BEB-017", "Aprobada", "10", "copas", [
        ("VIN-001", "0.6"), ("LAC-004", "0.25"), ("PAN-002", "0.3"), ("SRV-003", "1.0")]),
    ("SER-001", "Aprobada", "1", "servicio", [("SRV-003", "1.0"), ("SRV-005", "1.0")]),
    ("SER-002", "Aprobada", "50", "comensales", [
        ("INS-001", "7.5"), ("INS-002", "2.0"), ("INS-005", "1.2"), ("INS-007", "1.0"),
        ("CAR-001", "6.0"), ("AVE-001", "11.0"), ("VEG-001", "2.0"), ("VEG-004", "4.0"),
        ("VEG-006", "4.0"), ("FRU-001", "3.0"), ("BEB-002", "20.0"), ("CAF-001", "50"),
        ("PAN-002", "1.0"), ("SRV-002", "20.0"), ("SRV-003", "8.0"), ("SRV-005", "4.0")]),
]

# Controles de ejemplo: (código de producto, período, estado)
CONTROLS: list[tuple[str, str, str]] = [
    ("BEB-001", "2026-07", "Validado"),
    ("COM-001", "2026-07", "Validado"),
    ("COM-002", "2026-08", "Pendiente"),
    ("BEB-003", "2026-08", "Pendiente"),
    ("COM-005", "2026-08", "Con diferencias"),
]
