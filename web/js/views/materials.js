/**
 * IPV · Fichas y Costos
 * Vista: valores de referencia del IPV (insumos, servicios y tarifas).
 * Autor: Ing. Yosvany Hernández Quintero
 */

import { clear, el, frag, icon, mount } from '../core/dom.js';
import { api } from '../core/api.js';
import { data } from '../core/data.js';
import { daysUntil, exportCsv, fmtAmount, fmtDate, fmtNumber, timestampForFilename } from '../core/format.js';
import { button, copyText, field, openModal, readForm, runAction, setFormBusy, statusPill, tag, toast } from '../core/ui.js';
import { dataTable } from '../components/data-table.js';
import { catalogCell } from '../components/cells.js';
import { printTableReport } from '../components/print.js';

const KINDS = ['Insumo', 'Materia prima', 'Mano de obra', 'Servicio', 'Gasto indirecto', 'Otros'];
const STATES = ['Vigente', 'Suspendido', 'Descontinuado'];
const UNITS = ['kg', 'g', 'L', 'ml', 'unidad', 'porción', 'hora', 'servicio', 'caja', 'paquete', 'm', 'kWh'];
const CURRENCIES = ['CUP', 'USD', 'EUR', 'MLC'];

let unsubscribe = null;
let ctxRef = null;
let table = null;
let host = null;
let kindSelect = null;
let stateSelect = null;
let filters = { kind: '', state: '' };
let initialQuery = '';

function materialForm(material = null) {
  const today = new Date().toISOString().slice(0, 10);
  return el('form', { class: 'stack-sm', novalidate: true },
    el('div', { class: 'form-grid' },
      field({ label: 'Código', name: 'code', value: material?.code || '', required: true, placeholder: 'INS-013', hint: 'Identificador único del valor.' }),
      field({ label: 'Nombre', name: 'name', value: material?.name || '', required: true, placeholder: 'Nombre del insumo, servicio o tarifa' }),
      field({
        label: 'Tipo de valor', name: 'kind', value: material?.kind || 'Insumo', required: true,
        options: [...new Set([...KINDS, material?.kind].filter(Boolean))].map((item) => ({ value: item, label: item })),
      }),
      field({
        label: 'Unidad de medida', name: 'unit', value: material?.unit || 'kg', required: true,
        options: [...new Set([...UNITS, material?.unit].filter(Boolean))].map((item) => ({ value: item, label: item })),
      }),
      field({ label: 'Precio unitario', name: 'unit_price', type: 'number', value: material?.unit_price ?? '', required: true, min: 0, step: '0.01', placeholder: '0.00' }),
      field({
        label: 'Moneda', name: 'currency', value: material?.currency || 'CUP',
        options: [...new Set([...CURRENCIES, material?.currency].filter(Boolean))].map((item) => ({ value: item, label: item })),
      }),
      field({ label: 'Vigente desde', name: 'effective_from', type: 'date', value: (material?.effective_from || today).slice(0, 10) }),
      field({ label: 'Vigente hasta', name: 'effective_to', type: 'date', value: (material?.effective_to || '').slice(0, 10), hint: 'Deje vacío si el valor no tiene fecha de término prevista.' }),
      field({ label: 'Proveedor o fuente', name: 'supplier', value: material?.supplier || '', placeholder: 'Almacén, mercado, nómina…' }),
      field({ label: 'Documento de respaldo', name: 'source', value: material?.source || '', placeholder: 'Factura, acta, acuerdo…' }),
      field({
        label: 'Estado del registro', name: 'status', value: material?.status || 'Vigente',
        options: STATES.map((item) => ({ value: item, label: item })),
        hint: 'El estado «Vigente» se recalcula como «Por vencer» o «Vencido» según la fecha de vigencia.',
      }),
      field({ label: 'Notas', name: 'notes', type: 'textarea', value: material?.notes || '', full: true, placeholder: 'Observaciones sobre la procedencia o el cálculo del valor' })));
}

function openMaterialModal(material = null) {
  const form = materialForm(material);
  form.id = 'material-form';
  const modal = openModal({
    title: material ? 'Editar valor del IPV' : 'Registrar valor del IPV',
    subtitle: material
      ? `${material.code} · utilizado en ${fmtNumber(material.usage_count || 0)} ficha(s)`
      : 'Registre el precio, la vigencia y la procedencia documental del valor.',
    size: 'wide',
    content: frag(
      form,
      el('div', { class: 'banner banner--neutral' },
        icon('info', { size: 16 }),
        el('span', { text: 'Los cambios de precio no modifican las fichas ya aprobadas: en las nuevas versiones se aplica el valor vigente y durante la validación del control se informa cualquier variación.' }))),
    actions: [
      el('button', { class: 'btn btn--secondary', type: 'button', text: 'Cancelar', on: { click: () => modal.close() } }),
      el('button', { class: 'btn btn--primary', type: 'submit', form: 'material-form', text: material ? 'Guardar cambios' : 'Registrar valor' }),
    ],
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    const payload = readForm(form);
    payload.unit_price = String(payload.unit_price ?? '');
    setFormBusy(form, true, 'Guardando…');
    const result = await runAction(
      () => (material ? api.put(`/api/materials/${material.id}`, payload) : api.post('/api/materials', payload)),
      { success: material ? 'Valor del IPV actualizado.' : 'Valor registrado en el IPV.' },
    );
    setFormBusy(form, false);
    if (result === null) return;
    modal.close();
    await data.reload({ silent: true });
  });

  const first = form.querySelector('input');
  if (first) first.focus();
}

function validityCell(row) {
  const remaining = daysUntil(row.effective_to);
  return el('div', { class: 'catalog-headline' },
    el('span', { class: 'numeric', style: { fontSize: 'var(--text-xs)', color: 'var(--text)' },
      text: `${fmtDate(row.effective_from)} — ${row.effective_to ? fmtDate(row.effective_to) : 'sin término'}` }),
    el('span', { class: 'row-meta', text: row.state === 'Vencido'
      ? `Vencido hace ${Math.abs(remaining)} día(s)`
      : remaining !== null && remaining <= 30 ? `Vence en ${remaining} día(s)` : 'Valor vigente' }));
}

function buildTable() {
  table = dataTable({
    state: { query: initialQuery },
    columns: [
      {
        key: 'name', label: 'Valor de referencia',
        render: (row) => catalogCell({ code: row.code, name: row.name, category: row.kind, meta: [row.supplier, row.source].filter(Boolean) }),
      },
      { key: 'kind', label: 'Tipo', render: (row) => tag(row.kind, 'tag') },
      { key: 'unit', label: 'Unidad', render: (row) => el('span', { class: 'muted', text: row.unit }) },
      {
        key: 'unit_price', label: 'Precio unitario', align: 'right',
        render: (row) => el('span', { class: 'amount', text: fmtAmount(row.unit_price) }),
      },
      { key: 'currency', label: 'Moneda', render: (row) => el('span', { class: 'muted', text: row.currency }) },
      { key: 'effective_to', label: 'Vigencia', render: validityCell },
      {
        key: 'usage_count', label: 'Uso', align: 'right',
        render: (row) => (row.usage_count
          ? el('button', {
            class: 'link-btn', type: 'button', title: 'Ver fichas que utilizan este valor',
            on: { click: () => ctxRef.navigate('/fichas', { query: { q: row.code } }) },
          }, el('span', { text: `${fmtNumber(row.usage_count)} ficha(s)` }))
          : el('span', { class: 'subtle', text: 'Sin uso' })),
      },
      { key: 'state', label: 'Estado', render: (row) => statusPill(row.state) },
      {
        key: 'actions', label: 'Acciones', align: 'right', sortable: false,
        render: (row) => el('div', { class: 'table-actions' },
          el('button', {
            class: 'icon-btn', type: 'button', title: 'Editar valor', 'aria-label': 'Editar valor',
            on: { click: () => openMaterialModal(row) },
          }, icon('edit', { size: 16 })),
          el('button', {
            class: 'icon-btn', type: 'button', title: 'Copiar código', 'aria-label': 'Copiar código',
            on: { click: () => copyText(row.code, `Código ${row.code} copiado al portapapeles.`) },
          }, icon('copy', { size: 16 }))),
      },
    ],
    rows: [],
    toolbar: buildToolbar(),
    searchPlaceholder: 'Buscar por insumo, código, proveedor o tipo…',
    searchKeys: ['name', 'code', 'supplier', 'source', 'kind'],
    pageSize: 12,
    sortKey: 'name',
    empty: {
      iconName: 'tag',
      title: 'No hay valores registrados',
      message: 'Registre el primer insumo, servicio o tarifa para utilizarlo en las fichas de costo.',
      actionLabel: 'Registrar valor',
      onAction: () => openMaterialModal(),
    },
    onRowClick: (row) => openMaterialModal(row),
    onStateChange: (uiState) => {
      ctxRef.navigate('/valores', {
        replace: true,
        query: { q: uiState.query || '', tipo: filters.kind || '', estado: filters.state || '' },
      });
    },
  });
  return table.element;
}

function refreshToolbarOptions() {
  const state = data.state();
  const kinds = [...new Set(state.materials.map((material) => material.kind))].sort();
  const states = [...new Set(state.materials.map((material) => material.state))].sort();
  kindSelect.replaceChildren(el('option', { value: '', text: 'Todos los tipos' }),
    ...kinds.map((kind) => el('option', { value: kind, text: kind })));
  kindSelect.value = kinds.includes(filters.kind) ? filters.kind : '';
  filters.kind = kindSelect.value;
  stateSelect.replaceChildren(el('option', { value: '', text: 'Todos los estados' }),
    ...states.map((state) => el('option', { value: state, text: state })));
  stateSelect.value = states.includes(filters.state) ? filters.state : '';
  filters.state = stateSelect.value;
}

function buildToolbar() {
  kindSelect = el('select', {
    class: 'select', 'aria-label': 'Filtrar por tipo de valor', style: { maxWidth: '200px' },
    on: { change: (event) => { filters.kind = event.target.value; sync(); } },
  });
  stateSelect = el('select', {
    class: 'select', 'aria-label': 'Filtrar por estado', style: { maxWidth: '180px' },
    on: { change: (event) => { filters.state = event.target.value; sync(); } },
  });
  refreshToolbarOptions();
  return [
    button('Exportar CSV', { iconName: 'download', size: 'sm', onClick: exportMaterials }),
    button('Imprimir listado', { iconName: 'printer', size: 'sm', onClick: printMaterials }),
    kindSelect,
    stateSelect,
  ];
}

function visibleRows() {
  let rows = data.state().materials;
  if (filters.kind) rows = rows.filter((row) => row.kind === filters.kind);
  if (filters.state) rows = rows.filter((row) => row.state === filters.state);
  return rows;
}

function exportMaterials() {
  const rows = visibleRows();
  exportCsv(`valores-ipv-${timestampForFilename()}.csv`,
    ['Código', 'Nombre', 'Tipo', 'Unidad', 'Precio unitario', 'Moneda', 'Vigente desde', 'Vigente hasta', 'Estado',
      'Proveedor', 'Documento de respaldo', 'Fichas que lo usan', 'Notas'],
    rows.map((row) => [row.code, row.name, row.kind, row.unit, row.unit_price, row.currency, row.effective_from,
      row.effective_to, row.state, row.supplier, row.source, row.usage_count, row.notes]));
  toast(`${rows.length} valor(es) exportado(s) a CSV.`, { type: 'success' });
}

function printMaterials() {
  const rows = visibleRows();
  printTableReport({
    title: 'Valores de referencia del IPV',
    subtitle: 'Registro de valores aplicados a las fichas de costo',
    meta: [
      ['Valores listados', String(rows.length)],
      ['Tipo', filters.kind || 'Todos'],
      ['Generado', new Date().toLocaleString('es')],
    ],
    columns: [
      { key: 'code', label: 'Código' },
      { key: 'name', label: 'Valor' },
      { key: 'kind', label: 'Tipo' },
      { key: 'unit', label: 'Unidad' },
      { key: 'unit_price', label: 'Precio (CUP)', align: 'right' },
      { key: 'effective_from', label: 'Vigente desde' },
      { key: 'effective_to', label: 'Vigente hasta' },
      { key: 'state', label: 'Estado' },
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
    const expired = data.state().materials.filter((material) => material.state === 'Vencido').length;
    counter.textContent = `${fmtNumber(rows.length)} en pantalla · ${fmtNumber(expired)} vencido(s)`;
  }
}

function render() {
  if (host) {
    mount(host, frag(
      el('header', { class: 'page-heading' },
        el('div', { class: 'page-heading-main' },
          el('p', { class: 'eyebrow', text: 'Registro de valores' }),
          el('h1', { text: 'Valores del IPV' }),
          el('p', { text: 'Insumos, materias primas, tarifas y servicios con su precio unitario, vigencia y documento de respaldo. Cada ficha conserva el valor aplicado en el momento de su elaboración.' })),
        el('div', { class: 'page-heading-actions' },
          el('span', { class: 'tag', 'data-role': 'count' }, '—'),
          button('Registrar valor', { variant: 'primary', iconName: 'plus', onClick: () => openMaterialModal() }))),
      buildTable(),
      el('p', {
        class: 'subtle', style: { marginTop: 'var(--space-4)', fontSize: 'var(--text-2xs)' },
        text: 'Un valor vencido o suspendido no bloquea las fichas históricas, pero se informa durante la validación de los controles de IPV.',
      })));
  }
  sync();
}

function onDataChange() {
  const state = data.state();
  if (!state.ready || !host) return;
  if (!table || !host.querySelector('table.data')) render();
  else sync();
}

/** Abre el formulario cuando la ruta lo solicita (?nueva=1). */
function applyRoute(route = {}) {
  if ((route.query || {}).nueva === '1') {
    openMaterialModal();
    ctxRef?.navigate('/valores', { replace: true });
  }
}

export const materialsView = {
  id: 'materials',
  title: 'Valores del IPV',
  crumb: 'Valores del IPV',
  description: 'Valores de referencia utilizados en las fichas de costo.',
  mount(container, ctx) {
    host = container;
    ctxRef = ctx;
    const query = ctx.route?.query || {};
    initialQuery = query.q || '';
    filters = { kind: query.tipo || '', state: query.estado || '' };
    table = null;
    if (data.state().ready) render();
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
