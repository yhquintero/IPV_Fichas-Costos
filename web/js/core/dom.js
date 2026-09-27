/**
 * IPV · Fichas y Costos
 * Utilidades de construcción y manipulación del DOM (sin dependencias externas).
 * Autor: Ing. Yosvany Hernández Quintero
 */

const SVG_NS = 'http://www.w3.org/2000/svg';

/** Registro de iconos vectoriales (trazo 24×24, estilo lineal consistente). */
const ICONS = {
  dashboard: '<rect x="3" y="3" width="7.5" height="7.5" rx="1.6"/><rect x="13.5" y="3" width="7.5" height="7.5" rx="1.6"/><rect x="3" y="13.5" width="7.5" height="7.5" rx="1.6"/><rect x="13.5" y="13.5" width="7.5" height="7.5" rx="1.6"/>',
  package: '<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.3 7 12 12 20.7 7"/><line x1="12" y1="22" x2="12" y2="12"/>',
  tag: '<path d="M20.6 13.4l-7.2 7.2a2 2 0 0 1-2.8 0L2 12V2h10l8.6 8.6a2 2 0 0 1 0 2.8z"/><line x1="7" y1="7" x2="7.01" y2="7"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/>',
  history: '<path d="M3 3v6h6"/><path d="M3.5 9a9 9 0 1 0 2.6-5.4L3 9"/><polyline points="12 7 12 12 16 14"/>',
  settings: '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>',
  info: '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="11"/><line x1="12" y1="8" x2="12.01" y2="8"/>',
  search: '<circle cx="11" cy="11" r="7.5"/><line x1="20.5" y1="20.5" x2="16.2" y2="16.2"/>',
  plus: '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
  minus: '<line x1="5" y1="12" x2="19" y2="12"/>',
  refresh: '<polyline points="22 4 22 10 16 10"/><polyline points="2 20 2 14 8 14"/><path d="M3.6 9a9 9 0 0 1 14.8-3.4L22 10"/><path d="M2 14l3.6 4.4A9 9 0 0 0 20.4 15"/>',
  moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
  sun: '<circle cx="12" cy="12" r="4.6"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.2" y1="4.2" x2="5.6" y2="5.6"/><line x1="18.4" y1="18.4" x2="19.8" y2="19.8"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.2" y1="19.8" x2="5.6" y2="18.4"/><line x1="18.4" y1="5.6" x2="19.8" y2="4.2"/>',
  menu: '<line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>',
  x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
  check: '<polyline points="20 6 9 17 4 12"/>',
  'check-circle': '<circle cx="12" cy="12" r="9.5"/><polyline points="8 12 11 15 16 9"/>',
  alert: '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><line x1="12" y1="9" x2="12" y2="13.5"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
  clock: '<circle cx="12" cy="12" r="9.5"/><polyline points="12 7 12 12.5 16 14.5"/>',
  calendar: '<rect x="3" y="4.5" width="18" height="17" rx="2.2"/><line x1="16" y1="2.5" x2="16" y2="6.5"/><line x1="8" y1="2.5" x2="8" y2="6.5"/><line x1="3" y1="10" x2="21" y2="10"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
  upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>',
  printer: '<polyline points="6 9 6 2.5 18 2.5 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="7.5"/>',
  edit: '<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4z"/>',
  copy: '<rect x="9" y="9" width="12.5" height="12.5" rx="2.2"/><path d="M5.5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1.5"/>',
  trash: '<polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/>',
  'chevron-right': '<polyline points="9 18 15 12 9 6"/>',
  'chevron-left': '<polyline points="15 18 9 12 15 6"/>',
  'chevron-down': '<polyline points="6 9 12 15 18 9"/>',
  'arrow-right': '<line x1="4" y1="12" x2="20" y2="12"/><polyline points="14 6 20 12 14 18"/>',
  'arrow-left': '<line x1="20" y1="12" x2="4" y2="12"/><polyline points="10 18 4 12 10 6"/>',
  'arrow-up': '<line x1="12" y1="19" x2="12" y2="5"/><polyline points="6 11 12 5 18 11"/>',
  'arrow-down': '<line x1="12" y1="5" x2="12" y2="19"/><polyline points="6 13 12 19 18 13"/>',
  'external-link': '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>',
  database: '<ellipse cx="12" cy="5.5" rx="8.5" ry="3.2"/><path d="M20.5 12c0 1.8-3.8 3.2-8.5 3.2S3.5 13.8 3.5 12"/><path d="M3.5 5.5v13c0 1.8 3.8 3.2 8.5 3.2s8.5-1.4 8.5-3.2v-13"/>',
  user: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7.5" r="4"/>',
  users: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
  lock: '<rect x="3" y="11" width="18" height="11" rx="2.2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
  key: '<path d="M21 2l-2 2m-7.6 7.6a5.5 5.5 0 1 1-7.8 7.8 5.5 5.5 0 0 1 7.8-7.8zm0 0L15.5 7.5m0 0 3 3L22 7l-3-3"/>',
  monitor: '<rect x="2" y="3" width="20" height="14" rx="2.2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>',
  server: '<rect x="2" y="2.5" width="20" height="8" rx="2.2"/><rect x="2" y="13.5" width="20" height="8" rx="2.2"/><line x1="6" y1="6.5" x2="6.01" y2="6.5"/><line x1="6" y1="17.5" x2="6.01" y2="17.5"/>',
  trend: '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>',
  chart: '<line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/>',
  layers: '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>',
  scale: '<path d="M12 3v18"/><path d="M5 7h14"/><path d="M5 7l-3 7h6z"/><path d="M19 7l-3 7h6z"/>',
  sparkle: '<path d="M12 3l1.9 5.6L19.5 10l-5.6 1.9L12 17.5l-1.9-5.6L4.5 10l5.6-1.4z"/><path d="M18 16l.8 2.2L21 19l-2.2.8L18 22l-.8-2.2L15 19l2.2-.8z"/>',
  shieldCheck: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/>',
  filter: '<polygon points="22 3 2 3 10 12.5 10 19 14 21 14 12.5 22 3"/>',
  wand: '<path d="M15 4V2"/><path d="M15 16v-2"/><path d="M8 9h2"/><path d="M20 9h2"/><path d="M17.8 11.8 19 13"/><path d="M15 9h0"/><path d="M17.8 6.2 19 5"/><path d="m3 21 9-9"/><path d="M12.2 6.2 11 5"/>',
  archive: '<polyline points="21 8 21 21 3 21 3 8"/><rect x="1" y="3" width="22" height="5" rx="1.5"/><line x1="10" y1="12" x2="14" y2="12"/>',
  clipboard: '<path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1.5"/>',
  book: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>',
  link: '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7L12 5"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7L12 19"/>',
  hash: '<line x1="4" y1="9" x2="20" y2="9"/><line x1="4" y1="15" x2="20" y2="15"/><line x1="10" y1="3" x2="8" y2="21"/><line x1="16" y1="3" x2="14" y2="21"/>',
};

/**
 * Crea un elemento HTML.
 * @param {string} tag
 * @param {object} [props] Atributos: class, text, html, dataset, style, on, attrs y propiedades del nodo.
 * @param {...(Node|string|null|undefined|Array)} children
 */
export function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  applyProps(node, props, false);
  appendChildren(node, children);
  return node;
}

/** Crea un elemento SVG con los atributos indicados. */
export function svgEl(tag, props = {}, ...children) {
  const node = document.createElementNS(SVG_NS, tag);
  applyProps(node, props, true);
  appendChildren(node, children);
  return node;
}

/** Devuelve un icono vectorial del registro interno. */
export function icon(name, { size = 18, stroke = 1.8, className = '' } = {}) {
  const body = ICONS[name] || ICONS.info;
  const node = svgEl('svg', {
    viewBox: '0 0 24 24',
    width: size,
    height: size,
    fill: 'none',
    stroke: 'currentColor',
    'stroke-width': stroke,
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round',
    class: className,
    'aria-hidden': 'true',
    focusable: 'false',
  });
  node.innerHTML = body;
  return node;
}

export function hasIcon(name) {
  return Boolean(ICONS[name]);
}

/** Sustituye los marcadores `<span data-icon="…">` por el icono correspondiente. */
export function hydrateIcons(root = document) {
  root.querySelectorAll('[data-icon]').forEach((node) => {
    node.replaceWith(icon(node.dataset.icon, { size: Number(node.dataset.iconSize) || 18 }));
  });
}

function applyProps(node, props, isSvg) {
  for (const [key, value] of Object.entries(props || {})) {
    if (value === undefined || value === null) continue;
    if (key === 'class' || key === 'className') {
      const classes = Array.isArray(value) ? value.filter(Boolean).join(' ') : String(value);
      if (classes) node.setAttribute('class', classes);
      continue;
    }
    if (key === 'text') { node.textContent = String(value); continue; }
    if (key === 'html') { node.innerHTML = String(value); continue; }
    if (key === 'dataset') { Object.assign(node.dataset, value); continue; }
    if (key === 'style') {
      if (typeof value === 'string') node.setAttribute('style', value);
      else Object.assign(node.style, value);
      continue;
    }
    if (key === 'on') {
      for (const [eventName, handler] of Object.entries(value)) {
        if (typeof handler === 'function') node.addEventListener(eventName, handler);
      }
      continue;
    }
    if (key === 'attrs') {
      for (const [attr, attrValue] of Object.entries(value)) {
        if (attrValue === false || attrValue === null || attrValue === undefined) continue;
        node.setAttribute(attr, attrValue === true ? '' : String(attrValue));
      }
      continue;
    }
    if (value === false) {
      if (key in node) { try { node[key] = false; } catch { /* atributo de solo lectura */ } }
      node.removeAttribute(key);
      continue;
    }
    if (!isSvg) {
      if (key in node) {
        try { node[key] = value; continue; } catch { /* continuar con atributos */ }
      }
    }
    node.setAttribute(key, value === true ? '' : String(value));
  }
}

function appendChildren(node, children) {
  for (const child of children) {
    if (child === null || child === undefined || child === false) continue;
    if (Array.isArray(child)) { appendChildren(node, child); continue; }
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

/** Crea un fragmento con los hijos indicados. */
export function frag(...children) {
  const fragment = document.createDocumentFragment();
  appendChildren(fragment, children);
  return fragment;
}

/** Reemplaza el contenido de un nodo. */
export function mount(parent, ...children) {
  parent.replaceChildren(frag(...children));
  return parent;
}

export function qs(selector, root = document) { return root.querySelector(selector); }
export function qsa(selector, root = document) { return Array.from(root.querySelectorAll(selector)); }
export function clear(node) { if (node) node.replaceChildren(); return node; }

/** Atajo para crear un elemento con texto. */
export function text(tag, content, props = {}) {
  return el(tag, { ...props, text: content });
}

export function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[character]));
}

/** Escucha eventos delegados desde un contenedor. */
export function delegate(root, eventName, selector, handler) {
  const listener = (event) => {
    const target = event.target instanceof Element ? event.target.closest(selector) : null;
    if (target && root.contains(target)) handler(event, target);
  };
  root.addEventListener(eventName, listener);
  return () => root.removeEventListener(eventName, listener);
}

/** Añade un manejador y devuelve la función para retirarlo. */
export function on(target, eventName, handler, options) {
  target.addEventListener(eventName, handler, options);
  return () => target.removeEventListener(eventName, handler, options);
}

export function focusWithoutScroll(node) {
  if (!node) return;
  try { node.focus({ preventScroll: true }); } catch { node.focus(); }
}

/** Lista de elementos enfocables dentro de un contenedor. */
export function focusableWithin(root) {
  return qsa('a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])', root)
    .filter((node) => node.offsetParent !== null || node === document.activeElement);
}

/** Ejecuta una función tras un intervalo sin actividad. */
export function debounce(fn, wait = 180) {
  let timer = 0;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}

export function nextFrame() {
  return new Promise((resolve) => requestAnimationFrame(() => resolve()));
}

export function uid(prefix = 'ipv') {
  return `${prefix}-${Math.random().toString(36).slice(2, 9)}`;
}
