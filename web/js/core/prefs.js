/**
 * IPV · Fichas y Costos
 * Preferencias del usuario persistidas en el navegador.
 * Autor: Ing. Yosvany Hernández Quintero
 */

const STORAGE_KEY = 'ipv.prefs.v1';

const DEFAULTS = Object.freeze({
  theme: 'auto',            // auto | light | dark
  operator: 'Operador local',
  density: 'comfortable',   // comfortable | compact
  pageSize: 12,
  sidebarOpen: false,
  lastRoute: '/resumen',
});

function readStored() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

const listeners = new Set();
let values = { ...DEFAULTS, ...readStored() };

const media = typeof window.matchMedia === 'function'
  ? window.matchMedia('(prefers-color-scheme: dark)')
  : { matches: false, addEventListener: null, addListener: null };

export function resolvedTheme() {
  if (values.theme === 'light' || values.theme === 'dark') return values.theme;
  return media.matches ? 'dark' : 'light';
}

export function applyTheme() {
  document.documentElement.dataset.theme = resolvedTheme();
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', resolvedTheme() === 'dark' ? '#0d1513' : '#0d3a2f');
}

function persist() {
  try { window.localStorage.setItem(STORAGE_KEY, JSON.stringify(values)); } catch { /* modo privado */ }
}

function notify() {
  listeners.forEach((listener) => listener({ ...values }));
}

export const prefs = {
  all() { return { ...values }; },
  get(key) { return values[key]; },
  set(key, value) {
    if (values[key] === value) return;
    values = { ...values, [key]: value };
    persist();
    if (key === 'theme') applyTheme();
    notify();
  },
  patch(patch) {
    values = { ...values, ...patch };
    persist();
    if ('theme' in patch) applyTheme();
    notify();
  },
  reset() {
    values = { ...DEFAULTS };
    persist();
    applyTheme();
    notify();
  },
  subscribe(listener) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  toggleTheme() {
    this.set('theme', resolvedTheme() === 'dark' ? 'light' : 'dark');
  },
};

const onSchemeChange = () => { if (values.theme === 'auto') { applyTheme(); notify(); } };
if (media.addEventListener) media.addEventListener('change', onSchemeChange);
else if (media.addListener) media.addListener(onSchemeChange);

applyTheme();

export { DEFAULTS as PREF_DEFAULTS };
