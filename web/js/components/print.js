/**
 * IPV · Fichas y Costos
 * Documentos imprimibles: Ficha de Costo y Acta de Control de IPV.
 * Autor: Ing. Yosvany Hernández Quintero
 */

import { clear, el, mount, qs } from '../core/dom.js';
import { fmtAmount, fmtDate, fmtFullStamp, fmtMoney, fmtPercent, fmtQuantity } from '../core/format.js';

const APP = {
  name: 'IPV · Fichas y Costos',
  version: '2.0.0',
  author: 'Ing. Yosvany Hernández Quintero',
};

const NOTICE = 'Documento generado por el sistema. Los valores aplicados son los registrados y aprobados en la ficha. '
  + 'Conserve este documento junto a la documentación primaria del costo.';

function header({ documentTitle, documentSubtitle, code, version }) {
  return el('div', { class: 'doc-header' },
    el('div', { class: 'doc-brand' },
      el('div', { class: 'doc-mark', text: 'iv' }),
      el('div', {},
        el('h1', { text: APP.name }),
        el('p', { text: 'Gestión de costos · Control de precios · Trazabilidad documental' }))),
    el('div', { class: 'doc-id' },
      el('b', { text: code }),
      el('span', { text: `${documentTitle}${version ? ` · v${version}` : ''}` }),
      el('span', { text: documentSubtitle || '' })));
}

function titleBlock(title, subtitle, state) {
  return el('div', { class: 'doc-title' },
    el('div', {}, el('h2', { text: title }), el('p', { text: subtitle })),
    state ? el('span', { class: 'doc-state', text: state }) : null);
}

function metaGrid(pairs) {
  const list = el('dl', { class: 'doc-meta' });
  pairs.filter(Boolean).forEach(([label, value]) => {
    list.append(el('div', {}, el('dt', { text: label }), el('dd', { text: value ?? '—' })));
  });
  return list;
}

function itemsTable(items, { currency = 'CUP', showShare = true } = {}) {
  const head = el('tr', {},
    el('th', { style: { width: '30px' }, text: '#' }),
    el('th', { text: 'Componente' }),
    el('th', { text: 'Unidad' }),
    el('th', { class: 'num', text: 'Cantidad' }),
    el('th', { class: 'num', text: 'Costo unitario' }),
    el('th', { class: 'num', text: 'Subtotal' }),
    showShare ? el('th', { class: 'num', text: '% del total' }) : null);

  const body = el('tbody');
  let total = 0;
  items.forEach((item, index) => {
    const subtotal = Number(item.subtotal) || 0;
    total += subtotal;
    body.append(el('tr', {},
      el('td', { text: String(index + 1) }),
      el('td', { text: item.description }),
      el('td', { text: item.unit }),
      el('td', { class: 'num', text: fmtQuantity(item.quantity) }),
      el('td', { class: 'num', text: fmtMoney(item.unit_cost, currency) }),
      el('td', { class: 'num', text: fmtMoney(subtotal, currency) }),
      showShare
        ? el('td', { class: 'num', text: fmtPercent(item.share_percent ?? (total ? (subtotal / total) * 100 : 0)) })
        : null));
  });

  const foot = el('tfoot', {}, el('tr', {},
    el('td', { colspan: showShare ? '5' : '4', text: 'TOTAL' }),
    el('td', { class: 'num', text: fmtMoney(total, currency) }),
    showShare ? el('td', {}) : null));

  return el('table', { class: 'doc-table' }, el('thead', {}, head), body, foot);
}

function signatures(names) {
  return el('div', { class: 'doc-signatures' },
    ...names.map((entry) => el('div', { class: 'doc-signature' },
      el('b', { text: entry.name || ' ' }),
      el('span', { text: entry.role }))));
}

function footer() {
  return el('div', { class: 'doc-footer' },
    el('span', { text: `${APP.name} · versión ${APP.version} · ${APP.author}` }),
    el('span', { text: `Generado el ${fmtFullStamp(new Date())}` }),
    el('span', { text: NOTICE }));
}

function run(documentNode) {
  const root = qs('#print-root');
  if (!root) return;
  mount(root, documentNode);
  root.setAttribute('aria-hidden', 'false');
  const cleanup = () => {
    clear(root);
    root.setAttribute('aria-hidden', 'true');
    window.removeEventListener('afterprint', cleanup);
  };
  window.addEventListener('afterprint', cleanup);
  setTimeout(() => window.print(), 120);
  setTimeout(cleanup, 120000);
}

/** Imprime la Ficha de Costo de un producto o servicio. */
export function printFicha(ficha) {
  const currency = 'CUP';
  const doc = el('article', { class: 'doc' },
    header({
      documentTitle: 'Ficha de Costo',
      documentSubtitle: `Producto ${ficha.product_code}`,
      code: `FC-${ficha.product_code}-v${ficha.version}`,
      version: ficha.version,
    }),
    titleBlock('Ficha de costo', `${ficha.product_name} · ${ficha.category}`, ficha.status),
    metaGrid([
      ['Producto / servicio', `${ficha.product_code} · ${ficha.product_name}`],
      ['Categoría', ficha.category],
      ['Unidad de salida', ficha.product_unit],
      ['Versión', `v${ficha.version}`],
      ['Vigente desde', fmtDate(ficha.valid_from)],
      ['Componentes', `${ficha.items.length}`],
      ['Costo total', fmtMoney(ficha.total_cost, currency)],
      ['Estado', ficha.status],
      ['Elaborado por', ficha.prepared_by || '—'],
      ['Aprobado por', ficha.approved_by || 'Pendiente'],
      ['Fecha de aprobación', ficha.approved_at ? fmtFullStamp(ficha.approved_at) : 'Pendiente'],
      ['Última actualización', fmtFullStamp(ficha.updated_at)],
    ]),
    itemsTable(ficha.items, { currency }),
    ficha.observations ? el('div', { class: 'doc-notes' }, el('b', { text: 'Observaciones: ' }), ficha.observations) : null,
    signatures([
      { name: ficha.prepared_by || '', role: 'Elaborado por' },
      { name: '', role: 'Revisado por' },
      { name: ficha.approved_by || '', role: 'Aprobado por' },
    ]),
    footer());

  run(doc);
}

/** Imprime el acta del Control de IPV con su informe de validación. */
export function printControl(control) {
  const currency = 'CUP';
  const report = control.validation_report || [];
  const errors = report.filter((entry) => entry.level === 'error');
  const warnings = report.filter((entry) => entry.level === 'warning');

  const checklist = el('div', { class: 'doc-checklist' },
    ...report.map((entry) => el('div', {},
      el('span', { class: 'mark', text: entry.level === 'ok' ? '✓' : entry.level === 'warning' ? '!' : '×' }),
      el('span', { text: `${entry.check}: ${entry.text}` }),
      entry.expected
        ? el('span', { class: 'expected', text: `Esperado ${entry.expected} · Registrado ${entry.actual ?? '—'}` })
        : null)));

  const doc = el('article', { class: 'doc' },
    header({
      documentTitle: 'Acta de Control de IPV',
      documentSubtitle: `Período ${control.period}`,
      code: `CT-${control.code}`,
      version: control.ficha_version,
    }),
    titleBlock('Control de IPV', `${control.product_code} · ${control.product_name}`, control.status),
    metaGrid([
      ['Código del control', control.code],
      ['Período revisado', control.period],
      ['Ficha vinculada', `FC-${control.product_code}-v${control.ficha_version}`],
      ['Estado de la ficha', control.ficha_status],
      ['Total del control', fmtMoney(control.snapshot_total, currency)],
      ['Total verificado', control.checked_at ? fmtMoney(control.checked_total, currency) : 'Sin validar'],
      ['Registrado por', control.created_by || '—'],
      ['Fecha de creación', fmtFullStamp(control.created_at)],
      ['Validado por', control.checked_by || 'Pendiente'],
      ['Fecha de validación', control.checked_at ? fmtFullStamp(control.checked_at) : 'Pendiente'],
    ]),
    itemsTable(control.items, { currency }),
    el('div', { class: 'doc-verdict' },
      el('b', { text: 'Resultado de la validación' }),
      el('p', { text: `${control.status}. Comprobaciones con error: ${errors.length}. Observaciones informativas: ${warnings.length}.` })),
    report.length ? checklist : null,
    control.notes ? el('div', { class: 'doc-notes' }, el('b', { text: 'Observaciones del control: ' }), control.notes) : null,
    signatures([
      { name: control.created_by || '', role: 'Responsable del control' },
      { name: control.checked_by || '', role: 'Validador del IPV' },
      { name: '', role: 'Dirección de la unidad' },
    ]),
    footer());

  run(doc);
}

/** Imprime un reporte tabular genérico (usado por el catálogo y los listados). */
export function printTableReport({ title, subtitle = '', columns, rows, meta = [] }) {
  const table = el('table', { class: 'doc-table' },
    el('thead', {}, el('tr', {}, ...columns.map((column) => el('th', {
      class: column.align === 'right' ? 'num' : '', text: column.label,
    })))),
    el('tbody', {}, ...rows.map((row) => el('tr', {},
      ...columns.map((column) => {
        const value = typeof column.value === 'function' ? column.value(row) : row[column.key];
        return el('td', { class: column.align === 'right' ? 'num' : '', text: value ?? '—' });
      })))));

  const doc = el('article', { class: 'doc' },
    header({ documentTitle: title, documentSubtitle: subtitle, code: 'IPV', version: '' }),
    titleBlock(title, subtitle, `${rows.length} registro(s)`),
    meta.length ? metaGrid(meta) : null,
    table,
    footer());

  run(doc);
}

export const printDefaults = { APP, NOTICE, fmtAmount };
