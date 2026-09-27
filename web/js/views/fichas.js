/**
 * IPV · Fichas y Costos
 * Vista: Fichas de Costo versionadas (elaboración, aprobación y control).
 * Autor: Ing. Yosvany Hernández Quintero
 */

import { clear, el, frag, icon, mount, qs } from '../core/dom.js';
import { api } from '../core/api.js';
import { data } from '../core/data.js';
import { prefs } from '../core/prefs.js';
import { selectors } from '../core/store.js';
import { downloadJson, exportCsv, fmtAmount, fmtDate, fmtDateTime, fmtMoney, fmtNumber, fmtPercent, fmtQuantity, fmtRelative, timestampForFilename } from '../core/format.js';
import { button, card, confirmAction, definition, emptyState, field, linkAction, openDrawer, openModal, readForm, runAction, setFormBusy, statusPill, tag, toast } from '../core/ui.js';
import { dataTable } from '../components/data-table.js';
import { catalogCell, itemsTable } from '../components/cells.js';
import { shareBar } from '../components/charts.js';
import { printFicha } from '../components/print.js';

const STATUSES = ['Borrador', 'Aprobada'];
const AUDIT_TONES = { crear: 'brand', actualizar: 'brand', aprobar: 'success', validar: 'success', versionar: 'brand', recalcular: 'warning', reabrir: 'warning' };

let unsubscribe = null;
let ctxRef = null;
let table = null;
let host = null;
let statusSelect = null;
let categorySelect = null;
let filters = { status: '', category: '' };
let initialQuery = '';
let newFichaHandler = null;
let activeDrawer = null;
let drawerId = null;
let pendingNew = false;

/* -------------------------------------------------------------------------- */
/* Elaboración de fichas                                                       */
/* -------------------------------------------------------------------------- */
function lineUnitCost(line) {
  if (line.manual) return Number(line.unit_cost) || 0;
  const material = selectors.materialById(data.state(), line.material_id);
  return material ? Number(material.unit_price) || 0 : 0;
}

function lineName(line) {
  if (line.manual) return line.description || 'Componente manual';
  const material = selectors.materialById(data.state(), line.material_id);
  return material ? material.name : 'Componente sin definir';
}

function lineUnit(line) {
  if (line.manual) return line.unit || 'unidad';
  const material = selectors.materialById(data.state(), line.material_id);
  return material ? material.unit : '—';
}

function fichaTotal(lines) {
  return lines.reduce((sum, line) => sum + (Number(line.quantity) || 0) * lineUnitCost(line), 0);
}

function openFichaModal(ficha = null) {
  const state = data.state();
  const products = selectors.activeProducts(state);
  if (!products.length) {
    toast('Registre primero un producto o servicio en el catálogo.', { type: 'warning' });
    ctxRef.navigate('/productos', { query: { nueva: '1' } });
    return;
  }
  if (!state.materials.length) {
    toast('Registre al menos un valor del IPV antes de elaborar una ficha.', { type: 'warning' });
    ctxRef.navigate('/valores', { query: { nueva: '1' } });
    return;
  }

  let lines = ficha ? ficha.items.map((item) => ({
    material_id: item.material_id,
    quantity: item.quantity,
    manual: item.material_id === null,
    description: item.description,
    unit: item.unit,
    unit_cost: item.unit_cost,
  })) : [];
  let mode = 'catalog';

  const lineList = el('div', { class: 'line-list' });
  const totalLabel = el('b', { text: fmtMoney(0) });
  const quantityInput = el('input', { class: 'input', type: 'number', min: '0.0001', step: '0.001', value: '1', 'aria-label': 'Cantidad' });
  const materialSelect = el('select', { class: 'select', 'aria-label': 'Valor del IPV' },
    ...state.materials.map((material) => el('option', {
      value: material.id,
      text: `${material.name} · ${fmtAmount(material.unit_price)} ${material.currency}/${material.unit}`,
    })));
  const unitPreview = el('input', { class: 'input', readonly: true, value: state.materials[0]?.unit || '', tabindex: '-1', 'aria-label': 'Unidad' });
  const manualDescription = el('input', { class: 'input', placeholder: 'Descripción del componente', 'aria-label': 'Descripción del componente' });
  const manualUnit = el('input', { class: 'input', placeholder: 'unidad, kg, hora…', 'aria-label': 'Unidad del componente' });
  const manualCost = el('input', { class: 'input', type: 'number', min: '0', step: '0.01', placeholder: '0.00', 'aria-label': 'Costo unitario' });
  const manualRow = el('div', { class: 'line-entry', hidden: true },
    el('div', { class: 'field' }, el('label', { text: 'Descripción del componente' }), manualDescription),
    el('div', { class: 'field' }, el('label', { text: 'Unidad' }), manualUnit),
    el('div', { class: 'field' }, el('label', { text: 'Costo unitario' }), manualCost),
    el('div', { class: 'field' }, el('label', { text: 'Cantidad' }), quantityInput.cloneNode(true)));

  const catalogRow = el('div', { class: 'line-entry' },
    el('div', { class: 'field line-entry-material' }, el('label', { text: 'Valor del IPV' }), materialSelect),
    el('div', { class: 'field' }, el('label', { text: 'Unidad' }), unitPreview),
    el('div', { class: 'field' }, el('label', { text: 'Cantidad' }), quantityInput),
    el('div', { class: 'field' }, el('label', { text: '\u00a0' }),
      el('button', { class: 'btn btn--secondary', type: 'button', text: 'Añadir componente', on: { click: () => addLine() } })));

  const modeSelect = el('select', { class: 'select', style: { maxWidth: '230px' }, 'aria-label': 'Origen del componente' },
    el('option', { value: 'catalog', text: 'Componente del catálogo de valores' }),
    el('option', { value: 'manual', text: 'Componente manual (sin catálogo)' }));

  const form = el('form', { novalidate: true, id: 'ficha-form' },
    el('div', { class: 'form-grid' },
      field({
        label: 'Producto o servicio', name: 'product_id', required: true, full: true,
        value: ficha?.product_id || products[0].id,
        options: products.map((product) => ({ value: product.id, label: `${product.code} · ${product.name} — ${product.category}` })),
        hint: ficha ? 'El producto no se modifica al editar una ficha; para otro producto cree una ficha nueva.' : '',
      }),
      field({ label: 'Vigente desde', name: 'valid_from', type: 'date', value: (ficha?.valid_from || new Date().toISOString().slice(0, 10)).slice(0, 10) }),
      field({ label: 'Observaciones', name: 'observations', type: 'textarea', full: true, value: ficha?.observations || '', placeholder: 'Notas de elaboración, fuentes consultadas o acuerdos aplicados' })),
    el('div', { class: 'line-builder' },
      el('div', { class: 'row', style: { justifyContent: 'space-between', marginBottom: 'var(--space-4)' } },
        el('div', {},
          el('p', { class: 'field-label', text: 'Componentes del costo' }),
          el('p', { class: 'field-hint', text: 'Añada cada insumo, tarifa o servicio con su cantidad. El importe se calcula automáticamente.' })),
        modeSelect),
      catalogRow,
      manualRow,
      lineList,
      el('div', { class: 'line-total' },
        el('span', { text: 'Costo total calculado' }),
        totalLabel)),
    ficha ? el('div', { class: 'banner banner--neutral' },
      icon('info', { size: 16 }),
      el('span', { text: 'Esta ficha está en estado Borrador: puede ajustar sus componentes. Al aprobarla quedará bloqueada y los cambios posteriores requerirán una nueva versión.' })) : null);

  if (ficha) {
    const productField = form.querySelector('select[name="product_id"]');
    if (productField) productField.disabled = true;
  }

  const renderLines = () => {
    if (!lines.length) {
      lineList.replaceChildren(el('div', { class: 'line-empty', text: 'Todavía no se han añadido componentes.' }));
    } else {
      lineList.replaceChildren(...lines.map((line, index) => el('div', { class: 'line-row' },
        el('span', { class: 'line-row-name' },
          el('span', { text: lineName(line) }),
          el('small', { text: `${fmtQuantity(line.quantity)} ${lineUnit(line)} × ${fmtMoney(lineUnitCost(line))}  ${line.manual ? '· componente manual' : ''}` })),
        el('span', { class: 'line-row-amount', text: fmtMoney((Number(line.quantity) || 0) * lineUnitCost(line)) }),
        el('span', { class: 'tag', text: lineUnit(line) }),
        el('button', {
          class: 'icon-btn', type: 'button', 'aria-label': 'Quitar componente', title: 'Quitar componente',
          on: { click: () => { lines.splice(index, 1); renderLines(); } },
        }, icon('x', { size: 15 })))));
    }
    totalLabel.textContent = fmtMoney(fichaTotal(lines));
  };

  const addLine = () => {
    if (mode === 'manual') {
      const description = manualDescription.value.trim();
      const unit = manualUnit.value.trim();
      const cost = Number(manualCost.value);
      const quantity = Number(manualRow.querySelector('input[type="number"]').value);
      const errors = [];
      if (!description) errors.push('la descripción');
      if (!unit) errors.push('la unidad');
      if (!Number.isFinite(cost) || cost < 0) errors.push('un costo unitario válido');
      if (!Number.isFinite(quantity) || quantity <= 0) errors.push('una cantidad mayor que cero');
      if (errors.length) { toast(`Indique ${errors.join(', ')}.`, { type: 'warning' }); return; }
      lines.push({ manual: true, material_id: null, description, unit, unit_cost: cost, quantity });
      manualDescription.value = '';
      manualCost.value = '';
      manualRow.querySelector('input[type="number"]').value = '1';
    } else {
      const materialId = Number(materialSelect.value);
      const quantity = Number(quantityInput.value);
      if (!materialId) { toast('Seleccione un valor del IPV.', { type: 'warning' }); return; }
      if (!Number.isFinite(quantity) || quantity <= 0) { toast('La cantidad debe ser mayor que cero.', { type: 'warning' }); return; }
      lines.push({ manual: false, material_id: materialId, quantity });
      quantityInput.value = '1';
    }
    renderLines();
  };

  const updateUnitPreview = () => {
    const material = selectors.materialById(data.state(), Number(materialSelect.value));
    unitPreview.value = material ? material.unit : '';
  };

  materialSelect.addEventListener('change', updateUnitPreview);
  modeSelect.addEventListener('change', () => {
    mode = modeSelect.value;
    catalogRow.hidden = mode === 'manual';
    manualRow.hidden = mode !== 'manual';
  });
  updateUnitPreview();
  renderLines();

  const modal = openModal({
    title: ficha ? `Editar borrador · ${ficha.document_code}` : 'Nueva Ficha de Costo',
    subtitle: ficha
      ? `Versión ${ficha.version} en estado Borrador`
      : 'La ficha se crea en estado Borrador y requiere aprobación para generar controles.',
    size: 'wide',
    content: form,
    actions: [
      el('button', { class: 'btn btn--secondary', type: 'button', text: 'Cancelar', on: { click: () => modal.close() } }),
      el('button', { class: 'btn btn--primary', type: 'submit', form: 'ficha-form', text: ficha ? 'Guardar cambios' : 'Crear ficha' }),
    ],
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!lines.length) { toast('Añada al menos un componente a la ficha.', { type: 'warning' }); return; }
    if (!form.reportValidity()) return;
    const values = readForm(form);
    const payload = {
      product_id: ficha ? ficha.product_id : Number(values.product_id),
      valid_from: values.valid_from,
      observations: values.observations,
      items: lines.map((line) => (line.manual
        ? { description: line.description, unit: line.unit, unit_cost: line.unit_cost, quantity: line.quantity }
        : { material_id: line.material_id, quantity: line.quantity })),
    };
    setFormBusy(form, true, 'Guardando…');
    const result = await runAction(
      () => (ficha ? api.put(`/api/fichas/${ficha.id}`, payload) : api.post('/api/fichas', payload)),
      { success: ficha ? 'Ficha de costo actualizada.' : 'Ficha de costo creada como borrador.' },
    );
    setFormBusy(form, false);
    if (result === null) return;
    modal.close();
    await data.reload({ silent: true });
    if (!ficha && result?.id) ctxRef.navigate(`/fichas/${result.id}`);
  });
}

/* -------------------------------------------------------------------------- */
/* Acciones sobre la ficha                                                     */
/* -------------------------------------------------------------------------- */
async function approveFicha(ficha) {
  const form = el('form', {},
    field({
      label: 'Responsable de la aprobación', name: 'approved_by', required: true,
      value: ficha.approved_by || prefs.get('operator'), hint: 'Quedará registrado en el documento y en la bitácora de auditoría.',
    }));
  const modal = openModal({
    title: 'Aprobar Ficha de Costo',
    subtitle: `${ficha.document_code} · ${fmtMoney(ficha.total_cost)}`,
    size: 'narrow',
    content: frag(
      el('div', { class: 'banner' }, icon('info', { size: 16 }),
        el('span', { text: 'Al aprobar la ficha sus componentes quedan bloqueados. Los cambios posteriores requieren crear una nueva versión, garantizando la trazabilidad del costo.' })),
      form),
    actions: [
      el('button', { class: 'btn btn--secondary', type: 'button', text: 'Cancelar', on: { click: () => modal.close() } }),
      el('button', {
        class: 'btn btn--primary', type: 'button', text: 'Aprobar ficha',
        on: {
          click: async () => {
            if (!form.reportValidity()) return;
            const payload = readForm(form);
            modal.close();
            const result = await runAction(() => api.post(`/api/fichas/${ficha.id}/approve`, payload),
              { success: `Ficha ${ficha.document_code} aprobada.` });
            if (result === null) return;
            await data.reload({ silent: true });
            refreshDrawer(ficha.id);
          },
        },
      }),
    ],
  });
}

async function duplicateFicha(ficha) {
  const confirmed = await confirmAction({
    title: 'Crear nueva versión',
    message: `Se creará una copia en borrador de la ficha ${ficha.document_code} como versión ${Number(ficha.version) + 1}.`,
    note: 'La versión anterior se conserva sin cambios y mantiene su vínculo con los controles ya generados.',
    confirmLabel: 'Crear versión',
  });
  if (!confirmed) return;
  const result = await runAction(() => api.post(`/api/fichas/${ficha.id}/duplicate`, {}),
    { success: 'Nueva versión creada en estado borrador.' });
  if (result === null) return;
  await data.reload({ silent: true });
  ctxRef.navigate(`/fichas/${result.id}`);
}

async function reopenFicha(ficha) {
  const form = el('form', {}, field({
    label: 'Motivo de la reapertura', name: 'reason', type: 'textarea', required: true,
    placeholder: 'Explique por qué la ficha vuelve a estado Borrador',
  }));
  const modal = openModal({
    title: 'Reabrir ficha aprobada',
    subtitle: `${ficha.document_code} · ${ficha.product_name}`,
    size: 'narrow',
    content: frag(
      el('div', { class: 'banner banner--warning' }, icon('alert', { size: 16 }),
        el('span', { text: 'Solo se reabren fichas sin controles validados. El motivo quedará registrado en la bitácora de auditoría.' })),
      form),
    actions: [
      el('button', { class: 'btn btn--secondary', type: 'button', text: 'Cancelar', on: { click: () => modal.close() } }),
      el('button', {
        class: 'btn btn--danger', type: 'button', text: 'Reabrir ficha',
        on: {
          click: async () => {
            if (!form.reportValidity()) return;
            const payload = readForm(form);
            modal.close();
            const result = await runAction(() => api.post(`/api/fichas/${ficha.id}/reopen`, payload),
              { success: 'Ficha devuelta a borrador.' });
            if (result === null) return;
            await data.reload({ silent: true });
            refreshDrawer(ficha.id);
          },
        },
      }),
    ],
  });
}

async function refreshPrices(ficha) {
  const confirmed = await confirmAction({
    title: 'Actualizar precios del borrador',
    message: 'Los componentes se recalcularán con los precios vigentes del catálogo de valores del IPV.',
    note: 'Solo afecta a esta ficha en estado Borrador; las fichas aprobadas no se modifican.',
    confirmLabel: 'Actualizar precios',
  });
  if (!confirmed) return;
  const result = await runAction(() => api.post(`/api/fichas/${ficha.id}/refresh-prices`, {}),
    { success: 'Precios actualizados desde el catálogo.' });
  if (result === null) return;
  await data.reload({ silent: true });
  refreshDrawer(ficha.id);
}

function generateControl(ficha) {
  const form = el('form', {},
    field({
      label: 'Período del control', name: 'period', type: 'month', required: true,
      value: new Date().toISOString().slice(0, 7), hint: 'Período mensual que se somete a control de precios.',
    }),
    field({ label: 'Observaciones', name: 'notes', type: 'textarea', placeholder: 'Notas para la revisión y el acta de control' }));
  const modal = openModal({
    title: 'Generar Control de IPV',
    subtitle: `${ficha.document_code} · ${ficha.product_name}`,
    content: frag(
      el('dl', { class: 'def-grid', style: { marginBottom: 'var(--space-5)' } },
        definition('Producto', ficha.product_name),
        definition('Versión de la ficha', `v${ficha.version}`),
        definition('Total aprobado', fmtMoney(ficha.total_cost), { emphasis: true })),
      form),
    actions: [
      el('button', { class: 'btn btn--secondary', type: 'button', text: 'Cancelar', on: { click: () => modal.close() } }),
      el('button', {
        class: 'btn btn--primary', type: 'button', text: 'Crear control',
        on: {
          click: async () => {
            if (!form.reportValidity()) return;
            const payload = readForm(form);
            modal.close();
            const result = await runAction(() => api.post('/api/controls', { ...payload, ficha_id: ficha.id }),
              { success: 'Control de IPV creado y pendiente de validación.' });
            if (result === null) return;
            await data.reload({ silent: true });
            ctxRef.navigate(`/controles/${result.id}`);
          },
        },
      }),
    ],
  });
}

function exportFichaCsv(ficha) {
  exportCsv(`ficha-${ficha.document_code}-${timestampForFilename()}.csv`,
    ['Componente', 'Unidad', 'Cantidad', 'Costo unitario', 'Subtotal', '% del total'],
    ficha.items.map((item) => [item.description, item.unit, item.quantity, item.unit_cost, item.subtotal, fmtPercent(item.share_percent)]));
  toast('Detalle de la ficha exportado a CSV.', { type: 'success' });
}

/* -------------------------------------------------------------------------- */
/* Panel de detalle                                                            */
/* -------------------------------------------------------------------------- */
function timeline(events) {
  if (!events?.length) return emptyState({ iconName: 'history', title: 'Sin movimientos registrados', message: 'Las operaciones sobre esta ficha se mostrarán aquí.' });
  return el('div', { class: 'timeline' }, ...events.map((event) => el('div', { class: 'timeline-item' },
    el('span', { class: `timeline-dot timeline-dot--${AUDIT_TONES[event.action] || 'brand'}` }, icon('history', { size: 15 })),
    el('div', { class: 'timeline-body' },
      el('p', { class: 'timeline-title', text: event.summary }),
      el('p', { class: 'timeline-meta' },
        el('span', { text: event.actor }),
        el('span', { text: fmtDateTime(event.at) }),
        el('span', { text: fmtRelative(event.at) }))))));
}

function fichaDetailPanel(ficha, onChange) {
  const body = el('div');
  const tabList = el('div', { class: 'tabs', role: 'tablist' });
  const tabs = [
    { id: 'detalle', label: 'Detalle' },
    { id: 'versiones', label: `Versiones (${ficha.versions.length})` },
    { id: 'controles', label: `Controles (${ficha.controls.length})` },
    { id: 'bitacora', label: 'Bitácora' },
  ];
  let current = 'detalle';

  const renderTab = () => {
    if (current === 'detalle') {
      mount(body, frag(
        el('dl', { class: 'def-grid' },
          definition('Producto / servicio', ficha.product_name),
          definition('Código', ficha.product_code),
          definition('Categoría', ficha.category),
          definition('Unidad de salida', ficha.product_unit),
          definition('Versión', `v${ficha.version} · ${ficha.item_count} componente(s)`),
          definition('Vigente desde', fmtDate(ficha.valid_from)),
          definition('Elaborada por', ficha.prepared_by || '—'),
          definition('Aprobada por', ficha.approved_by || 'Pendiente'),
          definition('Fecha de aprobación', ficha.approved_at ? fmtDateTime(ficha.approved_at) : 'Pendiente'),
          definition('Última actualización', fmtDateTime(ficha.updated_at))),
        el('h3', { style: { margin: 'var(--space-6) 0 var(--space-3)' }, text: 'Composición del costo' }),
        itemsTable({
          headers: [
            { text: 'Componente' },
            { text: 'Unidad' },
            { class: 'align-right', text: 'Cantidad' },
            { class: 'align-right', text: 'Costo unitario' },
            { class: 'align-right', text: 'Subtotal' },
            { style: { minWidth: '130px' }, text: 'Participación' },
          ],
          rows: ficha.items.map((item) => [
            { class: 'strong', node: el('span', {}, el('span', { text: item.description }),
              item.price_changed
                ? el('span', { class: 'row-meta', text: 'El valor del catálogo cambió después de esta ficha' })
                : null) },
            { class: 'muted', text: item.unit },
            { class: 'align-right numeric', text: fmtQuantity(item.quantity) },
            { class: 'align-right numeric', text: fmtMoney(item.unit_cost) },
            { class: 'align-right amount', text: fmtAmount(item.subtotal) },
            { node: shareBar(item.share_percent) },
          ]),
        }),
        el('div', { class: 'detail-total' },
          el('span', { text: 'Costo total de la ficha' }),
          el('b', { text: fmtMoney(ficha.total_cost) })),
        ficha.observations ? el('div', { class: 'banner banner--neutral', style: { marginTop: 'var(--space-4)' } },
          icon('clipboard', { size: 16 }), el('span', { text: ficha.observations })) : null));
      return;
    }
    if (current === 'versiones') {
      mount(body, ficha.versions.length
        ? frag(
          el('p', { class: 'field-hint', style: { marginBottom: 'var(--space-4)' },
            text: `El producto ${ficha.product_code} tiene ${ficha.versions.length} versión(es) documentada(s). Las fichas aprobadas no se modifican.` }),
          el('div', { class: 'table-wrap' }, el('table', { class: 'data compact' },
            el('thead', {}, el('tr', {},
              el('th', { text: 'Versión' }),
              el('th', { text: 'Estado' }),
              el('th', { text: 'Vigente desde' }),
              el('th', { class: 'align-right', text: 'Costo total' }),
              el('th', { text: 'Aprobada por' }),
              el('th', { text: '' }))),
            el('tbody', {}, ...ficha.versions.map((version) => el('tr', {
              style: Number(version.id) === Number(ficha.id) ? { background: 'var(--brand-soft)' } : {},
            },
              el('td', { class: 'strong', text: `v${version.version}${Number(version.id) === Number(ficha.id) ? ' · actual' : ''}` }),
              el('td', {}, statusPill(version.status)),
              el('td', { class: 'muted', text: fmtDate(version.valid_from) }),
              el('td', { class: 'align-right amount', text: fmtAmount(version.total_cost) }),
              el('td', { class: 'muted', text: version.approved_by || '—' }),
              el('td', {}, Number(version.id) === Number(ficha.id)
                ? el('span', { class: 'subtle', text: '—' })
                : linkAction('Abrir', () => { onChange(version.id); }))))))))
        : emptyState({ iconName: 'layers', title: 'Sin otras versiones', message: 'Esta es la única versión registrada del producto.' }));
      return;
    }
    if (current === 'controles') {
      mount(body, ficha.controls.length
        ? frag(
          el('p', { class: 'field-hint', style: { marginBottom: 'var(--space-4)' },
            text: 'Cada control conserva la instantánea del período y el informe de validación correspondiente a esta versión de la ficha.' }),
          el('div', { class: 'table-wrap' }, el('table', { class: 'data compact' },
            el('thead', {}, el('tr', {},
              el('th', { text: 'Control' }),
              el('th', { text: 'Período' }),
              el('th', { text: 'Estado' }),
              el('th', { class: 'align-right', text: 'Total controlado' }),
              el('th', { class: 'align-right', text: 'Total verificado' }),
              el('th', { text: '' }))),
            el('tbody', {}, ...ficha.controls.map((control) => el('tr', {},
              el('td', { class: 'strong', text: control.code }),
              el('td', { class: 'muted', text: control.period }),
              el('td', {}, statusPill(control.status)),
              el('td', { class: 'align-right amount', text: fmtAmount(control.snapshot_total) }),
              el('td', { class: 'align-right numeric', text: control.checked_at ? fmtAmount(control.checked_total) : '—' }),
              el('td', {}, linkAction('Abrir control', () => ctxRef.navigate(`/controles/${control.id}`)))))))))
        : emptyState({
          iconName: 'shield',
          title: 'Sin controles de IPV',
          message: ficha.status === 'Aprobada'
            ? 'Genere un control para verificar el costo del período con la instantánea de esta ficha.'
            : 'La ficha debe estar aprobada para poder generar controles de IPV.',
          actionLabel: ficha.status === 'Aprobada' ? 'Generar control' : '',
          onAction: ficha.status === 'Aprobada' ? () => generateControl(ficha) : undefined,
        }));
      return;
    }
    mount(body, timeline(ficha.audit));
  };

  tabs.forEach((tab) => tabList.append(el('button', {
    class: 'tab', type: 'button', role: 'tab', 'data-tab': tab.id,
    'aria-selected': tab.id === current ? 'true' : 'false', text: tab.label,
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

async function openFichaDrawer(id) {
  let ficha;
  try {
    ficha = await api.ficha(id);
  } catch (error) {
    toast(error.message, { type: 'error' });
    if (activeDrawer) { const drawer = activeDrawer; activeDrawer = null; drawer.close({ silent: true }); }
    if (ctxRef?.route?.params?.id) ctxRef.navigate('/fichas', { replace: true });
    return;
  }
  if (String(drawerId) === String(ficha.id) && activeDrawer) {
    activeDrawer.setContent(fichaDetailPanel(ficha, (newId) => { ctxRef.navigate(`/fichas/${newId}`); }));
    return;
  }
  if (activeDrawer) { const drawer = activeDrawer; activeDrawer = null; drawer.close({ silent: true }); }
  drawerId = ficha.id;
  const isDraft = ficha.status === 'Borrador';
  const hasValidatedControl = ficha.controls.some((control) => control.status === 'Validado');

  const actions = [
    button('Imprimir', { iconName: 'printer', size: 'sm', onClick: () => printFicha(ficha) }),
    button('Exportar CSV', { iconName: 'download', size: 'sm', onClick: () => exportFichaCsv(ficha) }),
    button('Exportar JSON', { iconName: 'download', size: 'sm', onClick: () => downloadJson(`ficha-${ficha.document_code}.json`, ficha) }),
    isDraft ? button('Editar borrador', { iconName: 'edit', size: 'sm', onClick: () => openFichaModal(ficha) }) : null,
    isDraft ? button('Actualizar precios', { iconName: 'wand', size: 'sm', onClick: () => refreshPrices(ficha) }) : null,
    isDraft ? button('Aprobar ficha', { variant: 'primary', iconName: 'check', size: 'sm', onClick: () => approveFicha(ficha) }) : null,
    button('Nueva versión', { iconName: 'copy', size: 'sm', onClick: () => duplicateFicha(ficha) }),
    !isDraft ? button('Generar control', { variant: 'primary', iconName: 'shield', size: 'sm', onClick: () => generateControl(ficha) }) : null,
    !isDraft && !hasValidatedControl ? button('Reabrir', { iconName: 'clock', size: 'sm', onClick: () => reopenFicha(ficha) }) : null,
  ].filter(Boolean);

  activeDrawer = openDrawer({
    title: ficha.document_code,
    subtitle: `${ficha.product_name} · ${ficha.category} · actualizada ${fmtRelative(ficha.updated_at)}`,
    headerExtra: el('div', { class: 'row', style: { marginTop: 'var(--space-3)' } },
      statusPill(ficha.status),
      tag(`v${ficha.version}`, 'layers'),
      tag(`${ficha.item_count} componente(s)`, 'hash'),
      tag(fmtMoney(ficha.total_cost), 'scale')),
    actions,
    content: fichaDetailPanel(ficha, (newId) => { ctxRef.navigate(`/fichas/${newId}`); }),
    onClose: () => {
      activeDrawer = null;
      drawerId = null;
      if (ctxRef?.route?.params?.id) ctxRef.navigate('/fichas', { replace: true });
    },
  });
}

function refreshDrawer(id) {
  if (activeDrawer) openFichaDrawer(id);
}

/* -------------------------------------------------------------------------- */
/* Listado                                                                     */
/* -------------------------------------------------------------------------- */
function buildTable() {
  table = dataTable({
    state: { query: initialQuery },
    columns: [
      {
        key: 'document_code', label: 'Documento',
        render: (row) => catalogCell({
          code: `${row.product_code} · v${row.version}`,
          name: row.document_code,
          category: row.category,
          meta: [`Elaborada ${fmtRelative(row.created_at)}`],
        }),
      },
      { key: 'product_name', label: 'Producto o servicio', render: (row) => el('span', { text: row.product_name }) },
      { key: 'item_count', label: 'Componentes', align: 'right', render: (row) => el('span', { class: 'numeric', text: fmtNumber(row.item_count) }) },
      { key: 'valid_from', label: 'Vigente desde', render: (row) => el('span', { class: 'muted', text: fmtDate(row.valid_from) }) },
      { key: 'total_cost', label: 'Costo total', align: 'right', render: (row) => el('span', { class: 'amount', text: fmtAmount(row.total_cost) }) },
      { key: 'status', label: 'Estado', render: (row) => statusPill(row.status) },
      {
        key: 'last_control_status', label: 'Último control',
        render: (row) => (row.control_count
          ? el('span', { class: 'state-inline' }, statusPill(row.last_control_status), el('small', { text: `${row.control_count}` }))
          : el('span', { class: 'subtle', text: 'Sin control' })),
      },
      {
        key: 'actions', label: 'Acciones', align: 'right', sortable: false,
        render: (row) => el('div', { class: 'table-actions' },
          el('button', {
            class: 'icon-btn', type: 'button', title: 'Ver detalle', 'aria-label': 'Ver detalle',
            on: { click: () => ctxRef.navigate(`/fichas/${row.id}`) },
          }, icon('file', { size: 16 })),
          row.status === 'Borrador'
            ? el('button', {
              class: 'icon-btn', type: 'button', title: 'Aprobar ficha', 'aria-label': 'Aprobar ficha',
              on: { click: async () => { const detail = await api.ficha(row.id); approveFicha(detail); } },
            }, icon('check', { size: 16 }))
            : el('button', {
              class: 'icon-btn', type: 'button', title: 'Generar control de IPV', 'aria-label': 'Generar control',
              on: { click: async () => { const detail = await api.ficha(row.id); generateControl(detail); } },
            }, icon('shield', { size: 16 })),
          el('button', {
            class: 'icon-btn', type: 'button', title: 'Imprimir ficha', 'aria-label': 'Imprimir ficha',
            on: { click: async () => printFicha(await api.ficha(row.id)) },
          }, icon('printer', { size: 16 }))),
      },
    ],
    rows: [],
    toolbar: buildToolbar(),
    searchPlaceholder: 'Buscar por producto, código, estado u observaciones…',
    searchKeys: ['document_code', 'product_name', 'product_code', 'category', 'status', 'observations'],
    pageSize: 12,
    sortKey: 'updated_at',
    sortDir: 'desc',
    empty: {
      iconName: 'file',
      title: 'Todavía no hay fichas de costo',
      message: 'Elabore la primera ficha para documentar el costo de un producto o servicio.',
      actionLabel: 'Nueva ficha',
      onAction: () => openFichaModal(),
    },
    onRowClick: (row) => ctxRef.navigate(`/fichas/${row.id}`),
    onStateChange: (uiState) => {
      ctxRef.navigate('/fichas', {
        replace: true,
        query: { q: uiState.query || '', estado: filters.status || '', categoria: filters.category || '' },
      });
    },
  });
  return table.element;
}

function buildToolbar() {
  statusSelect = el('select', {
    class: 'select', 'aria-label': 'Filtrar por estado', style: { maxWidth: '170px' },
    on: { change: (event) => { filters.status = event.target.value; sync(); } },
  }, el('option', { value: '', text: 'Todos los estados' }),
    ...STATUSES.map((status) => el('option', { value: status, text: status })));
  categorySelect = el('select', {
    class: 'select', 'aria-label': 'Filtrar por categoría', style: { maxWidth: '200px' },
    on: { change: (event) => { filters.category = event.target.value; sync(); } },
  });
  refreshToolbarOptions();
  return [
    button('Exportar CSV', { iconName: 'download', size: 'sm', onClick: exportFichas }),
    button('Imprimir listado', { iconName: 'printer', size: 'sm', onClick: printFichas }),
    statusSelect,
    categorySelect,
  ];
}

function refreshToolbarOptions() {
  const categories = selectors.categories(data.state());
  categorySelect.replaceChildren(el('option', { value: '', text: 'Todas las categorías' }),
    ...categories.map((category) => el('option', { value: category, text: category })));
  categorySelect.value = categories.includes(filters.category) ? filters.category : '';
  filters.category = categorySelect.value;
  statusSelect.value = filters.status;
}

function visibleRows() {
  let rows = data.state().fichas;
  if (filters.status) rows = rows.filter((row) => row.status === filters.status);
  if (filters.category) rows = rows.filter((row) => row.category === filters.category);
  return rows;
}

function exportFichas() {
  const rows = visibleRows();
  exportCsv(`fichas-costo-${timestampForFilename()}.csv`,
    ['Documento', 'Producto', 'Código', 'Categoría', 'Versión', 'Componentes', 'Vigente desde', 'Costo total (CUP)',
      'Estado', 'Elaborada por', 'Aprobada por', 'Fecha de aprobación', 'Controles'],
    rows.map((row) => [row.document_code, row.product_name, row.product_code, row.category, row.version, row.item_count,
      row.valid_from, row.total_cost, row.status, row.prepared_by, row.approved_by, row.approved_at, row.control_count]));
  toast(`${rows.length} ficha(s) exportada(s) a CSV.`, { type: 'success' });
}

function printFichas() {
  const rows = visibleRows();
  printTableReport({
    title: 'Relación de Fichas de Costo',
    subtitle: 'Fichas registradas con su estado de aprobación',
    meta: [
      ['Fichas listadas', String(rows.length)],
      ['Estado', filters.status || 'Todos'],
      ['Generado', new Date().toLocaleString('es')],
    ],
    columns: [
      { key: 'document_code', label: 'Documento' },
      { key: 'product_name', label: 'Producto o servicio' },
      { key: 'category', label: 'Categoría' },
      { key: 'version', label: 'Versión', align: 'right' },
      { key: 'valid_from', label: 'Vigente desde' },
      { key: 'total_cost', label: 'Costo total (CUP)', align: 'right' },
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
    const drafts = data.state().fichas.filter((ficha) => ficha.status === 'Borrador').length;
    counter.textContent = `${fmtNumber(rows.length)} en pantalla · ${fmtNumber(drafts)} en borrador`;
  }
}

function render() {
  if (host) {
    mount(host, frag(
      el('header', { class: 'page-heading' },
        el('div', { class: 'page-heading-main' },
          el('p', { class: 'eyebrow', text: 'Costeo' }),
          el('h1', { text: 'Fichas de costo' }),
          el('p', { text: 'Documente el costo de cada producto o servicio por versiones. Las fichas aprobadas quedan bloqueadas y sirven de base para los controles de precios.' })),
        el('div', { class: 'page-heading-actions' },
          el('span', { class: 'tag', 'data-role': 'count' }, '—'),
          button('Nueva ficha de costo', { variant: 'primary', iconName: 'plus', onClick: () => openFichaModal() }))),
      buildTable(),
      el('p', {
        class: 'subtle', style: { marginTop: 'var(--space-4)', fontSize: 'var(--text-2xs)' },
        text: 'Cada versión conserva el precio aplicado de cada componente. Para reflejar cambios utilice «Nueva versión» y mantenga la trazabilidad con los controles anteriores.',
      })));
  }
  sync();
}

function onDataChange() {
  if (!host || !data.state().ready) return;
  if (!table || !host.querySelector('table.data')) render();
  else sync();
  if (pendingNew) {
    pendingNew = false;
    openFichaModal();
  }
}

/**
 * Aplica la ruta recibida: abre el panel de detalle, el formulario de alta
 * o vuelve al listado según los parámetros de la dirección.
 */
function applyRoute(route = {}) {
  const params = route.params || {};
  const query = route.query || {};
  if (params.id) {
    if (String(drawerId) !== String(params.id)) openFichaDrawer(params.id);
    return;
  }
  if (activeDrawer) {
    const drawer = activeDrawer;
    activeDrawer = null;
    drawerId = null;
    drawer.close({ silent: true });
  }
  if (query.nueva === '1') {
    if (data.state().ready) {
      openFichaModal();
      ctxRef?.navigate('/fichas', { replace: true });
    } else {
      pendingNew = true;
    }
  }
}

export const fichasView = {
  id: 'fichas',
  title: 'Fichas de costo',
  crumb: 'Fichas de costo',
  description: 'Fichas de costo versionadas por producto.',
  mount(container, ctx) {
    host = container;
    ctxRef = ctx;
    const query = ctx.route?.query || {};
    initialQuery = query.q || '';
    filters = { status: query.estado || '', category: query.categoria || '' };
    table = null;
    if (data.state().ready) render();
    else mount(host, el('div', { class: 'stack' },
      el('div', { class: 'skeleton', style: { height: '72px' } }),
      el('div', { class: 'skeleton', style: { height: '340px' } })));
    unsubscribe = data.subscribe(onDataChange);
    newFichaHandler = () => openFichaModal();
    document.addEventListener('ipv:new-ficha', newFichaHandler);
    applyRoute(ctx.route);
  },
  receiveRoute(route) {
    ctxRef = { ...ctxRef, route };
    applyRoute(route);
  },
  openNew() { openFichaModal(); },
  unmount() {
    if (unsubscribe) unsubscribe();
    if (newFichaHandler) document.removeEventListener('ipv:new-ficha', newFichaHandler);
    if (activeDrawer) { const drawer = activeDrawer; activeDrawer = null; drawer.close({ silent: true }); }
    unsubscribe = null;
    newFichaHandler = null;
    drawerId = null;
    table = null;
    if (host) clear(host);
    host = null;
  },
};
