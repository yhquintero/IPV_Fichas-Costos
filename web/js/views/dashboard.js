/**
 * IPV · Fichas y Costos
 * Vista: resumen general (indicadores, alertas, tendencia y actividad).
 * Autor: Ing. Yosvany Hernández Quintero
 */

import { clear, el, frag, icon, mount } from '../core/dom.js';
import { data } from '../core/data.js';
import { selectors } from '../core/store.js';
import { fmtDate, fmtMoney, fmtNumber, fmtPercent, fmtPeriod, fmtQuantity, fmtRelative } from '../core/format.js';
import { badge, button, card, emptyState, statusPill } from '../core/ui.js';
import { barChart, donutChart } from '../components/charts.js';

let unsubscribe = null;
let host = null;
let ctxRef = null;

const ALERT_ICONS = { critical: 'alert', warning: 'alert', info: 'info' };

function kpiCard({ label, value, iconName, tone = '', foot = [] }) {
  return el('article', { class: 'kpi' },
    el('div', { class: 'kpi-top' },
      el('span', { class: 'kpi-label', text: label }),
      el('span', { class: `kpi-icon${tone ? ` kpi-icon--${tone}` : ''}` }, icon(iconName, { size: 17 }))),
    el('div', { class: 'kpi-value', text: value }),
    el('div', { class: 'kpi-foot' }, ...foot));
}

function renderKpis(dashboard) {
  const kpis = dashboard.kpis || {};
  const previousMonth = dashboard.trend?.fichas?.slice(-2) ?? [];
  const monthDelta = previousMonth.length === 2 ? previousMonth[1] - previousMonth[0] : 0;
  const trendTone = monthDelta > 0 ? 'up' : monthDelta < 0 ? 'down' : 'flat';

  return el('div', { class: 'kpi-grid' },
    kpiCard({
      label: 'Productos y servicios activos',
      value: fmtNumber(kpis.active_products),
      iconName: 'package',
      foot: [
        el('strong', { text: `${fmtNumber(kpis.products)} en el catálogo` }),
        el('span', { text: `· ${fmtNumber(kpis.products_without_ficha)} sin ficha` }),
      ],
    }),
    kpiCard({
      label: 'Fichas de costo',
      value: fmtNumber(kpis.fichas),
      iconName: 'file',
      tone: 'accent',
      foot: [
        el('strong', { text: `${fmtNumber(kpis.approved_fichas)} aprobadas` }),
        el('span', { text: `· ${fmtPercent(kpis.approval_rate)} del total` }),
      ],
    }),
    kpiCard({
      label: 'Controles de IPV',
      value: fmtNumber(kpis.controls),
      iconName: 'shield',
      tone: kpis.pending_controls || kpis.controls_with_differences ? 'warning' : '',
      foot: [
        el('strong', { text: `${fmtNumber(kpis.pending_controls)} pendientes` }),
        kpis.controls_with_differences
          ? el('span', { text: `· ${fmtNumber(kpis.controls_with_differences)} con diferencias` })
          : el('span', { text: `· ${fmtNumber(kpis.validated_controls)} validados` }),
      ],
    }),
    kpiCard({
      label: 'Costo medio de ficha aprobada',
      value: fmtMoney(kpis.average_ficha_cost),
      iconName: 'scale',
      tone: 'info',
      foot: [
        el('strong', { text: fmtMoney(kpis.approved_cost_total) }),
        previousMonth.length === 2
          ? el('span', { class: `trend trend--${trendTone}` },
            icon(monthDelta >= 0 ? 'arrow-up' : 'arrow-down', { size: 12 }),
            `${Math.abs(monthDelta)} ficha(s) este mes`)
          : null,
      ],
    }));
}

function renderAlerts(alerts) {
  if (!alerts?.length) {
    return card({
      title: 'Estado de la gestión',
      subtitle: 'Sin alertas activas',
      body: el('div', { style: { padding: '0 var(--space-5) var(--space-5)' } },
        el('div', { class: 'banner', style: { background: 'var(--success-soft)', color: 'var(--success)' } },
          icon('check-circle', { size: 17 }),
          el('span', {}, el('b', { text: 'Todo en orden' }),
            'No se detectaron pendientes de validación, valores vencidos ni productos sin ficha.'))),
    });
  }
  return card({
    title: 'Atención requerida',
    subtitle: `${alerts.length} situación(es) que requieren seguimiento`,
    body: el('div', { style: { padding: '0 var(--space-5) var(--space-5)' } },
      el('div', { class: 'alert-list' },
        ...alerts.map((alert) => el('button', {
          class: `alert-item alert-item--${alert.severity}`,
          type: 'button',
          on: { click: () => ctxRef.navigate(`/${alert.view === 'materials' ? 'valores' : alert.view === 'products' ? 'productos' : alert.view === 'controls' ? 'controles' : 'fichas'}`) },
        },
          el('span', { class: 'alert-icon' }, icon(ALERT_ICONS[alert.severity] || 'info', { size: 16 })),
          el('span', { class: 'alert-copy' }, el('b', { text: alert.title }), el('span', { text: alert.detail })),
          el('span', { class: 'alert-count', text: fmtNumber(alert.count) }),
          icon('chevron-right', { size: 16 }))))),
  });
}

function renderTrend(dashboard) {
  const trend = dashboard.trend || { periods: [], fichas: [], controls: [] };
  const chart = barChart({
    labels: trend.periods.map((period) => fmtPeriod(period).replace(' ', '\n').split('\n')[0]),
    series: [
      { name: 'Fichas creadas', values: trend.fichas },
      { name: 'Controles generados', values: trend.controls, variant: 'alt' },
    ],
    title: 'Documentos registrados por mes',
  });
  return card({
    title: 'Actividad documental por mes',
    subtitle: 'Fichas de costo y controles registrados en los últimos seis meses',
    body: el('div', { style: { padding: '0 var(--space-5) var(--space-5)' } }, chart),
  });
}

function renderCategories(dashboard) {
  const categories = dashboard.categories || [];
  const total = categories.reduce((sum, item) => sum + Number(item.products || 0), 0);
  const body = categories.length
    ? el('div', { style: { padding: '0 var(--space-5) var(--space-5)' } },
      el('div', { class: 'category-list' },
        ...categories.map((item) => el('div', { class: 'category-row' },
          el('span', { class: 'category-name', title: item.category, text: item.category }),
          el('div', { class: 'category-track' },
            el('div', { class: 'category-fill', style: { width: `${total ? Math.max(6, (item.products / total) * 100) : 0}%` } })),
          el('span', { class: 'category-meta', text: `${item.products} prod. · ${fmtMoney(item.average_cost)}` })))),
      el('div', { class: 'insight-card' },
        el('small', { text: 'Control preventivo' }),
        el('b', { text: 'Compruebe la vigencia de los valores antes de aprobar.' }),
        el('p', { text: 'Toda ficha conserva el precio aplicado en el momento de su elaboración; si el catálogo cambia, la variación se informa durante la validación del control.' })))
    : emptyState({ iconName: 'layers', title: 'Sin categorías registradas', message: 'Registre productos o servicios para ver la distribución por categoría.' });

  const donutData = categories.slice(0, 5).map((item) => ({ label: item.category, value: item.products }));
  const donut = donutData.length
    ? donutChart({
      segments: donutData,
      centerLabel: 'productos',
      centerValue: fmtNumber(total),
      formatValue: (value) => fmtNumber(value),
    })
    : null;

  return card({
    title: 'Catálogo por categoría',
    subtitle: 'Productos activos y costo medio aprobado',
    body: el('div', {},
      donut ? el('div', { style: { padding: '0 var(--space-5) var(--space-5)' } }, donut) : null,
      body),
  });
}

function recentFichasCard(dashboard) {
  const rows = dashboard.recent_fichas || [];
  const body = rows.length
    ? el('div', { class: 'mini-list', style: { padding: '0 var(--space-4) var(--space-4)' } },
      ...rows.map((ficha) => el('button', {
        class: 'mini-item', type: 'button',
        on: { click: () => ctxRef.navigate(`/fichas/${ficha.id}`) },
      },
        el('span', { class: 'avatar-glyph', text: (ficha.product_code || '??').split('-')[0].slice(0, 2) }),
        el('span', { class: 'mini-item-main' },
          el('b', { text: ficha.product_name }),
          el('span', { text: `v${ficha.version} · ${ficha.product_code} · ${fmtRelative(ficha.updated_at)}` })),
        el('span', { class: 'mini-item-value', text: fmtMoney(ficha.total_cost) }),
        statusPill(ficha.status))))
    : emptyState({
      iconName: 'file',
      title: 'Todavía no hay fichas de costo',
      message: 'Cree la primera ficha para comenzar a documentar los costos de sus productos.',
      actionLabel: 'Ir a fichas de costo',
      onAction: () => ctxRef.navigate('/fichas'),
    });

  return card({
    title: 'Fichas actualizadas recientemente',
    subtitle: 'Últimos documentos modificados',
    actions: button('Ver todas', { variant: 'ghost', size: 'sm', iconName: 'arrow-right', onClick: () => ctxRef.navigate('/fichas') }),
    body,
  });
}

function activityCard(dashboard) {
  const events = dashboard.activity || [];
  const body = events.length
    ? el('div', { style: { padding: '0 var(--space-5) var(--space-5)' } },
      el('div', { class: 'timeline' }, ...events.map((event) => el('div', { class: 'timeline-item' },
        el('span', { class: 'timeline-dot timeline-dot--brand' }, icon('history', { size: 15 })),
        el('div', { class: 'timeline-body' },
          el('p', { class: 'timeline-title', text: event.summary }),
          el('p', { class: 'timeline-meta' },
            el('span', { text: event.actor }),
            el('span', { text: fmtRelative(event.at) })))))))
    : emptyState({ iconName: 'history', title: 'Sin eventos registrados', message: 'La bitácora mostrará cada operación realizada en el sistema.' });

  return card({
    title: 'Actividad reciente',
    subtitle: 'Últimos movimientos registrados en la bitácora',
    actions: button('Bitácora completa', { variant: 'ghost', size: 'sm', onClick: () => ctxRef.navigate('/bitacora') }),
    body,
  });
}

function render() {
  if (!host) return;
  const state = data.state();
  if (!state.dashboard) {
    mount(host, el('div', { class: 'stack' },
      el('div', { class: 'skeleton', style: { height: '72px' } }),
      el('div', { class: 'kpi-grid' }, ...Array.from({ length: 4 }, () => el('div', { class: 'skeleton', style: { height: '132px' } }))),
      el('div', { class: 'skeleton', style: { height: '280px' } })));
    return;
  }
  const dashboard = state.dashboard;
  const counts = selectors.counts(state);
  mount(host, frag(
    el('header', { class: 'page-heading' },
      el('div', { class: 'page-heading-main' },
        el('p', { class: 'eyebrow', text: 'Visión general' }),
        el('h1', { text: 'Tablero de control de costos' }),
        el('p', { text: 'Indicadores del catálogo, avance de las fichas de costo y estado de los controles de precios del IPV.' })),
      el('div', { class: 'page-heading-actions' },
        button('Registrar valor del IPV', { iconName: 'tag', onClick: () => ctxRef.navigate('/valores', { query: { nueva: '1' } }) }),
        button('Nueva ficha de costo', { variant: 'primary', iconName: 'plus', onClick: () => ctxRef.navigate('/fichas', { query: { nueva: '1' } }) }))),
    renderKpis(dashboard),
    el('div', { class: 'dashboard-columns', style: { marginTop: 'var(--space-4)' } },
      el('div', { class: 'stack' }, renderTrend(dashboard), recentFichasCard(dashboard)),
      el('div', { class: 'stack' },
        renderAlerts(dashboard.alerts),
        renderCategories(dashboard),
        activityCard(dashboard))),
    el('p', { class: 'subtle', style: { marginTop: 'var(--space-4)', fontSize: 'var(--text-2xs)' },
      text: `${fmtNumber(counts.products)} productos activos · ${fmtNumber(counts.materials)} valores registrados · ${fmtQuantity(counts.fichas)} fichas · actualizado ${fmtDate(new Date())}` })));
}

export const dashboardView = {
  id: 'dashboard',
  title: 'Resumen',
  crumb: 'Resumen',
  description: 'Indicadores generales del sistema de costos.',
  mount(container, ctx) {
    host = container;
    ctxRef = ctx;
    render();
    unsubscribe = data.subscribe(render);
  },
  unmount() {
    if (unsubscribe) unsubscribe();
    unsubscribe = null;
    host = null;
    if (host) clear(host);
    host = null;
  },
};
