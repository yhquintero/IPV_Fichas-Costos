/**
 * IPV · Fichas y Costos
 * Vista: Controles de IPV (validación de precios, instantáneas y actas).
 * Autor: Ing. Yosvany Hernández Quintero
 */

import { clear, el, frag, icon, mount } from '../core/dom.js';
import { api } from '../core/api.js';
import { data } from '../core/data.js';
import { prefs } from '../core/prefs.js';
import { downloadJson, exportCsv, fmtAmount, fmtDateTime, fmtMoney, fmtNumber, fmtPeriod, fmtQuantity, fmtRelative, timestampForFilename } from '../core/format.js';
import { button, definition, emptyState, field, linkAction, openDrawer, openModal, readForm, runAction, statusPill, tag, toast } from '../core/ui.js';
import { dataTable } from '../components/data-table.js';
import { catalogCell, itemsTable } from '../components/cells.js';
import { printControl, printTableReport } from '../components/print.js';

const AUDIT_TONES = { crear: 'brand', validar: 'success', actualizar: 'brand' };

let unsubscribe = null;
let ctxRef = null;
let table = null;
let host = null;
let statusSelect = null;
let periodSelect = null;
let filters = { status: '', period: '' };
let initialQuery = '';
let activeDrawer = null;
let drawerId = null;

/* -------------------------------------------------------------------------- */
/* Acciones                                                                    */
/* -------------------------------------------------------------------------- */
async function validateControl(control) {
  const form = el('form', {},
    field({
      label: 'Responsable de la validación', name: 'checked_by', required: true,
      value: control.checked_by || prefs.get('operator'),
      hint: 'Se registrará en el acta y en la bitácora de auditoría.',
    }),
    field({ label: 'Observaciones del control', name: 'notes', type: 'textarea', value: control.notes || '', placeholder: 'Notas de la revisión' }));
  const modal = openModal({
    title: control.checked_at ? 'Revalidar Control de IPV' : 'Validar Control de IPV',
    subtitle: `${control.code} · período ${control.period}`,
    content: frag(
      el('div', { class: 'banner' }, icon('shieldCheck', { size: 16 }),
        el('span', { text: 'La validación compara la instantánea del control con la ficha de costo aprobada, verifica los subtotales y deja constancia de las variaciones de precios detectadas.' })),
      form),
    actions: [
      el('button', { class: 'btn btn--secondary', type: 'button', text: 'Cancelar', on: { click: () => modal.close() } }),
      el('button', {
        class: 'btn btn--primary', type: 'button', text: control.checked_at ? 'Revalidar' : 'Ejecutar validación',
        on: {
          click: async () => {
            if (!form.reportValidity()) return;
            const payload = readForm(form);
            modal.close();
            const result = await runAction(() => api.post(`/api/controls/${control.id}/validate`, payload),
              { success: 'Validación ejecutada. Consulte el informe.' });
            if (result === null) return;
            await data.reload({ silent: true });
            openControlDrawer(control.id);
          },
        },
      }),
    ],
  });
}

function editNotes(control) {
  const form = el('form', {},
    field({ label: 'Observaciones del control', name: 'notes', type: 'textarea', value: control.notes || '', placeholder: 'Notas de revisión, acuerdos o seguimiento' }));
  const modal = openModal({
    title: 'Observaciones del control',
    subtitle: control.code,
    content: form,
    actions: [
      el('button', { class: 'btn btn--secondary', type: 'button', text: 'Cancelar', on: { click: () => modal.close() } }),
      el('button', {
        class: 'btn btn--primary', type: 'button', text: 'Guardar observaciones',
        on: {
          click: async () => {
            const payload = readForm(form);
            modal.close();
            const result = await runAction(() => api.patch(`/api/controls/${control.id}`, payload), { success: 'Observaciones actualizadas.' });
            if (result === null) return;
            await data.reload({ silent: true });
            openControlDrawer(control.id);
          },
        },
      }),
    ],
  });
}

function exportControlCsv(control) {
  exportCsv(`control-${control.code}-${timestampForFilename()}.csv`,
    ['Comprobación', 'Resultado', 'Esperado', 'Registrado'],
    [
      ...(control.validation_report || []).map((entry) => [entry.check, entry.text, entry.expected || '', entry.actual || '']),
      [],
      ['Componente', 'Unidad', 'Cantidad', 'Costo unitario', 'Subtotal', '% del total'],
      ...control.items.map((item) => [item.description, item.unit, item.quantity, item.unit_cost, item.subtotal, item.share_percent]),
    ]);
  toast('Control exportado a CSV.', { type: 'success' });
}

/* -------------------------------------------------------------------------- */
/* Panel de detalle                                                            */
/* -------------------------------------------------------------------------- */
function validationReport(control) {
  const report = control.validation_report || [];
  if (!report.length) {
    return el('div', { class: 'banner banner--neutral' }, icon('info', { size: 16 }),
      el('span', { text: 'Este control aún no ha sido validado. Ejecute la validación para comparar la instantánea con la ficha de costo vinculada.' }));
  }
  const errors = report.filter((entry) => entry.level === 'error').length;
  const warnings = report.filter((entry) => entry.level === 'warning').length;
  const tone = errors ? 'danger' : warnings ? 'warning' : 'success';
  return frag(
    el('div', { class: `banner banner--${tone}` },
      icon(errors ? 'alert' : warnings ? 'alert' : 'check-circle', { size: 17 }),
      el('span', {},
        el('b', { text: errors ? 'Se detectaron diferencias' : warnings ? 'Validado con observaciones' : 'Control validado sin diferencias' }),
        `${errors} comprobación(es) con error · ${warnings} observación(es) informativa(s)`)),
    el('div', { class: 'check-list', style: { marginTop: 'var(--space-4)' } },
      ...report.map((entry) => el('div', { class: `check-item check-item--${entry.level}` },
        el('span', { class: 'check-mark' }, icon(entry.level === 'ok' ? 'check' : entry.level === 'warning' ? 'alert' : 'x', { size: 12 })),
        el('div', { style: { minWidth: '0' } },
          el('b', { text: entry.check }),
          el('p', { text: entry.text }),
          entry.expected
            ? el('p', { class: 'check-compare' },
              el('span', {}, 'Esperado: ', el('code', { text: entry.expected })),
              el('span', {}, 'Registrado: ', el('code', { text: entry.actual ?? '—' })))
            : null)))));
}

function controlDetailPanel(control) {
  const body = el('div');
  const tabList = el('div', { class: 'tabs', role: 'tablist' });
  const tabs = [
    { id: 'validacion', label: 'Informe de validación' },
    { id: 'detalle', label: 'Detalle del control' },
    { id: 'bitacora', label: 'Bitácora' },
  ];
  let current = 'validacion';

  const renderTab = () => {
    if (current === 'validacion') { mount(body, validationReport(control)); return; }
    if (current === 'detalle') {
      mount(body, frag(
        el('dl', { class: 'def-grid' },
          definition('Código del control', control.code),
          definition('Período revisado', fmtPeriod(control.period)),
          definition('Producto / servicio', control.product_name),
          definition('Categoría', control.category),
          definition('Ficha vinculada', `FC-${control.product_code}-v${control.ficha_version}`),
          definition('Estado de la ficha', control.ficha_status),
          definition('Total de la instantánea', fmtMoney(control.snapshot_total), { emphasis: true }),
          definition('Total verificado', control.checked_at ? fmtMoney(control.checked_total) : 'Sin validar'),
          definition('Registrado por', control.created_by || '—'),
          definition('Fecha de creación', fmtDateTime(control.created_at)),
          definition('Validado por', control.checked_by || 'Pendiente'),
          definition('Fecha de validación', control.checked_at ? fmtDateTime(control.checked_at) : 'Pendiente')),
        el('h3', { style: { margin: 'var(--space-6) 0 var(--space-3)' }, text: 'Instantánea de componentes' }),
        itemsTable({
          headers: [
            { text: 'Componente' },
            { text: 'Unidad' },
            { class: 'align-right', text: 'Cantidad' },
            { class: 'align-right', text: 'Costo unitario' },
            { class: 'align-right', text: 'Subtotal' },
            { class: 'align-right', text: '% del total' },
          ],
          rows: control.items.map((item) => [
            { class: 'strong', text: item.description },
            { class: 'muted', text: item.unit },
            { class: 'align-right numeric', text: fmtQuantity(item.quantity) },
            { class: 'align-right numeric', text: fmtAmount(item.unit_cost) },
            { class: 'align-right amount', text: fmtAmount(item.subtotal) },
            { class: 'align-right numeric', text: `${item.share_percent} %` },
          ]),
        }),
        control.notes ? el('div', { class: 'banner banner--neutral', style: { marginTop: 'var(--space-4)' } },
          icon('clipboard', { size: 16 }), el('span', { text: control.notes })) : null));
      return;
    }
    mount(body, control.audit?.length
      ? el('div', { class: 'timeline' }, ...control.audit.map((event) => el('div', { class: 'timeline-item' },
        el('span', { class: `timeline-dot timeline-dot--${AUDIT_TONES[event.action] || 'brand'}` }, icon('history', { size: 15 })),
        el('div', { class: 'timeline-body' },
          el('p', { class: 'timeline-title', text: event.summary }),
          el('p', { class: 'timeline-meta' }, el('span', { text: event.actor }), el('span', { text: fmtDateTime(event.at) }))))))
      : emptyState({ iconName: 'history', title: 'Sin movimientos', message: 'Las operaciones sobre este control se mostrarán aquí.' }));
  };

  tabs.forEach((tab) => tabList.append(el('button', {
    class: 'tab', type: 'button', role: 'tab', 'aria-selected': tab.id === current ? 'true' : 'false', text: tab.label,
    on: {
      click: (event) => {
        current = tab.id;
        [...tabList.children].forEach((node) => node.setAttribute('aria-selected', node === event.currentTarget ? 'true' : 'false'));
        renderTab();
      },
    },
  })));

  renderTab();
  return el('div', {}, tabList, body);
}

async function openControlDrawer(id) {
  let control;
  try {
    control = await api.control(id);
  } catch (error) {
    toast(error.message, { type: 'error' });
    if (activeDrawer) { const drawer = activeDrawer; activeDrawer = null; drawer.close({ silent: true }); }
    if (ctxRef?.route?.params?.id) ctxRef.navigate('/controles', { replace: true });
    return;
  }
  if (String(drawerId) === String(control.id) && activeDrawer) {
    activeDrawer.setContent(controlDetailPanel(control));
    return;
  }
  if (activeDrawer) { const drawer = activeDrawer; activeDrawer = null; drawer.close({ silent: true }); }
  drawerId = control.id;
  const pending = control.status === 'Pendiente';

  activeDrawer = openDrawer({
    title: `Control ${control.code}`,
    subtitle: `${control.product_name} · período ${fmtPeriod(control.period)} · ${fmtRelative(control.created_at)}`,
    headerExtra: el('div', { class: 'row', style: { marginTop: 'var(--space-3)' } },
      statusPill(control.status),
      tag(fmtMoney(control.snapshot_total), 'scale'),
      tag(`Ficha v${control.ficha_version}`, 'file')),
    actions: [
      button(pending ? 'Ejecutar validación' : 'Revalidar', { variant: 'primary', iconName: 'shieldCheck', size: 'sm', onClick: () => validateControl(control) }),
      button('Observaciones', { iconName: 'edit', size: 'sm', onClick: () => editNotes(control) }),
      button('Imprimir acta', { iconName: 'printer', size: 'sm', onClick: () => printControl(control) }),
      button('Exportar CSV', { iconName: 'download', size: 'sm', onClick: () => exportControlCsv(control) }),
      button('Exportar JSON', { iconName: 'download', size: 'sm', onClick: () => downloadJson(`control-${control.code}.json`, control) }),
      button('Abrir ficha', { iconName: 'file', size: 'sm', onClick: () => ctxRef.navigate(`/fichas/${control.ficha_id}`) }),
    ],
    content: controlDetailPanel(control),
    onClose: () => {
      activeDrawer = null;
      drawerId = null;
      if (ctxRef?.route?.params?.id) ctxRef.navigate('/controles', { replace: true });
    },
  });
}

/** Aplica la ruta recibida sin volver a montar la vista. */
function applyRoute(route = {}) {
  const params = route.params || {};
  if (params.id) {
    if (String(drawerId) !== String(params.id)) openControlDrawer(params.id);
    return;
  }
  if (activeDrawer) {
    const drawer = activeDrawer;
    activeDrawer = null;
    drawerId = null;
    drawer.close({ silent: true });
  }
}

/* -------------------------------------------------------------------------- */
/* Listado                                                                     */
/* -------------------------------------------------------------------------- */
function buildTable() {
  table = dataTable({
    state: { query: initialQuery },
    columns: [
      {
        key: 'code', label: 'Control',
        render: (row) => catalogCell({
          code: `Creado ${fmtDateTime(row.created_at)}`,
          name: row.code,
          category: row.category,
          meta: [`Período ${fmtPeriod(row.period)}`],
        }),
      },
      { key: 'product_name', label: 'Producto o servicio', render: (row) => el('span', { text: row.product_name }) },
      { key: 'period', label: 'Período', render: (row) => el('span', { class: 'muted', text: fmtPeriod(row.period) }) },
      { key: 'ficha_version', label: 'Ficha vinculada', render: (row) => tag(`FC-${row.product_code}-v${row.ficha_version}`, 'file') },
      { key: 'snapshot_total', label: 'Total controlado', align: 'right', render: (row) => el('span', { class: 'amount', text: fmtAmount(row.snapshot_total) }) },
      {
        key: 'checked_total', label: 'Total verificado', align: 'right',
        render: (row) => (row.checked_at ? el('span', { class: 'numeric', text: fmtAmount(row.checked_total) }) : el('span', { class: 'subtle', text: '—' })),
      },
      { key: 'status', label: 'Estado', render: (row) => statusPill(row.status) },
      {
        key: 'actions', label: 'Acciones', align: 'right', sortable: false,
        render: (row) => el('div', { class: 'table-actions' },
          el('button', {
            class: 'icon-btn', type: 'button', title: 'Ver informe', 'aria-label': 'Ver informe',
            on: { click: () => ctxRef.navigate(`/controles/${row.id}`) },
          }, icon('clipboard', { size: 16 })),
          el('button', {
            class: 'icon-btn', type: 'button', title: 'Validar', 'aria-label': 'Validar',
            on: { click: async () => validateControl(await api.control(row.id)) },
          }, icon('shieldCheck', { size: 16 })),
          el('button', {
            class: 'icon-btn', type: 'button', title: 'Imprimir acta', 'aria-label': 'Imprimir acta',
            on: { click: async () => printControl(await api.control(row.id)) },
          }, icon('printer', { size: 16 }))),
      },
    ],
    rows: [],
    toolbar: buildToolbar(),
    searchPlaceholder: 'Buscar por código, producto, período o estado…',
    searchKeys: ['code', 'product_name', 'product_code', 'period', 'status', 'notes'],
    pageSize: 12,
    sortKey: 'created_at',
    sortDir: 'desc',
    empty: {
      iconName: 'shield',
      title: 'No hay controles de IPV',
      message: 'Abra una ficha aprobada y use «Generar control» para crear el control del período.',
      actionLabel: 'Ir a las fichas de costo',
      onAction: () => ctxRef.navigate('/fichas'),
    },
    onRowClick: (row) => ctxRef.navigate(`/controles/${row.id}`),
    onStateChange: (uiState) => {
      ctxRef.navigate('/controles', {
        replace: true,
        query: { q: uiState.query || '', estado: filters.status || '', periodo: filters.period || '' },
      });
    },
  });
  return table.element;
}

function refreshToolbarOptions() {
  const periods = selectorsPeriods();
  periodSelect.replaceChildren(el('option', { value: '', text: 'Todos los períodos' }),
    ...periods.map((period) => el('option', { value: period, text: fmtPeriod(period) })));
  periodSelect.value = periods.includes(filters.period) ? filters.period : '';
  filters.period = periodSelect.value;
  statusSelect.value = filters.status;
}

function selectorsPeriods() {
  return [...new Set(data.state().controls.map((control) => control.period).filter(Boolean))].sort().reverse();
}

function buildToolbar() {
  statusSelect = el('select', {
    class: 'select', 'aria-label': 'Filtrar por estado', style: { maxWidth: '190px' },
    on: { change: (event) => { filters.status = event.target.value; sync(); } },
  }, el('option', { value: '', text: 'Todos los estados' }),
    ...['Pendiente', 'Validado', 'Con diferencias'].map((status) => el('option', { value: status, text: status })));
  periodSelect = el('select', {
    class: 'select', 'aria-label': 'Filtrar por período', style: { maxWidth: '190px' },
    on: { change: (event) => { filters.period = event.target.value; sync(); } },
  });
  refreshToolbarOptions();
  return [
    button('Exportar CSV', { iconName: 'download', size: 'sm', onClick: exportControls }),
    button('Imprimir listado', { iconName: 'printer', size: 'sm', onClick: printControls }),
    statusSelect,
    periodSelect,
  ];
}

function visibleRows() {
  let rows = data.state().controls;
  if (filters.status) rows = rows.filter((row) => row.status === filters.status);
  if (filters.period) rows = rows.filter((row) => row.period === filters.period);
  return rows;
}

function exportControls() {
  const rows = visibleRows();
  exportCsv(`controles-ipv-${timestampForFilename()}.csv`,
    ['Control', 'Producto', 'Código', 'Categoría', 'Período', 'Versión de ficha', 'Total controlado (CUP)',
      'Total verificado (CUP)', 'Estado', 'Validado por', 'Fecha de validación', 'Observaciones'],
    rows.map((row) => [row.code, row.product_name, row.product_code, row.category, row.period, row.ficha_version,
      row.snapshot_total, row.checked_total, row.status, row.checked_by, row.checked_at, row.notes]));
  toast(`${rows.length} control(es) exportado(s) a CSV.`, { type: 'success' });
}

function printControls() {
  const rows = visibleRows();
  printTableReport({
    title: 'Relación de Controles de IPV',
    subtitle: 'Controles registrados con el resultado de su validación',
    meta: [
      ['Controles listados', String(rows.length)],
      ['Estado', filters.status || 'Todos'],
      ['Generado', new Date().toLocaleString('es')],
    ],
    columns: [
      { key: 'code', label: 'Control' },
      { key: 'product_name', label: 'Producto o servicio' },
      { key: 'period', label: 'Período' },
      { key: 'ficha_version', label: 'Ficha', align: 'right' },
      { key: 'snapshot_total', label: 'Total controlado (CUP)', align: 'right' },
      { key: 'checked_total', label: 'Total verificado (CUP)', align: 'right' },
      { key: 'status', label: 'Estado' },
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
    const pending = data.state().controls.filter((control) => control.status !== 'Validado').length;
    counter.textContent = `${fmtNumber(rows.length)} en pantalla · ${fmtNumber(pending)} por validar`;
  }
}

function render() {
  if (host) {
    mount(host, frag(
      el('header', { class: 'page-heading' },
        el('div', { class: 'page-heading-main' },
          el('p', { class: 'eyebrow', text: 'Revisión y control' }),
          el('h1', { text: 'Controles de IPV' }),
          el('p', { text: 'Cada control conserva una instantánea de la ficha aplicada al período y el informe de validación con las comprobaciones de importes y las variaciones de precios detectadas.' })),
        el('div', { class: 'page-heading-actions' },
          el('span', { class: 'tag', 'data-role': 'count' }, '—'),
          button('Ir a las fichas', { iconName: 'file', onClick: () => ctxRef.navigate('/fichas') }))),
      buildTable(),
      el('p', {
        class: 'subtle', style: { marginTop: 'var(--space-4)', fontSize: 'var(--text-2xs)' },
        text: 'El informe de validación es un instrumento de apoyo: no sustituye la revisión normativa ni la documentación primaria del costo.',
      })));
  }
  sync();
}

function onDataChange() {
  if (!host || !data.state().ready) return;
  if (!table || !host.querySelector('table.data')) render();
  else sync();
}

export const controlsView = {
  id: 'controls',
  title: 'Controles de IPV',
  crumb: 'Controles de IPV',
  description: 'Controles de precios y validaciones del período.',
  mount(container, ctx) {
    host = container;
    ctxRef = ctx;
    const query = ctx.route?.query || {};
    initialQuery = query.q || '';
    filters = { status: query.estado || '', period: query.periodo || '' };
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
    if (activeDrawer) { const drawer = activeDrawer; activeDrawer = null; drawer.close({ silent: true }); }
    unsubscribe = null;
    drawerId = null;
    table = null;
    if (host) clear(host);
    host = null;
  },
};
