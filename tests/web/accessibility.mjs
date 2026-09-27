/**
 * IPV · Fichas y Costos — Auditoría automática de accesibilidad del cliente web.
 *
 * Recorre todas las vistas, los enlaces profundos a los paneles de detalle y
 * los formularios, y comprueba que cada control tenga nombre accesible, que
 * cada campo esté etiquetado, que los encabezados y las tablas sean coherentes
 * y que los gráficos no interfieran con la tecnología de asistencia.
 *
 * Uso:
 *   cd tests/web && npm install && npm run test:a11y
 *
 * Requiere Node 18 o superior y Python 3.10 o superior disponibles en el PATH.
 */
import {
  accessibleName, assert, closeSuite, createReporter, openClient, settle, startServer, waitFor,
} from './harness.mjs';

const REPORTER_TITLE = 'IPV · Fichas y Costos — Auditoría de accesibilidad del cliente web';

const VIEWS = [
  ['/resumen', 'Tablero de control'],
  ['/productos', 'Productos y servicios'],
  ['/valores', 'Valores del IPV'],
  ['/fichas', 'Fichas de costo'],
  ['/controles', 'Controles de IPV'],
  ['/bitacora', 'Bitácora de auditoría'],
  ['/sistema', 'Sistema y respaldos'],
  ['/acerca-de', 'Acerca de'],
];

const DEEP_LINKS = [
  ['/fichas/1', 'Panel de la ficha de costo'],
  ['/controles/1', 'Panel del control de IPV'],
];

const FORMS = [
  ['/productos?nueva=1', 'Alta de producto'],
  ['/valores?nueva=1', 'Alta de valor del IPV'],
  ['/fichas?nueva=1', 'Alta de ficha de costo'],
];

/** Nodos interactivos y campos de un contenedor, omitiendo los ocultos. */
function auditScope(scope, label, problems) {
  const document_ = globalThis.document;

  for (const element of scope.querySelectorAll('button, a[href], [role="button"], [role="tab"]')) {
    if (element.getAttribute('aria-hidden') === 'true') continue;
    if (!accessibleName(element, document_)) {
      problems.push(`${label}: control sin nombre accesible (${element.tagName.toLowerCase()}${element.className ? `.${String(element.className).split(' ')[0]}` : ''})`);
    }
  }

  for (const element of scope.querySelectorAll('input:not([type="hidden"]), select, textarea')) {
    if (element.getAttribute('aria-hidden') === 'true') continue;
    const id = element.getAttribute('id');
    const labelled = (id && document_.querySelector(`label[for="${id}"]`))
      || element.closest('label')
      || element.getAttribute('aria-label');
    if (!labelled) problems.push(`${label}: campo sin etiqueta (${element.getAttribute('name') || element.type || element.tagName.toLowerCase()})`);
  }

  for (const svg of scope.querySelectorAll('svg')) {
    const parent = svg.parentElement;
    const hidden = svg.getAttribute('aria-hidden') === 'true' || (parent && parent.getAttribute('aria-hidden') === 'true');
    const named = svg.querySelector('title') || svg.getAttribute('role') === 'img' || svg.getAttribute('aria-label');
    if (!hidden && !named) problems.push(`${label}: gráfico sin descripción ni marca decorativa`);
  }

  for (const image of scope.querySelectorAll('img')) {
    if (image.getAttribute('alt') === null) problems.push(`${label}: imagen sin atributo alt`);
  }

  for (const table of scope.querySelectorAll('table')) {
    if (!table.querySelector('thead th')) problems.push(`${label}: tabla sin encabezados de columna`);
  }
}

/** Comprueba la estructura del contenedor principal de una vista. */
function auditStructure(scope, label, problems) {
  const headings = [...scope.querySelectorAll('h1')];
  if (headings.length !== 1) problems.push(`${label}: se esperaba un solo encabezado de nivel 1, hay ${headings.length}`);
}

async function main() {
  const server = await startServer();
  const reporter = createReporter(REPORTER_TITLE);
  let dom = null;

  try {
    const client = await openClient(server.base);
    dom = client.dom;
    const { document: document_, window, app } = client;

    await reporter.test('Estructura general: ayuda de salto, idioma y regiones principales', async () => {
      assert.equal(document_.documentElement.lang, 'es', 'El documento debe declarar el idioma español');
      assert.ok(document_.querySelector('.skip-link'), 'Debe existir el enlace para saltar al contenido');
      assert.ok(document_.querySelector('main#main-content'), 'Debe existir la región principal identificada');
      assert.ok(document_.querySelector('nav[aria-label]'), 'La navegación debe estar etiquetada');
      await waitFor(() => document_.querySelector('#view-root h1'), { label: 'el contenido inicial' });
    });

    await reporter.test('Vistas: controles con nombre accesible, campos etiquetados y tablas encabezadas', async () => {
      const problems = [];
      for (const [route, label] of VIEWS) {
        app.router.navigate(route);
        await waitFor(() => document_.querySelector('#view-root h1'), { label: `la vista ${label}` });
        await settle(320);
        const root = document_.querySelector('#view-root');
        auditStructure(root, label, problems);
        auditScope(root, label, problems);
      }
      assert.equal(problems.length, 0, `\n      · ${problems.join('\n      · ')}`);
    });

    await reporter.test('Paneles de detalle: los enlaces profundos abren diálogos accesibles', async () => {
      const problems = [];
      for (const [route, label] of DEEP_LINKS) {
        app.router.navigate(route);
        await waitFor(() => document_.querySelector('#overlay-root [role="dialog"]'), { label });
        await settle(250);
        const dialog = document_.querySelector('#overlay-root [role="dialog"]');
        if (!dialog.getAttribute('aria-labelledby') && !dialog.getAttribute('aria-label')) {
          problems.push(`${label}: el diálogo no tiene título accesible`);
        }
        if (dialog.getAttribute('aria-modal') !== 'true') {
          problems.push(`${label}: el diálogo no declara aria-modal`);
        }
        auditScope(dialog, label, problems);
        document_.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        await waitFor(() => !document_.querySelector('#overlay-root [role="dialog"]'), { label: 'el cierre del panel' });
      }
      assert.equal(problems.length, 0, `\n      · ${problems.join('\n      · ')}`);
    });

    await reporter.test('Formularios: los diálogos de alta etiquetan todos sus campos', async () => {
      const problems = [];
      for (const [route, label] of FORMS) {
        app.router.navigate(route);
        await waitFor(() => document_.querySelector('#overlay-root [role="dialog"]'), { label });
        await settle(250);
        auditScope(document_.querySelector('#overlay-root [role="dialog"]'), label, problems);
        document_.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        await waitFor(() => !document_.querySelector('#overlay-root [role="dialog"]'), { label: 'el cierre del formulario' });
      }
      assert.equal(problems.length, 0, `\n      · ${problems.join('\n      · ')}`);
    });

    await reporter.test('Identificadores: no se repiten en la página', async () => {
      const ids = [...document_.querySelectorAll('[id]')].map((element) => element.id);
      const duplicated = [...new Set(ids.filter((id, index) => ids.indexOf(id) !== index))];
      assert.equal(duplicated.length, 0, `Identificadores duplicados: ${duplicated.join(', ')}`);
    });

    await reporter.test('Navegación: el elemento activo se anuncia con aria-current', async () => {
      app.router.navigate('/valores');
      await waitFor(() => document_.querySelector('#view-root h1'), { label: 'la vista de valores' });
      await settle(250);
      const active = document_.querySelectorAll('.nav-item[aria-current="page"]');
      assert.equal(active.length, 1, `Se esperaba un único elemento activo, se encontraron ${active.length}`);
      assert.match(active[0].getAttribute('href'), /valores/);
    });

    await reporter.test('Teclado: los atajos globales responden sin ratón', async () => {
      document_.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'g', bubbles: true }));
      document_.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'f', bubbles: true }));
      await waitFor(() => document_.querySelector('#view-root h1'), { label: 'la navegación por atajos' });
      await settle(300);
      assert.match(document_.querySelector('#view-root h1').textContent, /Fichas de costo/);
      assert.match(document_.title, /Fichas de costo · IPV · Fichas y Costos/);
    });
  } finally {
    reporter.finish();
    await closeSuite({ dom, server, failures: reporter.failures });
  }
}

main().catch((error) => {
  console.error('La auditoría no pudo ejecutarse:', error);
  process.exitCode = 1;
});
