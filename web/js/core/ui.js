/**
 * IPV · Fichas y Costos
 * Componentes de interfaz reutilizables: avisos, modales, paneles, formularios.
 * Autor: Ing. Yosvany Hernández Quintero
 */

import { clear, el, focusableWithin, focusWithoutScroll, frag, icon, mount, qs, uid } from './dom.js';
import { describeError } from './api.js';

/* -------------------------------------------------------------------------- */
/* Barra de progreso global                                                    */
/* -------------------------------------------------------------------------- */
const progressBar = () => qs('#app-progress');
let progressTimer = 0;

export const progress = {
  start() {
    const bar = progressBar();
    if (!bar) return;
    clearTimeout(progressTimer);
    bar.classList.remove('is-done');
    const fill = bar.firstElementChild;
    if (fill) { fill.style.width = '12%'; }
    progressTimer = setTimeout(() => { if (fill) fill.style.width = '68%'; }, 260);
  },
  done() {
    const bar = progressBar();
    if (!bar) return;
    clearTimeout(progressTimer);
    const fill = bar.firstElementChild;
    if (fill) fill.style.width = '100%';
    bar.classList.add('is-done');
    setTimeout(() => { if (fill) fill.style.width = '0'; }, 320);
  },
};

/* -------------------------------------------------------------------------- */
/* Avisos flotantes                                                            */
/* -------------------------------------------------------------------------- */
const TOAST_ICONS = { success: 'check-circle', error: 'alert', warning: 'alert', info: 'info' };

export function toast(message, { type = 'info', title = '', duration = 4200 } = {}) {
  const stack = qs('#toast-stack');
  if (!stack) return () => {};
  const node = el('div', { class: `toast toast--${type}`, role: 'status' },
    icon(TOAST_ICONS[type] || 'info', { size: 17 }),
    el('div', { class: 'push', style: { flex: '1', minWidth: '0' } },
      title ? el('b', { text: title }) : null,
      el('span', { text: message })),
    el('button', {
      class: 'toast-close', type: 'button', 'aria-label': 'Cerrar aviso',
      on: { click: () => node.remove() },
    }, icon('x', { size: 14 })));
  stack.append(node);
  const timer = setTimeout(() => node.remove(), duration);
  node.addEventListener('mouseenter', () => clearTimeout(timer));
  return () => { clearTimeout(timer); node.remove(); };
}

export const notifySuccess = (message, title = 'Operación completada') => toast(message, { type: 'success', title });
export const notifyError = (message, title = 'No se pudo completar la operación') => toast(message, { type: 'error', title, duration: 6000 });

/** Ejecuta una operación asíncrona mostrando el resultado al usuario. */
export async function runAction(action, { success = '', errorTitle, onError } = {}) {
  progress.start();
  try {
    const result = await action();
    if (success) notifySuccess(success);
    return result;
  } catch (error) {
    if (onError) onError(error);
    else notifyError(describeError(error), errorTitle);
    return null;
  } finally {
    progress.done();
  }
}

/* -------------------------------------------------------------------------- */
/* Capa de superposición (modales y paneles)                                   */
/* -------------------------------------------------------------------------- */
let scrollLocks = 0;
const overlayRoot = () => qs('#overlay-root');

function lockScroll() {
  scrollLocks += 1;
  document.body.style.overflow = 'hidden';
}

function unlockScroll() {
  scrollLocks = Math.max(0, scrollLocks - 1);
  if (scrollLocks === 0) document.body.style.overflow = '';
}

function trapFocus(container, event) {
  if (event.key !== 'Tab') return;
  const focusables = focusableWithin(container);
  if (!focusables.length) return;
  const first = focusables[0];
  const last = focusables[focusables.length - 1];
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
}

/**
 * Muestra un modal accesible.
 * @returns {{close: Function, body: HTMLElement, footer: HTMLElement, modal: HTMLElement}}
 */
export function openModal({
  title, subtitle = '', content = null, size = 'default', actions = [], onClose, closeOnBackdrop = true,
} = {}) {
  const previousFocus = document.activeElement;
  const titleId = uid('modal-title');
  const body = el('div', { class: 'modal-body' });
  const footer = el('div', { class: 'modal-footer' });
  const modal = el('div', {
    class: `modal${size === 'wide' ? ' modal--wide' : size === 'narrow' ? ' modal--narrow' : ''}`,
    role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': titleId,
  },
    el('div', { class: 'modal-header' },
      el('div', { class: 'push', style: { minWidth: '0' } },
        el('h2', { id: titleId, text: title || '' }),
        subtitle ? el('p', { text: subtitle }) : null),
      closeButton(() => handle.close())),
    body,
    footer);

  const overlay = el('div', { class: 'overlay' }, modal);
  const handle = {
    modal, body, footer, overlay,
    close(options = {}) {
      if (handle.closed) return;
      handle.closed = true;
      document.removeEventListener('keydown', keyHandler);
      overlay.remove();
      unlockScroll();
      if (previousFocus && previousFocus.isConnected) focusWithoutScroll(previousFocus);
      if (typeof onClose === 'function' && !options.silent) onClose();
    },
    setActions(nodes) {
      mount(footer, nodes);
      return handle;
    },
    setContent(nodes) {
      mount(body, nodes);
      return handle;
    },
  };

  const keyHandler = (event) => {
    if (event.key === 'Escape') { event.stopPropagation(); handle.close(); return; }
    trapFocus(modal, event);
  };

  if (content) mount(body, content);
  if (actions.length) handle.setActions(actions);
  else footer.remove();

  if (closeOnBackdrop) overlay.addEventListener('mousedown', (event) => { if (event.target === overlay) handle.close(); });
  document.addEventListener('keydown', keyHandler);
  lockScroll();
  overlayRoot().append(overlay);
  const target = focusableWithin(modal).find((node) => !node.classList.contains('icon-btn'));
  focusWithoutScroll(target || modal);
  return handle;
}

function closeButton(onClick, label = 'Cerrar') {
  return el('button', {
    class: 'icon-btn', type: 'button', 'aria-label': label, on: { click: onClick },
  }, icon('x', { size: 18 }));
}

/** Panel lateral de detalle. */
export function openDrawer({ title, subtitle = '', headerExtra = null, actions = [], content = null, onClose } = {}) {
  const previousFocus = document.activeElement;
  const titleId = uid('drawer-title');
  const body = el('div', { class: 'drawer-body' });
  const actionsRow = el('div', { class: 'drawer-actions' });
  const drawer = el('aside', {
    class: 'drawer', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': titleId,
  },
    el('header', { class: 'drawer-header' },
      el('div', { style: { minWidth: '0', flex: '1' } },
        el('h2', { id: titleId, text: title || '' }),
        el('p', { class: 'drawer-subtitle', text: subtitle }),
        headerExtra),
      closeButton(() => handle.close())),
    actionsRow,
    body);

  const overlay = el('div', { class: 'drawer-overlay' });
  const handle = {
    drawer, body, actionsRow, overlay,
    close() {
      if (handle.closed) return;
      handle.closed = true;
      document.removeEventListener('keydown', keyHandler);
      overlay.remove();
      drawer.remove();
      unlockScroll();
      if (previousFocus && previousFocus.isConnected) focusWithoutScroll(previousFocus);
      if (typeof onClose === 'function') onClose();
    },
    setContent(nodes) { mount(body, nodes); return handle; },
    setActions(nodes) {
      if (!nodes || !nodes.length) { actionsRow.remove(); return handle; }
      mount(actionsRow, nodes);
      return handle;
    },
  };

  const keyHandler = (event) => {
    if (event.key === 'Escape') { event.stopPropagation(); handle.close(); return; }
    trapFocus(drawer, event);
  };

  handle.setActions(actions);
  if (content) handle.setContent(content);
  overlay.addEventListener('mousedown', () => handle.close());
  document.addEventListener('keydown', keyHandler);
  lockScroll();
  overlayRoot().append(frag(overlay, drawer));
  const target = focusableWithin(drawer).find((node) => !node.classList.contains('icon-btn'));
  focusWithoutScroll(target || drawer);
  return handle;
}

/** Diálogo de confirmación; devuelve una promesa con el resultado. */
export function confirmAction({
  title, message, confirmLabel = 'Confirmar', cancelLabel = 'Cancelar', tone = 'primary',
  requireText = '', note = '', details = null,
} = {}) {
  return new Promise((resolve) => {
    let settled = false;
    const confirmationInput = requireText
      ? el('input', { class: 'input', type: 'text', placeholder: requireText, autocomplete: 'off' })
      : null;

    const confirmButton = el('button', {
      class: `btn btn--${tone === 'danger' ? 'danger' : 'primary'}`, type: 'button',
      text: confirmLabel,
      on: {
        click: () => {
          if (confirmationInput && confirmationInput.value.trim().toUpperCase() !== requireText.toUpperCase()) {
            confirmationInput.setAttribute('aria-invalid', 'true');
            confirmationInput.focus();
            return;
          }
          settled = true;
          modal.close();
          resolve(true);
        },
      },
    });

    const modal = openModal({
      title,
      size: 'narrow',
      content: frag(
        el('p', { class: 'muted', style: { fontSize: 'var(--text-sm)' }, text: message }),
        note ? el('div', { class: 'banner banner--neutral', style: { marginTop: 'var(--space-4)' } },
          icon('info', { size: 16 }), el('span', { text: note })) : null,
        details,
        confirmationInput
          ? el('div', { class: 'field', style: { marginTop: 'var(--space-5)' } },
            el('label', { for: confirmationInput.name, text: `Escriba «${requireText}» para confirmar` }),
            confirmationInput)
          : null),
      actions: [
        el('button', {
          class: 'btn btn--secondary', type: 'button', text: cancelLabel,
          on: { click: () => { modal.close(); resolve(false); } },
        }),
        confirmButton,
      ],
      onClose: () => { if (!settled) resolve(false); },
    });

    if (confirmationInput) focusWithoutScroll(confirmationInput);
    else focusWithoutScroll(confirmButton);
  });
}

/* -------------------------------------------------------------------------- */
/* Formularios                                                                 */
/* -------------------------------------------------------------------------- */
/**
 * Crea un campo de formulario consistente.
 * @returns {HTMLElement} Contenedor `.field` (el control está en `container.querySelector('.input, .select, .textarea')`)
 */
export function field({
  label, name, type = 'text', value = '', options = null, hint = '', required = false, placeholder = '',
  min, max, step, rows = 4, disabled = false, full = false, autocomplete = 'off', id, help = '',
} = {}) {
  const controlId = id || `f-${name || uid('campo')}`;
  let control;
  if (options) {
    control = el('select', { class: 'select', id: controlId, name, required, disabled },
      ...options.map((option) => el('option', {
        value: option.value ?? option.label,
        text: option.label,
        selected: String(option.value ?? option.label) === String(value),
      })));
  } else if (type === 'textarea') {
    control = el('textarea', { class: 'textarea', id: controlId, name, required, placeholder, disabled, rows, text: value ?? '' });
  } else {
    control = el('input', {
      class: 'input', id: controlId, name, type, required, placeholder, disabled,
      value: value ?? '', autocomplete,
      min: min ?? undefined, max: max ?? undefined, step: step ?? undefined,
    });
  }
  const container = el('div', { class: `field${full ? ' field--full' : ''}` },
    label ? el('label', { for: controlId }, el('span', { text: label }), required ? el('span', { class: 'required', text: ' *' }) : null) : null,
    control,
    hint ? el('span', { class: 'field-hint', text: hint }) : null,
    help ? el('span', { class: 'field-error', text: help }) : null);
  container.dataset.field = name || '';
  return container;
}

/** Devuelve el objeto de valores de un formulario (los checkbox como booleanos). */
export function readForm(form) {
  const data = {};
  Array.from(form.elements).forEach((element) => {
    if (!element.name) return;
    if (element.type === 'checkbox') data[element.name] = element.checked;
    else if (element.type === 'number') data[element.name] = element.value === '' ? '' : Number(element.value);
    else data[element.name] = typeof element.value === 'string' ? element.value.trim() : element.value;
  });
  return data;
}

export function setFormBusy(form, busy, label = 'Procesando…') {
  Array.from(form.elements).forEach((element) => { element.disabled = busy; });
  const submit = form.querySelector('[type="submit"]');
  if (!submit) return;
  if (busy) {
    submit.dataset.label = submit.textContent;
    submit.textContent = label;
  } else if (submit.dataset.label) {
    submit.textContent = submit.dataset.label;
  }
  submit.disabled = busy;
}

/** Marca un campo con error y devuelve el primer mensaje. */
export function markFieldError(container, message) {
  if (!container) return;
  const control = container.querySelector('.input, .select, .textarea');
  if (control) control.setAttribute('aria-invalid', 'true');
  let hint = container.querySelector('.field-error');
  if (!hint) { hint = el('span', { class: 'field-error' }); container.append(hint); }
  hint.textContent = message;
}

export function clearFormErrors(form) {
  form.querySelectorAll('[aria-invalid]').forEach((node) => node.removeAttribute('aria-invalid'));
  form.querySelectorAll('.field-error').forEach((node) => node.remove());
}

/* -------------------------------------------------------------------------- */
/* Presentación de datos                                                       */
/* -------------------------------------------------------------------------- */
const STATUS_TONES = new Map(Object.entries({
  Aprobada: 'success',
  Validado: 'success',
  Vigente: 'success',
  Activo: 'success',
  Borrador: 'warning',
  Pendiente: 'warning',
  'Por vencer': 'warning',
  Suspendido: 'warning',
  'Con diferencias': 'danger',
  Vencido: 'danger',
  Descontinuado: 'neutral',
  Inactivo: 'neutral',
  Reabierta: 'info',
}));

/** Píldora de estado con color semántico. */
export function statusPill(status) {
  const tone = STATUS_TONES.get(String(status)) || 'info';
  return el('span', { class: `pill pill--${tone}`, text: status || 'Sin estado' });
}

export function badge(text, tone = 'neutral') {
  return el('span', { class: `pill pill--${tone} pill--plain`, text });
}

export function tag(text, iconName) {
  return el('span', { class: 'tag' }, iconName ? icon(iconName, { size: 12 }) : null, el('span', { text }));
}

export function metaRow(label, value, { code = false } = {}) {
  return el('div', { class: 'meta-row' },
    el('dt', { text: label }),
    el('dd', {}, code ? el('code', { text: String(value ?? '—') }) : String(value ?? '—')));
}

export function definition(label, value, { emphasis = false } = {}) {
  return el('div', { class: `def${emphasis ? ' def--emphasis' : ''}` },
    el('dt', { text: label }), el('dd', { text: value ?? '—' }));
}

export function emptyState({ iconName = 'info', title, message, actionLabel = '', onAction } = {}) {
  return el('div', { class: 'empty-state' },
    el('span', { class: 'empty-icon' }, icon(iconName, { size: 22 })),
    el('h3', { text: title }),
    message ? el('p', { text: message }) : null,
    actionLabel
      ? el('button', { class: 'btn btn--primary', type: 'button', text: actionLabel, on: { click: onAction } })
      : null);
}

export function skeletonTable(rows = 5, columns = 5) {
  const body = el('tbody');
  for (let row = 0; row < rows; row += 1) {
    const tr = el('tr');
    for (let column = 0; column < columns; column += 1) {
      tr.append(el('td', {}, el('div', { class: 'skeleton skeleton-row', style: { width: `${60 + ((row + column) % 4) * 10}%` } })));
    }
    body.append(tr);
  }
  return body;
}

export function card({ title, subtitle = '', actions = null, body, flush = false, headerDivided = true } = {}) {
  const head = (title || actions)
    ? el('div', { class: `card-header${headerDivided ? ' card-header--divided' : ''}` },
      el('div', { class: 'push', style: { minWidth: '0' } },
        title ? el('h2', { class: 'card-title', text: title }) : null,
        subtitle ? el('p', { class: 'card-subtitle', text: subtitle }) : null),
      actions)
    : null;
  return el('section', { class: `card${flush ? ' card--flush' : ''}` }, head, body);
}

export function button(label, { iconName, variant = 'secondary', onClick, size = 'default', type = 'button', title = '', disabled = false } = {}) {
  return el('button', {
    class: `btn btn--${variant}${size === 'sm' ? ' btn--sm' : ''}`,
    type, title: title || undefined, disabled,
    on: onClick ? { click: onClick } : undefined,
  }, iconName ? icon(iconName, { size: 16 }) : null, el('span', { text: label }));
}

export function iconAction(iconName, label, onClick, { variant = '' } = {}) {
  return el('button', {
    class: `icon-btn${variant === 'outlined' ? ' icon-btn--outlined' : ''}`,
    type: 'button', title: label, 'aria-label': label, on: { click: onClick },
  }, icon(iconName, { size: 17 }));
}

export function linkAction(label, onClick) {
  return el('button', { class: 'link-btn', type: 'button', on: { click: onClick } },
    el('span', { text: label }), icon('chevron-right', { size: 13 }));
}

/** Copia texto al portapapeles avisando el resultado. */
export async function copyText(value, label = 'Valor copiado al portapapeles.') {
  const fallback = () => {
    const area = el('textarea', {
      value, readonly: 'readonly', 'aria-hidden': 'true', tabindex: '-1',
      style: { position: 'fixed', top: '0', left: '-9999px' },
    });
    document.body.append(area);
    try {
      area.select();
      if (typeof document.execCommand !== 'function' || !document.execCommand('copy')) {
        throw new Error('copiado no disponible');
      }
    } finally {
      area.remove();
    }
  };
  try {
    if (typeof navigator.clipboard?.writeText === 'function' && window.isSecureContext) {
      await navigator.clipboard.writeText(value);
    } else {
      fallback();
    }
    toast(label, { type: 'success', duration: 2600 });
  } catch {
    try {
      fallback();
      toast(label, { type: 'success', duration: 2600 });
    } catch {
      notifyError('El navegador no permitió copiar el texto. Selecciónelo y cópielo manualmente.');
    }
  }
}
