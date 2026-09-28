'use strict';
/* ==========================================================================
   IPV · Fichas y Costos v1.0 — Aplicación web profesional
   Autor: Ing. Yosvany Hernández Quintero
   ========================================================================== */

const state = { view: 'dashboard', dashboard: null, products: [], materials: [], fichas: [], controls: [], search: '' };
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const content = $('#page-content');
const modalLayer = $('#modal-layer');
const APP_VERSION = '1.0.0';

const views = {
  dashboard: { crumb: 'Resumen' }, products: { crumb: 'Productos y servicios' },
  materials: { crumb: 'Valores del IPV' }, fichas: { crumb: 'Fichas de costo' }, controls: { crumb: 'Controles de IPV' },
};

/* ── Utilities ── */
function esc(v = '') { return String(v).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
function money(v) { const n = Number(v || 0); return `${new Intl.NumberFormat('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number.isFinite(n) ? n : 0)} CUP`; }
function dec(v, d = 3) { const n = Number(v || 0); return new Intl.NumberFormat('es-ES', { maximumFractionDigits: d }).format(Number.isFinite(n) ? n : 0); }
function dateLabel(v) { if (!v) return '—'; const d = new Date(v); if (Number.isNaN(d.getTime())) return esc(v); return new Intl.DateTimeFormat('es', { day: '2-digit', month: 'short', year: 'numeric' }).format(d); }
function currentMonth() { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`; }
function catClass(c = '') { const v = c.toLowerCase(); if (v.includes('comida') || v.includes('alimento')) return 'food'; if (v.includes('serv')) return 'service'; if (v.includes('beb')) return ''; return 'other'; }
function catIcon(c = '') { const v = c.toLowerCase(); return v.includes('comida') || v.includes('alimento') ? '◉' : v.includes('serv') ? '⌂' : v.includes('beb') ? '◒' : '◇'; }
function stClass(s = '') { const v = s.toLowerCase(); if (v.includes('aprob') || v.includes('vigente')) return 'approved'; if (v.includes('valid')) return 'validated'; if (v.includes('difer') || v.includes('error')) return 'difference'; if (v.includes('revisi')) return 'review'; if (v.includes('pend') || v.includes('borr')) return 'pending'; return ''; }
function stPill(s) { return `<span class="status ${stClass(s)}">${esc(s || 'Sin estado')}</span>`; }
function toast(msg, type = '') { const stack = $('#toast-stack'); const el = document.createElement('div'); el.className = `toast ${type}`; el.textContent = msg; stack.appendChild(el); setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity .3s'; setTimeout(() => el.remove(), 350); }, 3800); }

/* ── Theme ── */
function initTheme() {
  const saved = localStorage.getItem('ipv-theme') || 'light';
  document.documentElement.setAttribute('data-theme', saved);
}
function toggleTheme() {
  const current = document.documentElement.getAttribute('data-theme');
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('ipv-theme', next);
}
initTheme();

/* ── API ── */
async function api(path, opts = {}, retried = false) {
  const auth = window.IPVAuth ? window.IPVAuth.headers() : {};
  const r = await fetch(path, { ...opts, headers: { 'Content-Type': 'application/json', ...auth, ...(opts.headers || {}) } });
  if (r.status === 401 && window.IPVAuth && !retried && !path.startsWith('/api/auth/')) {
    if (await window.IPVAuth.recover()) return api(path, opts, true);
  }
  const d = await r.json().catch(() => ({}));
  if (r.status === 402 && d.license_required && window.IPVLicense) window.IPVLicense.show(null);
  if (r.status === 403 && d.password_expired && window.IPVAuth?.forcePasswordChange && !retried) {
    if (await window.IPVAuth.forcePasswordChange()) return api(path, opts, true);
  }
  if (!r.ok) throw new Error(d.error || `Error ${r.status}`);
  return d;
}

/* ── Connection ── */
function setConn(on, label = '') {
  $('#connection-dot').className = `connection-dot ${on ? 'online' : 'offline'}`;
  $('#connection-label').textContent = label || (on ? 'Base de datos conectada' : 'Sin conexión');
}

async function refreshData(quiet = false) {
  if (!quiet) setConn(false, 'Actualizando…');
  try {
    const [d, p, m, f, c] = await Promise.all([api('/api/dashboard'), api('/api/products'), api('/api/materials'), api('/api/fichas'), api('/api/controls')]);
    Object.assign(state, { dashboard: d, products: p, materials: m, fichas: f, controls: c });
    setConn(true, 'Base de datos conectada');
    $('#nav-products').textContent = p.filter(x => x.active).length;
    $('#nav-fichas').textContent = f.length;
    $('#nav-pending-dot').style.display = c.some(x => x.status === 'Pendiente' || x.status === 'Con diferencias') ? 'block' : 'none';
    render();
  } catch (e) {
    setConn(false, 'No se pudo conectar');
    if (!quiet) toast(e.message, 'error');
    content.innerHTML = `<div class="empty-state panel"><div class="empty-icon">⌁</div><b>No se pudo conectar con la base de datos</b><p>Verifique que el servidor esté activo y actualice la página.</p><button class="primary-btn" data-action="refresh">Reintentar conexión</button></div>`;
  }
}

/* ── Navigation ── */
function setView(v) {
  if (!views[v]) return;
  state.view = v; state.search = '';
  $$('[data-view]').forEach(el => el.classList.toggle('active', el.dataset.view === v));
  $('#crumb-current').textContent = views[v].crumb;
  $('#sidebar').classList.remove('open'); $('#sidebar-overlay').classList.remove('active');
  render();
}
function render() {
  if (!state.dashboard) return;
  ({ dashboard: renderDashboard, products: renderProducts, materials: renderMaterials, fichas: renderFichas, controls: renderControls })[state.view]();
}

/* ── Helpers ── */
function heading(eye, title, desc, action = '') { return `<div class="page-heading"><div><div class="eyebrow">${eye}</div><h1>${title}</h1><p>${desc}</p></div>${action ? `<div>${action}</div>` : ''}</div>`; }
function statCard(label, value, note, icon) { return `<article class="stat-card"><div class="stat-top"><span>${label}</span><span class="stat-icon">${icon}</span></div><div class="stat-value">${value}</div><div class="stat-note">${note}</div></article>`; }
function prodCell(name, code, cat) { return `<div class="product-cell"><div class="product-avatar ${catClass(cat)}">${catIcon(cat)}</div><div><span class="product-title">${esc(name)}</span><span class="product-code">${esc(code || '')}</span></div></div>`; }
function searchBox(ph = 'Buscar por nombre o código…') { return `<label class="searchbox"><span>⌕</span><input id="table-search" type="search" placeholder="${ph}" value="${esc(state.search)}" autocomplete="off"></label>`; }

/* ── Dashboard ── */
function renderDashboard() {
  const d = state.dashboard;
  const cats = d.categories || [];
  const max = Math.max(1, ...cats.map(c => Number(c.count)));
  const catRows = cats.length ? cats.map(c => `<div class="category-row"><span class="category-name">${esc(c.category)}</span><div class="category-track"><div class="category-fill" style="width:${Math.max(8, Number(c.count) / max * 100)}%"></div></div><span class="category-count">${c.count}</span></div>`).join('') : '<div class="empty-state">Sin categorías</div>';

  // Cost chart
  const costData = d.cost_by_category || [];
  const maxCost = Math.max(1, ...costData.map(c => Number(c.total || 0)));
  const chartBars = costData.length ? costData.map((c, i) => {
    const pct = Math.max(4, Number(c.total || 0) / maxCost * 100);
    const colors = ['var(--gradient-success)', 'var(--gradient-blue)', 'var(--gradient-warm)', 'linear-gradient(135deg, var(--purple), var(--blue))'];
    return `<div class="category-row"><span class="category-name">${esc(c.category)}</span><div class="category-track"><div class="category-fill" style="width:${pct}%;background:${colors[i % 4]}"></div></div><span class="category-count">${money(c.total)}</span></div>`;
  }).join('') : '';

  content.innerHTML = `
    ${heading('Visión general', 'Control de costos integral', 'Gestión centralizada de productos, valores de referencia del IPV, fichas de costo y controles de verificación.', '<button class="primary-btn" data-action="create-ficha"><span class="plus">＋</span> Nueva ficha de costo</button>')}
    <div class="stats-grid">
      ${statCard('Productos activos', d.products, '<span class="positive">Catálogo</span> · productos y servicios', '▦')}
      ${statCard('Fichas de costo', d.fichas, `<span class="positive">${d.approved_fichas} aprobadas</span> · todas las versiones`, '▤')}
      ${statCard('Controles pendientes', d.pending_controls, d.pending_controls ? '<span style="color:var(--orange)">Requieren revisión</span>' : '<span class="positive">Todos al día</span>', '◷')}
      ${statCard('Valores de referencia', d.materials, 'Insumos y servicios registrados', '◈')}
    </div>
    <div class="dashboard-grid">
      <section class="panel">
        <div class="panel-heading"><div><h2 class="panel-title">Fichas recientes</h2><p class="panel-subtitle">Últimos documentos modificados</p></div><button class="text-btn" data-view="fichas">Ver todas →</button></div>
        ${d.recent_fichas?.length
          ? `<div class="table-wrap"><table><thead><tr><th>Producto</th><th>Estado</th><th>Costo total</th><th>Actualización</th><th></th></tr></thead><tbody>${d.recent_fichas.map(f => `<tr><td>${prodCell(f.product_name, f.product_code, f.category)}</td><td>${stPill(f.status)}</td><td class="amount">${money(f.total_cost)}</td><td>${dateLabel(f.updated_at)}</td><td><button class="text-btn" data-action="view-ficha" data-id="${f.id}">Abrir ↗</button></td></tr>`).join('')}</tbody></table></div>`
          : '<div class="empty-state"><div class="empty-icon">▤</div><b>Empieza con una ficha</b><p>Crea la primera ficha de costo.</p><button class="primary-btn" data-action="create-ficha">Crear ficha</button></div>'}
      </section>
      <section class="panel category-panel">
        <div class="panel-heading"><div><h2 class="panel-title">Catálogo por categoría</h2><p class="panel-subtitle">Productos y servicios activos</p></div><button class="icon-button" data-view="products" title="Abrir catálogo">↗</button></div>
        <div class="category-list">${catRows}</div>
        ${chartBars ? `<div style="margin-top:20px"><div class="panel-subtitle" style="margin-bottom:10px;font-weight:600;font-size:10px;color:var(--text-3)">DISTRIBUCIÓN DE COSTOS</div><div class="category-list">${chartBars}</div></div>` : ''}
        <div class="insight-card"><small>CONTROL Y TRAZABILIDAD</small><b>Una historia para cada costo.</b><p>Las fichas aprobadas y los controles conservan la versión exacta utilizada para la revisión.</p></div>
      </section>
    </div>`;
}

/* ── Products ── */
function renderProducts() {
  const q = state.search.toLowerCase();
  const cf = $('#product-category')?.value || '';
  const rows = state.products.filter(p => `${p.name} ${p.code} ${p.category}`.toLowerCase().includes(q) && (!cf || p.category === cf));
  content.innerHTML = `
    ${heading('Catálogo', 'Productos y servicios', 'Organiza los elementos que tendrán una Ficha de Costo asociada.', '<button class="primary-btn" data-action="create-product"><span class="plus">＋</span> Nuevo producto</button>')}
    <div class="toolbar">${searchBox()}<select class="filter-select" id="product-category"><option value="">Todas las categorías</option>${[...new Set(state.products.map(p => p.category))].map(c => `<option value="${esc(c)}" ${c === cf ? 'selected' : ''}>${esc(c)}</option>`).join('')}</select><button class="secondary-btn" data-action="export-products">⤓ Exportar CSV</button></div>
    <section class="panel table-panel">${rows.length
      ? `<div class="table-wrap"><table><thead><tr><th>Producto</th><th>Categoría</th><th>Unidad</th><th>Fichas</th><th>Estado</th><th style="text-align:right">Acciones</th></tr></thead><tbody>${rows.map(p => `<tr><td>${prodCell(p.name, p.code, p.category)}</td><td class="category-tag">${esc(p.category)}</td><td>${esc(p.unit)}</td><td>${p.ficha_count || 0}</td><td>${p.active ? '<span class="status approved">Activo</span>' : '<span class="status">Inactivo</span>'}</td><td><div class="table-actions">${p.active ? `<button class="danger-btn" data-action="deactivate-product" data-id="${p.id}">Desactivar</button>` : ''}</div></td></tr>`).join('')}</tbody></table></div>`
      : `<div class="empty-state"><div class="empty-icon">▦</div><b>${q || cf ? 'Sin resultados' : 'No hay productos'}</b><p>${q || cf ? 'Ajusta los filtros.' : 'Registra el primer producto del catálogo.'}</p></div>`}</section>`;
  $('#table-search')?.addEventListener('input', e => { state.search = e.target.value; renderProducts(); });
  $('#product-category')?.addEventListener('change', () => renderProducts());
}

/* ── Materials ── */
function renderMaterials() {
  const q = state.search.toLowerCase();
  const rows = state.materials.filter(m => `${m.name} ${m.code} ${m.supplier}`.toLowerCase().includes(q));
  content.innerHTML = `
    ${heading('Referencias', 'Valores del IPV', 'Insumos, materias primas y servicios con precios unitarios de referencia para el cálculo de costos.', '<button class="primary-btn" data-action="create-material"><span class="plus">＋</span> Nuevo valor</button>')}
    <div class="toolbar">${searchBox()}<button class="secondary-btn" data-action="export-materials">⤓ Exportar CSV</button></div>
    <section class="panel table-panel">${rows.length
      ? `<div class="table-wrap"><table><thead><tr><th>Insumo</th><th>Unidad</th><th>Precio</th><th>Moneda</th><th>Fuente</th><th>Vigencia</th><th>Estado</th><th style="text-align:right">Acciones</th></tr></thead><tbody>${rows.map(m => `<tr><td><div class="product-cell"><div class="product-avatar" style="background:var(--orange-glow);color:var(--orange)">◈</div><div><span class="product-title">${esc(m.name)}</span><span class="product-code">${esc(m.code)}</span></div></div></td><td>${esc(m.unit)}</td><td class="amount">${money(m.unit_price)}</td><td>${esc(m.currency)}</td><td class="category-tag">${esc(m.source || m.supplier || '—')}</td><td>${dateLabel(m.effective_from)}</td><td>${stPill(m.status)}</td><td><div class="table-actions">${m.status !== 'Inactivo' ? `<button class="danger-btn" data-action="deactivate-material" data-id="${m.id}">Desactivar</button>` : ''}</div></td></tr>`).join('')}</tbody></table></div>`
      : `<div class="empty-state"><div class="empty-icon">◈</div><b>${q ? 'Sin resultados' : 'No hay valores'}</b><p>${q ? 'Ajusta la búsqueda.' : 'Registra los insumos de referencia.'}</p></div>`}</section>`;
  $('#table-search')?.addEventListener('input', e => { state.search = e.target.value; renderMaterials(); });
}

/* ── Fichas ── */
function renderFichas() {
  const q = state.search.toLowerCase();
  const sf = $('#ficha-status')?.value || '';
  const rows = state.fichas.filter(f => `${f.product_name} ${f.product_code} ${f.category}`.toLowerCase().includes(q) && (!sf || f.status === sf));
  content.innerHTML = `
    ${heading('Documentos', 'Fichas de costo', 'Cada ficha registra los componentes y el costo total. Se versionan automáticamente.', '<button class="primary-btn" data-action="create-ficha"><span class="plus">＋</span> Nueva ficha</button>')}
    <div class="toolbar">${searchBox()}<select class="filter-select" id="ficha-status"><option value="">Todos los estados</option><option value="Borrador" ${sf === 'Borrador' ? 'selected' : ''}>Borrador</option><option value="Aprobada" ${sf === 'Aprobada' ? 'selected' : ''}>Aprobada</option></select><button class="secondary-btn" data-action="export-fichas">⤓ Exportar CSV</button></div>
    <section class="panel table-panel">${rows.length
      ? `<div class="table-wrap"><table><thead><tr><th>Producto</th><th>Versión</th><th>Vigente</th><th>Componentes</th><th>Costo total</th><th>Estado</th><th></th></tr></thead><tbody>${rows.map(f => `<tr><td>${prodCell(f.product_name, f.product_code, f.category)}</td><td>v${f.version}</td><td>${dateLabel(f.valid_from)}</td><td>${f.item_count || 0}</td><td class="amount">${money(f.total_cost)}</td><td>${stPill(f.status)}</td><td><button class="text-btn" data-action="view-ficha" data-id="${f.id}">Abrir ↗</button></td></tr>`).join('')}</tbody></table></div>`
      : `<div class="empty-state"><div class="empty-icon">▤</div><b>${q || sf ? 'Sin resultados' : 'No hay fichas'}</b><p>${q || sf ? 'Ajusta los filtros.' : 'Crea la primera ficha de costo.'}</p></div>`}</section>`;
  $('#table-search')?.addEventListener('input', e => { state.search = e.target.value; renderFichas(); });
  $('#ficha-status')?.addEventListener('change', () => renderFichas());
}

/* ── Controls ── */
function renderControls() {
  const q = state.search.toLowerCase();
  const sf = $('#control-status')?.value || '';
  const rows = state.controls.filter(c => `${c.product_name} ${c.code} ${c.product_code}`.toLowerCase().includes(q) && (!sf || c.status === sf));
  content.innerHTML = `
    ${heading('Verificación', 'Controles de IPV', 'Cada control es una instantánea vinculada a una versión específica de ficha. La validación compara totales y líneas.', '')}
    <div class="toolbar">${searchBox()}<select class="filter-select" id="control-status"><option value="">Todos los estados</option><option value="Pendiente" ${sf === 'Pendiente' ? 'selected' : ''}>Pendiente</option><option value="Validado" ${sf === 'Validado' ? 'selected' : ''}>Validado</option><option value="Con diferencias" ${sf === 'Con diferencias' ? 'selected' : ''}>Con diferencias</option></select><button class="secondary-btn" data-action="export-controls">⤓ Exportar CSV</button></div>
    <section class="panel table-panel">${rows.length
      ? `<div class="table-wrap"><table><thead><tr><th>Control</th><th>Producto</th><th>Período</th><th>Ficha</th><th>Total</th><th>Estado</th><th></th></tr></thead><tbody>${rows.map(c => `<tr><td><b style="color:var(--text);font-size:12px">${esc(c.code)}</b></td><td>${prodCell(c.product_name, c.product_code, c.category)}</td><td>${esc(c.period)}</td><td>v${c.ficha_version}</td><td class="amount">${money(c.snapshot_total)}</td><td>${stPill(c.status)}</td><td><button class="text-btn" data-action="view-control" data-id="${c.id}">Abrir ↗</button></td></tr>`).join('')}</tbody></table></div>`
      : `<div class="empty-state"><div class="empty-icon">✓</div><b>${q || sf ? 'Sin resultados' : 'No hay controles'}</b><p>${q || sf ? 'Ajusta los filtros.' : 'Genera un control desde una ficha aprobada.'}</p></div>`}</section>`;
  $('#table-search')?.addEventListener('input', e => { state.search = e.target.value; renderControls(); });
  $('#control-status')?.addEventListener('change', () => renderControls());
}

/* ── Modal ── */
function showModal(title, subtitle, body) {
  modalLayer.hidden = false;
  modalLayer.innerHTML = `<div class="modal-card"><div class="modal-head"><div><h2>${esc(title)}</h2><p>${esc(subtitle)}</p></div><button class="modal-close" data-action="close-modal" aria-label="Cerrar">×</button></div><div class="modal-body">${body}</div></div>`;
}
function closeModal() { modalLayer.hidden = true; modalLayer.innerHTML = ''; }

/* ── About ── */
function openAbout() {
  showModal('Acerca de IPV', 'Sistema profesional de gestión de costos', `
    <div class="about-brand"><div class="brand-mark"><span>i</span><span>v</span></div><div><div style="font:800 24px Manrope,sans-serif;color:var(--text);letter-spacing:-.8px">IPV<span style="color:var(--accent-vivid)">.</span></div><div style="font-size:11px;color:var(--text-3);margin-top:3px">Fichas y Costos</div></div></div>
    <div class="about-version">🛡 v${APP_VERSION} · Edición profesional · Cifrado TLS</div>
    <div class="about-author"><div class="about-author-avatar">YH</div><div class="about-author-info"><b>Ing. Yosvany Hernández Quintero</b><small>Diseño y desarrollo del sistema</small></div></div>
    <div class="about-section"><h3>Sistema de gestión</h3><p>Plataforma integral para la gestión de Fichas de Costo, valores de referencia del IPV y Controles de verificación. Permite el registro centralizado de productos y servicios, el cálculo versionado de costos y la validación periódica mediante controles vinculados a cada versión aprobada.</p></div>
    <div class="about-section"><h3>Funcionalidades</h3><p>Catálogo de productos y servicios · Valores de referencia con vigencia · Fichas versionadas con aprobación por estados · Controles como instantáneas verificables · Validación automática de totales · Exportación CSV · Tema claro/oscuro · Búsqueda global.</p></div>
    <div class="about-divider"></div>
    <div class="about-section"><h3>Seguridad y arquitectura</h3><p>API REST en Python con HTTPS/TLS 1.2+. Rate limiting por IP. Autenticación por token API opcional. Cabeceras de seguridad (CSP, HSTS, X-Frame-Options). Sanitización de entradas. SQLite con WAL y claves foráneas. Auditoría de operaciones. Aplicación nativa Android en Kotlin.</p></div>
    <div class="about-tech"><span>🐍 Python 3</span><span>🗄 SQLite WAL</span><span>🔒 TLS 1.2+</span><span>🛡 Rate Limiting</span><span>📱 Kotlin</span><span>🎨 HTML5/CSS3</span><span>⚡ JavaScript ES6+</span><span>🌙 Dark Mode</span></div>
    <div class="modal-actions"><button class="primary-btn" data-action="close-modal">Entendido</button></div>`);
}

/* ── Forms ── */
function openProductModal() {
  showModal('Nuevo producto o servicio', 'Se añadirá al catálogo activo.', `<form id="pf"><div class="form-grid"><div class="form-field"><label>Código *</label><input id="p-code" required placeholder="Ej: BEB-003"></div><div class="form-field"><label>Categoría *</label><input id="p-cat" required placeholder="Bebidas, Comidas, Servicios"></div><div class="form-field full"><label>Nombre *</label><input id="p-name" required placeholder="Nombre del producto o servicio"></div><div class="form-field"><label>Unidad</label><input id="p-unit" value="unidad"></div><div class="form-field full"><label>Descripción</label><textarea id="p-desc" placeholder="Notas adicionales"></textarea></div></div><div class="modal-actions"><button type="button" class="secondary-btn" data-action="close-modal">Cancelar</button><button class="primary-btn" type="submit">Registrar producto</button></div></form>`);
  $('#pf').addEventListener('submit', async e => { e.preventDefault(); try { await api('/api/products', { method: 'POST', body: JSON.stringify({ code: $('#p-code').value, name: $('#p-name').value, category: $('#p-cat').value, unit: $('#p-unit').value || 'unidad', description: $('#p-desc').value }) }); closeModal(); await refreshData(true); toast('Producto registrado correctamente.', 'success'); } catch (err) { toast(err.message, 'error'); } });
}

function openMaterialModal() {
  showModal('Nuevo valor de referencia', 'Insumo o servicio con precio unitario.', `<form id="mf"><div class="form-grid"><div class="form-field"><label>Código *</label><input id="m-code" required placeholder="INS-013"></div><div class="form-field"><label>Nombre *</label><input id="m-name" required></div><div class="form-field"><label>Unidad *</label><input id="m-unit" required placeholder="kg, L, unidad"></div><div class="form-field"><label>Precio unitario *</label><input id="m-price" type="number" step="0.01" min="0" required></div><div class="form-field"><label>Moneda</label><select id="m-curr"><option>CUP</option><option>MLC</option><option>USD</option></select></div><div class="form-field"><label>Proveedor</label><input id="m-sup"></div><div class="form-field full"><label>Fuente</label><input id="m-src" placeholder="Resolución, factura…"></div><div class="form-field"><label>Vigente desde</label><input id="m-from" type="date" value="${new Date().toISOString().slice(0, 10)}"></div><div class="form-field"><label>Vigente hasta</label><input id="m-to" type="date"></div></div><div class="modal-actions"><button type="button" class="secondary-btn" data-action="close-modal">Cancelar</button><button class="primary-btn" type="submit">Registrar valor</button></div></form>`);
  $('#mf').addEventListener('submit', async e => { e.preventDefault(); try { await api('/api/materials', { method: 'POST', body: JSON.stringify({ code: $('#m-code').value, name: $('#m-name').value, unit: $('#m-unit').value, unit_price: $('#m-price').value, currency: $('#m-curr').value, supplier: $('#m-sup').value, source: $('#m-src').value, effective_from: $('#m-from').value, effective_to: $('#m-to').value }) }); closeModal(); await refreshData(true); toast('Valor registrado.', 'success'); } catch (err) { toast(err.message, 'error'); } });
}

function openFichaModal(ficha = null) {
  const isEdit = !!ficha;
  const ap = state.products.filter(p => p.active);
  if (!ap.length) { toast('Registre un producto activo primero.', 'error'); return; }
  if (!state.materials.length) { toast('Registre un valor de referencia primero.', 'error'); return; }
  const pid = ficha?.product_id || ap[0].id;
  const lines = ficha?.items?.map(i => ({ materialId: i.material_id, description: i.description, quantity: i.quantity, unit: i.unit, unitCost: i.unit_cost })) || [];

  showModal(isEdit ? 'Editar ficha' : 'Nueva ficha de costo', isEdit ? `Versión ${ficha.version}` : 'Se creará en estado borrador.', `<form id="ff"><div class="form-grid"><div class="form-field full"><label>Producto *</label><select id="f-prod" ${isEdit ? 'disabled' : ''}>${ap.map(p => `<option value="${p.id}" ${p.id === pid ? 'selected' : ''}>${esc(p.name)} (${esc(p.code)})</option>`).join('')}</select></div><div class="form-field"><label>Vigente desde</label><input id="f-date" type="date" value="${ficha?.valid_from || new Date().toISOString().slice(0, 10)}"></div><div class="form-field full"><label>Observaciones</label><textarea id="f-notes">${esc(ficha?.observations || '')}</textarea></div></div><div class="line-builder"><div class="line-builder-head"><b>Componentes</b><span id="line-total" class="amount">Total: 0.00 CUP</span></div><div class="line-entry"><div class="form-field"><label>Insumo</label><select id="f-mat">${state.materials.map(m => `<option value="${m.id}" data-price="${m.unit_price}" data-unit="${esc(m.unit)}">${esc(m.name)} (${esc(m.code)})</option>`).join('')}</select></div><div class="form-field"><label>Cantidad</label><input id="f-qty" type="number" step="0.001" min="0.001" placeholder="0"></div><div class="form-field">&nbsp;<button type="button" class="secondary-btn add-line-btn" id="add-line">＋ Añadir</button></div></div><div class="line-list" id="line-list"></div></div><div class="modal-actions"><button type="button" class="secondary-btn" data-action="close-modal">Cancelar</button><button class="primary-btn" type="submit">${isEdit ? 'Guardar' : 'Crear borrador'}</button></div></form>`);

  function renderLines() { let t = 0; $('#line-list').innerHTML = lines.map((l, i) => { const s = (parseFloat(l.quantity) || 0) * (parseFloat(l.unitCost) || 0); t += s; return `<div class="line-chip"><span>${esc(l.description)} · ${dec(l.quantity)} ${esc(l.unit)}</span><b>${money(s)}</b><button type="button" class="remove-line" data-idx="${i}">×</button></div>`; }).join(''); $('#line-total').textContent = `Total: ${money(t.toFixed(2))}`; $$('.remove-line', $('#line-list')).forEach(b => b.addEventListener('click', () => { lines.splice(+b.dataset.idx, 1); renderLines(); })); }
  renderLines();
  $('#add-line').addEventListener('click', () => { const s = $('#f-mat'), o = s.options[s.selectedIndex], q = parseFloat($('#f-qty').value); if (!q || q <= 0) { toast('Cantidad mayor que cero.', 'error'); return; } lines.push({ materialId: +s.value, description: o.textContent.split(' (')[0], quantity: String(q), unit: o.dataset.unit, unitCost: o.dataset.price }); $('#f-qty').value = ''; renderLines(); });
  $('#ff').addEventListener('submit', async e => { e.preventDefault(); if (!lines.length) { toast('Añada al menos un componente.', 'error'); return; } const payload = { product_id: isEdit ? ficha.product_id : +$('#f-prod').value, valid_from: $('#f-date').value, observations: $('#f-notes').value, items: lines.map(l => ({ material_id: l.materialId, quantity: l.quantity })) }; try { if (isEdit) await api(`/api/fichas/${ficha.id}`, { method: 'PUT', body: JSON.stringify(payload) }); else await api('/api/fichas', { method: 'POST', body: JSON.stringify(payload) }); closeModal(); await refreshData(true); toast(isEdit ? 'Ficha actualizada.' : 'Ficha creada como borrador.', 'success'); } catch (err) { toast(err.message, 'error'); } });
}

/* ── Detail views ── */
async function openFichaDetail(id) {
  try {
    const f = await api(`/api/fichas/${id}`);
    const lines = f.items.map(i => `<tr><td>${esc(i.description)}</td><td>${dec(i.quantity)} ${esc(i.unit)}</td><td class="amount">${money(i.unit_cost)}</td><td class="amount">${money(i.subtotal)}</td></tr>`).join('');
    showModal(`Ficha de Costo · v${f.version}`, `${f.product_code} · ${f.product_name}`, `<div class="detail-grid"><div class="detail-box"><span>Producto</span><b>${esc(f.product_name)} · ${esc(f.category)}</b></div><div class="detail-box"><span>Versión / estado</span><b>v${f.version} · ${esc(f.status)}</b></div><div class="detail-box"><span>Vigente desde</span><b>${dateLabel(f.valid_from)}</b></div><div class="detail-box"><span>Costo total</span><b>${money(f.total_cost)}</b></div></div><div class="table-wrap"><table><thead><tr><th>Componente</th><th>Cantidad</th><th>Precio</th><th>Subtotal</th></tr></thead><tbody>${lines}</tbody></table></div>${f.observations ? `<div class="small-note">${esc(f.observations)}</div>` : ''}<div class="modal-actions"><button class="secondary-btn" data-action="close-modal">Cerrar</button>${f.status === 'Borrador' ? `<button class="secondary-btn" data-action="edit-ficha" data-id="${f.id}">Editar</button><button class="primary-btn" data-action="approve-ficha" data-id="${f.id}">Aprobar ficha</button>` : `<button class="primary-btn" data-action="generate-control" data-id="${f.id}">＋ Generar Control IPV</button>`}</div>`);
  } catch (e) { toast(e.message, 'error'); }
}
async function approveFicha(id) { try { await api(`/api/fichas/${id}/approve`, { method: 'POST', body: '{}' }); closeModal(); await refreshData(true); toast('Ficha aprobada.', 'success'); } catch (e) { toast(e.message, 'error'); } }
async function openGenerateControl(id) {
  const f = await api(`/api/fichas/${id}`);
  showModal('Generar Control de IPV', 'Vinculado a la versión exacta de esta ficha.', `<form id="cf"><div class="detail-grid"><div class="detail-box"><span>Producto</span><b>${esc(f.product_name)} · v${f.version}</b></div><div class="detail-box"><span>Total</span><b>${money(f.total_cost)}</b></div></div><div class="form-field"><label>Período *</label><input id="c-period" type="month" required value="${currentMonth()}"><span class="form-hint">Se creará una instantánea de las líneas y el total.</span></div><div class="form-field"><label>Observaciones</label><textarea id="c-notes"></textarea></div><div class="modal-actions"><button type="button" class="secondary-btn" data-action="close-modal">Cancelar</button><button class="primary-btn" type="submit">Crear Control IPV</button></div></form>`);
  $('#cf').addEventListener('submit', async e => { e.preventDefault(); try { await api('/api/controls', { method: 'POST', body: JSON.stringify({ ficha_id: id, period: $('#c-period').value, notes: $('#c-notes').value }) }); closeModal(); await refreshData(true); setView('controls'); toast('Control IPV creado.', 'success'); } catch (err) { toast(err.message, 'error'); } });
}
async function openControlDetail(id) {
  try {
    const c = await api(`/api/controls/${id}`);
    const lines = c.items.map(i => `<tr><td>${esc(i.description)}</td><td>${dec(i.quantity)} ${esc(i.unit)}</td><td class="amount">${money(i.unit_cost)}</td><td class="amount">${money(i.subtotal)}</td></tr>`).join('');
    const msgs = (c.validation_messages || []).map(m => `<div class="small-note" style="margin-top:8px;color:${m.type === 'error' ? 'var(--red)' : m.type === 'success' ? 'var(--green)' : 'var(--text-3)'}">${m.type === 'error' ? '⚠ ' : m.type === 'success' ? '✓ ' : '• '}${esc(m.text)}</div>`).join('');
    showModal(`Control IPV · ${c.code}`, `${c.product_code} · ${c.product_name}`, `<div class="detail-grid"><div class="detail-box"><span>Producto / ficha</span><b>${esc(c.product_name)} · v${c.ficha_version}</b></div><div class="detail-box"><span>Período / estado</span><b>${esc(c.period)} · ${esc(c.status)}</b></div><div class="detail-box"><span>Total</span><b>${money(c.snapshot_total)}</b></div><div class="detail-box"><span>Verificado</span><b>${c.checked_at ? money(c.checked_total) : 'Sin validar'}</b></div></div><div class="table-wrap"><table><thead><tr><th>Componente</th><th>Cantidad</th><th>Precio</th><th>Subtotal</th></tr></thead><tbody>${lines}</tbody></table></div>${msgs}<div class="modal-actions"><button class="secondary-btn" data-action="close-modal">Cerrar</button>${c.status !== 'Validado' ? `<button class="primary-btn" data-action="validate-control" data-id="${c.id}">Ejecutar validación</button>` : ''}</div>`);
  } catch (e) { toast(e.message, 'error'); }
}
async function validateControl(id) { try { const c = await api(`/api/controls/${id}/validate`, { method: 'POST', body: '{}' }); await refreshData(true); openControlDetail(c.id); toast(c.status === 'Validado' ? 'Control validado.' : 'Se encontraron observaciones.', c.status === 'Validado' ? 'success' : 'error'); } catch (e) { toast(e.message, 'error'); } }

/* ── CSV Export ── */
function exportCsv(type) {
  let rows = [], fn = 'export.csv';
  if (type === 'products') { fn = 'productos.csv'; rows = [['Código', 'Nombre', 'Categoría', 'Unidad', 'Estado'], ...state.products.map(p => [p.code, p.name, p.category, p.unit, p.active ? 'Activo' : 'Inactivo'])]; }
  else if (type === 'materials') { fn = 'valores-ipv.csv'; rows = [['Código', 'Nombre', 'Unidad', 'Precio', 'Moneda', 'Fuente', 'Vigencia', 'Estado'], ...state.materials.map(m => [m.code, m.name, m.unit, m.unit_price, m.currency, m.source || m.supplier, m.effective_from, m.status])]; }
  else if (type === 'fichas') { fn = 'fichas.csv'; rows = [['Producto', 'Código', 'Categoría', 'Versión', 'Vigente', 'Total', 'Estado'], ...state.fichas.map(f => [f.product_name, f.product_code, f.category, f.version, f.valid_from, f.total_cost, f.status])]; }
  else { fn = 'controles.csv'; rows = [['Control', 'Producto', 'Código', 'Período', 'Ficha', 'Total', 'Estado'], ...state.controls.map(c => [c.code, c.product_name, c.product_code, c.period, c.ficha_version, c.snapshot_total, c.status])]; }
  const csv = '\ufeff' + rows.map(r => r.map(c => `"${String(c ?? '').replaceAll('"', '""')}"`).join(';')).join('\r\n');
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' })); const a = document.createElement('a'); a.href = url; a.download = fn; a.click(); URL.revokeObjectURL(url); toast('CSV exportado.', 'success');
}

/* ── Global Search ── */
function globalSearch(query) {
  if (!query || query.length < 2) { $('#search-overlay').hidden = true; return; }
  const q = query.toLowerCase();
  const results = [
    ...state.products.filter(p => `${p.name} ${p.code}`.toLowerCase().includes(q)).slice(0, 3).map(p => ({ type: 'Producto', name: p.name, sub: p.code, action: 'view-product', id: p.id })),
    ...state.fichas.filter(f => `${f.product_name} ${f.product_code}`.toLowerCase().includes(q)).slice(0, 3).map(f => ({ type: 'Ficha', name: `${f.product_name} v${f.version}`, sub: `${f.status} · ${money(f.total_cost)}`, action: 'view-ficha', id: f.id })),
    ...state.materials.filter(m => `${m.name} ${m.code}`.toLowerCase().includes(q)).slice(0, 3).map(m => ({ type: 'Valor', name: m.name, sub: `${money(m.unit_price)} / ${m.unit}`, action: '', id: 0 })),
    ...state.controls.filter(c => `${c.code} ${c.product_name}`.toLowerCase().includes(q)).slice(0, 3).map(c => ({ type: 'Control', name: c.code, sub: `${c.product_name} · ${c.status}`, action: 'view-control', id: c.id })),
  ];
  const overlay = $('#search-overlay');
  const container = $('#search-results');
  if (!results.length) { container.innerHTML = '<div style="padding:24px;text-align:center;color:var(--text-3)">Sin resultados</div>'; }
  else { container.innerHTML = results.map(r => `<div class="search-result-item" data-action="${r.action}" data-id="${r.id}" style="padding:12px 16px;cursor:pointer;border-radius:var(--radius-sm);transition:background .15s;display:flex;justify-content:space-between;align-items:center"><div><b style="font-size:12px;color:var(--text)">${esc(r.name)}</b><div style="font-size:10px;color:var(--text-3)">${esc(r.sub)}</div></div><span class="status" style="font-size:8px">${esc(r.type)}</span></div>`).join(''); }
  overlay.hidden = false;
}

/* ── Event Delegation ── */
modalLayer.addEventListener('click', async e => {
  const b = e.target.closest('[data-action]'); if (!b) return;
  const { action, id } = b.dataset;
  try { if (action === 'close-modal') closeModal(); else if (action === 'approve-ficha') approveFicha(id); else if (action === 'edit-ficha') { const f = await api(`/api/fichas/${id}`); openFichaModal(f); } else if (action === 'generate-control') openGenerateControl(id); else if (action === 'validate-control') validateControl(id); } catch (err) { toast(err.message, 'error'); }
});

content.addEventListener('click', async e => {
  const nav = e.target.closest('[data-view]'); if (nav) { setView(nav.dataset.view); return; }
  const b = e.target.closest('[data-action]'); if (!b) return;
  const { action, id } = b.dataset;
  try {
    if (action === 'refresh') refreshData();
    else if (action === 'create-product') openProductModal();
    else if (action === 'create-material') openMaterialModal();
    else if (action === 'create-ficha') openFichaModal();
    else if (action === 'view-ficha') openFichaDetail(id);
    else if (action === 'approve-ficha') approveFicha(id);
    else if (action === 'generate-control') openGenerateControl(id);
    else if (action === 'view-control') openControlDetail(id);
    else if (action === 'validate-control') validateControl(id);
    else if (action === 'export-products') exportCsv('products');
    else if (action === 'export-materials') exportCsv('materials');
    else if (action === 'export-fichas') exportCsv('fichas');
    else if (action === 'export-controls') exportCsv('controls');
    else if (action === 'close-modal') closeModal();
    else if (action === 'deactivate-product') { if (confirm('¿Desactivar este producto?')) { await api(`/api/products/${id}`, { method: 'DELETE' }); await refreshData(true); toast('Producto desactivado.'); } }
  } catch (err) { toast(err.message, 'error'); }
});

// Search overlay clicks
$('#search-overlay').addEventListener('click', async e => {
  const item = e.target.closest('[data-action]');
  if (item && item.dataset.action) { $('#search-overlay').hidden = true; $('#global-search').value = ''; const { action, id } = item.dataset; if (action === 'view-ficha') openFichaDetail(id); else if (action === 'view-control') openControlDetail(id); }
  else if (e.target === $('#search-overlay')) { $('#search-overlay').hidden = true; $('#global-search').value = ''; }
});

$$('[data-view]').forEach(el => el.addEventListener('click', () => setView(el.dataset.view)));
$('#refresh-btn').addEventListener('click', () => refreshData());
$('#about-btn').addEventListener('click', () => openAbout());
$('#theme-toggle')?.addEventListener('click', toggleTheme);
$('#mobile-menu-btn')?.addEventListener('click', () => { $('#sidebar').classList.toggle('open'); $('#sidebar-overlay').classList.toggle('active'); });
$('#sidebar-overlay')?.addEventListener('click', () => { $('#sidebar').classList.remove('open'); $('#sidebar-overlay').classList.remove('active'); });

// Global search input
$('#global-search')?.addEventListener('input', e => globalSearch(e.target.value));
$('#global-search')?.addEventListener('focus', e => { if (e.target.value.length >= 2) globalSearch(e.target.value); });

/* ── Keyboard Shortcuts ── */
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') { if (!modalLayer.hidden) closeModal(); $('#search-overlay').hidden = true; }
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') { e.preventDefault(); $('#global-search')?.focus(); }
  if (e.key === 'F5') { e.preventDefault(); refreshData(); }
  if (!e.ctrlKey && !e.metaKey && !e.altKey && modalLayer.hidden && $('#search-overlay').hidden) {
    if (e.key === '1') setView('dashboard');
    else if (e.key === '2') setView('products');
    else if (e.key === '3') setView('materials');
    else if (e.key === '4') setView('fichas');
    else if (e.key === '5') setView('controls');
  }
});

/* ── Init ── */
refreshData();

/* ==========================================================================
   ENHANCED FEATURES — Skeleton, Confirm, Auto-refresh, Charts, Timeline
   ========================================================================== */

/* ── Skeleton Loading ── */
function showSkeleton() {
  content.innerHTML = `
    <div class="page-heading animate-fade"><div><div class="eyebrow skeleton skeleton-text short" style="width:100px;height:12px"></div><div class="skeleton skeleton-text" style="width:250px;height:28px"></div><div class="skeleton skeleton-text medium" style="height:14px;margin-top:8px"></div></div></div>
    <div class="skeleton-grid">${Array(4).fill('<div class="skeleton skeleton-card"></div>').join('')}</div>
    <div class="dashboard-grid"><div class="skeleton skeleton-panel"></div><div class="skeleton skeleton-panel" style="height:240px"></div></div>`;
}

/* ── Confirmation Dialog ── */
function confirm2(title, message, type = 'warning') {
  return new Promise(resolve => {
    const overlay = document.createElement('div');
    overlay.className = 'confirm-overlay';
    const icons = { warning: '⚠', danger: '⛔', info: 'ℹ' };
    overlay.innerHTML = `<div class="confirm-card">
      <div class="confirm-icon ${type}">${icons[type] || '⚠'}</div>
      <h3>${esc(title)}</h3>
      <p>${esc(message)}</p>
      <div class="confirm-actions">
        <button class="secondary-btn" data-r="0">Cancelar</button>
        <button class="${type === 'danger' ? 'danger-btn' : 'primary-btn'}" data-r="1">${type === 'danger' ? 'Eliminar' : 'Confirmar'}</button>
      </div>
    </div>`;
    document.body.appendChild(overlay);
    overlay.addEventListener('click', e => {
      const btn = e.target.closest('[data-r]');
      if (btn || e.target === overlay) { overlay.remove(); resolve(btn ? btn.dataset.r === '1' : false); }
    });
    // Focus the cancel button for accessibility
    overlay.querySelector('[data-r="0"]').focus();
  });
}

/* ── Auto-refresh ── */
let _autoRefreshTimer = null;
let _autoRefreshActive = false;
function toggleAutoRefresh() {
  _autoRefreshActive = !_autoRefreshActive;
  const pill = $('#auto-refresh-pill');
  if (pill) pill.classList.toggle('active', _autoRefreshActive);
  if (_autoRefreshTimer) { clearInterval(_autoRefreshTimer); _autoRefreshTimer = null; }
  if (_autoRefreshActive) {
    _autoRefreshTimer = setInterval(() => refreshData(true), 30000); // every 30s
    toast('Auto-actualización activada (30s)', 'success');
  } else {
    toast('Auto-actualización desactivada');
  }
}
// Sin manejadores en línea (CSP estricta: script-src 'self')
$('#auto-refresh-pill')?.addEventListener('click', toggleAutoRefresh);
$('#auto-refresh-pill')?.addEventListener('keydown', e => {
  if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleAutoRefresh(); }
});

/* ── Enhanced Global Search with API ── */
let _searchDebounce = null;
function globalSearchAPI(query) {
  if (_searchDebounce) clearTimeout(_searchDebounce);
  if (!query || query.length < 2) { $('#search-overlay').hidden = true; return; }
  _searchDebounce = setTimeout(async () => {
    try {
      const results = await api(`/api/search?q=${encodeURIComponent(query)}&limit=15`);
      const overlay = $('#search-overlay');
      const container = $('#search-results');
      if (!results.length) {
        container.innerHTML = `<div style="padding:32px;text-align:center;color:var(--text-3)"><div style="font-size:28px;margin-bottom:8px">⌕</div><b style="display:block;font-size:13px;color:var(--text)">Sin resultados</b><p style="font-size:11px;margin-top:4px">No se encontraron coincidencias para "${esc(query)}"</p></div>`;
      } else {
        const typeLabels = { product: 'Producto', material: 'Valor', ficha: 'Ficha', control: 'Control' };
        const typeActions = { product: '', material: '', ficha: 'view-ficha', control: 'view-control' };
        container.innerHTML = `<div style="padding:8px 12px;font-size:9px;color:var(--text-4);text-transform:uppercase;letter-spacing:1px;font-weight:700">${results.length} resultados</div>` +
          results.map(r => {
            const name = r.name || r.code || '';
            const sub = r.category || r.unit || (r.version ? `v${r.version}` : '') || r.period || '';
            const status = r.status ? ` · ${r.status}` : '';
            return `<div class="search-result-item" data-action="${typeActions[r.type] || ''}" data-id="${r.id}">
              <div><b>${esc(name)}</b><small>${esc(sub)}${esc(status)}</small></div>
              <span class="status" style="font-size:8px">${esc(typeLabels[r.type] || r.type)}</span>
            </div>`;
          }).join('');
      }
      overlay.hidden = false;
    } catch (e) { /* silent */ }
  }, 250);
}

/* ── Activity Timeline ── */
function renderTimeline(activity) {
  if (!activity || !activity.length) return '<p style="color:var(--text-4);font-size:11px;text-align:center;padding:20px">Sin actividad reciente</p>';
  const icons = { ficha: '▤', control: '✓', product: '▦' };
  return `<div class="timeline">${activity.slice(0, 6).map(a => `
    <div class="timeline-item">
      <div class="timeline-dot ${a.type}">${icons[a.type] || '•'}</div>
      <div class="timeline-content"><b>${esc(a.action)}</b><small>${dateLabel(a.timestamp)}</small></div>
    </div>`).join('')}</div>`;
}

/* ── Progress Ring ── */
function progressRing(value, max, size = 80, color = 'var(--primary-light)') {
  const pct = max > 0 ? Math.min(100, Math.round(value / max * 100)) : 0;
  const r = (size - 8) / 2;
  const circ = 2 * Math.PI * r;
  const offset = circ - (pct / 100) * circ;
  return `<div class="progress-ring" style="width:${size}px;height:${size}px">
    <svg width="${size}" height="${size}"><circle class="track" cx="${size/2}" cy="${size/2}" r="${r}"/><circle class="fill" cx="${size/2}" cy="${size/2}" r="${r}" stroke="${color}" stroke-dasharray="${circ}" stroke-dashoffset="${offset}"/></svg>
    <span class="value">${pct}%</span></div>`;
}

/* ── Inline Form Validation ── */
function validateField(input, rules = {}) {
  const field = input.closest('.form-field');
  const val = input.value.trim();
  let error = '';
  if (rules.required && !val) error = 'Este campo es obligatorio.';
  else if (rules.minLength && val.length < rules.minLength) error = `Mínimo ${rules.minLength} caracteres.`;
  else if (rules.pattern && !rules.pattern.test(val)) error = rules.patternMsg || 'Formato no válido.';
  else if (rules.min !== undefined && Number(val) < rules.min) error = `Valor mínimo: ${rules.min}`;
  // Remove old error
  field.classList.remove('error', 'success');
  const old = field.querySelector('.field-error');
  if (old) old.remove();
  if (error) {
    field.classList.add('error');
    const errEl = document.createElement('div');
    errEl.className = 'field-error';
    errEl.textContent = error;
    field.appendChild(errEl);
    return false;
  } else if (val) {
    field.classList.add('success');
  }
  return true;
}

/* ── Animated Number Counter ── */
function animateValue(el, start, end, duration = 600) {
  const range = end - start;
  const startTime = performance.now();
  function step(now) {
    const elapsed = now - startTime;
    const progress = Math.min(elapsed / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
    el.textContent = Math.round(start + range * eased);
    if (progress < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

/* ── Override global search to use API ── */
(function() {
  const gs = $('#global-search');
  if (gs) {
    gs.removeEventListener('input', globalSearch);
    gs.addEventListener('input', e => globalSearchAPI(e.target.value));
    gs.addEventListener('focus', e => { if (e.target.value.length >= 2) globalSearchAPI(e.target.value); });
  }
})();

/* ── Override deactivate to use confirm dialog ── */
(function() {
  const origClick = content.onclick;
  content.addEventListener('click', async e => {
    const btn = e.target.closest('[data-action="deactivate-product"]');
    if (btn) {
      e.stopImmediatePropagation();
      const ok = await confirm2('Desactivar producto', 'El producto se marcará como inactivo. Los documentos históricos se conservarán.', 'warning');
      if (ok) {
        try {
          await api(`/api/products/${btn.dataset.id}`, { method: 'DELETE' });
          await refreshData(true);
          toast('Producto desactivado.', 'success');
        } catch (err) { toast(err.message, 'error'); }
      }
    }
  }, true);
})();

/* ── Keyboard shortcut overlay ── */
function showShortcutsHelp() {
  showModal('Atajos de teclado', 'Navega más rápido por el sistema', `
    <div style="display:grid;gap:10px">
      <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)"><span style="font-size:12px">Ir a Resumen</span><div class="kbd-hint"><kbd>1</kbd></div></div>
      <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)"><span style="font-size:12px">Ir a Productos</span><div class="kbd-hint"><kbd>2</kbd></div></div>
      <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)"><span style="font-size:12px">Ir a Valores IPV</span><div class="kbd-hint"><kbd>3</kbd></div></div>
      <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)"><span style="font-size:12px">Ir a Fichas</span><div class="kbd-hint"><kbd>4</kbd></div></div>
      <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)"><span style="font-size:12px">Ir a Controles</span><div class="kbd-hint"><kbd>5</kbd></div></div>
      <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)"><span style="font-size:12px">Búsqueda global</span><div class="kbd-hint"><kbd>Ctrl</kbd>+<kbd>K</kbd></div></div>
      <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)"><span style="font-size:12px">Actualizar datos</span><div class="kbd-hint"><kbd>F5</kbd></div></div>
      <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)"><span style="font-size:12px">Cerrar modal/búsqueda</span><div class="kbd-hint"><kbd>Esc</kbd></div></div>
      <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)"><span style="font-size:12px">Paleta de comandos</span><div class="kbd-hint"><kbd>Ctrl</kbd><kbd>Shift</kbd><kbd>P</kbd></div></div>
      <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)"><span style="font-size:12px">Deshacer / Rehacer</span><div class="kbd-hint"><kbd>Ctrl</kbd><kbd>Z</kbd> · <kbd>Ctrl</kbd><kbd>Shift</kbd><kbd>Z</kbd></div></div>
      <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)"><span style="font-size:12px">Accesibilidad</span><div class="kbd-hint"><kbd>Alt</kbd><kbd>Shift</kbd><kbd>A</kbd></div></div>
      <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)"><span style="font-size:12px">Filas de tabla</span><div class="kbd-hint"><kbd>↑</kbd><kbd>↓</kbd> · <kbd>Enter</kbd> abre</div></div>
      <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0"><span style="font-size:12px">Mostrar esta ayuda</span><div class="kbd-hint"><kbd>?</kbd></div></div>
    </div>
    <div class="modal-actions"><button class="primary-btn" data-action="close-modal">Entendido</button></div>`);
}

// Add '?' shortcut
document.addEventListener('keydown', e => {
  if (e.key === '?' && !e.ctrlKey && !e.metaKey && modalLayer.hidden && !e.target.closest('input,textarea,select')) {
    e.preventDefault();
    showShortcutsHelp();
  }
});

/* ==========================================================================
   ULTRA FEATURES — Confetti, Charts, Statistics, Advanced Interactions
   ========================================================================== */

/* ── Confetti Celebration ── */
function triggerConfetti(duration = 3000) {
  const container = document.createElement('div');
  container.className = 'confetti-container';
  document.body.appendChild(container);
  
  const colors = ['var(--accent)', 'var(--primary-light)', 'var(--blue)', 'var(--purple)', 'var(--orange)'];
  const confettiCount = 100;
  
  for (let i = 0; i < confettiCount; i++) {
    const confetti = document.createElement('div');
    confetti.className = 'confetti';
    confetti.style.left = Math.random() * 100 + '%';
    confetti.style.animationDelay = Math.random() * 2 + 's';
    confetti.style.background = colors[Math.floor(Math.random() * colors.length)];
    confetti.style.width = (Math.random() * 10 + 5) + 'px';
    confetti.style.height = confetti.style.width;
    confetti.style.borderRadius = Math.random() > 0.5 ? '50%' : '0';
    container.appendChild(confetti);
  }
  
  setTimeout(() => container.remove(), duration);
}

/* ── Statistics Dashboard ── */
async function loadStatistics() {
  try {
    const stats = await api('/api/statistics');
    return stats;
  } catch (e) {
    console.error('Error loading statistics:', e);
    return null;
  }
}

/* ── Render Bar Chart ── */
function renderBarChart(data, labels, maxValue = null) {
  if (!data || !data.length) return '<p style="color:var(--text-4)">Sin datos</p>';
  const max = maxValue || Math.max(...data);
  const bars = data.map((val, i) => {
    const height = (val / max * 100);
    const label = labels[i] || '';
    return `<div style="display:flex;flex-direction:column;align-items:center;gap:4px;flex:1">
      <div style="width:100%;height:120px;display:flex;align-items:flex-end;justify-content:center">
        <div style="width:80%;height:${height}%;background:var(--gradient-success);border-radius:4px 4px 0 0;transition:height 0.6s ease;min-height:4px" title="${val}"></div>
      </div>
      <div style="font-size:10px;color:var(--text-3);text-align:center;max-width:60px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(label)}</div>
      <div style="font-size:11px;font-weight:600;color:var(--text)">${val}</div>
    </div>`;
  }).join('');
  return `<div style="display:flex;gap:8px;align-items:flex-end;padding:16px 8px">${bars}</div>`;
}

/* ── Render Donut Chart ── */
function renderDonutChart(data, size = 120) {
  if (!data || !data.length) return '';
  const total = data.reduce((sum, item) => sum + item.value, 0);
  if (total === 0) return '';
  
  let cumulativePercent = 0;
  const colors = ['var(--green)', 'var(--blue)', 'var(--orange)', 'var(--purple)', 'var(--red)'];
  const segments = data.map((item, i) => {
    const percent = item.value / total;
    const startAngle = cumulativePercent * 360;
    const endAngle = (cumulativePercent + percent) * 360;
    cumulativePercent += percent;
    
    const startRad = (startAngle - 90) * Math.PI / 180;
    const endRad = (endAngle - 90) * Math.PI / 180;
    const largeArc = percent > 0.5 ? 1 : 0;
    
    const x1 = 50 + 40 * Math.cos(startRad);
    const y1 = 50 + 40 * Math.sin(startRad);
    const x2 = 50 + 40 * Math.cos(endRad);
    const y2 = 50 + 40 * Math.sin(endRad);
    
    return `<path d="M 50 50 L ${x1} ${y1} A 40 40 0 ${largeArc} 1 ${x2} ${y2} Z" fill="${colors[i % colors.length]}" opacity="0.8"/>`;
  }).join('');
  
  return `<svg viewBox="0 0 100 100" width="${size}" height="${size}" style="transform:rotate(-90deg)">
    ${segments}
    <circle cx="50" cy="50" r="25" fill="var(--surface)"/>
  </svg>
  <div style="display:flex;flex-direction:column;gap:6px;margin-top:12px">
    ${data.map((item, i) => `<div style="display:flex;align-items:center;gap:8px;font-size:11px">
      <div style="width:12px;height:12px;border-radius:3px;background:${colors[i % colors.length]}"></div>
      <span style="color:var(--text-2)">${esc(item.label)}</span>
      <span style="margin-left:auto;font-weight:600;color:var(--text)">${item.value}</span>
    </div>`).join('')}
  </div>`;
}

/* ── Render Statistics Panel ── */
async function renderStatisticsPanel() {
  const stats = await loadStatistics();
  if (!stats) return '<div class="empty-state"><p>No se pudieron cargar las estadísticas</p></div>';
  
  const monthlyData = (stats.monthly_trend || []).slice(0, 6).reverse();
  const monthlyValues = monthlyData.map(m => m.count);
  const monthlyLabels = monthlyData.map(m => m.month.split('-')[1]);
  
  const statusData = (stats.status_distribution || []).map(s => ({
    label: s.status,
    value: s.count
  }));
  
  return `
    <div class="dashboard-grid" style="grid-template-columns:1fr 1fr;gap:20px">
      <section class="panel">
        <div class="panel-heading">
          <div>
            <h2 class="panel-title">Tendencia Mensual</h2>
            <p class="panel-subtitle">Fichas creadas en los últimos 6 meses</p>
          </div>
        </div>
        ${renderBarChart(monthlyValues, monthlyLabels)}
      </section>
      <section class="panel">
        <div class="panel-heading">
          <div>
            <h2 class="panel-title">Distribución por Estado</h2>
            <p class="panel-subtitle">Estado actual de las fichas</p>
          </div>
        </div>
        <div style="display:flex;justify-content:center;padding:20px">
          ${renderDonutChart(statusData)}
        </div>
      </section>
    </div>
    <section class="panel" style="margin-top:20px">
      <div class="panel-heading">
        <div>
          <h2 class="panel-title">Productos Más Costosos</h2>
          <p class="panel-subtitle">Top 5 por costo total</p>
        </div>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Producto</th>
              <th>Código</th>
              <th>Versión</th>
              <th style="text-align:right">Costo Total</th>
            </tr>
          </thead>
          <tbody>
            ${(stats.top_expensive || []).map(p => `
              <tr>
                <td>${esc(p.name)}</td>
                <td><code style="background:var(--surface-3);padding:2px 6px;border-radius:4px;font-size:10px">${esc(p.code)}</code></td>
                <td>v${p.version}</td>
                <td class="amount" style="text-align:right">${money(p.total_cost)}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </section>
  `;
}

/* ── Floating Action Button ── */
function addFAB() {
  if ($('#fab-main')) return;
  const fab = document.createElement('button');
  fab.id = 'fab-main';
  fab.className = 'fab';
  fab.innerHTML = '＋';
  fab.setAttribute('aria-label', 'Acciones rápidas');
  fab.addEventListener('click', () => {
    showModal('Acciones Rápidas', '¿Qué deseas crear?', `
      <div style="display:grid;gap:12px">
        <button class="primary-btn" data-action="quick-product" style="justify-content:flex-start;padding:16px">
          <span style="font-size:20px;margin-right:12px">▦</span>
          <div style="text-align:left">
            <div style="font-weight:600">Nuevo Producto</div>
            <div style="font-size:11px;opacity:0.8;margin-top:2px">Agregar al catálogo</div>
          </div>
        </button>
        <button class="primary-btn" data-action="quick-material" style="justify-content:flex-start;padding:16px">
          <span style="font-size:20px;margin-right:12px">◈</span>
          <div style="text-align:left">
            <div style="font-weight:600">Nuevo Valor IPV</div>
            <div style="font-size:11px;opacity:0.8;margin-top:2px">Registrar insumo o servicio</div>
          </div>
        </button>
        <button class="primary-btn" data-action="quick-ficha" style="justify-content:flex-start;padding:16px">
          <span style="font-size:20px;margin-right:12px">▤</span>
          <div style="text-align:left">
            <div style="font-weight:600">Nueva Ficha de Costo</div>
            <div style="font-size:11px;opacity:0.8;margin-top:2px">Crear documento versionado</div>
          </div>
        </button>
      </div>
      <div class="modal-actions">
        <button class="secondary-btn" data-action="close-modal">Cancelar</button>
      </div>
    `);
  });
  document.body.appendChild(fab);
}

/* ── Quick Actions Handler ── */
modalLayer.addEventListener('click', async e => {
  const btn = e.target.closest('[data-action]');
  if (!btn) return;
  const action = btn.dataset.action;
  
  if (action === 'quick-product') {
    closeModal();
    setTimeout(() => openProductModal(), 200);
  } else if (action === 'quick-material') {
    closeModal();
    setTimeout(() => openMaterialModal(), 200);
  } else if (action === 'quick-ficha') {
    closeModal();
    setTimeout(() => openFichaModal(), 200);
  }
});

/* ── Enhanced Approval with Confetti ── */
const originalApproveFicha = approveFicha;
async function approveFichaWithConfetti(id) {
  try {
    await api(`/api/fichas/${id}/approve`, { method: 'POST', body: '{}' });
    triggerConfetti();
    closeModal();
    await refreshData(true);
    toast('¡Ficha aprobada exitosamente! 🎉', 'success');
  } catch (e) {
    toast(e.message, 'error');
  }
}

/* ── Export Report ── */
async function exportReport(type) {
  try {
    const report = await api(`/api/report/${type}`);
    if (!report.data || !report.data.length) {
      toast('No hay datos para exportar', 'error');
      return;
    }
    
    const headers = Object.keys(report.data[0]);
    const csv = [
      headers.join(';'),
      ...report.data.map(row => headers.map(h => `"${String(row[h] ?? '').replaceAll('"', '""')}"`).join(';'))
    ].join('\r\n');
    
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `reporte_${type}_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    toast('Reporte exportado exitosamente', 'success');
  } catch (e) {
    toast('Error al exportar: ' + e.message, 'error');
  }
}

/* ── Keyboard Shortcut: S for Statistics ── */
document.addEventListener('keydown', e => {
  if (e.key === 's' && !e.ctrlKey && !e.metaKey && !e.altKey && 
      modalLayer.hidden && !e.target.closest('input,textarea,select')) {
    e.preventDefault();
    showStatisticsModal();
  }
});

async function showStatisticsModal() {
  showModal('Estadísticas Avanzadas', 'Análisis completo del sistema', '<div id="stats-content"><div class="typing-indicator"><span></span><span></span><span></span></div></div>');
  const content = await renderStatisticsPanel();
  $('#stats-content').innerHTML = content;
}

/* ── Initialize FAB ── */
setTimeout(addFAB, 1000);

/* ── Parallax Scroll Effect ── */
window.addEventListener('scroll', () => {
  const scrolled = window.pageYOffset;
  $$('.parallax-bg').forEach(bg => {
    bg.style.transform = `translateY(${scrolled * 0.5}px)`;
  });
});

/* ── Spotlight Effect on Mouse Move ── */
document.addEventListener('mousemove', e => {
  $$('.spotlight').forEach(el => {
    const rect = el.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    el.style.setProperty('--mouse-x', x + 'px');
    el.style.setProperty('--mouse-y', y + 'px');
  });
});
