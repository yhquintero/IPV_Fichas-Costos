/**
 * IPV · Fichas y Costos — Resiliencia del cliente web.
 *
 * Comprueba que la interfaz siga siendo utilizable en entornos restringidos:
 * almacenamiento local bloqueado (modo privado o página incrustada), historial
 * del navegador no disponible, portapapeles sin permiso, impresión bloqueada y
 * servicio momentáneamente inaccesible con recuperación mediante «Reintentar».
 *
 * Uso:
 *   cd tests/web && npm install && npm run test:resilience
 *
 * Requiere Node 18 o superior y Python 3.10 o superior disponibles en el PATH.
 */
import {
  assert, closeSuite, createReporter, importModule, openClient, startServer, waitFor,
} from './harness.mjs';

const REPORTER_TITLE = 'IPV · Fichas y Costos — Resiliencia del cliente web';

/** Sustituye un método y devuelve la función que lo restaura. */
function replaceMethod(target, name, replacement) {
  const original = target[name];
  target[name] = replacement;
  return () => { target[name] = original; };
}

async function main() {
  const server = await startServer();
  const reporter = createReporter(REPORTER_TITLE);
  const doms = [];
  const track = (client) => { doms.push(client.dom); return client; };

  try {
    await reporter.test('Almacenamiento bloqueado: la aplicación arranca sin poder guardar preferencias', async () => {
      const client = track(await openClient(server.base, {
        beforeBoot({ window }) {
          Object.defineProperty(window, 'localStorage', {
            configurable: true,
            get: () => { throw new window.DOMException('almacenamiento bloqueado', 'SecurityError'); },
          });
        },
      }));
      const document_ = client.document;
      await waitFor(() => document_.querySelector('#view-root h1'), { label: 'el tablero sin almacenamiento' });
      assert.match(document_.querySelector('#view-root h1').textContent, /Tablero de control de costos/);
      assert.ok(document_.querySelectorAll('#view-root .kpi').length >= 4, 'Los indicadores deben mostrarse igualmente');
    });

    await reporter.test('Historial bloqueado: la navegación entre vistas continúa funcionando', async () => {
      const client = track(await openClient(server.base, {
        beforeBoot({ window }) {
          const blocked = () => { throw new window.DOMException('historial bloqueado', 'SecurityError'); };
          window.history.pushState = blocked;
          window.history.replaceState = blocked;
        },
      }));
      const document_ = client.document;
      await waitFor(() => document_.querySelector('#view-root h1'), { label: 'el tablero sin historial' });
      client.app.router.navigate('/productos');
      await waitFor(() => /Productos y servicios/.test(document_.querySelector('#view-root h1')?.textContent || ''),
        { label: 'la vista de productos' });
      client.app.router.navigate('/fichas');
      await waitFor(() => /Fichas de costo/.test(document_.querySelector('#view-root h1')?.textContent || ''),
        { label: 'la vista de fichas' });
    });

    await reporter.test('Servicio interrumpido: se informa el fallo y «Reintentar» recupera la sesión', async () => {
      const client = track(await openClient(server.base));
      const document_ = client.document;
      await waitFor(() => document_.querySelector('#view-root h1'), { label: 'el contenido inicial' });

      const realFetch = globalThis.fetch;
      globalThis.fetch = () => Promise.reject(new TypeError('Failed to fetch'));
      try {
        await client.app.bootstrap(true);
      } finally {
        globalThis.fetch = realFetch;
      }

      const fatal = document_.querySelector('#view-root .fatal');
      assert.ok(fatal, 'Debe mostrarse la pantalla de error cuando el servicio no responde');
      assert.match(fatal.textContent, /No se pudo cargar la información/);
      const retry = [...fatal.querySelectorAll('button')].find((node) => /Reintentar/.test(node.textContent));
      assert.ok(retry, 'La pantalla de error debe ofrecer el botón «Reintentar»');

      retry.click();
      await waitFor(() => /Tablero de control de costos/.test(document_.querySelector('#view-root h1')?.textContent || ''),
        { label: 'la recuperación de la sesión' });
      assert.ok(document_.querySelectorAll('#view-root .kpi').length >= 4, 'Los indicadores deben volver tras la recuperación');
    });

    await reporter.test('Portapapeles sin permiso: se usa el mecanismo alternativo y se confirma el copiado', async () => {
      const client = track(await openClient(server.base));
      const document_ = client.document;
      await waitFor(() => document_.querySelector('#view-root h1'), { label: 'el contenido inicial' });

      const { copyText } = await importModule('js/core/ui.js');
      const restoreExec = replaceMethod(document_, 'execCommand', () => true);
      const hadClipboard = 'clipboard' in client.window.navigator;
      const originalClipboard = client.window.navigator.clipboard;
      Object.defineProperty(client.window.navigator, 'clipboard', { configurable: true, value: undefined });
      try {
        await copyText('IPV-2026-0001');
      } finally {
        restoreExec();
        if (hadClipboard) Object.defineProperty(client.window.navigator, 'clipboard', { configurable: true, value: originalClipboard });
      }
      await waitFor(() => /copiad/i.test(document_.querySelector('#toast-stack').textContent),
        { label: 'el aviso de copiado' });
    });

    await reporter.test('Impresión bloqueada: el documento se retira y la interfaz sigue operativa', async () => {
      const client = track(await openClient(server.base));
      const document_ = client.document;
      await waitFor(() => document_.querySelector('#view-root h1'), { label: 'el contenido inicial' });

      const print = await importModule('js/components/print.js');
      const original = client.window.print;
      client.window.print = () => { throw new client.window.DOMException('impresión bloqueada', 'SecurityError'); };
      try {
        const ficha = await (await fetch(`${server.base}/api/fichas/1`)).json();
        print.printFicha(ficha);
        await waitFor(() => document_.querySelector('#print-root .doc'), { label: 'el documento generado' });
        await waitFor(() => !document_.querySelector('#print-root .doc'), { label: 'la limpieza del documento', timeout: 6000 });
        await waitFor(() => /imprimir/i.test(document_.querySelector('#toast-stack').textContent),
          { label: 'el aviso sobre la impresión bloqueada' });
      } finally {
        client.window.print = original;
      }
      assert.ok(document_.querySelector('#view-root h1'), 'La interfaz debe seguir operativa después del bloqueo');
    });
  } finally {
    reporter.finish();
    for (const dom of doms) { try { dom.window.close(); } catch { /* sin efecto */ } }
    await closeSuite({ server, failures: reporter.failures });
  }
}

main().catch((error) => {
  console.error('La prueba de resiliencia no pudo ejecutarse:', error);
  process.exitCode = 1;
});
