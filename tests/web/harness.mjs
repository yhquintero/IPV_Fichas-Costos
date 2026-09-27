/**
 * IPV · Fichas y Costos — Utilidades compartidas por las pruebas del cliente web.
 *
 * Levanta el servidor real sobre una base de datos temporal, prepara un DOM
 * simulado (jsdom) con los servicios del navegador y ofrece un reportero de
 * comprobaciones reutilizable por las distintas suites.
 *
 * Garantías de ejecución:
 *  · El servidor de prueba se crea en su propio grupo de procesos y se termina
 *    por completo (grupo incluido) al finalizar, al recibir Ctrl+C o ante un fallo.
 *  · Un vigilante (watchdog) cierra la prueba transcurrido IPV_TEST_TIMEOUT
 *    segundos (240 por omisión), de modo que ninguna ejecución queda colgada.
 *  · Los directorios temporales se eliminan siempre, incluso en salidas abruptas.
 *
 * Autor: Ing. Yosvany Hernández Quintero
 */
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

export const HERE = path.dirname(fileURLToPath(import.meta.url));
export const REPO_ROOT = path.resolve(HERE, '..', '..');
export const WEB_ROOT = path.join(REPO_ROOT, 'web');
export const PYTHON = process.env.PYTHON || 'python3';

const WATCHDOG_MS = Number(process.env.IPV_TEST_TIMEOUT || 240000);

/* -------------------------------------------------------------------------- */
/* Dependencias                                                               */
/* -------------------------------------------------------------------------- */
let JSDOM;
let VirtualConsole;
try {
  ({ JSDOM, VirtualConsole } = await import('jsdom'));
} catch {
  console.error([
    '',
    'No se encontró la dependencia «jsdom», necesaria para simular el navegador.',
    'Instálela una sola vez con:',
    '',
    '    cd tests/web && npm install',
    '',
    'Requiere Node 18 o superior.',
    '',
  ].join('\n'));
  process.exit(2);
}

/* -------------------------------------------------------------------------- */
/* Limpieza garantizada                                                       */
/* -------------------------------------------------------------------------- */
/** Servidores y directorios temporales creados por la suite en curso. */
const registry = { children: new Set(), dirs: new Set() };
let cleaned = false;

/** Termina el servidor de prueba con su grupo de procesos y borra lo temporal. */
export function cleanup({ silent = false } = {}) {
  if (cleaned) return;
  cleaned = true;
  for (const child of registry.children) {
    try {
      if (child.pid && !child.killed) process.kill(-child.pid, 'SIGKILL'); // grupo completo
    } catch {
      try { child.kill('SIGKILL'); } catch { /* ya terminado */ }
    }
  }
  registry.children.clear();
  for (const dir of registry.dirs) {
    try { rmSync(dir, { recursive: true, force: true }); } catch { /* sin efecto */ }
  }
  registry.dirs.clear();
  if (!silent) process.stderr.write('');
}

process.on('exit', () => cleanup({ silent: true }));
for (const signal of ['SIGINT', 'SIGTERM', 'SIGHUP']) {
  process.on(signal, () => {
    console.error(`\nPrueba interrumpida (${signal}): se detienen los servidores de prueba y se limpian los archivos temporales.`);
    cleanup({ silent: true });
    process.exit(130);
  });
}
process.on('uncaughtException', (error) => {
  console.error('\nFallo inesperado en la prueba:', error?.message || error);
  cleanup({ silent: true });
  process.exit(1);
});
process.on('unhandledRejection', (reason) => {
  console.error('\nPromesa rechazada sin manejar en la prueba:', reason?.message || reason);
  cleanup({ silent: true });
  process.exit(1);
});

/* -------------------------------------------------------------------------- */
/* Vigilante                                                                  */
/* -------------------------------------------------------------------------- */
const watchdog = setTimeout(() => {
  console.error([
    '',
    `La prueba superó el tiempo máximo de ${Math.round(WATCHDOG_MS / 1000)} s y se detuvo automáticamente.`,
    'No es necesario interrumpirla a mano. Para ampliar el límite use la variable IPV_TEST_TIMEOUT.',
    '',
  ].join('\n'));
  cleanup({ silent: true });
  process.exit(3);
}, WATCHDOG_MS);
if (typeof watchdog.unref === 'function') watchdog.unref();

const SERVER_SNIPPET = `
import server
from http.server import ThreadingHTTPServer
server.init_db()
httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
print(f"PORT={httpd.server_port}", flush=True)
httpd.serve_forever()
`;

/** Espera a que una condición se cumpla, con reintentos. */
export function waitFor(check, { timeout = 15000, interval = 40, label = 'condición' } = {}) {
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

/** Pausa auxiliar para dejar que el cliente reaccione a un evento. */
export const settle = (ms = 350) => new Promise((resolve) => setTimeout(resolve, ms));

/** Reportero de comprobaciones: ejecuta cada prueba y resume el resultado. */
export function createReporter(title) {
  const results = [];
  let failures = 0;
  return {
    results,
    get failures() { return failures; },
    async test(name, fn) {
      try {
        await fn();
        results.push(`  ✓ ${name}`);
      } catch (error) {
        failures += 1;
        results.push(`  ✗ ${name}\n      → ${error.message}`);
      }
    },
    finish() {
      console.log(`\n${title}\n`);
      console.log(results.join('\n'));
      console.log(`\n${results.length - failures}/${results.length} comprobaciones superadas.\n`);
    },
  };
}

/** Inicia `server.py` con una base de datos temporal y devuelve su dirección. */
export async function startServer() {
  const tempDir = mkdtempSync(path.join(tmpdir(), 'ipv-web-'));
  registry.dirs.add(tempDir);
  const child = spawn(PYTHON, ['-c', SERVER_SNIPPET], {
    cwd: REPO_ROOT,
    env: { ...process.env, PYTHONPATH: REPO_ROOT, IPV_DB_PATH: path.join(tempDir, 'prueba.db') },
    stdio: ['ignore', 'pipe', 'pipe'],
    detached: true, // grupo propio: se puede terminar por completo, sin huérfanos
  });
  registry.children.add(child);

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
  return { child, base: `http://127.0.0.1:${port}`, tempDir };
}

/** Detiene el servidor de prueba y elimina sus archivos temporales. */
export async function stopServer({ child, tempDir } = {}) {
  if (child && child.pid) {
    try { process.kill(-child.pid, 'SIGTERM'); } catch { try { child.kill('SIGTERM'); } catch { /* ya terminado */ } }
  }
  await settle(150);
  if (child && child.pid) {
    try { process.kill(-child.pid, 'SIGKILL'); } catch { /* ya terminado */ }
  }
  registry.children.delete(child);
  if (tempDir) {
    registry.dirs.delete(tempDir);
    rmSync(tempDir, { recursive: true, force: true });
  }
}

/**
 * Carga el cliente en un DOM simulado: descarga el documento, publica los
 * objetos globales del navegador y arranca el módulo principal de la interfaz.
 */
export async function openClient(base, { route = '/resumen', quiet = true, beforeBoot = null } = {}) {
  const html = await (await fetch(`${base}/`)).text();
  const virtualConsole = new VirtualConsole();
  virtualConsole.on('jsdomError', (error) => {
    if (/Not implemented/.test(error.message)) return; // scrollTo y similares
    if (!quiet) console.error('jsdom:', error.message);
  });
  virtualConsole.on('error', (message) => { if (!quiet) console.error('Consola del navegador:', message); });

  const dom = new JSDOM(html, { url: `${base}${route}`, pretendToBeVisual: true, virtualConsole });
  const { window } = dom;
  const nativeFetch = globalThis.fetch;
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
    fetch: (input, init) => nativeFetch(
      typeof input === 'string' && input.startsWith('/') ? `${base}${input}` : input, init,
    ),
  };
  Object.entries(globals).forEach(([key, value]) => {
    Object.defineProperty(globalThis, key, { value, configurable: true, writable: true });
  });
  window.print = () => { window.__printCalls = (window.__printCalls || 0) + 1; };
  window.URL.createObjectURL = () => 'blob:prueba';
  window.URL.revokeObjectURL = () => {};
  if (typeof beforeBoot === 'function') beforeBoot({ window, document: window.document, base });

  const app = await import(`${pathToFileURL(path.join(WEB_ROOT, 'js/app.js')).href}?t=${Date.now()}`);
  return { dom, window, document: window.document, app, html };
}

/** Importa un módulo del cliente con caché renovada. */
export function importModule(relativePath) {
  return import(`${pathToFileURL(path.join(WEB_ROOT, relativePath)).href}?t=${Date.now()}`);
}

/** Nombre accesible de un control, según las reglas de ARIA. */
export function accessibleName(element, document_) {
  const explicit = element.getAttribute('aria-label') || element.getAttribute('title');
  if (explicit && explicit.trim()) return explicit.trim();
  const labelledby = element.getAttribute('aria-labelledby');
  if (labelledby) {
    const target = document_.getElementById(labelledby);
    const label = target ? target.textContent.replace(/\s+/g, ' ').trim() : '';
    if (label) return label;
  }
  const inner = element.textContent.replace(/\s+/g, ' ').trim();
  if (inner) return inner;
  const image = element.querySelector('img[alt]');
  if (image && image.getAttribute('alt')) return image.getAttribute('alt');
  return '';
}

/** Cierra la suite de forma ordenada y devuelve el código de salida. */
export async function closeSuite({ dom, server, failures }) {
  try { if (dom) dom.window.close(); } catch { /* sin efecto */ }
  await stopServer(server);
  cleanup({ silent: true });
  await new Promise((resolve) => process.stdout.write('', resolve));
  process.exit(failures ? 1 : 0);
}

export { assert };
