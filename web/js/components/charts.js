/**
 * IPV · Fichas y Costos
 * Gráficos vectoriales generados en el cliente (SVG, sin dependencias).
 * Autor: Ing. Yosvany Hernández Quintero
 */

import { el, svgEl } from '../core/dom.js';
import { fmtNumber } from '../core/format.js';

const WIDTH = 640;
const HEIGHT = 240;
const PADDING = { top: 18, right: 12, bottom: 34, left: 40 };

/**
 * Diagrama de barras agrupadas.
 * @param {object} options
 * @param {string[]} options.labels Etiquetas del eje X.
 * @param {{name: string, values: number[], variant?: string}[]} options.series
 * @param {string} [options.title] Descripción accesible.
 */
export function barChart({ labels = [], series = [], title = 'Evolución mensual', formatValue = (value) => fmtNumber(value) } = {}) {
  const innerWidth = WIDTH - PADDING.left - PADDING.right;
  const innerHeight = HEIGHT - PADDING.top - PADDING.bottom;
  const maxValue = Math.max(1, ...series.flatMap((item) => item.values));
  const niceMax = niceCeiling(maxValue);
  const groupWidth = labels.length ? innerWidth / labels.length : innerWidth;
  const barWidth = Math.max(6, Math.min(26, (groupWidth - 10) / Math.max(1, series.length)));
  const scale = (value) => innerHeight - (value / niceMax) * innerHeight;

  const root = svgEl('svg', {
    viewBox: `0 0 ${WIDTH} ${HEIGHT}`,
    role: 'img',
    'aria-label': `${title}. Valores máximos: ${formatValue(maxValue)}.`,
    preserveAspectRatio: 'xMidYMid meet',
  });

  // Líneas guía y etiquetas del eje Y
  const ticks = 4;
  for (let index = 0; index <= ticks; index += 1) {
    const value = (niceMax / ticks) * index;
    const y = PADDING.top + scale(value);
    root.append(svgEl('line', {
      x1: PADDING.left, x2: WIDTH - PADDING.right, y1: y, y2: y, class: 'chart-grid-line',
      'stroke-dasharray': index === 0 ? '' : '3 5',
    }));
    root.append(svgEl('text', {
      x: PADDING.left - 8, y: y + 3.5, 'text-anchor': 'end', class: 'chart-axis-label',
    }, formatValue(Math.round(value))));
  }

  labels.forEach((label, index) => {
    const groupStart = PADDING.left + index * groupWidth + (groupWidth - barWidth * series.length - 4 * (series.length - 1)) / 2;
    series.forEach((item, seriesIndex) => {
      const value = item.values[index] || 0;
      const height = Math.max(value > 0 ? 2 : 0, innerHeight - scale(value));
      const x = groupStart + seriesIndex * (barWidth + 4);
      const bar = svgEl('rect', {
        x, y: PADDING.top + scale(value), width: barWidth, height,
        rx: Math.min(4, barWidth / 2),
        class: `chart-bar${item.variant === 'alt' ? ' chart-bar--alt' : ''}`,
      });
      bar.append(svgEl('title', {}, `${label} · ${item.name}: ${formatValue(value)}`));
      root.append(bar);
    });
    root.append(svgEl('text', {
      x: PADDING.left + index * groupWidth + groupWidth / 2,
      y: HEIGHT - 10, 'text-anchor': 'middle', class: 'chart-axis-label',
    }, label));
  });

  const legend = el('div', { class: 'chart-legend' },
    ...series.map((item) => el('span', {}, el('i', { class: item.variant === 'alt' ? 'alt' : '' }), el('span', { text: item.name }))));

  return el('figure', { class: 'chart-figure' }, root, legend);
}

/**
 * Anillo de proporción para un conjunto de segmentos.
 * @param {{segments: {label: string, value: number, variant?: number}[], centerLabel?: string}} options
 */
export function donutChart({ segments = [], centerLabel = '', centerValue = '', formatValue = (value) => fmtNumber(value) } = {}) {
  const size = 190;
  const stroke = 22;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const total = segments.reduce((sum, item) => sum + Number(item.value || 0), 0);
  const root = svgEl('svg', {
    viewBox: `0 0 ${size} ${size}`, width: size, height: size, role: 'img',
    'aria-label': `${centerLabel}: ${centerValue || formatValue(total)}`,
  });
  root.append(svgEl('circle', {
    cx: size / 2, cy: size / 2, r: radius, fill: 'none',
    stroke: 'var(--surface-3)', 'stroke-width': stroke,
  }));
  let offset = 0;
  segments.forEach((segment, index) => {
    const portion = total ? Number(segment.value || 0) / total : 0;
    const length = portion * circumference;
    if (length > 0.4) {
      const arc = svgEl('circle', {
        cx: size / 2, cy: size / 2, r: radius, fill: 'none',
        stroke: `var(--chart-${(index % 5) + 1})`,
        'stroke-width': stroke,
        'stroke-dasharray': `${length} ${circumference - length}`,
        'stroke-dashoffset': -offset,
        transform: `rotate(-90 ${size / 2} ${size / 2})`,
        'stroke-linecap': 'butt',
      });
      arc.append(svgEl('title', {}, `${segment.label}: ${formatValue(segment.value)}`));
      root.append(arc);
    }
    offset += length;
  });
  root.append(svgEl('text', {
    x: size / 2, y: size / 2 - 4, 'text-anchor': 'middle',
    fill: 'var(--text)', 'font-size': '22', 'font-weight': '700',
  }, centerValue || formatValue(total)));
  root.append(svgEl('text', {
    x: size / 2, y: size / 2 + 16, 'text-anchor': 'middle', class: 'chart-axis-label',
  }, centerLabel));

  const legend = el('div', { class: 'chart-legend', style: { flexDirection: 'column', gap: '6px' } },
    ...segments.map((segment, index) => el('span', {},
      el('i', { style: { background: `var(--chart-${(index % 5) + 1})` } }),
      el('span', { text: `${segment.label} · ${formatValue(segment.value)}` }))));

  return el('div', { style: { display: 'flex', gap: 'var(--space-5)', alignItems: 'center', flexWrap: 'wrap' } }, root, legend);
}

/** Barra de proporción simple (usada en listas de participación). */
export function shareBar(percent) {
  const value = Math.max(0, Math.min(100, Number(percent) || 0));
  return el('div', { class: 'share-bar' },
    el('div', { class: 'share-track' }, el('div', { class: 'share-fill', style: { width: `${value}%` } })),
    el('span', { class: 'subtle numeric', style: { fontSize: 'var(--text-2xs)', minWidth: '38px', textAlign: 'right' }, text: `${value.toFixed(1)} %` }));
}

function niceCeiling(value) {
  if (value <= 5) return 5;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  return Math.ceil(value / magnitude) * magnitude;
}
