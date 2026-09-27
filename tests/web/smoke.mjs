/**
 * IPV · Fichas y Costos — Prueba de humo del cliente web.
 *
 * Levanta el servidor real (server.py) con una base de datos temporal,
 * carga la interfaz en un DOM simulado (jsdom) y verifica el renderizado de
 * todas las vistas, el enrutado, la búsqueda global y la generación de documentos.
 *
 * Uso:
 *   cd tests/web && npm install && npm test
 *
 * Requiere Node 18 o superior y Python 3.10 o superior disponibles en el PATH.
 */
import {
  assert, closeSuite, createReporter, importModule, openClient, startServer, waitFor,
} from './harness.mjs';

const REPORTER_TITLE = 'IPV · Fichas y Costos — Prueba de humo del cliente web';

async function main() {
  const server = await startServer();
  const { base } = server;
  const reporter = createReporter(REPORTER_TITLE);
  let dom = null;

  try {
    const client = await openClient(base);
    dom = client.dom;
    const { window, app } = client;
    const document_ = client.document;

    assert.match(client.html, /IPV · Fichas y Costos/, 'La interfaz debe servirse en la raíz');
    assert.match(client.html, /Ing\. Yosvany Hernández Quintero/, 'La portada debe acreditar al autor');
    assert.ok(document_.querySelector('script[type="module"]'), 'La interfaz debe declarar el módulo de arranque');

    await reporter.test('Arranque: la aplicación carga los datos y muestra el tablero', async () => {
      await waitFor(() => document_.querySelector('#view-root h1'), { label: 'el tablero' });
      const heading = document_.querySelector('#view-root h1').textContent;
      assert.match(heading, /Tablero de control de costos/);
      const kpis = document_.querySelectorAll('#view-root .kpi');
      assert.ok(kpis.length >= 4, `Se esperaban al menos 4 indicadores, se encontraron ${kpis.length}`);
      assert.ok(document_.querySelector('#view-root .chart-figure svg'), 'El tablero debe incluir un gráfico vectorial');
      await waitFor(() => document_.querySelector('#connection-text').textContent.includes('en línea'),
        { label: 'el indicador de conexión' });
    });

    await reporter.test('Navegación: los contadores del menú muestran los totales reales', async () => {
      const products = document_.querySelector('[data-count="products"]').textContent;
      const fichas = document_.querySelector('[data-count="fichas"]').textContent;
      assert.equal(products, '5', 'Debe contarse los 5 productos activos del conjunto inicial');
      assert.equal(fichas, '5', 'Debe contarse las 5 fichas del conjunto inicial');
    });

    await reporter.test('Catálogo: la tabla de productos renderiza y filtra resultados', async () => {
      app.router.navigate('/productos');
      await waitFor(() => document_.querySelector('#view-root table.data tbody tr'), { label: 'la tabla de productos' });
      const rows = document_.querySelectorAll('#view-root table.data tbody tr');
      assert.equal(rows.length, 5, `Se esperaban 5 filas, se encontraron ${rows.length}`);
      const search = document_.querySelector('#view-root input[type="search"]');
      search.value = 'mango';
      search.dispatchEvent(new window.Event('input', { bubbles: true }));
      await waitFor(() => document_.querySelectorAll('#view-root table.data tbody tr').length === 1, { label: 'el filtro de búsqueda' });
      assert.match(document_.querySelector('#view-root table.data tbody tr').textContent, /Mango/i);
    });

    await reporter.test('Valores del IPV: se muestran precios, vigencia y estados', async () => {
      app.router.navigate('/valores');
      await waitFor(() => document_.querySelectorAll('#view-root table.data tbody tr').length >= 10, { label: 'la tabla de valores' });
      const text = document_.querySelector('#view-root table.data tbody').textContent;
      assert.match(text, /Mano de obra directa/);
      assert.match(text, /Vigente/);
    });

    await reporter.test('Fichas: el listado muestra el documento versionado y sus acciones', async () => {
      app.router.navigate('/fichas');
      await waitFor(() => document_.querySelector('#view-root table.data tbody tr'), { label: 'la tabla de fichas' });
      const text = document_.querySelector('#view-root table.data tbody').textContent;
      assert.match(text, /FC-BEB-001-v1/);
      assert.match(text, /Aprobada/);
    });

    await reporter.test('Fichas: el enlace profundo abre el panel de detalle con la composición del costo', async () => {
      app.router.navigate('/fichas/1');
      await waitFor(() => document_.querySelector('#overlay-root .drawer'), { label: 'el panel de la ficha' });
      const drawer = document_.querySelector('#overlay-root .drawer');
      assert.match(drawer.textContent, /FC-BEB-001-v1/);
      assert.match(drawer.textContent, /Composición del costo/);
      assert.ok(drawer.querySelector('.share-fill'), 'El detalle debe mostrar la participación de cada componente');
      drawer.querySelector('.drawer-header .icon-btn').click();
      await waitFor(() => !document_.querySelector('#overlay-root .drawer'), { label: 'el cierre del panel' });
    });

    await reporter.test('Controles: el informe de validación se muestra con sus comprobaciones', async () => {
      app.router.navigate('/controles');
      await waitFor(() => document_.querySelectorAll('#view-root table.data tbody tr').length >= 2, { label: 'la tabla de controles' });
      const text = document_.querySelector('#view-root table.data tbody').textContent;
      assert.match(text, /IPV-2026-0001/);
      app.router.navigate('/controles/1');
      await waitFor(() => document_.querySelector('#overlay-root .check-list'), { label: 'el informe de validación' });
      assert.match(document_.querySelector('#overlay-root .drawer').textContent, /Comprobación|Estado de la ficha/);
      document_.querySelector('#overlay-root .drawer-header .icon-btn').click();
    });

    await reporter.test('Bitácora: se listan los movimientos con su responsable', async () => {
      app.router.navigate('/bitacora');
      await waitFor(() => document_.querySelectorAll('#view-root .timeline-item').length > 0, { label: 'la bitácora' });
      const text = document_.querySelector('#view-root [data-role="list"]').textContent;
      assert.match(text, /Ficha v1 creada/);
    });

    await reporter.test('Sistema: se muestra el diagnóstico de la base de datos y del certificado', async () => {
      app.router.navigate('/sistema');
      await waitFor(() => document_.querySelector('#view-root .system-grid'), { label: 'el diagnóstico' });
      const text = document_.querySelector('#view-root').textContent;
      assert.match(text, /SQLite/);
      assert.match(text, /Respaldos/);
      assert.match(text, /Atajos de teclado/);
    });

    await reporter.test('Acerca de: se acredita al autor y se describe el alcance', async () => {
      app.router.navigate('/acerca-de');
      await waitFor(() => document_.querySelector('#view-root .about-hero'), { label: 'la vista Acerca de' });
      const text = document_.querySelector('#view-root').textContent;
      assert.match(text, /Ing\. Yosvany Hernández Quintero/);
      assert.match(text, /Diseño, desarrollo e implementación/);
      assert.match(text, /Bitácora de auditoría/);
    });

    await reporter.test('Paleta de comandos: se abre, busca en el servidor y navega', async () => {
      const palette = await importModule('js/components/command-palette.js');
      palette.openCommandPalette({ navigate: app.router.navigate });
      await waitFor(() => document_.querySelector('#palette-root .palette'), { label: 'la paleta' });
      const input = document_.querySelector('#palette-root .palette input');
      input.value = 'mojito';
      input.dispatchEvent(new window.Event('input', { bubbles: true }));
      await waitFor(() => document_.querySelectorAll('#palette-root .palette-item').length > 0, { label: 'los resultados remotos' });
      const text = document_.querySelector('#palette-root').textContent;
      assert.match(text, /Mojito/i);
      document_.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      await waitFor(() => !document_.querySelector('#palette-root .palette'), { label: 'el cierre de la paleta' });
    });

    await reporter.test('Documentos: la ficha y el acta de control generan una impresión', async () => {
      const print = await importModule('js/components/print.js');
      const ficha = await (await fetch(`${base}/api/fichas/1`)).json();
      print.printFicha(ficha);
      await waitFor(() => document_.querySelector('#print-root .doc'), { label: 'el documento de la ficha' });
      const doc = document_.querySelector('#print-root .doc');
      assert.match(doc.textContent, /Ficha de costo/);
      assert.match(doc.textContent, /Ing\. Yosvany Hernández Quintero/);
      assert.ok(doc.querySelectorAll('.doc-signature').length >= 3, 'La ficha impresa debe incluir las firmas');
      await waitFor(() => window.__printCalls >= 1, { label: 'la orden de impresión' });

      const control = await (await fetch(`${base}/api/controls/1`)).json();
      print.printControl(control);
      await waitFor(() => document_.querySelector('#print-root .doc-verdict'), { label: 'el acta del control' });
      assert.match(document_.querySelector('#print-root').textContent, /Control de IPV/);
    });

    await reporter.test('Creación: se registra un producto y una ficha mediante la API pública', async () => {
      const product = await (await fetch(`${base}/api/products`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: 'SMK-01', name: 'Producto de humo', category: 'Bebidas', unit: 'copa' }),
      })).json();
      assert.equal(product.code, 'SMK-01');
      const material = await (await fetch(`${base}/api/materials`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: 'SMK-V1', name: 'Valor de humo', unit: 'kg', unit_price: '12.5' }),
      })).json();
      const ficha = await (await fetch(`${base}/api/fichas`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ product_id: product.id, items: [{ material_id: material.id, quantity: '3' }] }),
      })).json();
      assert.equal(ficha.total_cost, '37.50');
      const approved = await (await fetch(`${base}/api/fichas/${ficha.id}/approve`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
      })).json();
      assert.equal(approved.status, 'Aprobada');
    });

    await reporter.test('Tema: el cambio de tema se aplica y se persiste en el navegador', async () => {
      const { prefs } = await importModule('js/core/prefs.js');
      prefs.set('theme', 'dark');
      assert.equal(document_.documentElement.dataset.theme, 'dark');
      assert.match(window.localStorage.getItem('ipv.prefs.v1') || '', /"theme":"dark"/);
      prefs.set('theme', 'light');
      assert.equal(document_.documentElement.dataset.theme, 'light');
    });

    await reporter.test('Resiliencia: una ruta desconocida se resuelve con la vista predeterminada', async () => {
      app.router.navigate('/ruta-inexistente');
      await waitFor(() => document_.querySelector('#view-root h1'), { label: 'la vista predeterminada' });
      assert.match(document_.querySelector('#view-root h1').textContent, /Tablero de control de costos/);
    });
  } finally {
    reporter.finish();
    await closeSuite({ dom, server, failures: reporter.failures });
  }
}

main().catch((error) => {
  console.error('La prueba no pudo ejecutarse:', error);
  process.exitCode = 1;
});
