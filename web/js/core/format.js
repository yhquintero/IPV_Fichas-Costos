/**
 * IPV · Fichas y Costos
 * Formatos de presentación localizados (es) y utilidades de exportación.
 * Autor: Ing. Yosvany Hernández Quintero
 */

const LOCALE = 'es';

const moneyFormatter = new Intl.NumberFormat(LOCALE, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const integerFormatter = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0 });
const quantityFormatter = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 4 });
const percentFormatter = new Intl.NumberFormat(LOCALE, { minimumFractionDigits: 0, maximumFractionDigits: 1 });
const dateFormatter = new Intl.DateTimeFormat(LOCALE, { day: '2-digit', month: 'short', year: 'numeric' });
const longDateFormatter = new Intl.DateTimeFormat(LOCALE, { day: '2-digit', month: 'long', year: 'numeric' });
const dateTimeFormatter = new Intl.DateTimeFormat(LOCALE, {
  day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
});
const monthFormatter = new Intl.DateTimeFormat(LOCALE, { month: 'short', year: 'numeric' });

const numeric = (value) => {
  const parsed = typeof value === 'number' ? value : Number.parseFloat(String(value ?? '0').replace(',', '.'));
  return Number.isFinite(parsed) ? parsed : 0;
};

/** Importe monetario, con la moneda indicada. */
export function fmtMoney(value, currency = 'CUP') {
  return `${moneyFormatter.format(numeric(value))} ${currency}`;
}

/** Importe sin la moneda (para tablas compactas). */
export function fmtAmount(value) {
  return moneyFormatter.format(numeric(value));
}

export function fmtNumber(value) {
  return integerFormatter.format(numeric(value));
}

export function fmtQuantity(value) {
  const parsed = numeric(value);
  return Number.isInteger(parsed) ? integerFormatter.format(parsed) : quantityFormatter.format(parsed);
}

export function fmtPercent(value, { withSign = false } = {}) {
  const parsed = numeric(value);
  const sign = withSign && parsed > 0 ? '+' : '';
  return `${sign}${percentFormatter.format(parsed)} %`;
}

export function fmtDate(value) {
  if (!value) return '—';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return dateFormatter.format(parsed);
}

export function fmtLongDate(value) {
  if (!value) return '—';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return longDateFormatter.format(parsed);
}

export function fmtDateTime(value) {
  if (!value) return '—';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return dateTimeFormatter.format(parsed);
}

/** Período AAAA-MM como «sept 2026». */
export function fmtPeriod(value) {
  if (!value) return '—';
  const [year, month] = String(value).split('-');
  if (!year || !month) return String(value);
  const parsed = new Date(Number(year), Number(month) - 1, 1);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return monthFormatter.format(parsed);
}

export function fmtRelative(value) {
  if (!value) return '—';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  const seconds = Math.round((Date.now() - parsed.getTime()) / 1000);
  if (Math.abs(seconds) < 60) return 'hace instantes';
  const units = [
    ['minuto', 60], ['hora', 3600], ['día', 86400], ['mes', 2592000], ['año', 31536000],
  ];
  let chosen = units[0];
  for (const unit of units) if (Math.abs(seconds) >= unit[1]) chosen = unit;
  const amount = Math.round(seconds / chosen[1]);
  const plural = Math.abs(amount) === 1 ? '' : 's';
  return `hace ${amount} ${chosen[0]}${plural}`;
}

/** Fecha y hora en texto completo, para documentos impresos. */
export function fmtFullStamp(value = new Date()) {
  return new Intl.DateTimeFormat(LOCALE, {
    day: '2-digit', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(value instanceof Date ? value : new Date(value));
}

export function fmtBytes(value) {
  const bytes = numeric(value);
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB'];
  let size = bytes / 1024;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) { size /= 1024; index += 1; }
  return `${size.toFixed(size < 10 ? 1 : 0)} ${units[index]}`;
}

export function fmtDuration(seconds) {
  const total = Math.max(0, Math.round(numeric(seconds)));
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (days) return `${days} d ${hours} h`;
  if (hours) return `${hours} h ${minutes} min`;
  if (minutes) return `${minutes} min`;
  return `${total} s`;
}

/** Días restantes hasta una fecha (negativo si ya venció). */
export function daysUntil(value) {
  if (!value) return null;
  const target = new Date(`${String(value).slice(0, 10)}T00:00:00`);
  if (Number.isNaN(target.getTime())) return null;
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return Math.round((target - today) / 86400000);
}

export function initials(value = '') {
  const parts = String(value).trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return '??';
  return `${parts[0][0] || ''}${parts.length > 1 ? parts[parts.length - 1][0] : ''}`.toUpperCase();
}

export function slugify(value = '') {
  return String(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
}

/** Descarga un archivo de texto generado en el cliente. */
export function downloadText(filename, content, mime = 'text/plain;charset=utf-8') {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

export function downloadJson(filename, data) {
  downloadText(filename, JSON.stringify(data, null, 2), 'application/json;charset=utf-8');
}

/** Convierte una matriz de valores en CSV (Excel en español: separador «;» y BOM). */
export function toCsv(rows) {
  const cell = (value) => `"${String(value ?? '').replace(/"/g, '""')}"`;
  return `\ufeff${rows.map((row) => row.map(cell).join(';')).join('\r\n')}`;
}

export function exportCsv(filename, headers, rows) {
  downloadText(filename, toCsv([headers, ...rows]), 'text/csv;charset=utf-8');
}

export function timestampForFilename(date = new Date()) {
  const pad = (value) => String(value).padStart(2, '0');
  return `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}-${pad(date.getHours())}${pad(date.getMinutes())}`;
}
