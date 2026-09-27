/**
 * IPV · Fichas y Costos
 * Tabla de datos con búsqueda, ordenamiento y paginación consistentes.
 * Autor: Ing. Yosvany Hernández Quintero
 */

import { clear, debounce, el, frag, icon, mount } from '../core/dom.js';
import { emptyState, skeletonTable } from '../core/ui.js';

const PAGE_SIZES = [8, 12, 25, 50];

/**
 * @typedef {object} Column
 * @property {string} key Identificador del campo.
 * @property {string} label Encabezado visible.
 * @property {'left'|'right'|'center'} [align]
 * @property {boolean} [sortable]
 * @property {(row: any) => (Node|string)} [render]
 * @property {(row: any) => any} [value] Valor para ordenar.
 */

/**
 * Construye una tabla de datos.
 * @param {object} options
 * @returns {{element: HTMLElement, update: Function, setLoading: Function, setToolbar: Function, getState: Function}}
 */
export function dataTable({
  columns, rows = [], caption = '', pageSize = 12, sortKey = '', sortDir = 'asc', searchable = true,
  searchPlaceholder = 'Buscar…', searchKeys = [], toolbar = [], onRowClick = null, onStateChange = null,
  empty = {}, state = null, dense = false,
} = {}) {
  const ui = {
    query: state?.query || '',
    sortKey: state?.sortKey || sortKey,
    sortDir: state?.sortDir || sortDir,
    page: state?.page || 1,
    pageSize: state?.pageSize || pageSize,
  };

  const thead = el('thead');
  const tbody = el('tbody');
  const footer = el('div', { class: 'table-footer' });
  const toolbarRow = el('div', { class: 'table-toolbar' });
  const searchInput = el('input', {
    type: 'search', value: ui.query, placeholder: searchPlaceholder, 'aria-label': searchPlaceholder,
    autocomplete: 'off',
  });
  const wrapper = el('div', { class: 'table-wrap' });
  const table = el('table', { class: `data${dense ? ' compact' : ''}` }, caption ? el('caption', { text: caption }) : null, thead, tbody);
  wrapper.append(table);
  const element = el('section', { class: 'card card--flush' }, toolbarRow, wrapper, footer);

  const buildHeader = () => {
    clear(thead);
    const row = el('tr');
    columns.forEach((column) => {
      const sortable = column.sortable !== false && Boolean(column.key);
      const active = ui.sortKey === column.key;
      const header = el('th', {
        class: column.align ? `align-${column.align}` : '',
        scope: 'col',
        'aria-sort': active ? (ui.sortDir === 'asc' ? 'ascending' : 'descending') : undefined,
        dataset: sortable ? { sortable: 'true' } : {},
        on: sortable ? {
          click: () => {
            if (ui.sortKey === column.key) ui.sortDir = ui.sortDir === 'asc' ? 'desc' : 'asc';
            else { ui.sortKey = column.key; ui.sortDir = 'asc'; }
            ui.page = 1;
            renderBody();
            publish();
          },
        } : undefined,
      }, el('span', { text: column.label }));
      if (sortable) {
        header.append(el('span', { class: 'sort-mark' },
          icon(active && ui.sortDir === 'desc' ? 'arrow-down' : 'arrow-up', { size: 12 })));
      }
      row.append(header);
    });
    thead.append(row);
  };

  const valueOf = (row, column) => (typeof column.value === 'function' ? column.value(row) : row[column.key]);

  const filtered = () => {
    if (!ui.query) return rows;
    const needle = ui.query.toLowerCase();
    const keys = searchKeys.length ? searchKeys : columns.map((column) => column.key);
    return rows.filter((row) => keys.some((key) => String(row[key] ?? '').toLowerCase().includes(needle)));
  };

  const ordered = (list) => {
    const column = columns.find((item) => item.key === ui.sortKey);
    if (!column) return list;
    const factor = ui.sortDir === 'asc' ? 1 : -1;
    return [...list].sort((a, b) => {
      const left = valueOf(a, column);
      const right = valueOf(b, column);
      if (left === right) return 0;
      const leftNumber = typeof left === 'number' ? left : Number.parseFloat(String(left ?? '').replace(',', '.'));
      const rightNumber = typeof right === 'number' ? right : Number.parseFloat(String(right ?? '').replace(',', '.'));
      const bothNumeric = Number.isFinite(leftNumber) && Number.isFinite(rightNumber)
        && String(left).trim() !== '' && String(right).trim() !== '';
      if (bothNumeric) return (leftNumber - rightNumber) * factor;
      return String(left ?? '').localeCompare(String(right ?? ''), 'es', { numeric: true }) * factor;
    });
  };

  const renderBody = () => {
    const list = ordered(filtered());
    const totalPages = Math.max(1, Math.ceil(list.length / ui.pageSize));
    ui.page = Math.min(Math.max(1, ui.page), totalPages);
    const start = (ui.page - 1) * ui.pageSize;
    const pageRows = list.slice(start, start + ui.pageSize);

    clear(tbody);
    if (!pageRows.length) {
      tbody.append(el('tr', {}, el('td', { colspan: String(columns.length) },
        emptyState({
          iconName: empty.iconName || 'search',
          title: empty.title || (rows.length ? 'Sin resultados coincidentes' : 'Todavía no hay registros'),
          message: empty.message || (rows.length
            ? 'Ajuste el término de búsqueda o los filtros aplicados.'
            : 'Registre el primer elemento para comenzar.'),
          actionLabel: rows.length ? '' : (empty.actionLabel || ''),
          onAction: rows.length ? undefined : empty.onAction,
        }))));
    } else {
      pageRows.forEach((row) => {
        const tr = el('tr');
        if (onRowClick) {
          tr.tabIndex = 0;
          tr.style.cursor = 'pointer';
          tr.addEventListener('click', (event) => {
            if (event.target instanceof Element && event.target.closest('button, a, input, select')) return;
            onRowClick(row);
          });
          tr.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') { event.preventDefault(); onRowClick(row); }
          });
        }
        columns.forEach((column) => {
          const cell = el('td', { class: [column.align ? `align-${column.align}` : '', column.className || ''].filter(Boolean).join(' ') });
          const content = typeof column.render === 'function' ? column.render(row) : row[column.key];
          if (content instanceof Node) cell.append(content);
          else if (Array.isArray(content)) cell.append(frag(...content));
          else cell.textContent = content === null || content === undefined ? '—' : String(content);
          tr.append(cell);
        });
        tbody.append(tr);
      });
    }

    mount(footer,
      el('span', {
        text: list.length
          ? `Mostrando ${start + 1}–${Math.min(start + ui.pageSize, list.length)} de ${list.length} registro${list.length === 1 ? '' : 's'}`
          : 'Sin registros',
      }),
      el('div', { class: 'row-tight' },
        el('label', { class: 'row-tight', style: { fontSize: 'var(--text-2xs)', color: 'var(--text-3)' } },
          el('span', { text: 'Filas' }),
          el('select', {
            class: 'select', style: { minHeight: '30px', height: '30px', padding: '0 22px 0 8px' },
            'aria-label': 'Registros por página',
            on: {
              change: (event) => { ui.pageSize = Number(event.target.value); ui.page = 1; renderBody(); publish(); },
            },
          }, ...PAGE_SIZES.map((size) => el('option', { value: size, text: String(size), selected: size === ui.pageSize })))),
        el('div', { class: 'pagination' },
          pageButton('‹ Anterior', () => { ui.page -= 1; renderBody(); publish(); }, ui.page <= 1),
          el('div', { class: 'pages' }, ...pageNumbers(ui.page, totalPages).map((number) => number === '…'
            ? el('span', { style: { padding: '0 4px', color: 'var(--text-3)' }, text: '…' })
            : el('button', {
              class: 'page-btn', type: 'button', text: String(number),
              'aria-current': number === ui.page ? 'true' : undefined,
              on: { click: () => { ui.page = number; renderBody(); publish(); } },
            }))),
          pageButton('Siguiente ›', () => { ui.page += 1; renderBody(); publish(); }, ui.page >= totalPages))));
  };

  const pageButton = (label, onClick, disabled) => el('button', {
    class: 'page-btn', type: 'button', text: label, disabled, on: { click: onClick },
  });

  const publish = () => {
    if (typeof onStateChange === 'function') onStateChange({ ...ui });
  };

  if (searchable) {
    toolbarRow.append(el('label', { class: 'search-field' }, icon('search', { size: 16 }), searchInput));
    searchInput.addEventListener('input', debounce(() => {
      ui.query = searchInput.value;
      ui.page = 1;
      renderBody();
      publish();
    }, 160));
  }
  let toolbarNodes = toolbar;
  if (toolbarNodes.length) toolbarRow.append(frag(...toolbarNodes));

  buildHeader();
  renderBody();

  return {
    element,
    update(nextRows) { rows = nextRows; renderBody(); },
    setLoading() {
      clear(thead);
      clear(tbody);
      thead.append(el('tr', {}, ...columns.map((column) => el('th', { text: column.label }))));
      tbody.append(skeletonTable(6, columns.length));
      clear(footer);
    },
    setToolbar(nodes) {
      toolbarNodes.forEach((node) => node.remove());
      toolbarNodes = nodes || [];
      if (toolbarNodes.length) toolbarRow.append(frag(...toolbarNodes));
    },
    getState() { return { ...ui }; },
    setFilter(patch) { Object.assign(ui, patch); renderBody(); publish(); },
  };
}

function pageNumbers(current, total) {
  if (total <= 7) return Array.from({ length: total }, (_, index) => index + 1);
  const numbers = new Set([1, total, current, current - 1, current + 1]);
  const sorted = [...numbers].filter((number) => number >= 1 && number <= total).sort((a, b) => a - b);
  const result = [];
  let previous = 0;
  sorted.forEach((number) => {
    if (previous && number - previous > 1) result.push('…');
    result.push(number);
    previous = number;
  });
  return result;
}
