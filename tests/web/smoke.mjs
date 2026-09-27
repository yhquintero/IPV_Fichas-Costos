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
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { JSDOM, VirtualConsole } from 'jsdom';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(HERE, '..', '..');
const WEB_ROOT = path.join(REPO_ROOT, 'web');
const PYTHON = process.env.PYTHON || 'python3';

const SERVER_SNIPPET = `
import server
from http.server import ThreadingHTTPServer
server.init_db()
httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
print(f"PORT={httpd.server_port}", flush=True)
httpd.serve_forever()
`;

const results = [];
let failures = 0;

async function test(name, fn) {
  try {
    await fn();
    results.push(`  ✓ ${name}`);
  } catch (error) {
    failures += 1;
    results.push(`  ✗ ${name}\n      → ${error.message}`);
  }
}

function waitFor(check, { timeout = 15000, interval = 40, label = 'condición' } = {}) {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const tick = () => {
      let value;
      try { value = check(); } catch (error) { reject(error); return; }
      if (value) { resolve(value); return; }
      if (Date.now() - started > timeout) { reject(new Error(`Tiempo de espera agotado esperando ${label}`)); return; }
      setTimeout(tick, interval);
    };
    tick();
  });
}

async function startServer(tempDir) {
  const child = spawn(PYTHON, ['-c', SERVER_SNIPPET], {
    cwd: REPO_ROOT,
    env: { ...process.env, PYTHONPATH: REPO_ROOT, IPV_DB_PATH: path.join(tempDir, 'smoke.db') },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  const port = await new Promise((resolve, reject) => {
    let buffer = '';
    const timer = setTimeout(() => reject(new Error('El servidor de prueba no informó el puerto')), 20000);
    child.stdout.on('data', (chunk) => {
      buffer += String(chunk);
      const match = buffer.match(/PORT=(\d+)/);
      if (match) { clearTimeout(timer); resolve(Number(match[1])); }
    });
    child.stderr.on('data', (chunk) => { buffer += String(chunk); });
    child.on('exit', (code) => { clearTimeout(timer); reject(new Error(`El servidor terminó con código ${code}: ${buffer}`)); });
  });
  return { child, base: `http://127.0.0.1:${port}` };
}

function installGlobals(dom, base) {
  const { window } = dom;
  const nativeFetch = globalThis.fetch;
  const globalFetch = (input, init) => {
    const url = typeof input === 'string' && input.startsWith('/') ? `${base}${input}` : input;
    return nativeFetch(url, init);
  };
  const globals = {
    window,
    document: window.document,
    navigator: window.navigator,
    localStorage: window.localStorage,
    sessionStorage: window.sessionStorage,
    location: window.location,
    history: window.history,
    Node: window.Node,
    Element: window.Element,
    HTMLElement: window.HTMLElement,
    SVGElement: window.SVGElement,
    DocumentFragment: window.DocumentFragment,
    CustomEvent: window.CustomEvent,
    Event: window.Event,
    KeyboardEvent: window.KeyboardEvent,
    MouseEvent: window.MouseEvent,
    requestAnimationFrame: window.requestAnimationFrame.bind(window),
    cancelAnimationFrame: window.cancelAnimationFrame.bind(window),
    getComputedStyle: window.getComputedStyle.bind(window),
    fetch: globalFetch,
  };
  Object.entries(globals).forEach(([key, value]) => {
    Object.defineProperty(globalThis, key, { value, configurable: true, writable: true });
  });
  window.print = () => { window.__printCalls = (window.__printCalls || 0) + 1; };
  window.URL.createObjectURL = () => 'blob:prueba';
  window.URL.revokeObjectURL = () => {};
  return window;
}

async function main() {
  const tempDir = mkdtempSync(path.join(tmpdir(), 'ipv-smoke-'));
  const { child, base } = await startServer(tempDir);
  let dom = null;

  try {
    const html = await (await fetch(`${base}/`)).text();
    assert.match(html, /IPV · Fichas y Costos/, 'La interfaz debe servirse en la raíz');
    assert.match(html, /Ing\. Yosvany Hernández Quintero/, 'La portada debe acreditar al autor');

    const virtualConsole = new VirtualConsole();
    virtualConsole.on('jsdomError', (error) => {
      if (/Not implemented/.test(error.message)) return; // scrollTo y similares
      console.error('jsdom:', error.message);
    });
    virtualConsole.on('error', (message) => console.error('Consola del navegador:', message));
    dom = new JSDOM(html, { url: `${base}/resumen`, pretendToBeVisual: true, virtualConsole });
    const window = installGlobals(dom, base);
    const scriptRoot = document.querySelector('script[type="module"]');
    assert.ok(scriptRoot, 'La interfaz debe declarar el módulo de arranque');

    const app = await import(`${pathToFileURL(path.join(WEB_ROOT, 'js/app.js')).href}?t=${Date.now()}`);
    const document_ = window.document;

    await test('Arranque: la aplicación carga los datos y muestra el tablero', async () => {
      await waitFor(() => document_.querySelector('#view-root h1'), { label: 'el tablero' });
      const heading = document_.querySelector('#view-root h1').textContent;
      assert.match(heading, /Tablero de control de costos/);
      const kpis = document_.querySelectorAll('#view-root .kpi');
      assert.ok(kpis.length >= 4, `Se esperaban al menos 4 indicadores, se encontraron ${kpis.length}`);
      assert.ok(document_.querySelector('#view-root .chart-figure svg'), 'El tablero debe incluir un gráfico vectorial');
      await waitFor(() => document_.querySelector('#connection-text').textContent.includes('en línea'),
        { label: 'el indicador de conexión' });
    });

    await test('Navegación: los contadores del menú muestran los totales reales', async () => {
      const products = document_.querySelector('[data-count="products"]').textContent;
      const fichas = document_.querySelector('[data-count="fichas"]').textContent;
      assert.equal(products, '5', 'Debe contarse los 5 productos activos del conjunto inicial');
      assert.equal(fichas, '5', 'Debe contarse las 5 fichas del conjunto inicial');
    });

    await test('Catálogo: la tabla de productos renderiza y filtra resultados', async () => {
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

    await test('Valores del IPV: se muestran precios, vigencia y estados', async () => {
      app.router.navigate('/valores');
      await waitFor(() => document_.querySelectorAll('#view-root table.data tbody tr').length >= 10, { label: 'la tabla de valores' });
      const text = document_.querySelector('#view-root table.data tbody').textContent;
      assert.match(text, /Mano de obra directa/);
      assert.match(text, /Vigente/);
    });

    await test('Fichas: el listado muestra el documento versionado y sus acciones', async () => {
      app.router.navigate('/fichas');
      await waitFor(() => document_.querySelector('#view-root table.data tbody tr'), { label: 'la tabla de fichas' });
      const text = document_.querySelector('#view-root table.data tbody').textContent;
      assert.match(text, /FC-BEB-001-v1/);
      assert.match(text, /Aprobada/);
    });

    await test('Fichas: el enlace profundo abre el panel de detalle con la composición del costo', async () => {
      app.router.navigate('/fichas/1');
      await waitFor(() => document_.querySelector('#overlay-root .drawer'), { label: 'el panel de la ficha' });
      const drawer = document_.querySelector('#overlay-root .drawer');
      assert.match(drawer.textContent, /FC-BEB-001-v1/);
      assert.match(drawer.textContent, /Composición del costo/);
      assert.ok(drawer.querySelector('.share-fill'), 'El detalle debe mostrar la participación de cada componente');
      drawer.querySelector('.drawer-header .icon-btn').click();
      await waitFor(() => !document_.querySelector('#overlay-root .drawer'), { label: 'el cierre del panel' });
    });

    await test('Controles: el informe de validación se muestra con sus comprobaciones', async () => {
      app.router.navigate('/controles');
      await waitFor(() => document_.querySelectorAll('#view-root table.data tbody tr').length >= 2, { label: 'la tabla de controles' });
      const text = document_.querySelector('#view-root table.data tbody').textContent;
      assert.match(text, /IPV-2026-0001/);
      app.router.navigate('/controles/1');
      await waitFor(() => document_.querySelector('#overlay-root .check-list'), { label: 'el informe de validación' });
      assert.match(document_.querySelector('#overlay-root .drawer').textContent, /Comprobación|Estado de la ficha/);
      document_.querySelector('#overlay-root .drawer-header .icon-btn').click();
    });

    await test('Bitácora: se listan los movimientos con su responsable', async () => {
      app.router.navigate('/bitacora');
      await waitFor(() => document_.querySelectorAll('#view-root .timeline-item').length > 0, { label: 'la bitácora' });
      const text = document_.querySelector('#view-root [data-role="list"]').textContent;
      assert.match(text, /Ficha v1 creada/);
    });

    await test('Sistema: se muestra el diagnóstico de la base de datos y del certificado', async () => {
      app.router.navigate('/sistema');
      await waitFor(() => document_.querySelector('#view-root .system-grid'), { label: 'el diagnóstico' });
      const text = document_.querySelector('#view-root').textContent;
      assert.match(text, /SQLite/);
      assert.match(text, /Respaldos/);
      assert.match(text, /Atajos de teclado/);
    });

    await test('Acerca de: se acredita al autor y se describe el alcance', async () => {
      app.router.navigate('/acerca-de');
      await waitFor(() => document_.querySelector('#view-root .about-hero'), { label: 'la vista Acerca de' });
      const text = document_.querySelector('#view-root').textContent;
      assert.match(text, /Ing\. Yosvany Hernández Quintero/);
      assert.match(text, /Diseño, desarrollo e implementación/);
      assert.match(text, /Bitácora de auditoría/);
    });

    await test('Paleta de comandos: se abre, busca en el servidor y navega', async () => {
      const palette = await import(`${pathToFileURL(path.join(WEB_ROOT, 'js/components/command-palette.js')).href}?t=${Date.now()}`);
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

    await test('Documentos: la ficha y el acta de control generan una impresión', async () => {
      const print = await import(`${pathToFileURL(path.join(WEB_ROOT, 'js/components/print.js')).href}?t=${Date.now()}`);
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

    await test('Creación: se registra un producto y una ficha mediante la API pública', async () => {
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
      await waitFor(() => true);
    });

    await test('Tema: el cambio de tema se aplica y se persiste en el navegador', async () => {
      const prefs = await import(`${pathToFileURL(path.join(WEB_ROOT, 'js/core/prefs.js')).href}?t=${Date.now()}`);
      prefs.prefs.set('theme', 'dark');
      assert.equal(document_.documentElement.dataset.theme, 'dark');
      assert.match(window.localStorage.getItem('ipv.prefs.v1') || '', /"theme":"dark"/);
      prefs.prefs.set('theme', 'light');
      assert.equal(document_.documentElement.dataset.theme, 'light');
    });

    await test('Resiliencia: una ruta desconocida se resuelve con la vista predeterminada', async () => {
      app.router.navigate('/ruta-inexistente');
      await waitFor(() => document_.querySelector('#view-root h1'), { label: 'la vista predeterminada' });
      assert.match(document_.querySelector('#view-root h1').textContent, /Tablero de control de costos/);
    });
  } finally {
    // Cierre ordenado: DOM simulado, procesos temporizadores y servidor de prueba.
    try { if (dom) dom.window.close(); } catch { /* sin efecto */ }
    child.kill('SIGTERM');
    await new Promise((resolve) => setTimeout(resolve, 150));
    rmSync(tempDir, { recursive: true, force: true });
  }

  console.log('\nIPV · Fichas y Costos — Prueba de humo del cliente web\n');
  console.log(results.join('\n'));
  console.log(`\n${results.length - failures}/${results.length} comprobaciones superadas.\n`);
  await new Promise((resolve) => process.stdout.write('', resolve));
  process.exit(failures ? 1 : 0);
}

main().catch((error) => {
  console.error('La prueba no pudo ejecutarse:', error);
  process.exitCode = 1;
});
