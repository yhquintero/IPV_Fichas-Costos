/**
 * IPV · Fichas y Costos
 * Vista: bitácora de auditoría (trazabilidad de todas las operaciones).
 * Autor: Ing. Yosvany Hernández Quintero
 */

import { clear, el, frag, icon, mount } from '../core/dom.js';
import { api } from '../core/api.js';
import { data } from '../core/data.js';
import { exportCsv, fmtDateTime, fmtNumber, fmtRelative, timestampForFilename } from '../core/format.js';
import { badge, button, emptyState, runAction, toast } from '../core/ui.js';
import { printTableReport } from '../components/print.js';

const ACTION_LABELS = {
  crear: 'Registro creado',
  actualizar: 'Datos actualizados',
  aprobar: 'Aprobación',
  validar: 'Validación',
  versionar: 'Nueva versión',
  recalcular: 'Recálculo de precios',
  reabrir: 'Reapertura',
  activar: 'Reactivación',
  desactivar: 'Desactivación',
  restaurar: 'Restauración de respaldo',
  sistema: 'Evento del sistema',
};
const ACTION_TONES = {
  crear: 'brand', actualizar: 'brand', aprobar: 'success', validar: 'success',
  versionar: 'brand', recalcular: 'warning', reabrir: 'warning', desactivar: 'danger',
  restaurar: 'warning', sistema: 'neutral',
};
const ENTITY_LABELS = {
  producto: 'Productos', valor: 'Valores del IPV', ficha: 'Fichas de costo',
  control: 'Controles de IPV', sistema: 'Sistema',
};

let unsubscribe = null;
let host = null;
let ctxRef = null;
let events = [];
let limit = 80;
let filters = { entity: '', query: '' };

function visibleEvents() {
  let rows = events;
  if (filters.entity) rows = rows.filter((event) => event.entity === filters.entity);
  if (filters.query) {
    const needle = filters.query.toLowerCase();
    rows = rows.filter((event) => `${event.summary} ${event.actor} ${event.action} ${event.entity}`
      .toLowerCase().includes(needle));
  }
  return rows;
}

async function loadEvents({ more = false } = {}) {
  if (more) limit += 80;
  const result = await runAction(() => api.audit(limit));
  if (result === null) return;
  events = result;
  render();
}

function timelineItem(event) {
  const iconName = event.action === 'validar' ? 'shieldCheck'
    : event.action === 'aprobar' ? 'check-circle'
      : event.action === 'reabrir' || event.action === 'recalcular' ? 'clock'
        : event.action === 'desactivar' ? 'archive'
          : event.action === 'restaurar' ? 'upload'
            : event.action === 'sistema' ? 'server' : 'history';
  const tone = ACTION_TONES[event.action] || 'brand';
  return el('div', { class: 'timeline-item' },
    el('span', { class: `timeline-dot timeline-dot--${tone === 'neutral' ? 'brand' : tone}` }, icon(iconName, { size: 15 })),
    el('div', { class: 'timeline-body' },
      el('p', { class: 'timeline-title', text: event.summary }),
      el('p', { class: 'timeline-meta' },
        badge(ACTION_LABELS[event.action] || event.action, tone),
        el('span', {}, 'Entidad: ', el('strong', { text: ENTITY_LABELS[event.entity] || event.entity })),
        event.entity_id ? el('span', {}, '#', el('span', { text: String(event.entity_id) })) : null,
        el('span', {}, icon('user', { size: 12 }), ' ', el('span', { text: event.actor })),
        el('span', { text: fmtDateTime(event.at) }),
        el('span', { text: fmtRelative(event.at) }))));
}

function render() {
  if (!host) return;
  const rows = visibleEvents();
  const counter = host.querySelector?.('[data-role="count"]');
  const list = host.querySelector('[data-role="list"]');
  const footer = host.querySelector('[data-role="footer"]');
  if (!list) return;
  mount(list, rows.length
    ? el('div', { class: 'timeline' }, ...rows.map(timelineItem))
    : emptyState({
      iconName: 'history',
      title: 'Sin eventos para los filtros aplicados',
      message: 'Ajuste la entidad o el término de búsqueda para ver otros movimientos.',
    }));
  if (counter) counter.textContent = `${fmtNumber(rows.length)} evento(s) · ${fmtNumber(events.length)} cargado(s)`;
  if (footer) {
    mount(footer, el('div', { class: 'row', style: { justifyContent: 'center' } },
      events.length >= limit
        ? button('Cargar más eventos', { iconName: 'arrow-down', onClick: () => loadEvents({ more: true }) })
        : el('span', { class: 'subtle', text: 'Se muestran todos los eventos disponibles.' })));
  }
}

function buildLayout() {
  const entitySelect = el('select', {
    class: 'select', 'aria-label': 'Filtrar por entidad', style: { maxWidth: '220px' },
    on: { change: (event) => { filters.entity = event.target.value; render(); } },
  }, el('option', { value: '', text: 'Todas las entidades' }),
    ...Object.entries(ENTITY_LABELS).map(([value, label]) => el('option', { value, text: label })));

  const searchInput = el('input', {
    type: 'search', placeholder: 'Buscar por descripción, acción o responsable…',
    'aria-label': 'Buscar en la bitácora', autocomplete: 'off',
    on: {
      input: (event) => {
        filters.query = event.target.value.trim();
        clearTimeout(searchInput.__timer);
        searchInput.__timer = setTimeout(render, 160);
      },
    },
  });

  const card = el('section', { class: 'card card--flush' },
    el('div', { class: 'table-toolbar' },
      el('label', { class: 'search-field' }, icon('search', { size: 16 }), searchInput),
      entitySelect,
      el('span', { class: 'tag', 'data-role': 'count' }, '—'),
      button('Exportar CSV', { iconName: 'download', size: 'sm', onClick: exportAudit }),
      button('Imprimir', { iconName: 'printer', size: 'sm', onClick: printAudit })),
    el('div', { style: { padding: 'var(--space-5)' }, 'data-role': 'list' }),
    el('div', { style: { padding: 'var(--space-4)', borderTop: '1px solid var(--border)' }, 'data-role': 'footer' }));

  return frag(
    el('header', { class: 'page-heading' },
      el('div', { class: 'page-heading-main' },
        el('p', { class: 'eyebrow', text: 'Administración' }),
        el('h1', { text: 'Bitácora de auditoría' }),
        el('p', { text: 'Registro cronológico de cada operación realizada sobre el catálogo, los valores del IPV, las fichas de costo y los controles.' })),
      el('div', { class: 'page-heading-actions' },
        button('Actualizar', { iconName: 'refresh', onClick: () => loadEvents() }))),
    card,
    el('p', { class: 'subtle', style: { marginTop: 'var(--space-4)', fontSize: 'var(--text-2xs)' },
      text: 'La bitácora es de solo lectura. Cada asiento identifica la acción, la entidad afectada, el responsable y el momento exacto de la operación.' }));
}

function exportAudit() {
  const rows = visibleEvents();
  exportCsv(`bitacora-auditoria-${timestampForFilename()}.csv`,
    ['Fecha y hora', 'Acción', 'Entidad', 'Identificador', 'Descripción', 'Responsable'],
    rows.map((event) => [event.at, ACTION_LABELS[event.action] || event.action, ENTITY_LABELS[event.entity] || event.entity,
      event.entity_id ?? '', event.summary, event.actor]));
  toast(`${rows.length} evento(s) exportado(s) a CSV.`, { type: 'success' });
}

function printAudit() {
  const rows = visibleEvents();
  printTableReport({
    title: 'Bitácora de auditoría',
    subtitle: 'Trazabilidad de las operaciones registradas en el sistema',
    meta: [
      ['Eventos', String(rows.length)],
      ['Entidad', filters.entity ? (ENTITY_LABELS[filters.entity] || filters.entity) : 'Todas'],
      ['Generado', new Date().toLocaleString('es')],
    ],
    columns: [
      { key: 'at', label: 'Fecha y hora' },
      { label: 'Acción', value: (row) => ACTION_LABELS[row.action] || row.action },
      { label: 'Entidad', value: (row) => ENTITY_LABELS[row.entity] || row.entity },
      { key: 'summary', label: 'Descripción' },
      { key: 'actor', label: 'Responsable' },
    ],
    rows,
  });
}

export const auditView = {
  id: 'audit',
  title: 'Bitácora de auditoría',
  crumb: 'Bitácora de auditoría',
  description: 'Registro cronológico de operaciones.',
  async mount(container, ctx) {
    host = container;
    ctxRef = ctx;
    mount(host, buildLayout());
    const state = data.state();
    events = Array.isArray(state.audit) ? state.audit : [];
    render();
    if (!events.length) await loadEvents();
    unsubscribe = data.subscribe(() => {
      const current = data.state().audit;
      if (Array.isArray(current) && current.length > events.length) {
        events = current;
        render();
      }
    });
  },
  unmount() {
    if (unsubscribe) unsubscribe();
    unsubscribe = null;
    if (host) clear(host);
    host = null;
  },
};
