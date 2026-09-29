'use strict';
/* ==========================================================================
   IPV · Fichas y Costos v1.0 — Aplicación web profesional
   Autor: Ing. Yosvany Hernández Quintero
   ========================================================================== */

const state = {
  view: 'dashboard', dashboard: null, matTab: 'valores',
  products: [], materials: [], fichas: [], controls: [],
  trash: [], inventory: null, license: null, categories: { materials: [], products: [] },
  search: '',
  filters: { materials: { category: '', status: '' }, products: { category: '' }, inventory: { category: '', low: false } },
};
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const content = $('#page-content');
const modalLayer = $('#modal-layer');
const APP_VERSION = '1.1.0';
const YIELD_UNITS = ['comensales', 'copas', 'vasos', 'raciones', 'porciones', 'tazas', 'botellas', 'servicios', 'unidad'];

const views = {
  dashboard: { crumb: 'Resumen' }, products: { crumb: 'Productos y servicios' },
  materials: { crumb: 'Valores del IPV' }, inventory: { crumb: 'Valores del IPV · Inventario' },
  fichas: { crumb: 'Fichas de costo' }, controls: { crumb: 'Controles de IPV' },
  trash: { crumb: 'Papelera de reciclaje' }, license: { crumb: 'Licencia' },
  creator: { crumb: 'Creador de Licencias' },
};
const viewRenderers = {
  dashboard: 'renderDashboard', products: 'renderProducts', materials: 'renderMaterials',
  inventory: 'renderInventory', fichas: 'renderFichas', controls: 'renderControls',
  trash: 'renderTrash', license: 'renderLicense', creator: 'renderCreator',
};

/* ── Sistema de Seguridad por Usuarios ─────────────────────────────────────
   Cada usuario tiene permisos por módulo (view / edit / costs). Llegan con la
   sesión desde el servidor y se usan para no dibujar apartados ni botones que
   ese usuario no puede utilizar; el servidor los vuelve a comprobar y filtra
   los datos, así que ocultar aquí es comodidad, no la única defensa.
   Sin sesión (servidor en modo abierto) se permite todo, igual que en el API. */
const VIEW_MODULE = {
  products: 'products', materials: 'materials', inventory: 'materials',
  fichas: 'fichas', controls: 'controls', trash: 'trash',
};
const MODULE_LABEL = {
  materials: 'Valores del IPV', products: 'Productos y servicios', fichas: 'Fichas de costo',
  controls: 'Controles de IPV', trash: 'Papelera de reciclaje',
};
/* Acción de pantalla → (módulo, permiso) que exige. El servidor lo comprueba igual;
   esto evita mostrar botones que terminarían en un error 403. */
const ACTION_PERMISSION = {
  'view-material': ['materials', 'view'], 'create-material': ['materials', 'edit'],
  'edit-material': ['materials', 'edit'], 'trash-material': ['materials', 'edit'],
  'stock-plus': ['materials', 'edit'], 'stock-minus': ['materials', 'edit'],
  'stock-save': ['materials', 'edit'], 'seed-demo': ['materials', 'edit'],
  'export-materials': ['materials', 'view'], 'export-inventory': ['materials', 'view'],
  'view-fichas-of-material': ['fichas', 'view'],
  'view-product': ['products', 'view'], 'create-product': ['products', 'edit'],
  'edit-product': ['products', 'edit'], 'trash-product': ['products', 'edit'],
  'export-products': ['products', 'view'],
  'view-ficha': ['fichas', 'view'], 'create-ficha': ['fichas', 'edit'],
  'edit-ficha': ['fichas', 'edit'], 'approve-ficha': ['fichas', 'edit'],
  'trash-ficha': ['fichas', 'edit'], 'export-fichas': ['fichas', 'view'],
  'create-ficha-for': ['fichas', 'edit'],
  'view-control': ['controls', 'view'], 'generate-control': ['controls', 'edit'],
  'validate-control': ['controls', 'edit'], 'trash-control': ['controls', 'edit'],
  'export-controls': ['controls', 'view'],
  'restore-trash': ['trash', 'edit'], 'purge-trash': ['trash', 'edit'], 'empty-trash': ['trash', 'edit'],
};
function canDo(module, perm) {
  const a = window.IPVAuth;
  return a && typeof a.can === 'function' ? a.can(module, perm) : true;
}
function canSee(module) { return canDo(module, 'view'); }
function canEdit(module) { return canDo(module, 'edit'); }
function canSeeCosts(module = 'materials') { return canDo(module, 'costs'); }

/* Oculta del menú (y de los accesos rápidos) los apartados sin permiso de view,
   y saca al usuario de una pantalla a la que ya no puede entrar. */
function applyPermissionNav() {
  $$('[data-view]').forEach(el => {
    const modulo = VIEW_MODULE[el.dataset.view];
    if (!modulo) return;
    const visible = canSee(modulo);
    el.style.display = visible ? '' : 'none';
    el.toggleAttribute('aria-hidden', !visible);
    el.tabIndex = visible ? 0 : -1;
  });
  if (VIEW_MODULE[state.view] && !canSee(VIEW_MODULE[state.view])) setView('dashboard');
}

/* ── Utilities ── */
function esc(v = '') { return String(v).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
/* Dinero en formato $ 3,163,138.00 CUP: $ delante, miles con coma y decimales con punto. */
const NUM_FMT = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
function money(v) { const n = Number(v || 0); return `$ ${NUM_FMT.format(Number.isFinite(n) ? n : 0)} CUP`; }
/* Importe o candado: el servidor envía null cuando el usuario no tiene permiso `costs` */
function moneyOrLock(v, module = 'materials') {
  if (v !== null && v !== undefined) return money(v);
  return canSeeCosts(module) ? money(v)
    : '<span class="lock-pill" title="Su usuario no puede ver precios ni importes">🔒 protegido</span>';
}
function dec(v, d = 3) { const n = Number(v || 0); return new Intl.NumberFormat('en-US', { maximumFractionDigits: d }).format(Number.isFinite(n) ? n : 0); }
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
  if (r.status === 402 && d.license_required && window.IPVLicense) {
    /* Dentro del Creador de Licencias no se tapa la pantalla: allí mismo se emite
       y activa la licencia de este equipo con el código de solicitud. */
    if (state.view === 'creator') toast(`🔒 Emita la licencia de este equipo con su código ${d.request_code || ''} y pulse «Activar en este equipo».`, 'info');
    else window.IPVLicense.show(null);
  }
  if (r.status === 403 && d.password_expired && window.IPVAuth?.forcePasswordChange && !retried) {
    if (await window.IPVAuth.forcePasswordChange()) return api(path, opts, true);
  }
  if (!r.ok) {
    const err = new Error(d.error || `Error ${r.status}`);
    err.status = r.status;
    err.denied = d.permission_denied || '';  // permiso denegado por el Sistema de Seguridad por Usuarios
    throw err;
  }
  return d;
}

/* ── Connection ── */
function setConn(on, label = '') {
  $('#connection-dot').className = `connection-dot ${on ? 'online' : 'offline'}`;
  $('#connection-label').textContent = label || (on ? 'Base de datos conectada' : 'Sin conexión');
}

async function refreshData(quiet = false) {
  if (!quiet) setConn(false, 'Actualizando…');
  /* Un apartado sin permiso devuelve 403: se omite y la carga sigue adelante. */
  const optional = async (path, fallback) => {
    try { return await api(path); } catch (e) { if (e.status === 403) return fallback; throw e; }
  };
  try {
    const [d, p, m, f, c, t, inv, cat] = await Promise.all([
      api('/api/dashboard'),
      optional('/api/products', []), optional('/api/materials', []), optional('/api/fichas', []),
      optional('/api/controls', []), optional('/api/trash', { items: [] }),
      optional('/api/inventory', null), optional('/api/categories', { materials: [], products: [] }),
    ]);
    Object.assign(state, { dashboard: d, products: p, materials: m, fichas: f, controls: c,
      trash: t.items || [], inventory: inv, categories: cat });
    setConn(true, 'Base de datos conectada');
    const nav = (sel, texto) => { const el = $(sel); if (el) el.textContent = texto; };
    nav('#nav-products', p.filter(x => x.active).length);
    nav('#nav-materials', canSee('materials') ? m.length : '🔒');
    nav('#nav-fichas', f.length);
    nav('#nav-trash', state.trash.length || '');
    const dot = $('#nav-pending-dot');
    if (dot) dot.style.display = c.some(x => x.status === 'Pendiente' || x.status === 'Con diferencias') ? 'block' : 'none';
    applyPermissionNav();
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
  /* «Inventario» ya no es una entrada aparte: es la segunda pestaña de Valores del IPV */
  if (v === 'inventory') { state.matTab = 'inventario'; v = 'materials'; }
  else if (v === 'materials' && state.view !== 'materials') state.matTab = 'valores';
  if (VIEW_MODULE[v] && !canSee(VIEW_MODULE[v])) {
    toast(`Su usuario no tiene permiso para abrir «${views[v].crumb}».`, 'error');
    v = 'dashboard';
  }
  state.view = v; state.search = '';
  $$('[data-view]').forEach(el => el.classList.toggle('active', el.dataset.view === v));
  const crumb = $('#crumb-current');
  if (crumb) crumb.textContent = views[v].crumb;
  $('#sidebar').classList.remove('open'); $('#sidebar-overlay').classList.remove('active');
  render();
}
function render() {
  /* El Creador de Licencias funciona aunque la API esté bloqueada por licencia (402):
     sus rutas están exentas y es donde se emite la licencia del propio equipo. */
  if (!state.dashboard && state.view !== 'creator') return;
  const fns = {
    dashboard: renderDashboard, products: renderProducts, materials: renderMaterials,
    inventory: renderInventory, fichas: renderFichas, controls: renderControls,
    trash: renderTrash, license: renderLicense, creator: renderCreator,
  };
  (fns[state.view] || renderDashboard)();
}

/* ── Helpers ── */
function heading(eye, title, desc, action = '') { return `<div class="page-heading"><div><div class="eyebrow">${eye}</div><h1>${title}</h1><p>${desc}</p></div>${action ? `<div>${action}</div>` : ''}</div>`; }
function statCard(label, value, note, icon) { return `<article class="stat-card"><div class="stat-top"><span>${label}</span><span class="stat-icon">${icon}</span></div><div class="stat-value">${value}</div><div class="stat-note">${note}</div></article>`; }
/* Tarjeta del resumen: sin permiso de acceso al módulo, muestra el candado. */
function statCardPerm(module, label, value, note, icon) {
  return canSee(module)
    ? statCard(label, value, note, icon)
    : statCard(label, '🔒', '<span style="color:var(--text-4)">Sin permiso de acceso</span>', icon);
}
function prodCell(name, code, cat) { return `<div class="product-cell"><div class="product-avatar ${catClass(cat)}">${catIcon(cat)}</div><div><span class="product-title">${esc(name)}</span><span class="product-code">${esc(code || '')}</span></div></div>`; }
function searchBox(ph = 'Buscar por nombre o código…') { return `<label class="searchbox"><span>⌕</span><input id="table-search" type="search" placeholder="${ph}" value="${esc(state.search)}" autocomplete="off"></label>`; }
function yieldBadge(qty, unit, tone = '') { return `<span class="yield-badge ${tone}" title="Rendimiento de la ficha">👥 ${esc(dec(qty))} ${esc(unit || '')}</span>`; }
function stockPill(m) {
  const low = Number(m.min_stock) > 0 && Number(m.stock) <= Number(m.min_stock);
  return `<span class="stock-pill ${low ? 'low' : 'ok'}" title="Existencias / mínimo">${esc(dec(m.stock))} ${esc(m.unit)}${low ? ' ⚠' : ''}</span>`;
}
function rowActions(kind, item) {
  const id = item.id;
  /* Sin permiso de edición del módulo solo queda el detalle (el servidor
     rechazaría igualmente cualquier cambio) */
  const modulo = { material: 'materials', product: 'products', ficha: 'fichas', control: 'controls' }[kind] || '';
  const editar = canEdit(modulo);
  return `<div class="row-actions">
    <button class="icon-btn" data-action="view-${kind}" data-id="${id}" title="Ver detalle" aria-label="Ver detalle">👁</button>
    ${editar ? `<button class="icon-btn" data-action="edit-${kind}" data-id="${id}" title="Editar" aria-label="Editar">✎</button>
    <button class="icon-btn danger" data-action="trash-${kind}" data-id="${id}" title="Mover a la papelera" aria-label="Eliminar">🗑</button>` : ''}
  </div>`;
}

/* ── Columna «Id»: numera las filas de 1 a N ──
   Va siempre delante de las demás columnas, así el último número de la lista
   dice de un vistazo cuántos ítems hay. El atributo title muestra el Id interno
   (el de la base de datos) por si hace falta para soporte. */
function idTh() { return '<th class="row-id-h" title="Número de orden del ítem">Id</th>'; }
function idTd(i, realId) {
  const t = realId === undefined || realId === null || realId === '' ? '' : ` title="Id interno: ${esc(realId)}"`;
  return `<td class="row-id"${t}>${i + 1}</td>`;
}
/* Contador de ítems para las barras de herramientas: «33 ítems» o «5 de 33 ítems». */
function countPill(shown, total, label = 'ítems') {
  const t = Number(total === undefined || total === null ? shown : total);
  const s = Number(shown);
  return `<span class="count-pill" title="Cantidad de ${label} en la lista">▤ ${s === t ? `${t} ${label}` : `${s} de ${t} ${label}`}</span>`;
}

/* ── Dashboard ── */
function renderDashboard() {
  const d = state.dashboard;
  const cats = canSee('products') ? (d.categories || []) : [];
  const max = Math.max(1, ...cats.map(c => Number(c.count)));
  const catRows = cats.length ? cats.map(c => `<div class="category-row"><span class="category-name">${esc(c.category)}</span><div class="category-track"><div class="category-fill" style="width:${Math.max(8, Number(c.count) / max * 100)}%"></div></div><span class="category-count">${c.count}</span></div>`).join('')
    : canSee('products') ? '<div class="empty-state">Sin categorías</div>'
    : '<div class="empty-state"><div class="empty-icon">🔒</div><b>Catálogo protegido</b><p>Su usuario no tiene permiso para consultar «Productos y servicios».</p></div>';

  // Cost chart
  const costData = (canSee('fichas') && canSeeCosts('fichas')) ? (d.cost_by_category || []) : [];
  const maxCost = Math.max(1, ...costData.map(c => Number(c.total || 0)));
  const chartBars = costData.length ? costData.map((c, i) => {
    const pct = Math.max(4, Number(c.total || 0) / maxCost * 100);
    const colors = ['var(--gradient-success)', 'var(--gradient-blue)', 'var(--gradient-warm)', 'linear-gradient(135deg, var(--purple), var(--blue))'];
    return `<div class="category-row"><span class="category-name">${esc(c.category)}</span><div class="category-track"><div class="category-fill" style="width:${pct}%;background:${colors[i % 4]}"></div></div><span class="category-count">${money(c.total)}</span></div>`;
  }).join('') : '';

  const verCostos = canSeeCosts();
  content.innerHTML = `
    ${heading('Visión general', 'Control de costos integral', 'Gestión centralizada de productos, valores de referencia del IPV, inventario, fichas de costo y controles de verificación.', canEdit('fichas') ? '<button class="primary-btn" data-action="create-ficha"><span class="plus">＋</span> Nueva ficha de costo</button>' : '')}
    <div class="stats-grid">
      ${statCardPerm('products', 'Productos activos', d.products, '<span class="positive">Catálogo</span> · productos y servicios', '▦')}
      ${statCardPerm('fichas', 'Fichas de costo', d.fichas, `<span class="positive">${d.approved_fichas || 0} aprobadas</span> · todas las versiones`, '▤')}
      ${statCardPerm('controls', 'Controles pendientes', d.pending_controls, d.pending_controls ? '<span style="color:var(--orange)">Requieren revisión</span>' : '<span class="positive">Todos al día</span>', '◷')}
      ${statCardPerm('materials', 'Valores del IPV', d.materials, !canSee('materials') ? ''
        : d.low_stock
          ? `<span style="color:var(--orange)">${d.low_stock} bajo mínimo</span>${verCostos ? ` · existencias ${money(d.stock_value)}` : ' · costos protegidos'}`
          : (verCostos ? `Existencias valoradas en ${money(d.stock_value)}` : 'Existencias sin importe (costos protegidos)'), '◈')}
    </div>
    <div class="dashboard-grid">
      ${canSee('fichas') ? `<section class="panel">
        <div class="panel-heading"><div><h2 class="panel-title">Fichas recientes</h2><p class="panel-subtitle">Últimos documentos modificados</p></div><button class="text-btn" data-view="fichas">Ver todas →</button></div>
        ${d.recent_fichas?.length
          ? `<div class="table-wrap"><table><thead><tr>${idTh()}<th>Producto</th><th>Rendimiento</th><th>Estado</th><th>Costo total</th><th>Actualización</th><th></th></tr></thead><tbody>${d.recent_fichas.map((f, i) => `<tr>${idTd(i, f.id)}<td>${prodCell(f.product_name, f.product_code, f.category)}</td><td>${yieldBadge(f.yield_qty, f.yield_unit)}</td><td>${stPill(f.status)}</td><td class="amount">${moneyOrLock(f.total_cost, 'fichas')}</td><td>${dateLabel(f.updated_at)}</td><td><button class="text-btn" data-action="view-ficha" data-id="${f.id}">Abrir ↗</button></td></tr>`).join('')}</tbody></table></div>`
          : `<div class="empty-state"><div class="empty-icon">▤</div><b>Empieza con una ficha</b><p>Crea la primera ficha de costo.</p>${canEdit('fichas') ? '<button class="primary-btn" data-action="create-ficha">Crear ficha</button>' : ''}</div>`}
      </section>` : lockedDashPanel('Fichas de costo', 'Su usuario no tiene permiso para consultar las fichas de costo.')}
      <section class="panel category-panel">
        <div class="panel-heading"><div><h2 class="panel-title">${canSee('products') ? 'Catálogo por categoría' : 'Accesos rápidos'}</h2><p class="panel-subtitle">${canSee('products') ? 'Productos y servicios activos' : 'Apartados disponibles para su usuario'}</p></div>${canSee('products') ? '<button class="icon-button" data-view="products" title="Abrir catálogo">↗</button>' : ''}</div>
        <div class="category-list">${catRows}</div>
        ${chartBars ? `<div style="margin-top:20px"><div class="panel-subtitle" style="margin-bottom:10px;font-weight:600;font-size:10px;color:var(--text-3)">DISTRIBUCIÓN DE COSTOS</div><div class="category-list">${chartBars}</div></div>` : ''}
        <div class="quick-grid">
          ${canEdit('materials') ? '<button class="quick-tile" data-action="create-material"><span>◈</span><b>Nuevo valor del IPV</b><small>Desde cualquier pantalla</small></button>' : ''}
          ${canSee('materials') ? `<button class="quick-tile" data-view="inventory"><span>▣</span><b>Ver inventario</b><small>${verCostos ? `${money(d.stock_value)} en existencias` : 'existencias sin costos'}</small></button>` : ''}
          ${canSee('trash') ? `<button class="quick-tile" data-view="trash"><span>🗑</span><b>Papelera</b><small>${d.trash || 0} elemento(s)</small></button>` : ''}
        </div>
        <div class="insight-card"><small>CONTROL Y TRAZABILIDAD</small><b>Una historia para cada costo.</b><p>Las fichas aprobadas y los controles conservan la versión exacta utilizada para la revisión.</p></div>
      </section>
    </div>`;
}

/* ── Products ── */
function renderProducts() {
  const q = state.search.toLowerCase();
  const cf = state.filters.products.category;
  const cats = [...new Set(state.products.map(p => p.category))].sort();
  const rows = state.products.filter(p => `${p.name} ${p.code} ${p.category}`.toLowerCase().includes(q) && (!cf || p.category === cf));
  content.innerHTML = `
    ${heading('Catálogo', 'Productos y servicios', 'Organiza los elementos que tendrán una Ficha de Costo asociada. El rendimiento indica cuántos comensales, copas o vasos salen de cada lote.', canEdit('products') ? '<button class="primary-btn" data-action="create-product"><span class="plus">＋</span> Nuevo producto</button>' : '')}
    <div class="toolbar">${searchBox()}<select class="filter-select" id="product-category"><option value="">Todas las categorías</option>${cats.map(c => `<option value="${esc(c)}" ${c === cf ? 'selected' : ''}>${esc(c)}</option>`).join('')}</select><button class="secondary-btn" data-action="export-products">⤓ Exportar CSV</button>${countPill(rows.length, state.products.length, 'productos')}</div>
    <section class="panel table-panel">${rows.length
      ? `<div class="table-wrap"><table style="min-width:980px"><thead><tr>${idTh()}<th>Producto</th><th>Categoría</th><th>Unidad</th><th>Rendimiento</th><th>Fichas</th><th>Estado</th><th style="text-align:right">Acciones</th></tr></thead><tbody>${rows.map((p, i) => {
        const yq = p.last_yield_qty || p.yield_qty || 1, yu = p.last_yield_unit || p.yield_unit || 'unidad';
        return `<tr>${idTd(i, p.id)}<td>${prodCell(p.name, p.code, p.category)}</td><td><span class="cat-pill">${esc(p.category)}</span></td><td>${esc(p.unit)}</td><td>${yieldBadge(yq, yu, p.category === 'Comidas' ? 'orange' : p.category === 'Bebidas' ? 'blue' : '')}</td><td>${p.ficha_count || 0}</td><td>${p.active ? (p.last_status ? stPill(p.last_status) : '<span class="status approved">Activo</span>') : '<span class="status">Inactivo</span>'}</td><td>${rowActions('product', p)}</td></tr>`;
      }).join('')}</tbody></table></div>`
      : `<div class="empty-state"><div class="empty-icon">▦</div><b>${q || cf ? 'Sin resultados' : 'No hay productos'}</b><p>${q || cf ? 'Ajusta los filtros.' : 'Registra el primer producto del catálogo.'}</p></div>`}</section>`;
  $('#table-search')?.addEventListener('input', e => { state.search = e.target.value; renderProducts(); });
  $('#product-category')?.addEventListener('change', e => { state.filters.products.category = e.target.value; renderProducts(); });
}

/* ── Valores del IPV · entrada única con pestañas Valores e Inventario ──────
   Antes había dos entradas separadas («Valores del IPV» e «Inventario de
   valores del IPV»); ahora son una sola con dos pestañas y un único permiso de
   módulo. El Sistema de Seguridad por Usuarios decide qué se muestra:
     · view  — abrir la entrada (sin él se oculta del menú y el API responde 403)
     · edit  — crear, editar, ajustar existencias, papelera y datos de prueba
     · costs — ver precio unitario, valor en almacén y totales en dinero
   Los permisos llegan con la sesión y el servidor filtra además los datos:
   sin `costs` los precios viajan como null, no solo se esconden en pantalla. */
function permPill(text, title) { return `<span class="perm-pill" title="${esc(title)}">🔒 ${esc(text)}</span>`; }

function lockedPanel(title, message) {
  return `<section class="panel"><div class="empty-state"><div class="empty-icon">🔒</div>
    <b>Sin permiso para ver «${esc(title)}»</b><p>${esc(message)}</p>
    <button class="secondary-btn" data-view="dashboard">← Volver al resumen</button></div></section>`;
}
/* Variante para el propio resumen: no ofrece "volver" porque ya se está ahí. */
function lockedDashPanel(title, message) {
  return `<section class="panel"><div class="empty-state"><div class="empty-icon">🔒</div>
    <b>«${esc(title)}» protegido</b><p>${esc(message)}</p></div></section>`;
}

function materialsTabs() {
  const inv = state.inventory || { items: [], totals: {} };
  const total = inv.totals.materials === undefined ? state.materials.length : inv.totals.materials;
  const low = Number(inv.totals.low_stock || 0);
  const tab = state.matTab === 'inventario' ? 'inventario' : 'valores';
  return `<div class="seg-tabs" role="tablist" aria-label="Apartados de Valores del IPV">
    <button class="seg-tab ${tab === 'valores' ? 'active' : ''}" role="tab" aria-selected="${tab === 'valores'}" data-mat-tab="valores"><span class="seg-icon">◈</span>Valores<span class="seg-count">${state.materials.length}</span></button>
    <button class="seg-tab ${tab === 'inventario' ? 'active' : ''}" role="tab" aria-selected="${tab === 'inventario'}" data-mat-tab="inventario"><span class="seg-icon">▣</span>Inventario<span class="seg-count">${total}</span>${low ? `<span class="seg-warn" title="${low} valores bajo mínimo">⚠ ${low}</span>` : ''}</button>
    ${canSeeCosts() ? '' : permPill('Costos protegidos', 'Su usuario consulta existencias y recetas, pero no precios ni importes.')}
  </div>`;
}

/* Pestaña «Valores»: referencias con precio, vigencia y estado (CRUD completo) */
function valuesBody() {
  const q = state.search.toLowerCase();
  const { category, status } = state.filters.materials;
  const cats = [...new Set(state.materials.map(m => m.category || 'Insumos'))].sort();
  const rows = state.materials.filter(m =>
    `${m.name} ${m.code} ${m.supplier} ${m.category} ${m.source}`.toLowerCase().includes(q)
    && (!category || (m.category || 'Insumos') === category)
    && (!status || m.status === status));
  const low = state.materials.filter(m => Number(m.min_stock) > 0 && Number(m.stock) <= Number(m.min_stock)).length;
  const totalValue = state.materials.reduce((s, m) => s + Number(m.stock || 0) * Number(m.unit_price || 0), 0);
  const costos = canSeeCosts(), editar = canEdit('materials'), papelera = canSee('trash');
  return `
    <div class="inv-grid">
      <div class="inv-card"><small>Valores registrados</small><b>${state.materials.length}</b><span>${cats.length} categorías</span></div>
      <div class="inv-card"><small>Valor del inventario</small><b>${costos ? money(totalValue) : '🔒'}</b><span>${costos ? 'existencias × precio' : 'sin permiso para ver costos'}</span></div>
      <div class="inv-card ${low ? 'warn' : ''}"><small>Bajo mínimo</small><b>${low}</b><span>${low ? 'requiere reposición' : 'todo en orden'}</span></div>
      <div class="inv-card"><small>En la papelera</small><b>${papelera ? state.trash.filter(t => t.kind === 'materials').length : '🔒'}</b><span>${papelera ? '<button class="text-btn" data-view="trash">Ver papelera →</button>' : 'sin permiso'}</span></div>
    </div>
    <div class="toolbar">${searchBox()}
      <select class="filter-select" id="material-category"><option value="">Todas las categorías</option>${cats.map(c => `<option value="${esc(c)}" ${c === category ? 'selected' : ''}>${esc(c)}</option>`).join('')}</select>
      <select class="filter-select" id="material-status"><option value="">Todos los estados</option><option value="Vigente" ${status === 'Vigente' ? 'selected' : ''}>Vigente</option><option value="Inactivo" ${status === 'Inactivo' ? 'selected' : ''}>Inactivo</option></select>
      <button class="secondary-btn" data-action="export-materials" title="${costos ? 'Exportar CSV' : 'Exportar CSV sin precios (su usuario no puede verlos)'}">⤓ Exportar CSV</button>${countPill(rows.length, state.materials.length, 'valores')}</div>
    <section class="panel table-panel">${rows.length
      ? `<div class="table-wrap"><table style="min-width:${costos ? 1140 : 1040}px"><thead><tr>${idTh()}<th>Valor del IPV</th><th>Categoría</th><th>Unidad</th>${costos ? '<th>Precio</th>' : ''}<th>Existencias</th><th>Mínimo</th><th>Fuente</th><th>Vigencia</th><th>Estado</th><th style="text-align:right">Acciones</th></tr></thead><tbody>${rows.map((m, i) => `<tr>${idTd(i, m.id)}<td><div class="product-cell"><div class="product-avatar" style="background:var(--orange-glow);color:var(--orange)">◈</div><div><span class="product-title">${esc(m.name)}</span><span class="product-code">${esc(m.code)}</span></div></div></td><td><span class="cat-pill">${esc(m.category || 'Insumos')}</span></td><td>${esc(m.unit)}</td>${costos ? `<td class="amount">${money(m.unit_price)}</td>` : ''}<td>${stockPill(m)}</td><td>${dec(m.min_stock)}</td><td class="category-tag">${esc(m.source || m.supplier || '—')}</td><td>${dateLabel(m.effective_from)}</td><td>${stPill(m.status)}</td><td>${rowActions('material', m)}</td></tr>`).join('')}</tbody></table></div>`
      : `<div class="empty-state"><div class="empty-icon">◈</div><b>${q || category || status ? 'Sin resultados' : 'No hay valores'}</b><p>${q || category || status ? 'Ajusta los filtros.' : 'Registra los insumos de referencia.'}</p>${editar ? '<button class="primary-btn" data-action="create-material">Crear el primero</button>' : permPill('Solo consulta', 'Su usuario no puede crear valores del IPV.')}</div>`}</section>`;
}

/* Pestaña «Inventario»: existencias, valor en almacén y recetas que usa cada insumo */
function inventoryBody() {
  const inv = state.inventory || { items: [], totals: {} };
  const q = state.search.toLowerCase();
  const { category, low } = state.filters.inventory;
  const cats = [...new Set(inv.items.map(m => m.category || 'Insumos'))].sort();
  const rows = inv.items.filter(m => `${m.name} ${m.code} ${m.category}`.toLowerCase().includes(q)
    && (!category || (m.category || 'Insumos') === category) && (!low || m.low_stock));
  const costos = canSeeCosts(), editar = canEdit('materials'), papelera = canSee('trash');
  const stepper = m => editar
    ? `<div class="stock-stepper">
          <button data-action="stock-minus" data-id="${m.id}" title="Registrar salida">−</button>
          <input type="number" step="0.01" value="${esc(m.stock)}" data-stock-input="${m.id}" aria-label="Existencias de ${esc(m.name)}">
          <button data-action="stock-plus" data-id="${m.id}" title="Registrar entrada">＋</button>
          <button class="icon-btn" data-action="stock-save" data-id="${m.id}" title="Guardar existencias">✓</button>
        </div>`
    : `<span class="stock-readonly" title="Su usuario no puede mover existencias">${esc(dec(m.stock))} ${esc(m.unit)}</span>`;
  return `
    <div class="inv-grid">
      <div class="inv-card"><small>Valores con control</small><b>${inv.totals.materials || 0}</b><span>${inv.totals.categories || 0} categorías</span></div>
      <div class="inv-card"><small>Valor total del inventario</small><b>${costos ? money(inv.totals.stock_value) : '🔒'}</b><span>${costos ? 'existencias × precio unitario' : 'sin permiso para ver costos'}</span></div>
      <div class="inv-card ${inv.totals.low_stock ? 'warn' : ''}"><small>Bajo mínimo</small><b>${inv.totals.low_stock || 0}</b><span>${inv.totals.low_stock ? 'necesitan reposición' : 'nada que reponer'}</span></div>
      <div class="inv-card"><small>En la papelera</small><b>${papelera ? state.trash.filter(t => t.kind === 'materials').length : '🔒'}</b><span>${papelera ? '<button class="text-btn" data-view="trash">Recuperar →</button>' : 'sin permiso'}</span></div>
    </div>
    <div class="toolbar">${searchBox('Buscar en el inventario…')}
      <select class="filter-select" id="inv-category"><option value="">Todas las categorías</option>${cats.map(c => `<option value="${esc(c)}" ${c === category ? 'selected' : ''}>${esc(c)}</option>`).join('')}</select>
      <label class="check-inline"><input type="checkbox" id="inv-low" ${low ? 'checked' : ''}> Solo bajo mínimo</label>
      <button class="secondary-btn" data-action="export-inventory" title="${costos ? 'Exportar CSV' : 'Exportar CSV sin precios (su usuario no puede verlos)'}">⤓ Exportar CSV</button>${countPill(rows.length, inv.items.length, 'ítems')}</div>
    <section class="panel table-panel">${rows.length
      ? `<div class="table-wrap"><table style="min-width:${costos ? 1180 : 1000}px"><thead><tr>${idTh()}<th>Valor</th><th>Categoría</th><th>Existencias</th><th>Mínimo</th>${costos ? '<th>Precio</th><th>Valor total</th>' : ''}<th>Entradas / salidas</th><th>Se usa en</th><th style="text-align:right">Acciones</th></tr></thead><tbody>${rows.map((m, i) => `<tr>${idTd(i, m.id)}
        <td><div class="product-cell"><div class="product-avatar" style="background:var(--orange-glow);color:var(--orange)">◈</div><div><span class="product-title">${esc(m.name)}</span><span class="product-code">${esc(m.code)}</span></div></div></td>
        <td><span class="cat-pill">${esc(m.category || 'Insumos')}</span></td>
        <td>${stockPill(m)}</td><td>${dec(m.min_stock)} ${esc(m.unit)}</td>
        ${costos ? `<td class="amount">${money(m.unit_price)}</td><td class="amount">${money(m.stock_value)}</td>` : ''}
        <td>${stepper(m)}</td>
        <td>${m.used_by.length
          ? `<div class="chips">${m.used_by.slice(0, 3).map(u => `<span class="used-chip" title="${esc(u.product_name)}: ${esc(u.per_serving)} ${esc(m.unit)} por ${esc(u.yield_unit || 'unidad')}">${esc(u.product_name)} <b>${esc(dec(u.servings))}</b></span>`).join('')}${m.used_by.length > 3 ? `<span class="used-chip">+${m.used_by.length - 3}</span>` : ''}</div>`
          : '<span style="color:var(--text-4)">Sin recetas</span>'}</td>
        <td>${rowActions('material', m)}</td></tr>`).join('')}</tbody></table></div>`
      : `<div class="empty-state"><div class="empty-icon">▣</div><b>${q || category || low ? 'Sin resultados' : 'Inventario vacío'}</b><p>${q || category || low ? 'Ajusta los filtros.' : 'Cargue datos de prueba o registre valores del IPV.'}</p>${editar ? '<button class="primary-btn" data-action="seed-demo">🧪 Cargar datos de prueba</button>' : permPill('Solo consulta', 'Su usuario no puede cargar datos ni mover existencias.')}</div>`}</section>`;
}

function bindValuesTab() {
  $('#table-search')?.addEventListener('input', e => { state.search = e.target.value; renderMaterialsModule('valores'); });
  $('#material-category')?.addEventListener('change', e => { state.filters.materials.category = e.target.value; renderMaterialsModule('valores'); });
  $('#material-status')?.addEventListener('change', e => { state.filters.materials.status = e.target.value; renderMaterialsModule('valores'); });
}

function bindInventoryTab() {
  $('#table-search')?.addEventListener('input', e => { state.search = e.target.value; renderMaterialsModule('inventario'); });
  $('#inv-category')?.addEventListener('change', e => { state.filters.inventory.category = e.target.value; renderMaterialsModule('inventario'); });
  $('#inv-low')?.addEventListener('change', e => { state.filters.inventory.low = e.target.checked; renderMaterialsModule('inventario'); });
  $$('[data-stock-input]').forEach(inp => inp.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); saveStock(inp.dataset.stockInput); } }));
}

function bindMaterialsTabs() {
  $$('[data-mat-tab]').forEach(b => b.addEventListener('click', () => {
    if (b.dataset.matTab === state.matTab) return;
    state.search = '';
    renderMaterialsModule(b.dataset.matTab);
  }));
}

/* Entrada única: la misma pantalla para las pestañas Valores e Inventario */
function renderMaterialsModule(tab) {
  state.matTab = tab === 'inventario' ? 'inventario' : 'valores';
  const inventario = state.matTab === 'inventario';
  const crumb = $('#crumb-current');
  if (crumb) crumb.textContent = inventario ? 'Valores del IPV · Inventario' : 'Valores del IPV';
  $$('[data-view]').forEach(el => el.classList.toggle('active', el.dataset.view === 'materials'));
  if (!canSee('materials')) {
    content.innerHTML = lockedPanel('Valores del IPV',
      'Su usuario no tiene permiso para consultar los valores del IPV ni el inventario. Pida al administrador que se lo conceda en Usuarios → 🔐 Permisos.');
    return;
  }
  const editar = canEdit('materials');
  const acciones = editar
    ? (inventario
      ? '<button class="primary-btn" data-action="create-material"><span class="plus">＋</span> Nuevo valor</button>'
      : `<div class="btn-row">
        <button class="secondary-btn" data-action="seed-demo" title="Cargar más inventarios y fichas de ejemplo">🧪 Datos de prueba</button>
        <button class="primary-btn" data-action="create-material"><span class="plus">＋</span> Nuevo valor</button>
      </div>`)
    : permPill('Solo consulta', 'Su usuario puede ver estos datos, pero no crearlos ni modificarlos.');
  content.innerHTML = `
    ${heading('Referencias y almacén', 'Valores del IPV', inventario
      ? 'Cuánto queda de cada insumo, cuánto vale y para qué recetas se utiliza. Sirve para saber cuántos comensales o copas se pueden preparar.'
      : 'Insumos, licores, bebidas y servicios con precio unitario, existencias y vigencia. Puede crearlos, editarlos o eliminarlos desde cualquier pantalla.',
      acciones)}
    ${materialsTabs()}
    <div id="mat-body">${inventario ? inventoryBody() : valuesBody()}</div>`;
  bindMaterialsTabs();
  if (inventario) bindInventoryTab(); else bindValuesTab();
}

function renderMaterials() { renderMaterialsModule(state.matTab); }
function renderInventory() { renderMaterialsModule('inventario'); }

/* ── Papelera de reciclaje ── */
const TRASH_ICON = { products: '▦', materials: '◈', fichas: '▤', controls: '✓' };
function renderTrash() {
  const q = state.search.toLowerCase();
  const rows = state.trash.filter(t => `${t.name} ${t.code} ${t.kind_label}`.toLowerCase().includes(q));
  content.innerHTML = `
    ${heading('Recuperación', 'Papelera de reciclaje', 'Todo lo que elimina pasa aquí: puede restaurarlo o borrarlo definitivamente. Nada se pierde por accidente.', rows.length
      ? `<button class="danger-btn" data-action="empty-trash">Vaciar papelera</button>` : '')}
    <div class="toolbar">${searchBox('Buscar en la papelera…')}${countPill(rows.length, state.trash.length, 'elementos')}</div>
    <section class="panel">
      ${rows.length ? rows.map((t, i) => `<div class="trash-item">
        <div class="trash-index" title="Número de orden del ítem">${i + 1}</div>
        <div class="trash-icon">${TRASH_ICON[t.kind] || '•'}</div>
        <div class="trash-body">
          <b>${esc(t.name)}</b>
          <small>${esc(t.kind_label)}${t.code ? ` · ${esc(t.code)}` : ''}${t.period ? ` · ${esc(t.period)}` : ''}${t.detail ? ` · ${esc(t.detail)}` : ''} · eliminado el ${dateLabel(t.deleted_at)}</small>
        </div>
        <div class="trash-actions">
          <button class="secondary-btn" data-action="restore-trash" data-kind="${t.kind}" data-id="${t.id}">↶ Restaurar</button>
          <button class="danger-btn" data-action="purge-trash" data-kind="${t.kind}" data-id="${t.id}" title="Borrado definitivo">Eliminar</button>
        </div>
      </div>`).join('') : `<div class="trash-empty-note"><div style="font-size:34px;margin-bottom:10px">🗑</div><b>La papelera está vacía</b><p>Los elementos que elimine aparecerán aquí para poder recuperarlos.</p></div>`}
    </section>`;
  $('#table-search')?.addEventListener('input', e => { state.search = e.target.value; renderTrash(); });
}

/* ── Fichas ── */
function renderFichas() {
  const q = state.search.toLowerCase();
  const sf = $('#ficha-status')?.value || '';
  const rows = state.fichas.filter(f => `${f.product_name} ${f.product_code} ${f.category}`.toLowerCase().includes(q) && (!sf || f.status === sf));
  content.innerHTML = `
    ${heading('Documentos', 'Fichas de costo', 'Cada ficha registra los componentes, el costo del lote, cuántos comensales o copas salen de él y cuánto queda en inventario.', '<button class="primary-btn" data-action="create-ficha"><span class="plus">＋</span> Nueva ficha</button>')}
    <div class="toolbar">${searchBox()}<select class="filter-select" id="ficha-status"><option value="">Todos los estados</option><option value="Borrador" ${sf === 'Borrador' ? 'selected' : ''}>Borrador</option><option value="Aprobada" ${sf === 'Aprobada' ? 'selected' : ''}>Aprobada</option></select><button class="secondary-btn" data-action="export-fichas">⤓ Exportar CSV</button>${countPill(rows.length, state.fichas.length, 'fichas')}</div>
    <section class="panel table-panel">${rows.length
      ? `<div class="table-wrap"><table style="min-width:1060px"><thead><tr>${idTh()}<th>Producto</th><th>Versión</th><th>Vigente</th><th>Rinde</th><th>Componentes</th><th>Costo lote</th><th>Costo por unidad</th><th>Con el inventario</th><th>Estado</th><th style="text-align:right">Acciones</th></tr></thead><tbody>${rows.map((f, i) => {
        const short = Number(f.servings_from_stock);
        const tone = f.servings_from_stock === null || f.servings_from_stock === undefined ? '' : short <= 0 ? 'red' : short < Number(f.yield_qty || 1) ? 'orange' : 'green';
        return `<tr>${idTd(i, f.id)}<td>${prodCell(f.product_name, f.product_code, f.category)}</td><td>v${f.version}</td><td>${dateLabel(f.valid_from)}</td>
        <td>${yieldBadge(f.yield_qty, f.yield_unit, f.category === 'Comidas' ? 'orange' : 'blue')}</td>
        <td>${f.item_count || 0}</td><td class="amount">${money(f.total_cost)}</td>
        <td class="amount">${money(f.cost_per_serving)} <small style="color:var(--text-4)">/ ${esc(f.yield_unit || '')}</small></td>
        <td>${f.servings_from_stock === null || f.servings_from_stock === undefined ? '—' : `<span class="yield-badge ${tone}">≈ ${dec(f.servings_from_stock)} ${esc(f.yield_unit || '')}</span>`}</td>
        <td>${stPill(f.status)}</td><td>${rowActions('ficha', f)}</td></tr>`;
      }).join('')}</tbody></table></div>`
      : `<div class="empty-state"><div class="empty-icon">▤</div><b>${q || sf ? 'Sin resultados' : 'No hay fichas'}</b><p>${q || sf ? 'Ajusta los filtros.' : 'Cree la primera ficha de costo o cargue los datos de prueba.'}</p><button class="primary-btn" data-action="seed-demo">🧪 Cargar datos de prueba</button></div>`}</section>`;
  $('#table-search')?.addEventListener('input', e => { state.search = e.target.value; renderFichas(); });
  $('#ficha-status')?.addEventListener('change', () => renderFichas());
}

/* ── Licencia ── */
function renderLicense() {
  const lic = state.license;
  content.innerHTML = `<div class="lic-page">
    ${heading('Licencia', 'Licencia de uso', 'La licencia se firma digitalmente y queda atada a este equipo. Puede consultarla, renovarla o solicitar una nueva en cualquier momento.', '')}
    <div id="lic-body"><div class="lic-status-card"><div class="lic-status-icon">🔑</div><div class="lic-status-copy"><h3>Consultando…</h3><p>Verificando la licencia de este equipo.</p></div></div></div>
  </div>`;
  loadLicenseInto($('#lic-body'));
}

function fmtDate(ts) {
  if (!ts) return '—';
  return new Intl.DateTimeFormat('es', { day: '2-digit', month: '2-digit', year: 'numeric' }).format(new Date(ts * 1000));
}

function loadLicenseInto(box) {
  if (!box) return;
  fetch('/api/license', { headers: { Accept: 'application/json' } })
    .then(r => r.json())
    .then(lic => {
      state.license = lic;
      if (!box.isConnected) return;
      if (!lic.enforced) {
        const canCreate = !window.IPVAuth?.user || window.IPVAuth.user.role === 'admin';
        box.innerHTML = `<div class="lic-status-card off"><div class="lic-status-icon">🛡</div><div class="lic-status-copy">
          <h3>Licencias desactivadas</h3><p>Este servidor aún no tiene clave pública de licencias. Cree la clave de firma con el <b>Creador de Licencias</b> y el sistema quedará activado al instante, sin reiniciar.</p></div>
          <div style="display:flex;flex-direction:column;gap:8px">
          ${canCreate ? '<button class="primary-btn" data-action="open-creator">🛠 Abrir Creador de Licencias</button>' : ''}
          <button class="secondary-btn" data-action="reload-license">Actualizar</button></div></div>
          <div class="panel"><h3 class="panel-title">¿Cómo se activan?</h3>
          <p class="small-note">Abra el <b>Creador de Licencias</b> (menú lateral) y cree la clave de firma una sola vez: a partir de ahí el servidor exige licencia y cada equipo o teléfono solicita la suya con su código IPVW-… / IPVA-…. También puede usar el Keygen de escritorio: <code>python keygen/keygen.py init --whatsapp 53XXXXXXXX</code>.</p></div>`;
        return;
      }
      const days = lic.days_left ?? 0;
      const cls = lic.valid ? (days <= 7 ? 'bad' : 'ok') : 'bad';
      const icon = lic.valid ? (days <= 7 ? '⏳' : '✅') : '🔒';
      const plans = Object.entries(lic.plans || {});
      box.innerHTML = `
        <div class="lic-status-card ${cls}"><div class="lic-status-icon">${icon}</div>
          <div class="lic-status-copy"><h3>${lic.valid ? `Licencia vigente — ${esc(lic.plan_name || '')}` : 'Este equipo no tiene licencia'}</h3>
          <p>${lic.valid ? `A nombre de ${esc(lic.user || '')} · serie ${esc(lic.serial || '')}` : esc(lic.reason || '')}</p></div>
          <button class="primary-btn" data-action="open-license">${lic.valid ? 'Renovar' : 'Activar'}</button></div>
        ${lic.valid ? `<div class="lic-kv">
          <div><small>Plan</small><b>${esc(lic.plan_name)}</b></div>
          <div><small>Emitida</small><b>${fmtDate(lic.issued_at)}</b></div>
          <div><small>Vence</small><b>${fmtDate(lic.expires_at)}</b></div>
          <div><small>Días restantes</small><b style="color:${days <= 7 ? 'var(--orange)' : 'var(--green)'}">${days}</b></div>
        </div>` : ''}
        <div class="panel">
          <div class="panel-heading"><div><h2 class="panel-title">ID de este equipo</h2><p class="panel-subtitle">Cifrado con SHA-256: no contiene datos del equipo</p></div>
            <button class="secondary-btn" data-action="copy-device">📋 Copiar</button></div>
          <code class="lic-code">${esc(lic.request_code || '')}</code>
          <p class="small-note" style="margin-top:10px">Envíe este código al proveedor para recibir la licencia. ${lic.whatsapp ? `<button class="text-btn" data-action="whatsapp-license">💬 Solicitar por WhatsApp</button>` : ''}</p>
        </div>
        <div class="panel">
          <div class="panel-heading"><div><h2 class="panel-title">Planes disponibles</h2><p class="panel-subtitle">Precios de referencia del proveedor</p></div></div>
          <div class="plan-grid">${plans.map(([k, p]) => `<div class="plan-card"><b>${esc(p.name)}</b><div class="plan-usd">${p.usd} USD</div><small>${p.days} días de uso</small></div>`).join('')}</div>
        </div>`;
    })
    .catch(e => { if (box.isConnected) box.innerHTML = `<div class="lic-status-card bad"><div class="lic-status-icon">⚠</div><div class="lic-status-copy"><h3>No se pudo consultar la licencia</h3><p>${esc(e.message)}</p></div><button class="secondary-btn" data-action="reload-license">Reintentar</button></div>`; });
}

/* ── Creador de Licencias (administradores) ── */
function creatorPriceHint() {
  const st = state.creator; if (!st) return;
  const hint = $('#creator-price'); if (!hint) return;
  const code = ($('#creator-code')?.value || '').trim().toUpperCase();
  const p = (st.plans || {})[$('#creator-plan')?.value || '1M'];
  if (!p) return;
  if (code.startsWith('IPVA')) { hint.innerHTML = `📱 IPV Android (móvil) · <b>${esc(p.name)}</b> — ${p.usd_android} USD ≈ ${money(p.cup_android)}`; return; }
  if (code.startsWith('IPVW')) { hint.innerHTML = `💻 IPV Web (servidor/PC) · <b>${esc(p.name)}</b> — ${p.usd_web} USD ≈ ${money(p.cup_web)}`; return; }
  hint.innerHTML = code ? '<span style="color:var(--orange)">El código debe empezar por IPVW- (PC) o IPVA- (móvil).</span>'
    : 'Pegue el código de solicitud recibido por WhatsApp: IPVW-… (PC) o IPVA-… (móvil).';
}

function creatorResultPanel(r) {
  const self = state.creator?.license && !state.creator.license.valid;
  return `<div class="panel animate-fade" id="creator-result">
    <div class="panel-heading"><div><h2 class="panel-title">✅ Licencia creada — ${esc(r.plan_name)}</h2>
      <p class="panel-subtitle">${esc(r.app_name)} · Usuario: ${esc(r.user)} · Serie ${esc(r.serial)} · vence el ${fmtDate(r.expires_at)} · ${r.price_usd} USD ≈ ${money(r.price_cup)}</p></div></div>
    <textarea class="lic-input lic-token" id="creator-token" rows="4" readonly spellcheck="false">${esc(r.license)}</textarea>
    <div class="lic-actions">
      <button class="secondary-btn" data-action="creator-copy" data-target="#creator-token">📋 Copiar licencia</button>
      <button class="secondary-btn" data-action="creator-copy" data-target="#creator-reply">📋 Copiar mensaje de WhatsApp</button>
      ${self ? '<button class="primary-btn" data-action="creator-activate-here">🔓 Activar en este equipo</button>' : ''}
    </div>
    <pre id="creator-reply" hidden>${esc(r.reply)}</pre>
    <p class="small-note" style="margin-top:10px">Pegue la licencia en el equipo o teléfono del cliente (botón Activar licencia) o envíela por WhatsApp con el mensaje copiado. Quedó registrada en el historial.</p></div>`;
}

function renderCreator() {
  content.innerHTML = `<div class="lic-page">
    ${heading('Licencias', 'Creador de Licencias', 'Cree la clave de firma, active el sistema de licencias y emita licencias firmadas para sus clientes (PC y móvil) sin salir de la aplicación.', '<button class="secondary-btn" data-action="creator-refresh">↻ Actualizar</button>')}
    <div id="creator-body"><div class="lic-status-card"><div class="lic-status-icon">🛠</div><div class="lic-status-copy"><h3>Consultando…</h3><p>Cargando el estado del sistema de licencias.</p></div></div></div>
  </div>`;
  loadCreatorInto($('#creator-body'));
}

async function loadCreatorInto(box) {
  if (!box) return;
  let st;
  try { st = await api('/api/keygen/status'); }
  catch (e) {
    box.innerHTML = `<div class="lic-status-card bad"><div class="lic-status-icon">⚠</div><div class="lic-status-copy"><h3>No se pudo abrir el Creador de Licencias</h3><p>${esc(e.message)}</p></div><button class="secondary-btn" data-action="creator-refresh">Reintentar</button></div>`;
    return;
  }
  state.creator = st;
  const lic = st.license || {};
  const planOpts = Object.entries(st.plans || {}).map(([k, p]) => `<option value="${k}" ${k === '1M' ? 'selected' : ''}>${esc(p.name)} (${k})</option>`).join('');
  const rateInputs = Object.entries(st.rates || {}).map(([k, v]) =>
    `<div class="form-field"><label>${k} → CUP</label><input id="rate-${k}" value="${esc(v)}" inputmode="decimal" autocomplete="off"></div>`).join('');

  box.innerHTML = `
    <div class="lic-status-card ${st.configured ? (lic.valid ? 'ok' : 'bad') : 'off'}"><div class="lic-status-icon">${st.configured ? (lic.valid ? '✅' : '🔒') : '🛡'}</div>
      <div class="lic-status-copy"><h3>${st.configured ? `Licencias activadas — clave ${esc(st.fingerprint)}` : 'Licencias desactivadas (sin clave pública configurada)'}</h3>
        <p>${st.configured
          ? (lic.valid ? `Este equipo tiene licencia: ${esc(lic.plan_name || '')}, vence en ${lic.days_left ?? '—'} día(s).` : `Este equipo aún no tiene licencia: emítala abajo con su propio código de solicitud.`)
          : 'Cree la clave de firma una sola vez: el sistema quedará activado al instante, sin reiniciar el servidor.'}</p></div></div>

    ${st.configured && !lic.valid ? `<div class="panel">
      <div class="panel-heading"><div><h2 class="panel-title">Licencia de este equipo</h2>
        <p class="panel-subtitle">Emítala abajo pegando este código, para no bloquear la API (error 402)</p></div>
        <button class="secondary-btn" data-action="creator-copy" data-target="#creator-self-code">📋 Copiar</button></div>
      <code class="lic-code" id="creator-self-code">${esc(lic.request_code || '')}</code></div>` : ''}

    <div class="panel">
      <div class="panel-heading"><div><h2 class="panel-title">🔑 Emitir licencia</h2>
        <p class="panel-subtitle">Pegue el código de solicitud del cliente (IPVW-… PC · IPVA-… móvil) y firme su licencia</p></div></div>
      <div class="form-grid">
        <div class="form-field"><label>Usuario / cliente</label><input id="creator-user" maxlength="80" placeholder="Nombre o empresa" autocomplete="off"></div>
        <div class="form-field"><label>Plan</label><select id="creator-plan">${planOpts}</select></div>
        <div class="form-field full"><label>Código de solicitud</label><input id="creator-code" style="letter-spacing:1px" placeholder="IPVW-XXXXX-XXXXX-XXXXX-XXXXX-XX" spellcheck="false" autocomplete="off"></div>
        <div class="form-field full"><label>Contraseña de la clave de firma</label><input id="creator-pass" type="password" autocomplete="off" placeholder="La del archivo clave_privada.json"></div>
      </div>
      <p class="small-note" id="creator-price" style="margin:4px 0 12px"></p>
      <button class="primary-btn" id="creator-emit-btn">⚙️ Crear licencia</button>
      <p class="lic-msg" id="creator-emit-msg" role="alert" hidden></p>
    </div>
    <div id="creator-result-box"></div>

    <div class="panel">
      <div class="panel-heading"><div><h2 class="panel-title">🛠 Clave de firma</h2>
        <p class="panel-subtitle">${st.has_key_file ? 'Existe keygen/clave_privada.json (cifrada con su contraseña); es intercambiable con el Keygen de escritorio.' : 'Aún no existe keygen/clave_privada.json'}</p></div></div>
      ${st.configured ? `<details><summary class="small-note" style="cursor:pointer">⚠ Reemplazar la clave (invalida TODAS las licencias emitidas)</summary>
        <div class="form-grid" style="margin-top:10px">
          <div class="form-field"><label>Nueva contraseña (mín. 10)</label><input id="creator-pass2" type="password" autocomplete="new-password"></div>
          <div class="form-field"><label>Repetir</label><input id="creator-pass2b" type="password" autocomplete="new-password"></div>
          <div class="form-field full"><label>WhatsApp de solicitudes</label><input id="creator-wa2" value="${esc(st.whatsapp || '')}" placeholder="5355555555" inputmode="numeric"></div>
        </div>
        <button class="danger-btn" id="creator-init2-btn">♻ Reemplazar clave y activar licencias</button></details>`
      : `<div class="form-grid">
          <div class="form-field"><label>Contraseña de la clave (mín. 10)</label><input id="creator-pass2" type="password" autocomplete="new-password"></div>
          <div class="form-field"><label>Repetir</label><input id="creator-pass2b" type="password" autocomplete="new-password"></div>
          <div class="form-field full"><label>WhatsApp de solicitudes</label><input id="creator-wa2" value="${esc(st.whatsapp || '')}" placeholder="5355555555" inputmode="numeric"></div>
        </div>
        <button class="primary-btn" id="creator-init2-btn">🔐 Crear clave de firma y activar licencias</button>
        <p class="small-note" style="margin-top:8px">Guarde la contraseña en un lugar seguro: sin ella no podrá emitir renovaciones.</p>`}
      <p class="lic-msg" id="creator-init-msg" role="alert" hidden></p>
    </div>

    <div class="panel">
      <div class="panel-heading"><div><h2 class="panel-title">🔍 Verificar una licencia</h2>
        <p class="panel-subtitle">Comprueba firma, usuario, dispositivo y vigencia</p></div></div>
      <textarea class="lic-input lic-token" id="creator-verify-token" rows="3" placeholder="Pegue la licencia IPV1.…" spellcheck="false"></textarea>
      <div class="lic-actions"><button class="secondary-btn" id="creator-verify-btn">Verificar</button></div>
      <p class="lic-msg" id="creator-verify-msg" role="alert" hidden></p>
    </div>

    <div class="panel">
      <div class="panel-heading"><div><h2 class="panel-title">💱 Tasas de cambio</h2>
        <p class="panel-subtitle">Se usan para calcular el precio en CUP de cada licencia</p></div></div>
      <div class="form-grid">${rateInputs}</div>
      <button class="secondary-btn" id="creator-rates-btn">Guardar tasas</button>
      <p class="lic-msg" id="creator-rates-msg" role="alert" hidden></p>
    </div>

    <div class="panel">
      <div class="panel-heading"><div><h2 class="panel-title">📜 Historial (${st.ledger_count} emitidas)</h2>
        <p class="panel-subtitle">keygen/registro_licencias.csv</p></div>
        <button class="secondary-btn" data-action="creator-ledger">↻ Cargar</button></div>
      <div class="table-wrap"><table id="creator-ledger"><thead><tr>${idTh()}<th>Fecha</th><th>Serie</th><th>Usuario</th><th>App</th><th>Plan</th><th>Vence</th><th style="text-align:right">USD</th><th style="text-align:right">CUP</th></tr></thead>
      <tbody><tr><td colspan="9" class="small-note">Pulse «Cargar» para ver las últimas licencias emitidas.</td></tr></tbody></table></div>
    </div>`;

  creatorPriceHint();
  $('#creator-code')?.addEventListener('input', creatorPriceHint);
  $('#creator-plan')?.addEventListener('change', creatorPriceHint);

  const showMsg = (sel, msg, ok = false) => { const m = $(sel); if (m) { m.textContent = msg; m.hidden = false; m.style.color = ok ? 'var(--green)' : 'var(--red)'; } };

  $('#creator-emit-btn')?.addEventListener('click', async () => {
    const btn = $('#creator-emit-btn'), msg = $('#creator-emit-msg');
    btn.disabled = true; msg.hidden = true;
    try {
      const r = await api('/api/keygen/emit', { method: 'POST', body: JSON.stringify({
        user: $('#creator-user').value.trim(), code: $('#creator-code').value.trim(),
        plan: $('#creator-plan').value, passphrase: $('#creator-pass').value }) });
      $('#creator-result-box').innerHTML = creatorResultPanel(r);
      $('#creator-pass').value = '';
    } catch (e) { showMsg('#creator-emit-msg', e.message); }
    finally { btn.disabled = false; }
  });

  $('#creator-init2-btn')?.addEventListener('click', async () => {
    const btn = $('#creator-init2-btn');
    const force = st.configured || st.has_key_file;
    if (force && !await confirm2('Reemplazar la clave de firma', 'Se invalidarán TODAS las licencias ya emitidas (habrá que emitirlas de nuevo). ¿Continuar?', 'danger')) return;
    btn.disabled = true;
    try {
      const r = await api('/api/keygen/init', { method: 'POST', body: JSON.stringify({
        passphrase: $('#creator-pass2').value, whatsapp: $('#creator-wa2').value.trim(), force }) });
      toast(`🔑 Clave creada (${r.fingerprint}). Licencias activadas.`, 'success');
      if (r.patched?.includes('License.kt')) toast('📱 License.kt actualizado: recompile el APK para distribuirlo.', 'info');
      loadCreatorInto(box);
    } catch (e) { showMsg('#creator-init-msg', e.message); }
    finally { btn.disabled = false; }
  });

  $('#creator-verify-btn')?.addEventListener('click', async () => {
    try {
      const r = await api('/api/keygen/verify', { method: 'POST', body: JSON.stringify({ license: $('#creator-verify-token').value }) });
      showMsg('#creator-verify-msg', `✅ Firma ${r.signature} · ${r.app_name} · ${r.user} · ${r.plan_name} · vence el ${fmtDate(r.expires_at)} · serie ${r.serial}`, true);
    } catch (e) { showMsg('#creator-verify-msg', e.message); }
  });

  $('#creator-rates-btn')?.addEventListener('click', async () => {
    const rates = {};
    Object.keys(st.rates || {}).forEach(k => { const el = $(`#rate-${k}`); if (el) rates[k] = el.value.trim(); });
    try {
      const r = await api('/api/keygen/rates', { method: 'POST', body: JSON.stringify({ rates }) });
      state.creator.rates = r.rates; toast('Tasas actualizadas.', 'success'); creatorPriceHint();
    } catch (e) { showMsg('#creator-rates-msg', e.message); }
  });
}

async function loadCreatorLedger() {
  try {
    const { items } = await api('/api/keygen/ledger?limit=100');
    const tb = $('#creator-ledger tbody'); if (!tb) return;
    tb.innerHTML = items.length ? items.map((r, i) => `<tr>${idTd(i, r.serie)}<td>${esc(r.fecha || '')}</td><td>${esc(r.serie || '')}</td><td>${esc(r.usuario || '')}</td>
      <td>${r.app === 'A' ? '📱 Móvil' : '💻 Web'}</td><td>${esc(r.plan || '')}</td><td>${esc(r.vence || '')}</td>
      <td class="amount">${r.precio_usd ?? ''}</td><td class="amount">${money(r.precio_cup || 0).replace(' CUP', '')}</td></tr>`).join('')
      : '<tr><td colspan="9" class="small-note">Aún no se ha emitido ninguna licencia.</td></tr>';
  } catch (e) { toast(e.message, 'error'); }
}

/* ── Controls ── */
function renderControls() {
  const q = state.search.toLowerCase();
  const sf = $('#control-status')?.value || '';
  const rows = state.controls.filter(c => `${c.product_name} ${c.code} ${c.product_code}`.toLowerCase().includes(q) && (!sf || c.status === sf));
  content.innerHTML = `
    ${heading('Verificación', 'Controles de IPV', 'Cada control es una instantánea vinculada a una versión específica de ficha. La validación compara totales y líneas.', '')}
    <div class="toolbar">${searchBox()}<select class="filter-select" id="control-status"><option value="">Todos los estados</option><option value="Pendiente" ${sf === 'Pendiente' ? 'selected' : ''}>Pendiente</option><option value="Validado" ${sf === 'Validado' ? 'selected' : ''}>Validado</option><option value="Con diferencias" ${sf === 'Con diferencias' ? 'selected' : ''}>Con diferencias</option></select><button class="secondary-btn" data-action="export-controls">⤓ Exportar CSV</button>${countPill(rows.length, state.controls.length, 'controles')}</div>
    <section class="panel table-panel">${rows.length
      ? `<div class="table-wrap"><table><thead><tr>${idTh()}<th>Control</th><th>Producto</th><th>Período</th><th>Ficha</th><th>Total</th><th>Estado</th><th></th></tr></thead><tbody>${rows.map((c, i) => `<tr>${idTd(i, c.id)}<td><b style="color:var(--text);font-size:12px">${esc(c.code)}</b></td><td>${prodCell(c.product_name, c.product_code, c.category)}</td><td>${esc(c.period)}</td><td>v${c.ficha_version}</td><td class="amount">${money(c.snapshot_total)}</td><td>${stPill(c.status)}</td><td><button class="text-btn" data-action="view-control" data-id="${c.id}">Abrir ↗</button></td></tr>`).join('')}</tbody></table></div>`
      : `<div class="empty-state"><div class="empty-icon">✓</div><b>${q || sf ? 'Sin resultados' : 'No hay controles'}</b><p>${q || sf ? 'Ajusta los filtros.' : 'Genera un control desde una ficha aprobada.'}</p></div>`}</section>`;
  $('#table-search')?.addEventListener('input', e => { state.search = e.target.value; renderControls(); });
  $('#control-status')?.addEventListener('change', () => renderControls());
}

/* ── Modal ── */
function showModal(title, subtitle, body) {
  modalLayer.hidden = false;
  modalLayer.innerHTML = `<div class="modal-card"><div class="modal-head"><div><h2>${esc(title)}</h2><p>${esc(subtitle)}</p></div><button class="modal-close" data-action="close-modal" aria-label="Cerrar">×</button></div><div class="modal-body">${body}</div></div>`;
}
/* Permite abrir un formulario anidado (p. ej. crear un valor del IPV mientras se
   edita una ficha) sin perder lo que el usuario ya había escrito. */
let preservedModal = null;
function preserveModal() {
  const card = modalLayer.firstElementChild;
  if (card) { preservedModal = card; card.remove(); }
}
function restoreModal() {
  if (!preservedModal) return false;
  modalLayer.hidden = false;
  modalLayer.appendChild(preservedModal);
  preservedModal = null;
  return true;
}
function closeModal() { modalLayer.hidden = true; modalLayer.innerHTML = ''; restoreModal(); }

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
function yieldUnitOptions(selected) {
  const list = YIELD_UNITS.includes(selected) ? YIELD_UNITS : [selected, ...YIELD_UNITS].filter(Boolean);
  return list.map(u => `<option value="${esc(u)}" ${u === selected ? 'selected' : ''}>${esc(u)}</option>`).join('');
}

function openProductModal(existing = null) {
  const isEdit = !!existing;
  const p = existing || {};
  const cats = state.categories.products.length ? state.categories.products : ['Comidas', 'Bebidas', 'Servicios'];
  const unit = p.yield_unit || (/comida/i.test(p.category || '') ? 'comensales' : /bebida/i.test(p.category || '') ? 'copas' : 'unidad');
  showModal(isEdit ? 'Editar producto o servicio' : 'Nuevo producto o servicio', isEdit ? `Código ${p.code}` : 'Se añadirá al catálogo activo.', `
    <form id="pf"><div class="form-grid">
      <div class="form-field"><label>Código *</label><input id="p-code" required value="${esc(p.code || '')}" placeholder="Ej: BEB-003"></div>
      <div class="form-field"><label>Categoría *</label><input id="p-cat" required list="product-cats" value="${esc(p.category || '')}" placeholder="Comidas, Bebidas, Servicios">
        <datalist id="product-cats">${cats.map(c => `<option value="${esc(c)}">`).join('')}</datalist></div>
      <div class="form-field full"><label>Nombre *</label><input id="p-name" required value="${esc(p.name || '')}" placeholder="Nombre del producto o servicio"></div>
      <div class="form-field"><label>Unidad de venta</label><input id="p-unit" value="${esc(p.unit || 'unidad')}"></div>
      <div class="form-field"><label>Rendimiento del lote *</label><input id="p-yield" type="number" step="0.01" min="0.01" required value="${esc(p.yield_qty || p.last_yield_qty || 1)}"><span class="form-hint">Cuántas raciones, copas o comensales salen de una ficha completa.</span></div>
      <div class="form-field"><label>Unidad del rendimiento</label><select id="p-yield-unit">${yieldUnitOptions(unit)}</select></div>
      <div class="form-field full"><label>Descripción</label><textarea id="p-desc" placeholder="Notas adicionales">${esc(p.description || '')}</textarea></div>
    </div><div class="modal-actions">
      <button type="button" class="secondary-btn" data-action="close-modal">Cancelar</button>
      <button class="primary-btn" type="submit">${isEdit ? 'Guardar cambios' : 'Registrar producto'}</button></div></form>`);
  $('#pf').addEventListener('submit', async e => {
    e.preventDefault();
    const payload = { code: $('#p-code').value, name: $('#p-name').value, category: $('#p-cat').value,
      unit: $('#p-unit').value || 'unidad', description: $('#p-desc').value,
      yield_qty: $('#p-yield').value, yield_unit: $('#p-yield-unit').value };
    try {
      if (isEdit) await api(`/api/products/${p.id}`, { method: 'PUT', body: JSON.stringify(payload) });
      else await api('/api/products', { method: 'POST', body: JSON.stringify(payload) });
      closeModal(); await refreshData(true);
      toast(isEdit ? 'Producto actualizado.' : 'Producto registrado correctamente.', 'success');
    } catch (err) { toast(err.message, 'error'); }
  });
}

function openMaterialModal(existing = null, afterCreate = false) {
  const isEdit = !!existing;
  const m = existing || {};
  const cats = state.categories.materials.length ? state.categories.materials
    : ['Licores', 'Cervezas', 'Vinos', 'Bebidas sin alcohol', 'Cafés y tés', 'Granos y básicos', 'Condimentos', 'Vegetales', 'Frutas', 'Carnes', 'Aves', 'Pescados', 'Mariscos', 'Lácteos', 'Panadería', 'Hierbas', 'Servicios', 'Insumos'];
  const today = new Date().toISOString().slice(0, 10);
  showModal(isEdit ? 'Editar valor del IPV' : 'Nuevo valor del IPV', isEdit ? `Código ${m.code} · se actualizará en todas las fichas que lo usan` : 'Insumo, licor, bebida o servicio con precio y existencias.', `
    <form id="mf"><div class="form-grid">
      <div class="form-field"><label>Código *</label><input id="m-code" required value="${esc(m.code || '')}" placeholder="Ej: LIC-025"></div>
      <div class="form-field"><label>Nombre *</label><input id="m-name" required value="${esc(m.name || '')}"></div>
      <div class="form-field"><label>Categoría *</label><input id="m-cat" required list="material-cats" value="${esc(m.category || '')}" placeholder="Licores, Insumos, Servicios">
        <datalist id="material-cats">${cats.map(c => `<option value="${esc(c)}">`).join('')}</datalist></div>
      <div class="form-field"><label>Unidad *</label><input id="m-unit" required value="${esc(m.unit || '')}" placeholder="kg, L, unidad, hora"></div>
      <div class="form-field"><label>Precio unitario *</label><input id="m-price" type="number" step="0.01" min="0" required value="${esc(m.unit_price ?? '0')}"></div>
      <div class="form-field"><label>Moneda</label><select id="m-curr">${['CUP', 'MLC', 'USD', 'EUR'].map(c => `<option ${c === (m.currency || 'CUP') ? 'selected' : ''}>${c}</option>`).join('')}</select></div>
      <div class="form-field"><label>Existencias en almacén</label><input id="m-stock" type="number" step="0.001" min="0" value="${esc(m.stock ?? '0')}"><span class="form-hint">Cuánto queda ahora mismo.</span></div>
      <div class="form-field"><label>Existencia mínima</label><input id="m-min" type="number" step="0.001" min="0" value="${esc(m.min_stock ?? '0')}"><span class="form-hint">Por debajo de este valor se avisa.</span></div>
      <div class="form-field"><label>Proveedor</label><input id="m-sup" value="${esc(m.supplier || '')}"></div>
      <div class="form-field"><label>Estado</label><select id="m-status">${['Vigente', 'Inactivo'].map(s => `<option ${s === (m.status || 'Vigente') ? 'selected' : ''}>${s}</option>`).join('')}</select></div>
      <div class="form-field full"><label>Fuente</label><input id="m-src" value="${esc(m.source || '')}" placeholder="Resolución, factura, lista de precios…"></div>
      <div class="form-field"><label>Vigente desde</label><input id="m-from" type="date" value="${esc(m.effective_from || today)}"></div>
      <div class="form-field"><label>Vigente hasta</label><input id="m-to" type="date" value="${esc(m.effective_to || '')}"></div>
    </div><div class="modal-actions">
      <button type="button" class="secondary-btn" data-action="close-modal">Cancelar</button>
      <button class="primary-btn" type="submit">${isEdit ? 'Guardar cambios' : 'Registrar valor'}</button></div></form>`);
  $('#mf').addEventListener('submit', async e => {
    e.preventDefault();
    const payload = { code: $('#m-code').value, name: $('#m-name').value, unit: $('#m-unit').value,
      category: $('#m-cat').value, unit_price: $('#m-price').value, currency: $('#m-curr').value,
      stock: $('#m-stock').value, min_stock: $('#m-min').value, supplier: $('#m-sup').value,
      source: $('#m-src').value, status: $('#m-status').value,
      effective_from: $('#m-from').value, effective_to: $('#m-to').value };
    try {
      let saved;
      if (isEdit) saved = await api(`/api/materials/${m.id}`, { method: 'PUT', body: JSON.stringify(payload) });
      else saved = await api('/api/materials', { method: 'POST', body: JSON.stringify(payload) });
      closeModal(); await refreshData(true);
      toast(isEdit ? 'Valor del IPV actualizado.' : 'Valor del IPV registrado.', 'success');
      // Creado desde el constructor de una ficha: vuelve al lote y lo ofrece en la lista
      if (afterCreate && saved && saved.id) setTimeout(() => window.__fichaDraft?.add(saved), 80);
    } catch (err) { toast(err.message, 'error'); }
  });
}

/* ── Detalle de un valor del IPV ── */
async function openMaterialDetail(id) {
  try {
    const m = await api(`/api/materials/${id}`);
    const used = m.used_by.length
      ? `<div class="table-wrap"><table><thead><tr>${idTh()}<th>Se usa en</th><th>Por unidad</th><th>Con el inventario</th><th>Ficha</th></tr></thead><tbody>
        ${m.used_by.map((u, i) => `<tr>${idTd(i, u.ficha_id)}<td>${prodCell(u.product_name, u.product_code, u.category)}</td><td>${esc(u.per_serving)} ${esc(m.unit)}</td><td>${u.servings === null ? '—' : `<span class="yield-badge green">≈ ${dec(u.servings)} ${esc(u.yield_unit || 'unidad')}</span>`}</td><td>${stPill(u.ficha_status)}</td></tr>`).join('')}
        </tbody></table></div>`
      : '<div class="empty-state"><div class="empty-icon">▤</div><b>Sin recetas que lo usen</b><p>Este valor todavía no aparece en ninguna ficha de costo.</p></div>';
    showModal(`Valor del IPV · ${m.name}`, `${m.code} · ${m.category || 'Insumos'}`, `
      <div class="detail-grid">
        <div class="detail-box"><span>Precio unitario</span><b>${moneyOrLock(m.unit_price)}</b></div>
        <div class="detail-box"><span>Existencias</span><b style="color:${m.low_stock ? 'var(--red)' : 'var(--text)'}">${dec(m.stock)} ${esc(m.unit)}</b></div>
        <div class="detail-box"><span>Existencia mínima</span><b>${dec(m.min_stock)} ${esc(m.unit)}</b></div>
        <div class="detail-box"><span>Valor en almacén</span><b>${moneyOrLock(m.stock_value)}</b></div>
        <div class="detail-box"><span>Proveedor</span><b>${esc(m.supplier || '—')}</b></div>
        <div class="detail-box"><span>Fuente / vigencia</span><b>${esc(m.source || '—')} · ${dateLabel(m.effective_from)}</b></div>
      </div>${used}
      <div class="modal-actions">
        <button class="secondary-btn" data-action="close-modal">Cerrar</button>
        ${canEdit('materials') ? `<button class="secondary-btn" data-action="edit-material" data-id="${m.id}">✎ Editar</button>` : ''}
        ${canSee('fichas') ? `<button class="primary-btn" data-action="view-fichas-of-material" data-id="${m.id}">Ver fichas</button>` : ''}
      </div>`);
  } catch (e) { toast(e.message, 'error'); }
}

async function openProductDetail(id) {
  try {
    const p = await api(`/api/products/${id}`);
    const fichas = p.fichas.length
      ? `<div class="table-wrap"><table><thead><tr>${idTh()}<th>Versión</th><th>Rinde</th><th>Costo lote</th><th>Por unidad</th><th>Estado</th><th></th></tr></thead><tbody>
        ${p.fichas.map((f, i) => `<tr>${idTd(i, f.id)}<td>v${f.version}</td><td>${yieldBadge(f.yield_qty, f.yield_unit)}</td><td class="amount">${money(f.total_cost)}</td><td class="amount">${money(f.cost_per_serving || '0')}</td><td>${stPill(f.status)}</td><td><button class="text-btn" data-action="view-ficha" data-id="${f.id}">Abrir ↗</button></td></tr>`).join('')}
        </tbody></table></div>`
      : '<div class="empty-state"><div class="empty-icon">▤</div><b>Sin fichas de costo</b><p>Cree la primera ficha para este producto.</p></div>';
    showModal(`Producto · ${p.name}`, `${p.code} · ${p.category}`, `
      <div class="detail-grid">
        <div class="detail-box"><span>Unidad de venta</span><b>${esc(p.unit)}</b></div>
        <div class="detail-box"><span>Rendimiento por lote</span><b>${dec(p.yield_qty)} ${esc(p.yield_unit)}</b></div>
        <div class="detail-box"><span>Versiones de ficha</span><b>${p.fichas.length}</b></div>
        <div class="detail-box"><span>Estado</span><b>${p.active ? 'Activo' : 'Inactivo'}</b></div>
      </div>${p.description ? `<div class="small-note">${esc(p.description)}</div>` : ''}${fichas}
      <div class="modal-actions">
        <button class="secondary-btn" data-action="close-modal">Cerrar</button>
        <button class="secondary-btn" data-action="edit-product" data-id="${p.id}">✎ Editar</button>
        <button class="primary-btn" data-action="create-ficha-for" data-id="${p.id}">＋ Nueva ficha</button>
      </div>`);
  } catch (e) { toast(e.message, 'error'); }
}

function openFichaModal(ficha = null, presetProductId = null) {
  const isEdit = !!ficha;
  const ap = state.products.filter(p => p.active);
  if (!ap.length) { toast('Registre un producto activo primero.', 'error'); return; }
  if (!state.materials.length) { toast('Registre un valor de referencia primero.', 'error'); return; }
  const pid = Number(ficha?.product_id || presetProductId || ap[0].id);
  const sel = ap.find(p => p.id === pid) || ap[0];
  const lines = ficha?.items?.map(i => ({ materialId: i.material_id, description: i.description, quantity: i.quantity, unit: i.unit, unitCost: i.unit_cost })) || [];
  const defaultUnit = sel.yield_unit || (/comida/i.test(sel.category) ? 'comensales' : /bebida/i.test(sel.category) ? 'copas' : 'unidad');

  showModal(isEdit ? 'Editar ficha' : 'Nueva ficha de costo', isEdit ? `Versión ${ficha.version}` : 'Se creará en estado borrador. Indique cuántas raciones, copas o comensales salen del lote.', `
    <form id="ff"><div class="form-grid">
      <div class="form-field full"><label>Producto *</label><select id="f-prod" ${isEdit ? 'disabled' : ''}>${ap.map(p => `<option value="${p.id}" ${p.id === pid ? 'selected' : ''}>${esc(p.name)} (${esc(p.code)})</option>`).join('')}</select></div>
      <div class="form-field"><label>Rinde (cantidad del lote) *</label><input id="f-yield" type="number" step="0.01" min="0.01" required value="${esc(ficha?.yield_qty || sel.yield_qty || 1)}"><span class="form-hint">Ej.: 20 comensales, 15 copas.</span></div>
      <div class="form-field"><label>Unidad del rendimiento</label><select id="f-yield-unit">${yieldUnitOptions(ficha?.yield_unit || defaultUnit)}</select></div>
      <div class="form-field"><label>Vigente desde</label><input id="f-date" type="date" value="${ficha?.valid_from || new Date().toISOString().slice(0, 10)}"></div>
      <div class="form-field full"><label>Observaciones</label><textarea id="f-notes">${esc(ficha?.observations || '')}</textarea></div>
    </div>
    <div class="line-builder">
      <div class="line-builder-head"><b>Componentes del lote</b><span id="line-total" class="amount">Total: $ 0.00 CUP</span></div>
      <div class="line-entry">
        <div class="form-field"><label>Valor del IPV</label><select id="f-mat">${state.materials.map(m => `<option value="${m.id}" data-price="${m.unit_price ?? ''}" data-unit="${esc(m.unit)}" data-name="${esc(m.name)}">${esc(m.name)} (${esc(m.code)}) — ${m.unit_price === null || m.unit_price === undefined ? '🔒 costos protegidos' : `${money(m.unit_price)}/${esc(m.unit)}`}</option>`).join('')}</select></div>
        <div class="form-field"><label>Cantidad del lote</label><input id="f-qty" type="number" step="0.001" min="0.001" placeholder="0"></div>
        <div class="form-field">&nbsp;<button type="button" class="secondary-btn add-line-btn" id="add-line">＋ Añadir</button></div>
        <div class="form-field">&nbsp;<button type="button" class="secondary-btn add-line-btn" id="new-material" title="Crear un valor del IPV sin salir de esta ficha">＋ Valor</button></div>
      </div>
      <div class="line-list" id="line-list"></div>
      <div class="yield-preview" id="yield-preview"></div>
    </div>
    <div class="modal-actions"><button type="button" class="secondary-btn" data-action="close-modal">Cancelar</button><button class="primary-btn" type="submit">${isEdit ? 'Guardar' : 'Crear borrador'}</button></div></form>`);

  function renderLines() {
    let t = 0;
    const verCostos = canSeeCosts('materials');  // sin permiso, el total se calcula al guardar
    $('#line-list').innerHTML = lines.map((l, i) => {
      const s = (parseFloat(l.quantity) || 0) * (parseFloat(l.unitCost) || 0);
      t += s;
      return `<div class="line-chip"><span class="line-num" title="Número de orden del componente">${i + 1}</span><span class="line-text">${esc(l.description)} · ${dec(l.quantity)} ${esc(l.unit)}</span><b>${verCostos ? money(s) : '🔒'}</b><button type="button" class="remove-line" data-idx="${i}" aria-label="Quitar">×</button></div>`;
    }).join('');
    $('#line-total').textContent = verCostos ? `Total del lote: ${money(t.toFixed(2))}` : 'Total del lote: 🔒 costos protegidos';
    $$('.remove-line', $('#line-list')).forEach(b => b.addEventListener('click', () => { lines.splice(+b.dataset.idx, 1); renderLines(); }));
    renderYield();
  }
  function renderYield() {
    const y = parseFloat($('#f-yield').value) || 1;
    const unit = $('#f-yield-unit').value;
    const total = lines.reduce((s, l) => s + (parseFloat(l.quantity) || 0) * (parseFloat(l.unitCost) || 0), 0);
    $('#yield-preview').innerHTML = lines.length
      ? (canSeeCosts('materials')
        ? `<b>Con ${dec(y)} ${esc(unit)}</b> el costo por ${esc(unit.replace(/s$/, ''))} es <b>${money((total / y).toFixed(2))}</b> · total del lote ${money(total.toFixed(2))}`
        : `<b>Con ${dec(y)} ${esc(unit)}</b> el costo se calculará al guardar: su usuario no puede ver importes.`)
      : 'Añada componentes para ver el costo por comensal, copa o vaso.';
  }
  renderLines();
  $('#f-yield').addEventListener('input', renderYield);
  $('#f-yield-unit').addEventListener('change', renderYield);
  $('#add-line').addEventListener('click', () => {
    const s = $('#f-mat'), o = s.options[s.selectedIndex], q = parseFloat($('#f-qty').value);
    if (!q || q <= 0) { toast('Cantidad mayor que cero.', 'error'); return; }
    lines.push({ materialId: +s.value, description: o.dataset.name, quantity: String(q), unit: o.dataset.unit, unitCost: o.dataset.price });
    $('#f-qty').value = ''; renderLines();
  });
  $('#new-material').addEventListener('click', () => { preserveModal(); openMaterialModal(null, true); });
  // Permite que un valor creado desde otro formulario se añada a este lote
  window.__fichaDraft = {
    add(m) {
      const sel = $('#f-mat');
      if (sel && !sel.querySelector(`option[value="${m.id}"]`)) {
        sel.insertAdjacentHTML('beforeend', `<option value="${m.id}" data-price="${esc(m.unit_price ?? '')}" data-unit="${esc(m.unit)}" data-name="${esc(m.name)}">${esc(m.name)} (${esc(m.code)}) — ${m.unit_price === null || m.unit_price === undefined ? '🔒 costos protegidos' : `${money(m.unit_price)}/${esc(m.unit)}`}</option>`);
        sel.value = String(m.id);
      }
      $('#f-qty').value = '1';
      toast(`«${m.name}» añadido a la lista. Indique la cantidad del lote.`, 'success');
    },
  };
  $('#ff').addEventListener('submit', async e => {
    e.preventDefault();
    if (!lines.length) { toast('Añada al menos un componente.', 'error'); return; }
    const payload = { product_id: isEdit ? ficha.product_id : +$('#f-prod').value, valid_from: $('#f-date').value,
      observations: $('#f-notes').value, yield_qty: $('#f-yield').value, yield_unit: $('#f-yield-unit').value,
      items: lines.map(l => ({ material_id: l.materialId, quantity: l.quantity })) };
    try {
      if (isEdit) await api(`/api/fichas/${ficha.id}`, { method: 'PUT', body: JSON.stringify(payload) });
      else await api('/api/fichas', { method: 'POST', body: JSON.stringify(payload) });
      window.__fichaDraft = null;
      closeModal(); await refreshData(true);
      toast(isEdit ? 'Ficha actualizada.' : 'Ficha creada como borrador.', 'success');
    } catch (err) { toast(err.message, 'error'); }
  });
}

/* ── Detail views ── */
async function openFichaDetail(id) {
  try {
    const f = await api(`/api/fichas/${id}`);
    const lines = f.items.map((i, n) => `<tr>${idTd(n, i.material_id)}<td>${esc(i.description)}${i.material_code ? `<br><small style="color:var(--text-4)">${esc(i.material_code)}</small>` : ''}</td><td>${dec(i.quantity)} ${esc(i.unit)}</td><td>${i.per_serving ? `<span class="used-chip">${esc(i.per_serving)} ${esc(i.unit)} / ${esc(f.yield_unit)}</span>` : '—'}</td><td class="amount">${money(i.unit_cost)}</td><td class="amount">${money(i.subtotal)}</td></tr>`).join('');
    const srv = f.servings_from_stock;
    const srvBox = `<div class="detail-box"><span>Con el inventario actual</span><b style="color:${srv === 0 ? 'var(--red)' : 'var(--green)'}">${srv === null || srv === undefined ? '—' : `≈ ${dec(srv)} ${esc(f.yield_unit || '')}`}</b>${f.limited_by ? `<small style="color:var(--text-4)">limitado por ${esc(f.limited_by)}</small>` : ''}</div>`;
    const shortages = (f.shortages || []).length
      ? `<div class="small-note" style="color:var(--red)">⚠ Faltan existencias de: ${f.shortages.map(s => `${esc(s.material)} (${esc(s.stock)} de ${esc(s.required)} ${esc(f.yield_unit)})`).join(' · ')}</div>`
      : '';
    showModal(`Ficha de Costo · v${f.version}`, `${f.product_code} · ${f.product_name}`, `
      <div class="detail-grid">
        <div class="detail-box"><span>Producto</span><b>${esc(f.product_name)} · ${esc(f.category)}</b></div>
        <div class="detail-box"><span>Versión / estado</span><b>v${f.version} · ${esc(f.status)}</b></div>
        <div class="detail-box"><span>Vigente desde</span><b>${dateLabel(f.valid_from)}</b></div>
        <div class="detail-box"><span>Rinde</span><b>${yieldBadge(f.yield_qty, f.yield_unit)}</b></div>
        <div class="detail-box"><span>Costo del lote</span><b>${money(f.total_cost)}</b></div>
        <div class="detail-box"><span>Costo por ${esc((f.yield_unit || 'unidad').replace(/s$/, ''))}</span><b>${money(f.cost_per_serving)}</b></div>
        ${srvBox}
      </div>${shortages}
      <div class="table-wrap"><table style="min-width:700px"><thead><tr>${idTh()}<th>Componente</th><th>Lote</th><th>Por ${esc((f.yield_unit || 'unidad').replace(/s$/, ''))}</th><th>Precio</th><th>Subtotal</th></tr></thead><tbody>${lines}</tbody></table></div>
      ${f.observations ? `<div class="small-note">${esc(f.observations)}</div>` : ''}
      <div class="modal-actions">
        <button class="secondary-btn" data-action="close-modal">Cerrar</button>
        <button class="danger-btn" data-action="trash-ficha" data-id="${f.id}">Mover a la papelera</button>
        ${f.status === 'Borrador' ? `<button class="secondary-btn" data-action="edit-ficha" data-id="${f.id}">Editar</button><button class="primary-btn" data-action="approve-ficha" data-id="${f.id}">Aprobar ficha</button>` : `<button class="primary-btn" data-action="generate-control" data-id="${f.id}">＋ Generar Control IPV</button>`}
      </div>`);
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
    const lines = c.items.map((i, n) => `<tr>${idTd(n)}<td>${esc(i.description)}</td><td>${dec(i.quantity)} ${esc(i.unit)}</td><td class="amount">${money(i.unit_cost)}</td><td class="amount">${money(i.subtotal)}</td></tr>`).join('');
    const msgs = (c.validation_messages || []).map(m => `<div class="small-note" style="margin-top:8px;color:${m.type === 'error' ? 'var(--red)' : m.type === 'success' ? 'var(--green)' : 'var(--text-3)'}">${m.type === 'error' ? '⚠ ' : m.type === 'success' ? '✓ ' : '• '}${esc(m.text)}</div>`).join('');
    showModal(`Control IPV · ${c.code}`, `${c.product_code} · ${c.product_name}`, `<div class="detail-grid"><div class="detail-box"><span>Producto / ficha</span><b>${esc(c.product_name)} · v${c.ficha_version}</b></div><div class="detail-box"><span>Período / estado</span><b>${esc(c.period)} · ${esc(c.status)}</b></div><div class="detail-box"><span>Total del lote</span><b>${money(c.snapshot_total)}</b></div><div class="detail-box"><span>Costo por ${esc((c.yield_unit || 'unidad').replace(/s$/, ''))}</span><b>${money(c.cost_per_serving)}</b></div><div class="detail-box"><span>Verificado</span><b>${c.checked_at ? money(c.checked_total) : 'Sin validar'}</b></div></div><div class="table-wrap"><table><thead><tr>${idTh()}<th>Componente</th><th>Cantidad</th><th>Precio</th><th>Subtotal</th></tr></thead><tbody>${lines}</tbody></table></div>${msgs}<div class="modal-actions"><button class="secondary-btn" data-action="close-modal">Cerrar</button><button class="danger-btn" data-action="trash-control" data-id="${c.id}">Mover a la papelera</button>${c.status !== 'Validado' ? `<button class="primary-btn" data-action="validate-control" data-id="${c.id}">Ejecutar validación</button>` : ''}</div>`);
  } catch (e) { toast(e.message, 'error'); }
}
async function validateControl(id) { try { const c = await api(`/api/controls/${id}/validate`, { method: 'POST', body: '{}' }); await refreshData(true); openControlDetail(c.id); toast(c.status === 'Validado' ? 'Control validado.' : 'Se encontraron observaciones.', c.status === 'Validado' ? 'success' : 'error'); } catch (e) { toast(e.message, 'error'); } }

/* ── CSV Export ── */
function exportCsv(type) {
  /* Sistema de Seguridad por Usuarios: sin permiso de vista no hay datos que exportar,
     y sin permiso de costos el CSV sale sin columnas de precio ni importes. */
  const modulo = { products: 'products', materials: 'materials', inventory: 'materials',
    fichas: 'fichas', controls: 'controls' }[type];
  if (modulo && !canSee(modulo)) { toast('Su usuario no tiene permiso para exportar este apartado.', 'error'); return; }
  const costos = canSeeCosts('materials');
  let rows = [], fn = 'export.csv';
  if (type === 'products') { fn = 'productos.csv'; rows = [['Id', 'Código', 'Nombre', 'Categoría', 'Unidad', 'Rinde', 'Unidad rinde', 'Fichas', 'Estado'], ...state.products.map((p, i) => [i + 1, p.code, p.name, p.category, p.unit, p.last_yield_qty || p.yield_qty, p.last_yield_unit || p.yield_unit, p.ficha_count, p.active ? 'Activo' : 'Inactivo'])]; }
  else if (type === 'materials') { fn = 'valores-ipv.csv'; rows = [['Id', 'Código', 'Nombre', 'Categoría', 'Unidad', ...(costos ? ['Precio', 'Moneda'] : []), 'Existencias', 'Mínimo', 'Proveedor', 'Fuente', 'Vigencia', 'Estado'], ...state.materials.map((m, i) => [i + 1, m.code, m.name, m.category, m.unit, ...(costos ? [m.unit_price, m.currency] : []), m.stock, m.min_stock, m.supplier, m.source, m.effective_from, m.status])]; }
  else if (type === 'inventory') { const inv = state.inventory || { items: [] }; fn = 'inventario.csv'; rows = [['Id', 'Código', 'Nombre', 'Categoría', 'Unidad', 'Existencias', 'Mínimo', ...(costos ? ['Precio', 'Valor total'] : []), 'Recetas'], ...inv.items.map((m, i) => [i + 1, m.code, m.name, m.category, m.unit, m.stock, m.min_stock, ...(costos ? [m.unit_price, m.stock_value] : []), m.used_by.map(u => `${u.product_name} (${u.per_serving} ${m.unit}/${u.yield_unit})`).join(' | ')])]; }
  else if (type === 'fichas') { fn = 'fichas.csv'; rows = [['Id', 'Producto', 'Código', 'Categoría', 'Versión', 'Vigente', 'Rinde', 'Unidad rinde', 'Total lote', 'Costo por unidad', 'Con inventario', 'Estado'], ...state.fichas.map((f, i) => [i + 1, f.product_name, f.product_code, f.category, f.version, f.valid_from, f.yield_qty, f.yield_unit, f.total_cost, f.cost_per_serving, f.servings_from_stock ?? '', f.status])]; }
  else { fn = 'controles.csv'; rows = [['Id', 'Control', 'Producto', 'Código', 'Período', 'Ficha', 'Total', 'Estado'], ...state.controls.map((c, i) => [i + 1, c.code, c.product_name, c.product_code, c.period, c.ficha_version, c.snapshot_total, c.status])]; }
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
    ...state.materials.filter(m => `${m.name} ${m.code}`.toLowerCase().includes(q)).slice(0, 3).map(m => ({ type: 'Valor', name: m.name, sub: canSeeCosts() ? `${money(m.unit_price)} / ${m.unit}` : `${m.unit} · costos protegidos`, action: '', id: 0 })),
    ...state.controls.filter(c => `${c.code} ${c.product_name}`.toLowerCase().includes(q)).slice(0, 3).map(c => ({ type: 'Control', name: c.code, sub: `${c.product_name} · ${c.status}`, action: 'view-control', id: c.id })),
  ];
  const overlay = $('#search-overlay');
  const container = $('#search-results');
  if (!results.length) { container.innerHTML = '<div style="padding:24px;text-align:center;color:var(--text-3)">Sin resultados</div>'; }
  else { container.innerHTML = results.map(r => `<div class="search-result-item" data-action="${r.action}" data-id="${r.id}" style="padding:12px 16px;cursor:pointer;border-radius:var(--radius-sm);transition:background .15s;display:flex;justify-content:space-between;align-items:center"><div><b style="font-size:12px;color:var(--text)">${esc(r.name)}</b><div style="font-size:10px;color:var(--text-3)">${esc(r.sub)}</div></div><span class="status" style="font-size:8px">${esc(r.type)}</span></div>`).join(''); }
  overlay.hidden = false;
}

/* ── Acciones compartidas entre la página y los diálogos ── */
async function loadEntity(kind, id) {
  const url = { material: '/api/materials/', product: '/api/products/', ficha: '/api/fichas/' }[kind] + id;
  return api(url);
}
async function adjustStock(id, delta) {
  const m = await api(`/api/materials/${id}/stock`, { method: 'POST', body: JSON.stringify({ delta: String(delta) }) });
  await refreshData(true);
  toast(`«${m.name}»: ${dec(m.stock)} ${m.unit} en almacén.`, 'success');
  return m;
}
async function saveStock(id) {
  const input = $(`[data-stock-input="${id}"]`);
  if (!input) return;
  try {
    const m = await api(`/api/materials/${id}/stock`, { method: 'POST', body: JSON.stringify({ set: input.value }) });
    await refreshData(true);
    toast(`Existencias de «${m.name}» actualizadas a ${dec(m.stock)} ${m.unit}.`, 'success');
  } catch (err) { toast(err.message, 'error'); }
}
async function moveToTrash(kind, id) {
  const nouns = { material: ['el valor del IPV', 'Valor del IPV'], product: ['el producto', 'Producto'],
    ficha: ['la ficha de costo', 'Ficha de costo'], control: ['el control', 'Control de IPV'] };
  const [article, label] = nouns[kind] || nouns.material;
  const ok = await confirm2(`Mover ${article} a la papelera`,
    `El elemento dejará de aparecer en las listas, pero podrá restaurarlo desde la Papelera de reciclaje.`, 'warning');
  if (!ok) return;
  try {
    await api(`/api/${kind === 'material' ? 'materials' : kind === 'product' ? 'products' : kind + 's'}/${id}`, { method: 'DELETE' });
    closeModal(); await refreshData(true);
    toast(`${label} movido a la papelera. Puede restaurarlo cuando quiera.`, 'success');
  } catch (err) { toast(err.message, 'error'); }
}
async function restoreFromTrash(kind, id) {
  try {
    await api(`/api/trash/${kind}/${id}/restore`, { method: 'POST', body: '{}' });
    await refreshData(true);
    toast('Elemento restaurado.', 'success');
  } catch (err) { toast(err.message, 'error'); }
}
async function purgeFromTrash(kind, id) {
  const ok = await confirm2('Borrado definitivo',
    'Se eliminará para siempre, junto con sus fichas y controles dependientes. Esta acción no se puede deshacer.', 'danger');
  if (!ok) return;
  try {
    await api(`/api/trash/${kind}/${id}`, { method: 'DELETE' });
    await refreshData(true);
    toast('Elemento borrado definitivamente.', 'success');
  } catch (err) { toast(err.message, 'error'); }
}
async function emptyTrash() {
  const ok = await confirm2('Vaciar la papelera',
    `Se borrarán definitivamente los ${state.trash.length} elemento(s) de la papelera y sus documentos derivados.`, 'danger');
  if (!ok) return;
  try {
    const r = await api('/api/trash/empty', { method: 'POST', body: '{}' });
    await refreshData(true);
    toast(`Papelera vaciada: ${r.removed} elemento(s) eliminado(s).`, 'success');
  } catch (err) { toast(err.message, 'error'); }
}
async function seedDemo() {
  const ok = await confirm2('Cargar datos de prueba',
    'Se añadirán inventarios, productos y fichas de ejemplo (comidas con comensales, bebidas con licores de distintos IPV) para poder aprender el sistema. No se borra nada de lo que ya tenga.', 'info');
  if (!ok) return;
  try {
    const r = await api('/api/demo/seed', { method: 'POST', body: '{}' });
    await refreshData(true);
    const n = Object.values(r).reduce((a, b) => a + b, 0);
    toast(n ? `Datos de prueba cargados: ${n} registros nuevos.` : 'Ya estaban cargados los datos de prueba.', 'success');
  } catch (err) { toast(err.message, 'error'); }
}
async function editEntity(kind, id) {
  try { openKindModal(kind, await loadEntity(kind, id)); }
  catch (err) { toast(err.message, 'error'); }
}
function openKindModal(kind, entity) {
  if (kind === 'material') openMaterialModal(entity);
  else if (kind === 'product') openProductModal(entity);
  else openFichaModal(entity);
}
async function viewEntity(kind, id) {
  if (kind === 'material') return openMaterialDetail(id);
  if (kind === 'product') return openProductDetail(id);
  if (kind === 'ficha') return openFichaDetail(id);
  return openControlDetail(id);
}

async function runAction(action, id, el, extra = {}) {
  const exige = ACTION_PERMISSION[action];
  if (exige && !canDo(exige[0], exige[1])) {
    toast(`Su usuario no tiene permiso para esa acción en «${MODULE_LABEL[exige[0]] || exige[0]}».`, 'error');
    return;
  }
  const kind = { 'view-material': 'material', 'edit-material': 'material', 'trash-material': 'material',
    'view-product': 'product', 'edit-product': 'product', 'trash-product': 'product',
    'view-ficha': 'ficha', 'edit-ficha': 'ficha', 'trash-ficha': 'ficha',
    'trash-control': 'control' }[action];
  switch (action) {
    case 'refresh': return refreshData();
    case 'create-product': return openProductModal();
    case 'create-material': return openMaterialModal();
    case 'create-ficha': return openFichaModal(null, extra.productId ? Number(extra.productId) : null);
    case 'view-ficha': return openFichaDetail(id);
    case 'approve-ficha': return approveFicha(id);
    case 'generate-control': return openGenerateControl(id);
    case 'view-control': return openControlDetail(id);
    case 'validate-control': return validateControl(id);
    case 'export-products': return exportCsv('products');
    case 'export-materials': return exportCsv('materials');
    case 'export-fichas': return exportCsv('fichas');
    case 'export-controls': return exportCsv('controls');
    case 'export-inventory': return exportCsv('inventory');
    case 'close-modal': return closeModal();
    case 'seed-demo': return seedDemo();
    case 'stock-plus': return adjustStock(id, 1);
    case 'stock-minus': return adjustStock(id, -1);
    case 'stock-save': return saveStock(id);
    case 'restore-trash': return restoreFromTrash(el.dataset.kind, id);
    case 'purge-trash': return purgeFromTrash(el.dataset.kind, id);
    case 'empty-trash': return emptyTrash();
    case 'open-license': return window.IPVLicense?.renew();
    case 'reload-license': return loadLicenseInto($('#lic-body'));
    case 'open-creator': return setView('creator');
    case 'creator-refresh': return loadCreatorInto($('#creator-body'));
    case 'creator-ledger': return loadCreatorLedger();
    case 'creator-copy': {
      const src = $(el.dataset.target);
      await navigator.clipboard.writeText(src?.value || src?.textContent || '').catch(() => {});
      return toast('Copiado al portapapeles.', 'success');
    }
    case 'creator-activate-here': {
      const token = $('#creator-token')?.value || '';
      if (!token) return;
      const auth = window.IPVAuth ? window.IPVAuth.headers() : {};
      const r = await fetch('/api/license', { method: 'POST', headers: { 'Content-Type': 'application/json', ...auth }, body: JSON.stringify({ license: token }) });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.error || `Error ${r.status}`);
      toast('🔓 Licencia de este equipo activada.', 'success');
      setTimeout(() => location.reload(), 900);
      return;
    }
    case 'copy-device': {
      await navigator.clipboard.writeText(state.license?.request_code || '').catch(() => {});
      return toast('ID del equipo copiado.', 'success');
    }
    case 'whatsapp-license': return window.IPVLicense?.show(state.license, { closable: true });
    case 'view-fichas-of-material': {
      closeModal();
      const m = state.materials.find(x => String(x.id) === String(id));
      setView('fichas');
      setTimeout(() => { state.search = m ? m.name : ''; renderFichas(); }, 60);
      return;
    }
    case 'create-ficha-for': { closeModal(); return openFichaModal(null, id); }
    case 'view-product-search': return openProductDetail(id);
    default:
      if (kind) {
        if (action.startsWith('view-')) return viewEntity(kind, id);
        if (action.startsWith('edit-')) return editEntity(kind, id);
        if (action.startsWith('trash-')) return moveToTrash(kind, id);
      }
      return undefined;
  }
}

/* ── Event Delegation ── */
modalLayer.addEventListener('click', async e => {
  const b = e.target.closest('[data-action]'); if (!b) return;
  const { action, id } = b.dataset;
  try {
    if (action === 'edit-ficha') { const f = await api(`/api/fichas/${id}`); openFichaModal(f); return; }
    if (action === 'edit-material') { preserveModal(); openMaterialModal(await api(`/api/materials/${id}`)); return; }
    if (action === 'edit-product') { preserveModal(); openProductModal(await api(`/api/products/${id}`)); return; }
    if (action === 'view-fichas-of-material') { await runAction(action, id, b); return; }
    await runAction(action, id, b);
  } catch (err) { toast(err.message, 'error'); }
});

content.addEventListener('click', async e => {
  const nav = e.target.closest('[data-view]'); if (nav) { setView(nav.dataset.view); return; }
  const b = e.target.closest('[data-action]'); if (!b) return;
  try { await runAction(b.dataset.action, b.dataset.id, b, { productId: b.dataset.id }); }
  catch (err) { toast(err.message, 'error'); }
});

// Search overlay clicks
$('#search-overlay').addEventListener('click', async e => {
  const item = e.target.closest('[data-action]');
  if (item && item.dataset.action) {
    $('#search-overlay').hidden = true; $('#global-search').value = '';
    const { action, id } = item.dataset;
    if (action === 'view-ficha') openFichaDetail(id);
    else if (action === 'view-control') openControlDetail(id);
    else if (action === 'view-product') openProductDetail(id);
    else if (action === 'view-material') openMaterialDetail(id);
  } else if (e.target === $('#search-overlay')) { $('#search-overlay').hidden = true; $('#global-search').value = ''; }
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
    const byKey = { '1': 'dashboard', '2': 'products', '3': 'materials', '4': 'inventory',
      '5': 'fichas', '6': 'controls', '7': 'trash', '8': 'license', '9': 'creator' };
    if (byKey[e.key]) setView(byKey[e.key]);
  }
});

/* El Creador de Licencias solo se muestra a administradores (o en modo abierto) */
function updateCreatorNav() {
  const u = window.IPVAuth ? window.IPVAuth.user : null;
  const btn = $('#nav-creator');
  if (btn) btn.style.display = (!u || u.role === 'admin') ? '' : 'none';
}
document.addEventListener('ipv:auth', async () => {
  updateCreatorNav();
  const antes = JSON.stringify(window.IPVAuth?.permissions?.() || null);
  /* Los permisos los guarda el servidor: se vuelven a leer al entrar, al renovar
     la sesión y al recargar, por si el administrador los cambió en caliente. */
  const ahora = JSON.stringify((await window.IPVAuth?.reloadPermissions?.()) || null);
  applyPermissionNav();
  if ((!window.IPVAuth || window.IPVAuth.user) && state.dashboard && ahora !== antes) refreshData(true);
});

/* ── Init ── */
updateCreatorNav();
applyPermissionNav();
/* enterprise.js define IPVAuth (sesión + permisos) un instante después de app.js:
   se espera para que la primera carga de datos viaje ya autenticada. Sin esto, el
   primer lote de peticiones salía sin cabecera y terminaba en 401 + renovación. */
(async function boot() {
  for (let i = 0; i < 40 && !window.IPVAuth; i++) await new Promise(r => setTimeout(r, 25));
  if (window.IPVAuth?.user) {
    await window.IPVAuth.reloadPermissions?.();
    applyPermissionNav();
  }
  refreshData();
})();

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

/* ── Keyboard shortcut overlay ── */
function showShortcutsHelp() {
  showModal('Atajos de teclado', 'Navega más rápido por el sistema', `
    <div style="display:grid;gap:10px">
      <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)"><span style="font-size:12px">Ir a Resumen</span><div class="kbd-hint"><kbd>1</kbd></div></div>
      <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)"><span style="font-size:12px">Ir a Productos</span><div class="kbd-hint"><kbd>2</kbd></div></div>
      <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)"><span style="font-size:12px">Ir a Valores del IPV (pestaña Valores)</span><div class="kbd-hint"><kbd>3</kbd></div></div>
      <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)"><span style="font-size:12px">Ir a Valores del IPV (pestaña Inventario)</span><div class="kbd-hint"><kbd>4</kbd></div></div>
      <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)"><span style="font-size:12px">Ir a Fichas</span><div class="kbd-hint"><kbd>5</kbd></div></div>
      <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)"><span style="font-size:12px">Ir a Controles</span><div class="kbd-hint"><kbd>6</kbd></div></div>
      <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)"><span style="font-size:12px">Ir a Papelera</span><div class="kbd-hint"><kbd>7</kbd></div></div>
      <div style="display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border)"><span style="font-size:12px">Ir a Licencia</span><div class="kbd-hint"><kbd>8</kbd></div></div>
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
              ${idTh()}
              <th>Producto</th>
              <th>Código</th>
              <th>Versión</th>
              <th style="text-align:right">Costo Total</th>
            </tr>
          </thead>
          <tbody>
            ${(stats.top_expensive || []).map((p, i) => `
              <tr>
                ${idTd(i, p.id)}
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
const QUICK_TILES = [
  ['create-material', '◈', 'Nuevo Valor del IPV', 'Licor, insumo, bebida o servicio con precio y existencias'],
  ['create-product', '▦', 'Nuevo Producto', 'Agregar al catálogo de comidas, bebidas o servicios'],
  ['create-ficha', '▤', 'Nueva Ficha de Costo', 'Documento versionado con rendimiento y componentes'],
];
function addFAB() {
  if ($('#fab-main')) return;
  const fab = document.createElement('button');
  fab.id = 'fab-main';
  fab.className = 'fab';
  fab.innerHTML = '＋';
  fab.setAttribute('aria-label', 'Acciones rápidas');
  fab.addEventListener('click', () => {
    showModal('Acciones rápidas', 'Disponible en cualquier apartado del sistema', `
      <div class="quick-grid">
        ${QUICK_TILES.filter(([a]) => { const e = ACTION_PERMISSION[a]; return !e || canDo(e[0], e[1]); })
          .map(([a, i, t, s]) => `<button class="quick-tile" data-action="${a}"><span>${i}</span><b>${t}</b><small>${s}</small></button>`).join('')}
        ${canSee('materials') ? '<button class="quick-tile" data-view="inventory"><span>▣</span><b>Ver inventario</b><small>Cuánto queda y para qué se usa</small></button>' : ''}
        ${canSee('trash') ? '<button class="quick-tile" data-view="trash"><span>🗑</span><b>Papelera</b><small>Restaurar o borrar definitivamente</small></button>' : ''}
        ${canEdit('materials') ? '<button class="quick-tile" data-action="seed-demo"><span>🧪</span><b>Datos de prueba</b><small>Catálogo de ejemplo para aprender</small></button>' : ''}
      </div>
      <div class="modal-actions"><button class="secondary-btn" data-action="close-modal">Cerrar</button></div>`);
  });
  document.body.appendChild(fab);
}

/* ── Quick Actions Handler ── */
modalLayer.addEventListener('click', async e => {
  const nav = e.target.closest('[data-view]');
  if (nav) { closeModal(); setTimeout(() => setView(nav.dataset.view), 120); return; }
  const btn = e.target.closest('[data-action]');
  if (!btn) return;
  if (QUICK_TILES.some(t => t[0] === btn.dataset.action) || btn.dataset.action === 'seed-demo') {
    const action = btn.dataset.action;
    closeModal();
    await refreshData(true);
    setTimeout(() => runAction(action), 140);
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
const REPORT_MODULE = { materials_inventory: 'materials', fichas_summary: 'fichas', controls_pending: 'controls' };
async function exportReport(type) {
  const modulo = REPORT_MODULE[type];
  if (modulo && !canSee(modulo)) {
    toast(`Su usuario no tiene permiso para consultar «${MODULE_LABEL[modulo]}».`, 'error');
    return;
  }
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
  if (!canSee('fichas')) { toast('Su usuario no tiene permiso para ver las estadísticas de costos.', 'error'); return; }
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
