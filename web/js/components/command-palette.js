/**
 * IPV · Fichas y Costos
 * Paleta de comandos: navegación rápida y búsqueda global (Ctrl + K).
 * Autor: Ing. Yosvany Hernández Quintero
 */

import { clear, debounce, el, focusWithoutScroll, icon, mount, qs } from '../core/dom.js';
import { data } from '../core/data.js';
import { fmtMoney } from '../core/format.js';
import { statusPill } from '../core/ui.js';

/**
 * Abre la paleta de comandos.
 * @param {object} options
 * @param {(path: string, options?: object) => void} options.navigate
 * @param {{id: string, label: string, iconName?: string, keywords?: string, run: Function}[]} [options.commands]
 */
export function openCommandPalette({ navigate, commands = [] } = {}) {
  const previousFocus = document.activeElement;
  const input = el('input', {
    type: 'text', placeholder: 'Buscar productos, valores, fichas, controles o ir a una sección…',
    'aria-label': 'Búsqueda global', autocomplete: 'off', spellcheck: 'false',
  });
  const results = el('div', { class: 'palette-results', role: 'listbox', 'aria-label': 'Resultados' });
  const layer = el('div', { class: 'palette-layer' },
    el('div', { class: 'palette', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Paleta de comandos' },
      el('div', { class: 'palette-search' }, icon('search', { size: 18 }), input, el('kbd', { text: 'Esc' })),
      results,
      el('div', { class: 'palette-footer' },
        el('span', {}, el('kbd', { text: '↑ ↓' }), ' navegar'),
        el('span', {}, el('kbd', { text: 'Enter' }), ' abrir'),
        el('span', {}, el('kbd', { text: 'Esc' }), ' cerrar'))));

  let entries = [];
  let selected = 0;

  const close = () => {
    document.removeEventListener('keydown', onKeyDown, true);
    layer.remove();
    document.body.style.overflow = '';
    if (previousFocus && previousFocus.isConnected) focusWithoutScroll(previousFocus);
  };

  const NAVIGATION = [
    { label: 'Resumen general', hint: 'Tablero', path: '/resumen', iconName: 'dashboard' },
    { label: 'Productos y servicios', hint: 'Catálogo', path: '/productos', iconName: 'package' },
    { label: 'Valores del IPV', hint: 'Insumos y precios', path: '/valores', iconName: 'tag' },
    { label: 'Fichas de costo', hint: 'Costeo', path: '/fichas', iconName: 'file' },
    { label: 'Controles de IPV', hint: 'Revisión', path: '/controles', iconName: 'shield' },
    { label: 'Bitácora de auditoría', hint: 'Administración', path: '/bitacora', iconName: 'history' },
    { label: 'Sistema y respaldos', hint: 'Administración', path: '/sistema', iconName: 'settings' },
    { label: 'Acerca de', hint: 'Información', path: '/acerca-de', iconName: 'info' },
  ];

  const buildEntries = (search = '') => {
    const list = [];
    if (!search) {
      commands.forEach((command) => list.push({
        group: 'Acciones', label: command.label, iconName: command.iconName || 'wand',
        hint: command.hint || '', run: command.run,
      }));
      NAVIGATION.forEach((item) => list.push({
        group: 'Ir a', label: item.label, hint: item.hint, iconName: item.iconName,
        run: () => navigate(item.path),
      }));
      return list;
    }
    const needle = search.toLowerCase();
    commands
      .filter((command) => `${command.label} ${command.keywords || ''}`.toLowerCase().includes(needle))
      .forEach((command) => list.push({
        group: 'Acciones', label: command.label, iconName: command.iconName || 'wand',
        hint: command.hint || '', run: command.run,
      }));
    NAVIGATION
      .filter((item) => `${item.label} ${item.hint}`.toLowerCase().includes(needle))
      .forEach((item) => list.push({
        group: 'Ir a', label: item.label, hint: item.hint, iconName: item.iconName, run: () => navigate(item.path),
      }));
    return list;
  };

  const renderResults = (remote = null) => {
    clear(results);
    if (remote) {
      const groups = [
        ['Productos y servicios', remote.products.map((product) => ({
          label: product.name,
          hint: `${product.code} · ${product.category}`,
          iconName: 'package',
          run: () => navigate('/productos', { query: { q: product.code } }),
        }))],
        ['Valores del IPV', remote.materials.map((material) => ({
          label: material.name,
          hint: `${material.code} · ${fmtMoney(material.unit_price, material.currency)} / ${material.unit}`,
          iconName: 'tag',
          run: () => navigate('/valores', { query: { q: material.code } }),
        }))],
        ['Fichas de costo', remote.fichas.map((ficha) => ({
          label: `${ficha.product_name} · v${ficha.version}`,
          hint: `${ficha.product_code} · ${ficha.status}`,
          iconName: 'file',
          run: () => navigate(`/fichas/${ficha.id}`),
        }))],
        ['Controles de IPV', remote.controls.map((control) => ({
          label: `${control.code} · ${control.product_name}`,
          hint: `${control.period} · ${control.status}`,
          iconName: 'shield',
          run: () => navigate(`/controles/${control.id}`),
        }))],
      ];
      groups.forEach(([groupLabel, items]) => {
        if (!items.length) return;
        results.append(el('p', { class: 'palette-group-label', text: groupLabel }));
        items.forEach((item) => results.append(itemNode({ ...item, group: groupLabel })));
      });
      if (!results.childElementCount) {
        results.append(el('p', { class: 'palette-group-label', text: 'Sin coincidencias para la búsqueda' }));
      }
      entries = [...results.querySelectorAll('.palette-item')].map((node) => node.__entry);
      if (!entries.length) entries = buildEntries('').slice(0);
      selected = 0;
      highlight();
      return;
    }
    entries = buildEntries(input.value.trim());
    if (remote) return;
    const grouped = entries.reduce((accumulator, entry) => {
      (accumulator[entry.group] = accumulator[entry.group] || []).push(entry);
      return accumulator;
    }, {});
    Object.entries(grouped).forEach(([groupLabel, items]) => {
      results.append(el('p', { class: 'palette-group-label', text: groupLabel }));
      items.forEach((entry) => results.append(itemNode(entry)));
    });
    entries = [...results.querySelectorAll('.palette-item')].map((node) => node.__entry);
    selected = 0;
    highlight();
  };

  const itemNode = (entry) => {
    const node = el('button', {
      class: 'palette-item', type: 'button', role: 'option',
      on: {
        click: () => { close(); entry.run(); },
        mouseenter: () => { selected = entries.indexOf(node.__entry); highlight(); },
      },
    },
      icon(entry.iconName || 'arrow-right', { size: 16 }),
      el('span', { text: entry.label }),
      entry.hint ? el('span', { class: 'meta', text: entry.hint }) : null);
    node.__entry = entry;
    return node;
  };

  const highlight = () => {
    const nodes = [...results.querySelectorAll('.palette-item')];
    nodes.forEach((node, index) => node.setAttribute('aria-selected', index === selected ? 'true' : 'false'));
    const active = nodes[selected];
    if (active && active.scrollIntoView) active.scrollIntoView({ block: 'nearest' });
  };

  const onKeyDown = (event) => {
    if (event.key === 'Escape') { event.preventDefault(); close(); return; }
    if (event.key === 'ArrowDown') { event.preventDefault(); selected = Math.min(entries.length - 1, selected + 1); highlight(); return; }
    if (event.key === 'ArrowUp') { event.preventDefault(); selected = Math.max(0, selected - 1); highlight(); return; }
    if (event.key === 'Enter') {
      event.preventDefault();
      const entry = entries[selected];
      if (entry) { close(); entry.run(); }
    }
  };

  const runSearch = debounce(async (query) => {
    if (query.trim().length < 2) { renderResults(); return; }
    try {
      const remote = await data.search(query.trim());
      renderResults(remote);
    } catch {
      renderResults();
    }
  }, 200);

  input.addEventListener('input', () => {
    renderResults();
    runSearch(input.value);
  });
  layer.addEventListener('mousedown', (event) => { if (event.target === layer) close(); });
  document.addEventListener('keydown', onKeyDown, true);

  mount(qs('#palette-root'), layer);
  document.body.style.overflow = 'hidden';
  focusWithoutScroll(input);
  renderResults();
  return { close };
}
