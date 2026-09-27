/**
 * IPV · Fichas y Costos
 * Celdas y bloques reutilizables para listados.
 * Autor: Ing. Yosvany Hernández Quintero
 */

import { el } from '../core/dom.js';
import { slugify } from '../core/format.js';

const AVATAR_CLASSES = new Set(['comidas', 'bebidas', 'servicios', 'otros']);

/** Clase visual del distintivo según la categoría o el tipo. */
export function avatarClass(value = '') {
  const slug = slugify(value);
  if (AVATAR_CLASSES.has(slug)) return `avatar-glyph--${slug}`;
  if (/comida|alimento|gastronom/.test(slug)) return 'avatar-glyph--comidas';
  if (/bebida|bar|coctel/.test(slug)) return 'avatar-glyph--bebidas';
  if (/servicio|salón|salon|atenci/.test(slug)) return 'avatar-glyph--servicios';
  return 'avatar-glyph--otros';
}

/** Iniciales para el distintivo de un elemento del catálogo. */
export function glyph(value = '') {
  const parts = String(value).trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return '··';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
}

/**
 * Bloque principal de una fila: distintivo, nombre y código.
 */
export function catalogCell({ code = '', name = '', category = '', meta = [] } = {}) {
  return el('div', { class: 'row-start' },
    el('span', { class: `avatar-glyph ${avatarClass(category)}`, 'aria-hidden': 'true', text: glyph(name) }),
    el('span', { class: 'catalog-headline' },
      el('span', { class: 'catalog-title', text: name || '—' }),
      el('span', { class: 'catalog-code', text: code || '—' }),
      meta.length ? el('span', { class: 'row-meta', text: meta.join(' · ') }) : null));
}

/** Par de valores con separador, para celdas de importes. */
export function amountCell(value, secondary = '') {
  return el('span', { class: 'state-inline' },
    el('span', { class: 'numeric', text: value }),
    secondary ? el('small', { text: secondary }) : null);
}

/**
 * Tabla de datos simple a partir de encabezados y filas.
 * Cada celda puede ser: un nodo, un texto, o `{ node | text, class, ... }`.
 */
export function itemsTable({ headers = [], rows = [], className = 'data', caption = '' } = {}) {
  const head = el('tr', {}, ...headers.map((header) => el('th', typeof header === 'string' ? { text: header } : header)));
  const body = el('tbody', {}, ...rows.map((cells) => el('tr', {}, ...cells.map((cell) => cellToTd(cell)))));
  return el('div', { class: 'table-wrap' }, el('table', { class: className },
    caption ? el('caption', { text: caption }) : null,
    el('thead', {}, head),
    body));
}

function cellToTd(cell) {
  if (cell instanceof Node) return el('td', {}, cell);
  if (cell && typeof cell === 'object' && !Array.isArray(cell)) {
    const { node = null, text = null, ...attrs } = cell;
    if (node instanceof Node) return el('td', attrs, node);
    return el('td', attrs, String(text ?? '—'));
  }
  return el('td', { text: cell === null || cell === undefined ? '—' : String(cell) });
}
