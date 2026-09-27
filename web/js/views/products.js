/**
 * IPV · Fichas y Costos
 * Vista: catálogo de productos y servicios.
 * Autor: Ing. Yosvany Hernández Quintero
 */

import { clear, el, frag, icon, mount } from '../core/dom.js';
import { api } from '../core/api.js';
import { data } from '../core/data.js';
import { selectors } from '../core/store.js';
import { exportCsv, fmtAmount, fmtDate, fmtNumber, timestampForFilename } from '../core/format.js';
import { button, confirmAction, field, openModal, readForm, runAction, setFormBusy, statusPill, tag, toast } from '../core/ui.js';
import { dataTable } from '../components/data-table.js';
import { catalogCell } from '../components/cells.js';
import { printTableReport } from '../components/print.js';

const CATEGORY_SUGGESTIONS = ['Bebidas', 'Comidas', 'Servicios', 'Alimentos', 'Otros'];
const UNIT_SUGGESTIONS = ['unidad', 'ración', 'porción', 'vaso', 'copa', 'botella', 'plato', 'hora', 'servicio', 'kg', 'L'];

let unsubscribe = null;
let ctxRef = null;
let table = null;
let host = null;
let categorySelect = null;
let statusSelect = null;
let filters = { category: '', status: '' };
let initialQuery = '';

/** Construye el formulario de alta o edición. */
function productForm(product = null) {
  return el('form', { class: 'stack-sm', novalidate: true },
    el('div', { class: 'form-grid' },
      field({ label: 'Código', name: 'code', value: product?.code || '', required: true, placeholder: 'BEB-003', hint: 'Identificador único dentro del catálogo.' }),
      field({ label: 'Nombre', name: 'name', value: product?.name || '', required: true, placeholder: 'Nombre del producto o servicio' }),
      field({
        label: 'Categoría', name: 'category', required: true, value: product?.category || 'Bebidas',
        options: [...new Set([...CATEGORY_SUGGESTIONS, product?.category].filter(Boolean))].map((item) => ({ value: item, label: item })),
      }),
      field({
        label: 'Unidad de salida', name: 'unit', required: true, value: product?.unit || 'unidad',
        options: [...new Set([...UNIT_SUGGESTIONS, product?.unit].filter(Boolean))].map((item) => ({ value: item, label: item })),
        hint: 'Unidad con la que se costea el producto o servicio.',
      }),
      field({
        label: 'Descripción', name: 'description', type: 'textarea', full: true,
        value: product?.description || '', placeholder: 'Notas que ayuden a identificar el producto o servicio',
      })));
}

function openProductModal(product = null) {
  const form = productForm(product);
  form.id = 'product-form';
  const modal = openModal({
    title: product ? 'Editar producto o servicio' : 'Nuevo producto o servicio',
    subtitle: product
      ? `${product.code} · ${fmtNumber(product.ficha_count || 0)} ficha(s) asociada(s)`
      : 'Incorpore un nuevo elemento al catálogo del sistema.',
    content: form,
    actions: [
      el('button', { class: 'btn btn--secondary', type: 'button', text: 'Cancelar', on: { click: () => modal.close() } }),
      el('button', { class: 'btn btn--primary', type: 'submit', form: 'product-form', text: product ? 'Guardar cambios' : 'Registrar producto' }),
    ],
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const payload = readForm(form);
    setFormBusy(form, true, 'Guardando…');
    const result = await runAction(
      () => (product ? api.put(`/api/products/${product.id}`, payload) : api.post('/api/products', payload)),
      { success: product ? 'Producto actualizado correctamente.' : 'Producto registrado en el catálogo.' },
    );
    setFormBusy(form, false);
    if (result === null) return;
    modal.close();
    await data.reload({ silent: true });
  });

  const first = form.querySelector('input');
  if (first) first.focus();
}

async function toggleActive(row) {
  const label = row.active ? 'Desactivar' : 'Reactivar';
  const confirmed = await confirmAction({
    title: `${label} producto o servicio`,
    message: row.active
      ? `El producto «${row.name}» (${row.code}) dejará de estar disponible para nuevas fichas de costo.`
      : `El producto «${row.name}» (${row.code}) volverá a estar disponible para nuevas fichas de costo.`,
    note: 'Las fichas y los controles ya registrados se conservan sin modificaciones para mantener la trazabilidad.',
    confirmLabel: label,
    tone: row.active ? 'danger' : 'primary',
  });
  if (!confirmed) return;
  const result = await runAction(() => api.patch(`/api/products/${row.id}`, { active: !row.active }),
    { success: `Producto ${row.active ? 'desactivado' : 'reactivado'}.` });
  if (result === null) return;
  await data.reload({ silent: true });
}

function buildTable() {
  table = dataTable({
    state: { query: initialQuery },
    columns: [
      {
        key: 'name', label: 'Producto o servicio',
        render: (row) => catalogCell({
          code: row.code, name: row.name, category: row.category,
          meta: [row.description].filter(Boolean),
        }),
      },
      { key: 'category', label: 'Categoría', render: (row) => tag(row.category, 'layers') },
      { key: 'unit', label: 'Unidad de salida', render: (row) => el('span', { class: 'muted', text: row.unit }) },
      {
        key: 'ficha_count', label: 'Fichas', align: 'right',
        render: (row) => el('span', { class: 'state-inline' },
          el('span', { class: 'numeric', text: fmtNumber(row.ficha_count) }),
          row.ficha_count ? el('small', { text: `v${row.latest_version}` }) : null),
      },
      {
        key: 'latest_total', label: 'Último costo', align: 'right',
        render: (row) => (row.latest_total
          ? el('span', { class: 'amount', text: fmtAmount(row.latest_total) })
          : el('span', { class: 'subtle', text: 'Sin ficha' })),
      },
      {
        key: 'latest_updated_at', label: 'Actualizado',
        render: (row) => el('span', { class: 'muted', text: row.latest_updated_at ? fmtDate(row.latest_updated_at) : '—' }),
      },
      { key: 'active', label: 'Estado', render: (row) => statusPill(row.active ? 'Activo' : 'Inactivo') },
      {
        key: 'actions', label: 'Acciones', align: 'right', sortable: false,
        render: (row) => el('div', { class: 'table-actions' },
          el('button', {
            class: 'icon-btn', type: 'button', title: 'Ver fichas de costo', 'aria-label': 'Ver fichas de costo',
            on: { click: () => ctxRef.navigate('/fichas', { query: { q: row.code } }) },
          }, icon('file', { size: 16 })),
          el('button', {
            class: 'icon-btn', type: 'button', title: 'Editar', 'aria-label': 'Editar',
            on: { click: () => openProductModal(row) },
          }, icon('edit', { size: 16 })),
          el('button', {
            class: 'icon-btn', type: 'button',
            title: row.active ? 'Desactivar' : 'Reactivar',
            'aria-label': row.active ? 'Desactivar' : 'Reactivar',
            on: { click: () => toggleActive(row) },
          }, icon(row.active ? 'archive' : 'check-circle', { size: 16 }))),
      },
    ],
    rows: [],
    toolbar: buildToolbar(),
    searchPlaceholder: 'Buscar por nombre, código o categoría…',
    searchKeys: ['name', 'code', 'category', 'description'],
    pageSize: 12,
    sortKey: 'name',
    empty: {
      iconName: 'package',
      title: 'El catálogo está vacío',
      message: 'Registre el primer producto o servicio para poder crear sus fichas de costo.',
      actionLabel: 'Registrar producto',
      onAction: () => openProductModal(),
    },
    onRowClick: (row) => openProductModal(row),
    onStateChange: (uiState) => {
      ctxRef.navigate('/productos', {
        replace: true,
        query: { q: uiState.query || '', categoria: filters.category || '', estado: filters.status || '' },
      });
    },
  });
  return table.element;
}

function buildToolbar() {
  categorySelect = el('select', {
    class: 'select', 'aria-label': 'Filtrar por categoría', style: { maxWidth: '210px' },
    on: { change: (event) => { filters.category = event.target.value; sync(); } },
  });
  statusSelect = el('select', {
    class: 'select', 'aria-label': 'Filtrar por estado', style: { maxWidth: '160px' },
    on: { change: (event) => { filters.status = event.target.value; sync(); } },
  },
    el('option', { value: '', text: 'Todos los estados' }),
    el('option', { value: 'activos', text: 'Solo activos' }),
    el('option', { value: 'inactivos', text: 'Solo inactivos' }));
  refreshToolbarOptions();
  return [
    button('Exportar CSV', { iconName: 'download', size: 'sm', onClick: exportProducts }),
    button('Imprimir listado', { iconName: 'printer', size: 'sm', onClick: printProducts }),
    categorySelect,
    statusSelect,
  ];
}

function refreshToolbarOptions() {
  const state = data.state();
  const categories = selectors.categories(state);
  const current = filters.category;
  const options = [el('option', { value: '', text: 'Todas las categorías' }),
    ...categories.map((category) => el('option', { value: category, text: category }))];
  categorySelect.replaceChildren(...options);
  categorySelect.value = categories.includes(current) ? current : '';
  filters.category = categorySelect.value;
  statusSelect.value = filters.status;
}

function visibleRows() {
  let rows = data.state().products;
  if (filters.category) rows = rows.filter((row) => row.category === filters.category);
  if (filters.status === 'activos') rows = rows.filter((row) => row.active);
  if (filters.status === 'inactivos') rows = rows.filter((row) => !row.active);
  return rows;
}

function exportProducts() {
  const rows = visibleRows();
  exportCsv(`productos-servicios-${timestampForFilename()}.csv`,
    ['Código', 'Nombre', 'Categoría', 'Unidad de salida', 'Fichas', 'Versión vigente', 'Último costo (CUP)', 'Estado', 'Descripción'],
    rows.map((row) => [row.code, row.name, row.category, row.unit, row.ficha_count, row.latest_version || '',
      row.latest_total || '', row.active ? 'Activo' : 'Inactivo', row.description]));
  toast(`${rows.length} registro(s) exportado(s) a CSV.`, { type: 'success' });
}

function printProducts() {
  const rows = visibleRows();
  printTableReport({
    title: 'Catálogo de productos y servicios',
    subtitle: 'Listado del catálogo registrado en el sistema',
    meta: [
      ['Registros', String(rows.length)],
      ['Categoría', filters.category || 'Todas'],
      ['Generado', new Date().toLocaleString('es')],
    ],
    columns: [
      { key: 'code', label: 'Código' },
      { key: 'name', label: 'Producto o servicio' },
      { key: 'category', label: 'Categoría' },
      { key: 'unit', label: 'Unidad' },
      { key: 'ficha_count', label: 'Fichas', align: 'right' },
      { key: 'latest_total', label: 'Último costo (CUP)', align: 'right' },
      { label: 'Estado', value: (row) => (row.active ? 'Activo' : 'Inactivo') },
    ],
    rows,
  });
}

function sync() {
  if (!host || !table) return;
  refreshToolbarOptions();
  const rows = visibleRows();
  table.update(rows);
  const counter = host.querySelector('[data-role="count"]');
  if (counter) {
    const active = data.state().products.filter((item) => item.active).length;
    counter.textContent = `${fmtNumber(rows.length)} en pantalla · ${fmtNumber(active)} activos`;
  }
}

function render() {
  if (host) {
    mount(host, frag(
      el('header', { class: 'page-heading' },
        el('div', { class: 'page-heading-main' },
          el('p', { class: 'eyebrow', text: 'Catálogo' }),
          el('h1', { text: 'Productos y servicios' }),
          el('p', { text: 'Elementos del catálogo que pueden tener una Ficha de Costo versionada y ser objeto de Control de IPV.' })),
        el('div', { class: 'page-heading-actions' },
          el('span', { class: 'tag', 'data-role': 'count' }, '—'),
          button('Nuevo producto o servicio', { variant: 'primary', iconName: 'plus', onClick: () => openProductModal() }))),
      buildTable(),
      el('p', {
        class: 'subtle', style: { marginTop: 'var(--space-4)', fontSize: 'var(--text-2xs)' },
        text: 'El código del producto es único. Al desactivar un elemento, sus fichas y controles históricos se conservan íntegros.',
      })));
  }
  sync();
}

function onDataChange() {
  const state = data.state();
  if (!state.ready) return;
  if (!host) return;
  const showingSkeleton = !host.querySelector('table.data');
  if (showingSkeleton || !table) render();
  else sync();
}

/** Abre el formulario cuando la ruta lo solicita (?nueva=1). */
function applyRoute(route = {}) {
  if ((route.query || {}).nueva === '1') {
    openProductModal();
    ctxRef?.navigate('/productos', { replace: true });
  }
}

export const productsView = {
  id: 'products',
  title: 'Productos y servicios',
  crumb: 'Productos y servicios',
  description: 'Catálogo común de productos y servicios.',
  mount(container, ctx) {
    host = container;
    ctxRef = ctx;
    const query = ctx.route?.query || {};
    initialQuery = query.q || '';
    filters = { category: query.categoria || '', status: query.estado || '' };
    table = null;
    const state = data.state();
    if (state.ready) render();
    else mount(host, el('div', { class: 'stack' },
      el('div', { class: 'skeleton', style: { height: '72px' } }),
      el('div', { class: 'skeleton', style: { height: '340px' } })));
    unsubscribe = data.subscribe(onDataChange);
    applyRoute(ctx.route);
  },
  receiveRoute(route) {
    ctxRef = { ...ctxRef, route };
    applyRoute(route);
  },
  unmount() {
    if (unsubscribe) unsubscribe();
    unsubscribe = null;
    table = null;
    if (host) clear(host);
    host = null;
  },
};
