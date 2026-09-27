const state = {
  view: 'dashboard', dashboard: null, products: [], materials: [], fichas: [], controls: [], search: '',
};
const $ = (selector, root = document) => root.querySelector(selector);
const content = $('#page-content');
const modalLayer = $('#modal-layer');

const views = {
  dashboard: { crumb: 'Resumen' },
  products: { crumb: 'Productos y servicios' },
  materials: { crumb: 'Valores del IPV' },
  fichas: { crumb: 'Fichas de costo' },
  controls: { crumb: 'Controles de IPV' },
};

function escapeHtml(value = '') {
  return String(value).replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}
function money(value) {
  const n = Number(value || 0);
  return `${new Intl.NumberFormat('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number.isFinite(n) ? n : 0)} CUP`;
}
function decimal(value, digits = 3) {
  const n = Number(value || 0);
  return new Intl.NumberFormat('es-ES', { maximumFractionDigits: digits }).format(Number.isFinite(n) ? n : 0);
}
function dateLabel(value) {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return escapeHtml(value);
  return new Intl.DateTimeFormat('es', { day: '2-digit', month: 'short', year: 'numeric' }).format(d);
}
function initials(value = '') { return escapeHtml(value.trim().split(/\s+/).slice(0, 2).map(x => x[0] || '').join('').toUpperCase()); }
function categoryClass(category = '') {
  const v = category.toLowerCase();
  if (v.includes('comida') || v.includes('alimento')) return 'food';
  if (v.includes('serv')) return 'service';
  if (v.includes('beb')) return '';
  return 'other';
}
function categoryIcon(category = '') {
  const v = category.toLowerCase();
  return v.includes('comida') || v.includes('alimento') ? '◉' : v.includes('serv') ? '⌂' : v.includes('beb') ? '◒' : '◇';
}
function statusClass(status = '') {
  const v = status.toLowerCase();
  if (v.includes('aprob') || v.includes('vigente')) return 'approved';
  if (v.includes('valid')) return 'validated';
  if (v.includes('difer') || v.includes('error')) return 'difference';
  if (v.includes('revisi')) return 'review';
  if (v.includes('pend') || v.includes('borr')) return 'pending';
  return '';
}
function statusPill(status) { return `<span class="status ${statusClass(status)}">${escapeHtml(status || 'Sin estado')}</span>`; }

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Error ${response.status}`);
  return data;
}
function setConnection(online, label = '') {
  const dot = $('#connection-dot');
  dot.className = `connection-dot ${online ? 'online' : 'offline'}`;
  $('#connection-label').textContent = label || (online ? 'SQLite conectado' : 'Sin conexión');
}
async function refreshData(quiet = false) {
  if (!quiet) setConnection(false, 'Actualizando…');
  try {
    const [dashboard, products, materials, fichas, controls] = await Promise.all([
      api('/api/dashboard'), api('/api/products'), api('/api/materials'), api('/api/fichas'), api('/api/controls'),
    ]);
    Object.assign(state, { dashboard, products, materials, fichas, controls });
    setConnection(true, 'SQLite conectado');
    $('#nav-products').textContent = products.filter(p => p.active).length;
    $('#nav-fichas').textContent = fichas.length;
    $('#nav-pending-dot').style.display = controls.some(c => c.status === 'Pendiente' || c.status === 'Con diferencias') ? 'block' : 'none';
    render();
  } catch (error) {
    setConnection(false, 'No se pudo conectar');
    if (!quiet) toast(error.message, 'error');
    content.innerHTML = `<div class="empty-state panel"><div class="empty-icon">⌁</div><b>No se pudo conectar con SQLite</b><p>Comprueba que el servidor de prueba esté iniciado y actualiza la página.</p><button class="primary-btn" data-action="refresh">Reintentar conexión</button></div>`;
  }
}
function setView(view) {
  if (!views[view]) return;
  state.view = view;
  state.search = '';
  document.querySelectorAll('[data-view]').forEach(el => el.classList.toggle('active', el.dataset.view === view));
  $('#crumb-current').textContent = views[view].crumb;
  render();
}
function render() {
  if (!state.dashboard) return;
  const renderer = {
    dashboard: renderDashboard,
    products: renderProducts,
    materials: renderMaterials,
    fichas: renderFichas,
    controls: renderControls,
  }[state.view];
  renderer();
}
function heading(eyebrow, title, description, action = '') {
  return `<div class="page-heading"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1><p>${description}</p></div>${action ? `<div>${action}</div>` : ''}</div>`;
}
function demoBanner() {
  return `<div class="demo-banner"><span class="banner-icon">✦</span><span><strong>Modo demostración.</strong> Los productos, precios y cálculos precargados son ficticios. No constituyen una referencia normativa ni una tarifa oficial.</span><button class="banner-dismiss" data-action="dismiss-banner" aria-label="Cerrar">×</button></div>`;
}
function statCard(label, value, note, icon, hint = '') {
  return `<article class="stat-card"><div class="stat-top"><span>${label}</span><span class="stat-icon">${icon}</span></div><div class="stat-value">${value}</div><div class="stat-note">${note}${hint ? `<span>${hint}</span>` : ''}</div></article>`;
}
function productCell(name, code, category) {
  return `<div class="product-cell"><div class="product-avatar ${categoryClass(category)}">${categoryIcon(category)}</div><div><span class="product-title">${escapeHtml(name)}</span><span class="product-code">${escapeHtml(code || '')}</span></div></div>`;
}
function fichaRecentRow(ficha) {
  return `<tr><td>${productCell(ficha.product_name, ficha.product_code, ficha.category)}</td><td>${statusPill(ficha.status)}</td><td class="amount">${money(ficha.total_cost)}</td><td>${dateLabel(ficha.updated_at)}</td><td><button class="text-btn" data-action="view-ficha" data-id="${ficha.id}">Abrir&nbsp; ↗</button></td></tr>`;
}
function renderDashboard() {
  const d = state.dashboard;
  const actions = `<button class="primary-btn" data-action="create-ficha"><span class="plus">＋</span> Nueva ficha de costo</button>`;
  const categories = d.categories || [];
  const max = Math.max(1, ...categories.map(c => Number(c.count)));
  const categoryRows = categories.length ? categories.map(c => `<div class="category-row"><span class="category-name">${escapeHtml(c.category)}</span><div class="category-track"><div class="category-fill" style="width:${Math.max(8, Number(c.count) / max * 100)}%"></div></div><span class="category-count">${c.count}</span></div>`).join('') : `<div class="empty-state">Aún no hay categorías</div>`;
  content.innerHTML = `${heading('Visión general', 'Controla tus costos con claridad.', 'Un espacio de trabajo para productos, valores del IPV y fichas de costo.', actions)}${demoBanner()}
    <div class="stats-grid">
      ${statCard('Productos activos', d.products, `<span class="positive">Catálogo</span> · productos y servicios`, '▦')}
      ${statCard('Fichas de costo', d.fichas, `<span class="positive">${d.approved_fichas} aprobadas</span> · todas las versiones`, '▤')}
      ${statCard('Controles pendientes', d.pending_controls, d.pending_controls ? 'Requieren revisión' : 'Sin controles pendientes', '◷')}
      ${statCard('Valores de referencia', d.materials, 'Insumos y servicios registrados', '◈')}
    </div>
    <div class="dashboard-grid">
      <section class="panel"><div class="panel-heading"><div><h2 class="panel-title">Fichas recientes</h2><p class="panel-subtitle">Últimos documentos modificados</p></div><button class="text-btn" data-view="fichas">Ver todas&nbsp; →</button></div>
      ${d.recent_fichas && d.recent_fichas.length ? `<div class="table-wrap"><table><thead><tr><th>Producto / servicio</th><th>Estado</th><th>Costo total</th><th>Actualización</th><th></th></tr></thead><tbody>${d.recent_fichas.map(fichaRecentRow).join('')}</tbody></table></div>` : `<div class="empty-state"><div class="empty-icon">▤</div><b>Empieza con una ficha</b><p>Crea la primera ficha de costo para verla aquí.</p><button class="primary-btn" data-action="create-ficha">Crear ficha</button></div>`}</section>
      <section class="panel category-panel"><div class="panel-heading"><div><h2 class="panel-title">Catálogo por categoría</h2><p class="panel-subtitle">Productos y servicios activos</p></div><button class="icon-button" data-view="products" title="Abrir catálogo">↗</button></div>
      <div class="category-list">${categoryRows}</div><div class="insight-card"><small>CONTROL Y TRAZABILIDAD</small><b>Una historia para cada costo.</b><p>Las fichas aprobadas y los controles conservan la versión exacta utilizada para la revisión.</p></div></section>
    </div>`;
}
function searchInput(placeholder = 'Buscar por nombre o código…') {
  return `<label class="searchbox"><span>⌕</span><input id="table-search" type="search" placeholder="${placeholder}" value="${escapeHtml(state.search)}" autocomplete="off"></label>`;
}
function renderProducts() {
  const action = `<button class="primary-btn" data-action="create-product"><span class="plus">＋</span> Nuevo producto</button>`;
  const q = state.search.toLowerCase();
  const rows = state.products.filter(p => `${p.name} ${p.code} ${p.category}`.toLowerCase().includes(q));
  content.innerHTML = `${heading('Catálogo', 'Productos y servicios', 'Organiza los elementos que tendrán una Ficha de Costo.', action)}
    <div class="toolbar">${searchInput()}<select class="filter-select" id="product-category"><option value="">Todas las categorías</option>${[...new Set(state.products.map(p => p.category))].map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('')}</select><button class="secondary-btn" data-action="export-products">↓ Exportar CSV</button></div>
    <section class="panel table-panel"><div class="table-wrap"><table><thead><tr><th>Producto / servicio</th><th>Categoría</th><th>Unidad de salida</th><th>Fichas</th><th>Estado</th><th></th></tr></thead><tbody id="products-tbody">${productRows(rows)}</tbody></table></div></section>
    <div class="small-note">El catálogo es común a las Fichas de Costo y los Controles de IPV. Desactivar un elemento conserva sus documentos históricos.</div>`;
  $('#product-category').addEventListener('change', () => filterProducts());
  $('#table-search').addEventListener('input', e => { state.search = e.target.value; filterProducts(); });
}
function productRows(rows) {
  if (!rows.length) return `<tr><td colspan="6"><div class="empty-state"><div class="empty-icon">▦</div><b>No hay productos coincidentes</b><p>Prueba otro término de búsqueda o registra un nuevo elemento.</p></div></td></tr>`;
  return rows.map(p => `<tr><td>${productCell(p.name, p.code, p.category)}</td><td><span class="category-tag">${escapeHtml(p.category)}</span></td><td>${escapeHtml(p.unit)}</td><td>${p.ficha_count}</td><td>${p.active ? `<span class="status approved">Activo</span>` : `<span class="status">Inactivo</span>`}</td><td><div class="table-actions">${p.active ? `<button class="text-btn" data-action="deactivate-product" data-id="${p.id}" title="Desactivar">Desactivar</button>` : ''}</div></td></tr>`).join('');
}
function filterProducts() {
  const q = ($('#table-search')?.value || '').toLowerCase();
  const category = $('#product-category')?.value || '';
  const rows = state.products.filter(p => `${p.name} ${p.code} ${p.category}`.toLowerCase().includes(q) && (!category || p.category === category));
  const tbody = $('#products-tbody'); if (tbody) tbody.innerHTML = productRows(rows);
}
function renderMaterials() {
  const action = `<button class="primary-btn" data-action="create-material"><span class="plus">＋</span> Registrar valor</button>`;
  const q = state.search.toLowerCase();
  const rows = state.materials.filter(m => `${m.name} ${m.code} ${m.supplier}`.toLowerCase().includes(q));
  content.innerHTML = `${heading('Registro de valores', 'Valores del IPV', 'Insumos, servicios y valores de referencia usados en las fichas.', action)}
    <div class="demo-banner"><span class="banner-icon">◈</span><span>Registra la unidad, vigencia y procedencia de cada valor. Los datos de muestra no son precios oficiales.</span></div>
    <div class="toolbar">${searchInput('Buscar por insumo, código o proveedor…')}<button class="secondary-btn" data-action="export-materials">↓ Exportar CSV</button></div>
    <section class="panel table-panel"><div class="table-wrap"><table><thead><tr><th>Insumo / valor</th><th>Unidad</th><th>Precio unitario</th><th>Moneda</th><th>Procedencia</th><th>Vigencia desde</th><th>Estado</th></tr></thead><tbody id="materials-tbody">${materialRows(rows)}</tbody></table></div></section>
    <div class="small-note">Al incorporar un valor a una ficha, el sistema guarda el precio unitario aplicado como parte de esa versión. Cambiar un valor del catálogo no altera retrospectivamente fichas existentes.</div>`;
  $('#table-search').addEventListener('input', e => {
    state.search = e.target.value;
    const found = state.materials.filter(m => `${m.name} ${m.code} ${m.supplier}`.toLowerCase().includes(state.search.toLowerCase()));
    $('#materials-tbody').innerHTML = materialRows(found);
  });
}
function materialRows(rows) {
  if (!rows.length) return `<tr><td colspan="7"><div class="empty-state"><div class="empty-icon">◈</div><b>Sin valores registrados</b><p>Añade un insumo para usarlo en una ficha de costo.</p></div></td></tr>`;
  return rows.map(m => `<tr><td>${productCell(m.name, m.code, 'Otros')}</td><td>${escapeHtml(m.unit)}</td><td class="amount">${money(m.unit_price)}</td><td>${escapeHtml(m.currency)}</td><td>${escapeHtml(m.source || m.supplier || '—')}</td><td>${dateLabel(m.effective_from)}</td><td>${statusPill(m.status)}</td></tr>`).join('');
}
function renderFichas() {
  const action = `<button class="primary-btn" data-action="create-ficha"><span class="plus">＋</span> Nueva ficha</button>`;
  const q = state.search.toLowerCase();
  const rows = state.fichas.filter(f => `${f.product_name} ${f.product_code} ${f.category} ${f.status}`.toLowerCase().includes(q));
  content.innerHTML = `${heading('Costeo', 'Fichas de costo', 'Elabora, versiona y revisa los componentes de cada producto o servicio.', action)}
    <div class="toolbar">${searchInput('Buscar producto, código o estado…')}<button class="secondary-btn" data-action="export-fichas">↓ Exportar CSV</button><span class="category-tag">${state.fichas.length} versiones</span></div>
    <section class="panel table-panel"><div class="table-wrap"><table><thead><tr><th>Producto / servicio</th><th>Versión</th><th>Componentes</th><th>Vigente desde</th><th>Costo total</th><th>Estado</th><th>Acciones</th></tr></thead><tbody id="fichas-tbody">${fichaRows(rows)}</tbody></table></div></section>
    <div class="small-note">Las fichas aprobadas no se editan directamente. Para reflejar cambios, crea una nueva versión y conserva el vínculo con su Control de IPV.</div>`;
  $('#table-search').addEventListener('input', e => {
    state.search = e.target.value;
    const found = state.fichas.filter(f => `${f.product_name} ${f.product_code} ${f.category} ${f.status}`.toLowerCase().includes(state.search.toLowerCase()));
    $('#fichas-tbody').innerHTML = fichaRows(found);
  });
}
function fichaRows(rows) {
  if (!rows.length) return `<tr><td colspan="7"><div class="empty-state"><div class="empty-icon">▤</div><b>Aún no hay fichas</b><p>Crea una ficha para calcular el costo de un producto o servicio.</p><button class="primary-btn" data-action="create-ficha">Crear ficha</button></div></td></tr>`;
  return rows.map(f => `<tr><td>${productCell(f.product_name, f.product_code, f.category)}</td><td><span class="category-tag">v${f.version}</span></td><td>${f.item_count} líneas</td><td>${dateLabel(f.valid_from)}</td><td class="amount">${money(f.total_cost)}</td><td>${statusPill(f.status)}</td><td><div class="table-actions"><button class="text-btn" data-action="view-ficha" data-id="${f.id}">Ver</button>${f.status === 'Borrador' ? `<button class="text-btn" data-action="approve-ficha" data-id="${f.id}">Aprobar</button>` : ''}<button class="text-btn" data-action="generate-control" data-id="${f.id}">＋ Control</button></div></td></tr>`).join('');
}
function renderControls() {
  const q = state.search.toLowerCase();
  const rows = state.controls.filter(c => `${c.code} ${c.product_name} ${c.product_code} ${c.status} ${c.period}`.toLowerCase().includes(q));
  content.innerHTML = `${heading('Revisión', 'Controles de IPV', 'Cada control conserva una instantánea y referencia a la versión de ficha utilizada.', `<button class="secondary-btn" data-action="export-controls">↓ Exportar CSV</button>`)}
    <div class="toolbar">${searchInput('Buscar código, producto o período…')}<span class="category-tag">${state.controls.length} controles</span></div>
    <section class="panel table-panel"><div class="table-wrap"><table><thead><tr><th>Control IPV</th><th>Producto / servicio</th><th>Período</th><th>Ficha vinculada</th><th>Total controlado</th><th>Estado</th><th></th></tr></thead><tbody id="controls-tbody">${controlRows(rows)}</tbody></table></div></section>
    <div class="small-note">Un control nuevo se genera desde una versión de ficha y copia sus líneas. La validación compara esa instantánea con la ficha vinculada; no sustituye la revisión normativa de la entidad.</div>`;
  $('#table-search').addEventListener('input', e => {
    state.search = e.target.value;
    const found = state.controls.filter(c => `${c.code} ${c.product_name} ${c.product_code} ${c.status} ${c.period}`.toLowerCase().includes(state.search.toLowerCase()));
    $('#controls-tbody').innerHTML = controlRows(found);
  });
}
function controlRows(rows) {
  if (!rows.length) return `<tr><td colspan="7"><div class="empty-state"><div class="empty-icon">✓</div><b>No hay controles todavía</b><p>Abre una ficha y usa “+ Control” para crear el Control de IPV correspondiente.</p><button class="text-btn" data-view="fichas">Ir a las fichas&nbsp; →</button></div></td></tr>`;
  return rows.map(c => `<tr><td><span class="product-title">${escapeHtml(c.code)}</span><span class="product-code">Creado ${dateLabel(c.created_at)}</span></td><td>${productCell(c.product_name, c.product_code, c.category)}</td><td>${escapeHtml(c.period)}</td><td>Ficha v${c.ficha_version}</td><td class="amount">${money(c.snapshot_total)}</td><td>${statusPill(c.status)}</td><td><div class="table-actions"><button class="text-btn" data-action="view-control" data-id="${c.id}">Ver</button>${c.status !== 'Validado' ? `<button class="text-btn" data-action="validate-control" data-id="${c.id}">Validar</button>` : ''}</div></td></tr>`).join('');
}

function showModal(title, subtitle, body, size = '') {
  modalLayer.hidden = false;
  modalLayer.innerHTML = `<div class="modal-card ${escapeHtml(size)}" role="dialog" aria-modal="true"><div class="modal-head"><div><h2>${escapeHtml(title)}</h2><p>${escapeHtml(subtitle)}</p></div><button class="modal-close" data-action="close-modal" aria-label="Cerrar">×</button></div><div class="modal-body">${body}</div></div>`;
  modalLayer.onclick = e => { if (e.target === modalLayer) closeModal(); };
  document.addEventListener('keydown', escModal, { once: true });
}
function escModal(e) { if (e.key === 'Escape') closeModal(); }
function closeModal() { modalLayer.hidden = true; modalLayer.innerHTML = ''; modalLayer.onclick = null; }
function toast(message, type = '') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = message;
  $('#toast-stack').appendChild(el);
  setTimeout(() => el.remove(), 3800);
}
function currentMonth() { return new Date().toISOString().slice(0, 7); }

function openProductModal() {
  const body = `<form id="product-form"><div class="form-grid">
    <div class="form-field"><label for="product-code">Código *</label><input id="product-code" required placeholder="Ej. BEB-003" maxlength="30"></div>
    <div class="form-field"><label for="product-name">Nombre *</label><input id="product-name" required placeholder="Nombre del producto"></div>
    <div class="form-field"><label for="product-category-field">Categoría *</label><select id="product-category-field" required><option value="Bebidas">Bebidas</option><option value="Comidas">Comidas</option><option value="Servicios">Servicios</option><option value="Otros">Otros</option></select></div>
    <div class="form-field"><label for="product-unit">Unidad de salida *</label><input id="product-unit" required placeholder="ración, vaso, servicio…"></div>
    <div class="form-field full"><label for="product-description">Descripción (opcional)</label><textarea id="product-description" placeholder="Notas para identificar el producto o servicio"></textarea></div>
    </div><div class="modal-actions"><button type="button" class="secondary-btn" data-action="close-modal">Cancelar</button><button class="primary-btn" type="submit">Guardar producto</button></div></form>`;
  showModal('Nuevo producto o servicio', 'Añade un elemento al catálogo común.', body);
  $('#product-form').addEventListener('submit', async e => {
    e.preventDefault();
    try {
      await api('/api/products', { method: 'POST', body: JSON.stringify({ code: $('#product-code').value, name: $('#product-name').value, category: $('#product-category-field').value, unit: $('#product-unit').value, description: $('#product-description').value }) });
      closeModal(); await refreshData(true); toast('Producto guardado en SQLite.');
    } catch (error) { toast(error.message, 'error'); }
  });
}
function openMaterialModal() {
  const body = `<form id="material-form"><div class="form-grid">
    <div class="form-field"><label for="material-code">Código *</label><input id="material-code" required placeholder="Ej. INS-013"></div>
    <div class="form-field"><label for="material-name">Insumo o valor *</label><input id="material-name" required placeholder="Nombre del componente"></div>
    <div class="form-field"><label for="material-unit">Unidad *</label><input id="material-unit" required placeholder="kg, L, hora…"></div>
    <div class="form-field"><label for="material-price">Precio unitario *</label><input id="material-price" type="number" min="0" step="0.01" required placeholder="0.00"></div>
    <div class="form-field"><label for="material-currency">Moneda</label><input id="material-currency" value="CUP"></div>
    <div class="form-field"><label for="material-date">Vigente desde</label><input id="material-date" type="date" value="${new Date().toISOString().slice(0,10)}"></div>
    <div class="form-field"><label for="material-supplier">Proveedor / fuente</label><input id="material-supplier" placeholder="Origen del valor"></div>
    <div class="form-field"><label for="material-source">Documento de respaldo</label><input id="material-source" placeholder="Factura, acuerdo, referencia…"></div>
    </div><div class="form-hint">El sistema guarda este valor como referencia; verifica la vigencia y la documentación según el procedimiento de tu entidad.</div><div class="modal-actions"><button type="button" class="secondary-btn" data-action="close-modal">Cancelar</button><button class="primary-btn" type="submit">Guardar valor</button></div></form>`;
  showModal('Registrar valor del IPV', 'Guarda el precio, unidad, vigencia y procedencia.', body);
  $('#material-form').addEventListener('submit', async e => {
    e.preventDefault();
    try {
      await api('/api/materials', { method: 'POST', body: JSON.stringify({ code: $('#material-code').value, name: $('#material-name').value, unit: $('#material-unit').value, unit_price: $('#material-price').value, currency: $('#material-currency').value, effective_from: $('#material-date').value, supplier: $('#material-supplier').value, source: $('#material-source').value }) });
      closeModal(); await refreshData(true); toast('Valor registrado en el IPV.');
    } catch (error) { toast(error.message, 'error'); }
  });
}
let fichaDraftLines = [];
function lineSummary(line) {
  const material = state.materials.find(m => Number(m.id) === Number(line.material_id));
  const name = material?.name || line.description || 'Componente';
  const unit = material?.unit || line.unit || '';
  const unitCost = Number(material?.unit_price ?? line.unit_cost ?? 0);
  const subtotal = Number(line.quantity || 0) * unitCost;
  return { name, unit, unitCost, subtotal };
}
function openFichaModal(existing = null) {
  fichaDraftLines = existing ? existing.items.map(i => ({ material_id: i.material_id, quantity: i.quantity, description: i.description, unit: i.unit, unit_cost: i.unit_cost })) : [];
  const activeProducts = state.products.filter(p => p.active);
  if (!activeProducts.length) { toast('Primero registra un producto o servicio.', 'error'); return; }
  if (!state.materials.length) { toast('Primero registra al menos un valor del IPV.', 'error'); setView('materials'); return; }
  const productOptions = activeProducts.map(p => `<option value="${p.id}" ${existing && Number(existing.product_id) === Number(p.id) ? 'selected' : ''}>${escapeHtml(p.code)} · ${escapeHtml(p.name)} — ${escapeHtml(p.category)}</option>`).join('');
  const materialOptions = state.materials.map(m => `<option value="${m.id}">${escapeHtml(m.name)} · ${money(m.unit_price)}/${escapeHtml(m.unit)}</option>`).join('');
  const body = `<form id="ficha-form"><div class="form-grid">
    <div class="form-field full"><label for="ficha-product">Producto o servicio *</label><select id="ficha-product" required ${existing ? 'disabled' : ''}>${productOptions}</select>${existing ? `<span class="form-hint">Las nuevas versiones se crean desde el listado; esta ficha se edita solo si está en borrador.</span>` : ''}</div>
    <div class="form-field"><label for="ficha-valid-from">Vigente desde</label><input id="ficha-valid-from" type="date" value="${escapeHtml(existing?.valid_from || new Date().toISOString().slice(0,10))}"></div>
    <div class="form-field"><label for="ficha-observations">Observaciones</label><input id="ficha-observations" value="${escapeHtml(existing?.observations || '')}" placeholder="Notas de elaboración o revisión"></div>
    </div>
    <div class="line-builder"><div class="line-builder-head"><b>Componentes de la ficha</b><span class="category-tag">El costo se calcula al añadir cada insumo</span></div>
      <div class="line-entry"><div class="form-field"><label for="line-material">Insumo / valor</label><select id="line-material">${materialOptions}</select></div><div class="form-field"><label for="line-quantity">Cantidad</label><input id="line-quantity" type="number" min="0.0001" step="0.001" value="1"></div><div class="form-field"><label>Unidad</label><input id="line-unit-preview" value="${escapeHtml(state.materials[0]?.unit || '')}" readonly></div><button class="secondary-btn add-line-btn" id="add-line-btn" type="button">＋ Añadir</button></div>
      <div class="line-list" id="ficha-line-list"></div>
    </div>
    <div class="detail-box" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px"><span style="margin:0">Costo total calculado</span><b id="ficha-total" style="font-size:16px">0,00 CUP</b></div>
    <div class="modal-actions"><button type="button" class="secondary-btn" data-action="close-modal">Cancelar</button><button class="primary-btn" type="submit">${existing ? 'Guardar cambios' : 'Crear ficha'}</button></div></form>`;
  showModal(existing ? `Editar ficha v${existing.version}` : 'Nueva Ficha de Costo', existing ? 'Solo se editan fichas en borrador.' : 'Añade los componentes y cantidades de la receta o servicio.', body);
  const updateUnitPreview = () => {
    const selected = state.materials.find(m => Number(m.id) === Number($('#line-material').value));
    $('#line-unit-preview').value = selected?.unit || '';
  };
  const renderLines = () => {
    const host = $('#ficha-line-list');
    if (!fichaDraftLines.length) host.innerHTML = `<div class="form-hint">Todavía no hay componentes. Añade los insumos desde el registro de valores.</div>`;
    else host.innerHTML = fichaDraftLines.map((line, i) => {
      const s = lineSummary(line);
      return `<div class="line-chip"><span>${escapeHtml(s.name)} · ${decimal(line.quantity)} ${escapeHtml(s.unit)}</span><span>${money(s.unitCost)} / ${escapeHtml(s.unit)}</span><b>${money(s.subtotal)}</b><button type="button" class="remove-line" data-remove-line="${i}" aria-label="Quitar línea">×</button></div>`;
    }).join('');
    const total = fichaDraftLines.reduce((sum, line) => sum + lineSummary(line).subtotal, 0);
    $('#ficha-total').textContent = money(total);
  };
  updateUnitPreview(); renderLines();
  $('#line-material').addEventListener('change', updateUnitPreview);
  $('#add-line-btn').addEventListener('click', () => {
    const material = state.materials.find(m => Number(m.id) === Number($('#line-material').value));
    const qty = Number($('#line-quantity').value);
    if (!material || !Number.isFinite(qty) || qty <= 0) { toast('Selecciona un insumo e indica una cantidad mayor que cero.', 'error'); return; }
    fichaDraftLines.push({ material_id: material.id, quantity: String(qty) });
    $('#line-quantity').value = '1'; renderLines();
  });
  $('#ficha-line-list').addEventListener('click', e => {
    const btn = e.target.closest('[data-remove-line]');
    if (btn) { fichaDraftLines.splice(Number(btn.dataset.removeLine), 1); renderLines(); }
  });
  $('#ficha-form').addEventListener('submit', async e => {
    e.preventDefault();
    if (!fichaDraftLines.length) { toast('Añade al menos un componente.', 'error'); return; }
    const payload = { product_id: existing?.product_id || Number($('#ficha-product').value), valid_from: $('#ficha-valid-from').value, observations: $('#ficha-observations').value, items: fichaDraftLines };
    try {
      await api(existing ? `/api/fichas/${existing.id}` : '/api/fichas', { method: existing ? 'PUT' : 'POST', body: JSON.stringify(payload) });
      closeModal(); await refreshData(true); toast(existing ? 'Ficha actualizada.' : 'Ficha creada como borrador.');
    } catch (error) { toast(error.message, 'error'); }
  });
}
async function openFichaDetail(id) {
  try {
    const f = await api(`/api/fichas/${id}`);
    const lines = f.items.map(i => `<tr><td>${escapeHtml(i.description)}</td><td>${decimal(i.quantity)} ${escapeHtml(i.unit)}</td><td class="amount">${money(i.unit_cost)}</td><td class="amount">${money(i.subtotal)}</td></tr>`).join('');
    const body = `<div class="detail-grid"><div class="detail-box"><span>Producto / categoría</span><b>${escapeHtml(f.product_name)} · ${escapeHtml(f.category)}</b></div><div class="detail-box"><span>Versión / estado</span><b>v${f.version} · ${escapeHtml(f.status)}</b></div><div class="detail-box"><span>Vigente desde</span><b>${dateLabel(f.valid_from)}</b></div><div class="detail-box"><span>Costo total</span><b>${money(f.total_cost)}</b></div></div><div class="table-wrap"><table><thead><tr><th>Componente</th><th>Cantidad</th><th>Precio unitario</th><th>Subtotal</th></tr></thead><tbody>${lines}</tbody></table></div>${f.observations ? `<div class="small-note">${escapeHtml(f.observations)}</div>` : ''}<div class="modal-actions"><button class="secondary-btn" data-action="close-modal">Cerrar</button>${f.status === 'Borrador' ? `<button class="secondary-btn" data-action="edit-ficha" data-id="${f.id}">Editar borrador</button><button class="primary-btn" data-action="approve-ficha" data-id="${f.id}">Aprobar ficha</button>` : `<button class="primary-btn" data-action="generate-control" data-id="${f.id}">＋ Generar Control IPV</button>`}</div>`;
    showModal(`Ficha de Costo · v${f.version}`, `${f.product_code} · ${f.product_name}`, body);
  } catch (error) { toast(error.message, 'error'); }
}
async function approveFicha(id) {
  try { await api(`/api/fichas/${id}/approve`, { method: 'POST', body: '{}' }); closeModal(); await refreshData(true); toast('Ficha aprobada.'); }
  catch (error) { toast(error.message, 'error'); }
}
async function openGenerateControl(id) {
  const ficha = await api(`/api/fichas/${id}`);
  const body = `<form id="control-form"><div class="detail-grid"><div class="detail-box"><span>Producto / versión</span><b>${escapeHtml(ficha.product_name)} · v${ficha.version}</b></div><div class="detail-box"><span>Total de la ficha</span><b>${money(ficha.total_cost)}</b></div></div><div class="form-field"><label for="control-period">Período del control *</label><input id="control-period" type="month" required value="${currentMonth()}"><span class="form-hint">Se creará una instantánea de las líneas y el total de esta versión.</span></div><div class="form-field"><label for="control-notes">Observaciones</label><textarea id="control-notes" placeholder="Notas para la revisión"></textarea></div><div class="modal-actions"><button type="button" class="secondary-btn" data-action="close-modal">Cancelar</button><button class="primary-btn" type="submit">Crear Control IPV</button></div></form>`;
  showModal('Generar Control de IPV', 'El control quedará vinculado a la versión exacta de esta ficha.', body);
  $('#control-form').addEventListener('submit', async e => {
    e.preventDefault();
    try {
      await api('/api/controls', { method: 'POST', body: JSON.stringify({ ficha_id: id, period: $('#control-period').value, notes: $('#control-notes').value }) });
      closeModal(); await refreshData(true); setView('controls'); toast('Control IPV creado como pendiente de revisión.');
    } catch (error) { toast(error.message, 'error'); }
  });
}
async function openControlDetail(id) {
  try {
    const c = await api(`/api/controls/${id}`);
    const lines = c.items.map(i => `<tr><td>${escapeHtml(i.description)}</td><td>${decimal(i.quantity)} ${escapeHtml(i.unit)}</td><td class="amount">${money(i.unit_cost)}</td><td class="amount">${money(i.subtotal)}</td></tr>`).join('');
    const messages = (c.validation_messages || []).map(m => `<div class="small-note" style="margin-top:8px;color:${m.type === 'error' ? '#a34f43' : m.type === 'success' ? '#43815c' : '#74816f'}">${m.type === 'error' ? '⚠ ' : m.type === 'success' ? '✓ ' : '• '}${escapeHtml(m.text)}</div>`).join('');
    const body = `<div class="detail-grid"><div class="detail-box"><span>Producto / ficha vinculada</span><b>${escapeHtml(c.product_name)} · v${c.ficha_version}</b></div><div class="detail-box"><span>Período / estado</span><b>${escapeHtml(c.period)} · ${escapeHtml(c.status)}</b></div><div class="detail-box"><span>Total del control</span><b>${money(c.snapshot_total)}</b></div><div class="detail-box"><span>Total verificado</span><b>${c.checked_at ? money(c.checked_total) : 'Sin validar'}</b></div></div><div class="table-wrap"><table><thead><tr><th>Componente</th><th>Cantidad</th><th>Precio unitario</th><th>Subtotal</th></tr></thead><tbody>${lines}</tbody></table></div>${messages}<div class="modal-actions"><button class="secondary-btn" data-action="close-modal">Cerrar</button>${c.status !== 'Validado' ? `<button class="primary-btn" data-action="validate-control" data-id="${c.id}">Ejecutar validación</button>` : ''}</div>`;
    showModal(`Control IPV · ${c.code}`, `${c.product_code} · ${c.product_name}`, body);
  } catch (error) { toast(error.message, 'error'); }
}
async function validateControl(id) {
  try {
    const c = await api(`/api/controls/${id}/validate`, { method: 'POST', body: '{}' });
    await refreshData(true);
    openControlDetail(c.id);
    toast(c.status === 'Validado' ? 'Control validado sin diferencias.' : 'La revisión encontró observaciones.', c.status === 'Validado' ? '' : 'error');
  } catch (error) { toast(error.message, 'error'); }
}
function exportCsv(type) {
  let rows = [], filename = 'exportacion.csv';
  if (type === 'products') {
    filename = 'productos-servicios.csv'; rows = [['Código','Nombre','Categoría','Unidad','Estado'], ...state.products.map(p => [p.code,p.name,p.category,p.unit,p.active ? 'Activo' : 'Inactivo'])];
  } else if (type === 'materials') {
    filename = 'valores-ipv.csv'; rows = [['Código','Nombre','Unidad','Precio unitario','Moneda','Fuente','Vigente desde','Estado'], ...state.materials.map(m => [m.code,m.name,m.unit,m.unit_price,m.currency,m.source || m.supplier,m.effective_from,m.status])];
  } else if (type === 'fichas') {
    filename = 'fichas-costo.csv'; rows = [['Producto','Código','Categoría','Versión','Vigente desde','Costo total','Estado'], ...state.fichas.map(f => [f.product_name,f.product_code,f.category,f.version,f.valid_from,f.total_cost,f.status])];
  } else {
    filename = 'controles-ipv.csv'; rows = [['Control','Producto','Código','Período','Versión de ficha','Total','Estado'], ...state.controls.map(c => [c.code,c.product_name,c.product_code,c.period,c.ficha_version,c.snapshot_total,c.status])];
  }
  const csv = '\ufeff' + rows.map(row => row.map(cell => `"${String(cell ?? '').replaceAll('"', '""')}"`).join(';')).join('\r\n');
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  const a = document.createElement('a'); a.href = url; a.download = filename; a.click(); URL.revokeObjectURL(url);
  toast('Archivo CSV exportado.');
}

modalLayer.addEventListener('click', async e => {
  const btn = e.target.closest('[data-action]');
  if (!btn) return;
  const { action, id } = btn.dataset;
  try {
    if (action === 'close-modal') closeModal();
    else if (action === 'approve-ficha') approveFicha(id);
    else if (action === 'edit-ficha') { const f = await api(`/api/fichas/${id}`); openFichaModal(f); }
    else if (action === 'generate-control') openGenerateControl(id);
    else if (action === 'validate-control') validateControl(id);
  } catch (error) { toast(error.message, 'error'); }
});

content.addEventListener('click', async e => {
  const nav = e.target.closest('[data-view]');
  if (nav) { setView(nav.dataset.view); return; }
  const btn = e.target.closest('[data-action]');
  if (!btn) return;
  const { action, id } = btn.dataset;
  try {
    if (action === 'refresh') refreshData();
    else if (action === 'create-product') openProductModal();
    else if (action === 'create-material') openMaterialModal();
    else if (action === 'create-ficha') openFichaModal();
    else if (action === 'view-ficha') openFichaDetail(id);
    else if (action === 'edit-ficha') { const f = await api(`/api/fichas/${id}`); openFichaModal(f); }
    else if (action === 'approve-ficha') approveFicha(id);
    else if (action === 'generate-control') openGenerateControl(id);
    else if (action === 'view-control') openControlDetail(id);
    else if (action === 'validate-control') validateControl(id);
    else if (action === 'export-products') exportCsv('products');
    else if (action === 'export-materials') exportCsv('materials');
    else if (action === 'export-fichas') exportCsv('fichas');
    else if (action === 'export-controls') exportCsv('controls');
    else if (action === 'dismiss-banner') btn.closest('.demo-banner')?.remove();
    else if (action === 'close-modal') closeModal();
    else if (action === 'deactivate-product') {
      if (confirm('¿Desactivar este producto? Los documentos históricos se conservarán.')) {
        await api(`/api/products/${id}`, { method: 'DELETE' }); await refreshData(true); toast('Producto desactivado.');
      }
    }
  } catch (error) { toast(error.message, 'error'); }
});
document.querySelectorAll('[data-view]').forEach(el => el.addEventListener('click', () => setView(el.dataset.view)));
$('#refresh-btn').addEventListener('click', () => refreshData());
$('#about-btn').addEventListener('click', () => showModal('Sobre el prototipo', 'IPV · Fichas y Costos', `<p style="font-size:11px;line-height:1.7;color:#607067">Aplicación de prueba para explorar el flujo de catálogo, valores de referencia, Fichas de Costo versionadas y Controles de IPV conectados a una base de datos SQLite común.</p><div class="small-note">Los importes precargados son ilustrativos. Antes de utilizar el sistema en una operación real deben definirse y revisar las reglas normativas, cálculos, roles, firmas, permisos, seguridad, alojamiento y sincronización offline.</div><div class="modal-actions"><button class="primary-btn" data-action="close-modal">Entendido</button></div>`));
refreshData();
