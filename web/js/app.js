/**
 * IPV · Fichas y Costos
 * Punto de entrada del cliente web: arranque, enrutado y servicios comunes.
 * Autor: Ing. Yosvany Hernández Quintero
 */

import { clear, el, frag, hydrateIcons, icon, mount, qs, qsa } from './core/dom.js';
import { prefs, resolvedTheme } from './core/prefs.js';
import { selectors, store } from './core/store.js';
import { api, describeError } from './core/api.js';
import { data } from './core/data.js';
import { progress, toast, notifyError, openModal, field, readForm, button } from './core/ui.js';
import { createRouter } from './core/router.js';
import { openCommandPalette } from './components/command-palette.js';
import { dashboardView } from './views/dashboard.js';
import { productsView } from './views/products.js';
import { materialsView } from './views/materials.js';
import { fichasView } from './views/fichas.js';
import { controlsView } from './views/controls.js';
import { auditView } from './views/audit.js';
import { systemView } from './views/system.js';
import { aboutView } from './views/about.js';

const APP_TITLE = 'IPV · Fichas y Costos';

const VIEWS = {
  dashboard: dashboardView,
  products: productsView,
  materials: materialsView,
  fichas: fichasView,
  controls: controlsView,
  audit: auditView,
  system: systemView,
  about: aboutView,
};

const ROUTES = [
  { path: '/', view: 'dashboard', title: 'Resumen' },
  { path: '/resumen', view: 'dashboard', title: 'Resumen' },
  { path: '/productos', view: 'products', title: 'Productos y servicios' },
  { path: '/valores', view: 'materials', title: 'Valores del IPV' },
  { path: '/fichas', view: 'fichas', title: 'Fichas de costo' },
  { path: '/fichas/:id', view: 'fichas', title: 'Ficha de costo' },
  { path: '/controles', view: 'controls', title: 'Controles de IPV' },
  { path: '/controles/:id', view: 'controls', title: 'Control de IPV' },
  { path: '/bitacora', view: 'audit', title: 'Bitácora de auditoría' },
  { path: '/sistema', view: 'system', title: 'Sistema y respaldos' },
  { path: '/acerca-de', view: 'about', title: 'Acerca de' },
];

let currentView = null;
let currentViewId = null;

/* -------------------------------------------------------------------------- */
/* Enrutado                                                                    */
/* -------------------------------------------------------------------------- */
const router = createRouter({
  routes: ROUTES,
  fallback: '/resumen',
  onNavigate: (match) => renderRoute(match),
});

function renderRoute(match) {
  const { route, params, path, query } = match;
  const definition = VIEWS[route.view];
  const root = qs('#view-root');
  if (!definition || !root) return;

  const ctx = {
    store,
    data,
    api,
    prefs,
    navigate: (target, options) => router.navigate(target, options),
    route: { path, view: route.view, params, query },
  };

  if (currentView && currentViewId !== route.view) {
    try { currentView.unmount(); } catch (error) { console.error('Error al desmontar la vista:', error); }
    currentView = null;
    clear(root);
  }
  if (currentView && currentViewId === route.view && typeof currentView.receiveRoute === 'function') {
    currentView.receiveRoute({ params, query, path });
  }

  store.set({ route: { path, view: route.view, params, query } });
  document.title = `${route.title} · ${APP_TITLE}`;
  const crumb = qs('#breadcrumb-current');
  if (crumb) crumb.textContent = route.title;
  qsa('[data-route]').forEach((link) => {
    const href = link.getAttribute('href');
    const active = href === path || (path.startsWith(`${href}/`) && href !== '/');
    if (link.classList.contains('nav-item')) {
      if (active) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    }
  });
  prefs.set('lastRoute', path === '/' ? '/resumen' : path);
  if (document.body.classList.contains('sidebar-open')) toggleSidebar(false);

  if (currentView && currentViewId === route.view) {
    window.scrollTo({ top: 0, behavior: 'smooth' });
    return;
  }

  try {
    currentView = definition;
    currentViewId = route.view;
    definition.mount(root, ctx);
    window.scrollTo({ top: 0, behavior: 'auto' });
    const heading = root.querySelector('h1');
    if (heading) heading.setAttribute('tabindex', '-1');
  } catch (error) {
    console.error('Error al montar la vista:', error);
    mount(root, fatalScreen(describeError(error)));
  }
}

/* -------------------------------------------------------------------------- */
/* Interfaz global                                                             */
/* -------------------------------------------------------------------------- */
function toggleSidebar(force) {
  const sidebar = qs('#sidebar');
  const button = qs('#sidebar-toggle');
  if (!sidebar) return;
  const open = typeof force === 'boolean' ? force : !sidebar.classList.contains('is-open');
  sidebar.classList.toggle('is-open', open);
  document.body.classList.toggle('sidebar-open', open);
  if (button) button.setAttribute('aria-expanded', String(open));
}

function syncTheme() {
  const button = qs('#theme-btn');
  if (!button) return;
  clear(button);
  button.append(icon(resolvedTheme() === 'dark' ? 'sun' : 'moon', { size: 18 }));
  button.setAttribute('title', resolvedTheme() === 'dark' ? 'Cambiar a tema claro' : 'Cambiar a tema oscuro');
}

function syncCounts(state) {
  const counts = selectors.counts(state);
  const map = { products: counts.products, materials: counts.materials, fichas: counts.fichas };
  qsa('[data-count]').forEach((node) => {
    const value = map[node.dataset.count] ?? 0;
    node.textContent = String(value);
    node.hidden = !value;
  });
  const badge = qs('[data-badge="controls"]');
  if (badge) badge.hidden = counts.pending === 0;
}

function syncConnection(connection) {
  const dot = qs('#connection-dot');
  const text = qs('#connection-text');
  const pill = qs('#connection-pill');
  if (dot) {
    dot.className = `status-dot status-dot--${connection.checking ? 'checking' : connection.online ? 'online' : 'offline'}`;
  }
  if (text) {
    const label = connection.online
      ? (connection.latency !== null ? `Servicio en línea · ${connection.latency} ms` : 'Servicio en línea')
      : (connection.status || 'Sin conexión');
    text.textContent = label;
  }
  if (pill) {
    pill.setAttribute('title', connection.online
      ? `Base de datos SQLite disponible${connection.checkedAt ? ` · comprobado ${new Date(connection.checkedAt).toLocaleTimeString('es')}` : ''}`
      : 'No se pudo comunicar con el servicio. Verifique que el servidor esté iniciado.');
  }
}

function operatorInitials(name) {
  const parts = String(name || '').trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return 'OL';
  return `${parts[0][0] || ''}${parts.length > 1 ? parts[parts.length - 1][0] : ''}`.toUpperCase();
}

function syncOperator() {
  const name = prefs.get('operator');
  const label = qs('#operator-name');
  const initials = qs('#operator-initials');
  if (label) label.textContent = name;
  if (initials) initials.textContent = operatorInitials(name);
}

function openOperatorModal() {
  const form = el('form', {}, field({
    label: 'Nombre del operador', name: 'operator', required: true, value: prefs.get('operator'),
    hint: 'Se registra como responsable en la bitácora, en la aprobación de fichas y en las validaciones.',
  }));
  const modal = openModal({
    title: 'Operador del sistema',
    subtitle: 'Identificación del responsable de las operaciones',
    size: 'narrow',
    content: form,
    actions: [
      el('button', { class: 'btn btn--secondary', type: 'button', text: 'Cancelar', on: { click: () => modal.close() } }),
      el('button', {
        class: 'btn btn--primary', type: 'button', text: 'Guardar',
        on: {
          click: () => {
            if (!form.reportValidity()) return;
            const values = readForm(form);
            prefs.set('operator', values.operator.trim());
            syncOperator();
            modal.close();
            toast(`Operador registrado: ${values.operator.trim()}`, { type: 'success' });
          },
        },
      }),
    ],
  });
}

function fatalScreen(message) {
  return el('div', { class: 'fatal' },
    icon('alert', { size: 34 }),
    el('h1', { style: { fontSize: 'var(--text-xl)' }, text: 'No se pudo cargar la información' }),
    el('p', { text: message || 'El servicio no respondió. Compruebe que el servidor esté iniciado y vuelva a intentarlo.' }),
    el('div', { class: 'row', style: { justifyContent: 'center' } },
      button('Reintentar', { variant: 'primary', iconName: 'refresh', onClick: () => bootstrap(true) })));
}

/* -------------------------------------------------------------------------- */
/* Atajos de teclado                                                           */
/* -------------------------------------------------------------------------- */
function bindShortcuts() {
  let waitingForNavigation = false;
  const NAV_KEYS = {
    r: '/resumen', p: '/productos', v: '/valores', f: '/fichas', c: '/controles',
    b: '/bitacora', s: '/sistema', a: '/acerca-de',
  };

  document.addEventListener('keydown', (event) => {
    const target = event.target;
    const typing = target instanceof Element
      && (target.matches('input, textarea, select') || target.isContentEditable);

    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault();
      openCommandPalette({ navigate: router.navigate, commands: appCommands() });
      return;
    }
    if (typing || event.ctrlKey || event.metaKey || event.altKey) { waitingForNavigation = false; return; }
    if (event.key === 'Escape') { waitingForNavigation = false; return; }

    if (waitingForNavigation) {
      const path = NAV_KEYS[event.key.toLowerCase()];
      waitingForNavigation = false;
      if (path) { event.preventDefault(); router.navigate(path); }
      return;
    }
    if (event.key.toLowerCase() === 'g') { waitingForNavigation = true; setTimeout(() => { waitingForNavigation = false; }, 1200); return; }
    if (event.key.toLowerCase() === 'r') { event.preventDefault(); refreshAll(); return; }
    if (event.key.toLowerCase() === 't') { event.preventDefault(); prefs.toggleTheme(); syncTheme(); }
  });
}

function appCommands() {
  return [
    {
      id: 'new-ficha', label: 'Nueva ficha de costo', iconName: 'file', keywords: 'crear ficha costo',
      hint: 'Costeo',
      run: () => { router.navigate('/fichas', { query: { nueva: '1' } }); },
    },
    {
      id: 'new-product', label: 'Nuevo producto o servicio', iconName: 'package', keywords: 'crear catalogo',
      hint: 'Catálogo',
      run: () => { router.navigate('/productos', { query: { nueva: '1' } }); },
    },
    {
      id: 'new-material', label: 'Registrar valor del IPV', iconName: 'tag', keywords: 'precio insumo valor',
      hint: 'Valores',
      run: () => { router.navigate('/valores', { query: { nueva: '1' } }); },
    },
    {
      id: 'backup', label: 'Descargar respaldo de la información', iconName: 'download', keywords: 'backup copia seguridad',
      hint: 'Sistema',
      run: () => { router.navigate('/sistema'); },
    },
    {
      id: 'refresh', label: 'Actualizar los datos', iconName: 'refresh', keywords: 'recargar',
      hint: 'General',
      run: () => refreshAll(),
    },
  ];
}

async function refreshAll() {
  progress.start();
  try {
    await data.reload({ silent: false });
    toast('Información actualizada desde el servidor.', { type: 'success', duration: 2600 });
  } catch {
    /* el error se informa desde data.reload */
  } finally {
    progress.done();
  }
}

/* -------------------------------------------------------------------------- */
/* Arranque                                                                    */
/* -------------------------------------------------------------------------- */
async function bootstrap(isRetry = false) {
  const root = qs('#view-root');
  if (!root) return;
  hydrateIcons(document);
  syncTheme();
  syncOperator();
  syncCounts(store.get());
  syncConnection(store.get().connection);
  mount(root, el('div', { class: 'stack' },
    el('div', { class: 'skeleton', style: { height: '76px' } }),
    el('div', { class: 'kpi-grid' },
      ...Array.from({ length: 4 }, () => el('div', { class: 'skeleton', style: { height: '130px' } }))),
    el('div', { class: 'skeleton', style: { height: '300px' } })));

  try {
    await data.bootstrap();
    const meta = store.get().meta;
    const versionLabel = qs('#footer-version');
    if (versionLabel && meta) versionLabel.textContent = meta.application.version;
    if (isRetry) toast('Conexión restablecida con el servicio.', { type: 'success' });
    data.startMonitoring();
  } catch (error) {
    mount(root, fatalScreen(describeError(error)));
    notifyError(describeError(error), 'Sin conexión con el servicio');
    return;
  }

  const initial = window.location.pathname === '/' ? (prefs.get('lastRoute') || '/resumen') : window.location.pathname;
  if (initial !== window.location.pathname) router.navigate(initial, { replace: true });
  else renderRoute(router.current());
}

function wireInterface() {
  const sidebarToggle = qs('#sidebar-toggle');
  if (sidebarToggle) sidebarToggle.addEventListener('click', () => toggleSidebar());
  const themeButton = qs('#theme-btn');
  if (themeButton) themeButton.addEventListener('click', () => { prefs.toggleTheme(); syncTheme(); });
  const refreshButton = qs('#refresh-btn');
  if (refreshButton) refreshButton.addEventListener('click', refreshAll);
  const commandTrigger = qs('#command-trigger');
  if (commandTrigger) {
    commandTrigger.addEventListener('click', () => openCommandPalette({ navigate: router.navigate, commands: appCommands() }));
  }
  const operatorButton = qs('#operator-btn');
  if (operatorButton) operatorButton.addEventListener('click', openOperatorModal);
  qsa('[data-action="about"]').forEach((node) => node.addEventListener('click', () => router.navigate('/acerca-de')));
  document.addEventListener('click', (event) => {
    const sidebar = qs('#sidebar');
    if (!sidebar || !sidebar.classList.contains('is-open')) return;
    if (event.target instanceof Element && (sidebar.contains(event.target) || event.target.closest('#sidebar-toggle'))) return;
    toggleSidebar(false);
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && document.body.classList.contains('sidebar-open')) toggleSidebar(false);
  });

  store.subscribe((state) => { syncCounts(state); syncConnection(state.connection); });
  prefs.subscribe(() => { syncTheme(); syncOperator(); });
  // Evita que el navegador restaure la posición de desplazamiento entre vistas.
  if ('scrollRestoration' in window.history) window.history.scrollRestoration = 'manual';
}

function main() {
  hydrateIcons(document);
  wireInterface();
  bindShortcuts();
  bootstrap();
  router.start();
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', main, { once: true });
else main();

export { router, bootstrap, frag };
