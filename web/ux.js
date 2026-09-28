'use strict';
/* ==========================================================================
   IPV · Fichas y Costos — Experiencia de usuario Premium
   Autor: Ing. Yosvany Hernández Quintero

   · Deshacer / Rehacer (Ctrl+Z / Ctrl+Shift+Z) para desactivaciones
   · Filtros guardados por vista
   · Tablas grandes con renderizado progresivo y navegación por teclado
   · Panel de resumen personalizable (ocultar y reordenar)
   · Tutorial interactivo de bienvenida
   · Accesibilidad: foco atrapado en diálogos, enlace «saltar al contenido»,
     alto contraste, tamaño de texto y respeto a «reducir movimiento»
   ========================================================================== */
(() => {
  const store = {
    get(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } },
    set(k, v) { localStorage.setItem(k, JSON.stringify(v)); },
  };

  /* ───────────── Aviso con acción ───────────── */
  function actionToast(msg, label, onAction, ms = 8000) {
    const stack = document.getElementById('toast-stack');
    const el = document.createElement('div');
    el.className = 'toast success toast-action';
    el.setAttribute('role', 'status');
    el.innerHTML = `<span></span><button type="button"></button><i class="toast-timer" style="animation-duration:${ms}ms"></i>`;
    el.querySelector('span').textContent = msg;
    const btn = el.querySelector('button');
    btn.textContent = label;
    let done = false;
    const close = () => { if (!done) { done = true; el.style.opacity = '0'; setTimeout(() => el.remove(), 300); } };
    btn.onclick = async () => { close(); await onAction(); };
    stack.appendChild(el);
    setTimeout(close, ms);
  }

  /* ───────────── Deshacer / Rehacer (borrado lógico → papelera) ───────────── */
  const undoStack = [], redoStack = [];
  const KIND = {
    'trash-product': { kind: 'products', label: 'Producto', list: () => state.products, name: x => x.name },
    'trash-material': { kind: 'materials', label: 'Valor del IPV', list: () => state.materials, name: x => x.name },
    'trash-ficha': { kind: 'fichas', label: 'Ficha de costo', list: () => state.fichas, name: x => `${x.product_name} v${x.version}` },
    'deactivate-product': { kind: 'products', label: 'Producto', list: () => state.products, name: x => x.name },
    'deactivate-material': { kind: 'materials', label: 'Valor del IPV', list: () => state.materials, name: x => x.name },
  };
  async function doDeactivate(kind, id) {
    await api(`/api/${KIND[kind].kind}/${id}`, { method: 'DELETE' });
    await refreshData(true);
  }
  async function doRestore(kind, id) {
    await api(`/api/trash/${KIND[kind].kind}/${id}/restore`, { method: 'POST', body: '{}' });
    await refreshData(true);
  }
  async function undo() {
    const op = undoStack.pop();
    if (!op) { toast('No hay nada que deshacer.'); return; }
    try { await doRestore(op.kind, op.id); redoStack.push(op); toast(`↶ ${op.name} restaurado.`, 'success'); }
    catch (e) { toast(e.message, 'error'); }
  }
  async function redo() {
    const op = redoStack.pop();
    if (!op) { toast('No hay nada que rehacer.'); return; }
    try { await doDeactivate(op.kind, op.id); undoStack.push(op); toast(`↷ ${op.name} vuelve a la papelera.`); }
    catch (e) { toast(e.message, 'error'); }
  }
  // Se intercepta en fase de captura, antes que la confirmación de app.js
  document.addEventListener('click', async e => {
    const btn = e.target.closest('[data-action="trash-product"],[data-action="trash-material"],[data-action="trash-ficha"],[data-action="deactivate-product"],[data-action="deactivate-material"]');
    if (!btn) return;
    const kind = btn.dataset.action, id = btn.dataset.id;
    if (!KIND[kind]) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    const item = KIND[kind].list().find(x => String(x.id) === String(id));
    const name = item ? KIND[kind].name(item) : KIND[kind].label;
    btn.disabled = true;
    try {
      await doDeactivate(kind, id);
      const op = { kind, id, name };
      undoStack.push(op); redoStack.length = 0;
      if (undoStack.length > 30) undoStack.shift();
      actionToast(`«${name}» movido a la papelera.`, '↶ Deshacer', undo);
    } catch (err) { toast(err.message, 'error'); btn.disabled = false; }
  }, true);
  document.addEventListener('keydown', e => {
    if (!(e.ctrlKey || e.metaKey) || /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName)) return;
    const k = e.key.toLowerCase();
    if (k === 'z' && !e.shiftKey) { e.preventDefault(); undo(); }
    else if ((k === 'z' && e.shiftKey) || k === 'y') { e.preventDefault(); redo(); }
  });

  /* ───────────── Filtros guardados ───────────── */
  const FILTER_KEY = 'ipv.savedFilters';
  function currentFilter() {
    const selects = {};
    document.querySelectorAll('#page-content .toolbar select[id]').forEach(s => { selects[s.id] = s.value; });
    return { search: state.search || '', selects };
  }
  function describe(f) {
    const parts = [];
    if (f.search) parts.push(`«${f.search}»`);
    Object.values(f.selects).filter(Boolean).forEach(v => parts.push(v));
    return parts.join(' · ') || 'Todo';
  }
  function applyFilter(f) {
    state.search = f.search;
    Object.entries(f.selects).forEach(([id, v]) => { const s = document.getElementById(id); if (s) s.value = v; });
    render();
  }
  function enhanceToolbar() {
    const bar = document.querySelector('#page-content .toolbar');
    if (!bar || bar.nextElementSibling?.classList.contains('saved-filters')) return;
    const all = store.get(FILTER_KEY, {});
    const mine = all[state.view] || [];
    const wrap = document.createElement('div');
    wrap.className = 'saved-filters';
    wrap.innerHTML = `<button class="secondary-btn" data-sf="save" title="Guardar los filtros actuales">★ Guardar filtro</button>
      ${mine.map((f, i) => `<span class="sf-chip"><button data-sf="apply" data-i="${i}" title="${esc(describe(f))}">${esc(f.name)}</button><button data-sf="del" data-i="${i}" aria-label="Eliminar filtro ${esc(f.name)}">×</button></span>`).join('')}`;
    bar.after(wrap);
    wrap.onclick = e => {
      const b = e.target.closest('[data-sf]'); if (!b) return;
      const i = +b.dataset.i;
      if (b.dataset.sf === 'save') {
        const f = currentFilter();
        if (!f.search && !Object.values(f.selects).some(Boolean)) { toast('Aplique una búsqueda o un filtro antes de guardarlo.'); return; }
        const name = prompt('Nombre del filtro:', describe(f).slice(0, 40));
        if (!name) return;
        all[state.view] = [...mine, { ...f, name: name.trim().slice(0, 40) }].slice(-8);
        store.set(FILTER_KEY, all); render(); toast('Filtro guardado.', 'success');
      } else if (b.dataset.sf === 'apply') applyFilter(mine[i]);
      else { mine.splice(i, 1); all[state.view] = mine; store.set(FILTER_KEY, all); render(); }
    };
  }

  /* ───────────── Tablas: renderizado progresivo + teclado ───────────── */
  const PAGE = 100;
  function enhanceTables() {
    document.querySelectorAll('#page-content .table-panel table').forEach(table => {
      const rows = [...table.tBodies[0]?.rows || []];
      table.setAttribute('aria-rowcount', rows.length);
      // Navegación por teclado
      rows.forEach((r, i) => { r.tabIndex = i === 0 ? 0 : -1; r.setAttribute('aria-rowindex', i + 1); });
      table.addEventListener('keydown', e => {
        const row = e.target.closest('tr'); if (!row || !row.parentElement.matches('tbody')) return;
        const visible = rows.filter(r => !r.hidden);
        const idx = visible.indexOf(row);
        let next = null;
        if (e.key === 'ArrowDown' || e.key === 'j') next = visible[idx + 1];
        else if (e.key === 'ArrowUp' || e.key === 'k') next = visible[idx - 1];
        else if (e.key === 'Home') next = visible[0];
        else if (e.key === 'End') next = visible[visible.length - 1];
        else if (e.key === 'Enter') { row.querySelector('[data-action^="view-"]')?.click(); e.preventDefault(); return; }
        if (next) { e.preventDefault(); row.tabIndex = -1; next.tabIndex = 0; next.focus(); }
      });
      // Renderizado progresivo
      if (rows.length <= PAGE * 1.5) return;
      rows.slice(PAGE).forEach(r => { r.hidden = true; });
      const more = document.createElement('div');
      more.className = 'load-more';
      const update = () => {
        const shown = rows.filter(r => !r.hidden).length;
        more.innerHTML = shown < rows.length
          ? `<span>Mostrando ${shown} de ${rows.length}</span><button class="secondary-btn">Mostrar ${Math.min(PAGE, rows.length - shown)} más</button>`
          : `<span>${rows.length} registros</span>`;
        more.querySelector('button')?.addEventListener('click', reveal);
      };
      const reveal = () => { rows.filter(r => r.hidden).slice(0, PAGE).forEach(r => { r.hidden = false; }); update(); };
      table.closest('.table-wrap').after(more);
      update();
      if ('IntersectionObserver' in window) {
        const io = new IntersectionObserver(entries => { if (entries[0].isIntersecting && rows.some(r => r.hidden)) reveal(); }, { rootMargin: '300px' });
        io.observe(more);
      }
    });
  }

  /* ───────────── Panel de resumen personalizable ───────────── */
  const DASH_KEY = 'ipv.dashboard.layout';
  const keyOf = el => (el.querySelector('.panel-title, .stat-top span')?.textContent || '').trim();
  function enhanceDashboard() {
    if (state.view !== 'dashboard') return;
    const layout = store.get(DASH_KEY, { hidden: [], order: [] });
    const containers = [document.querySelector('#page-content .stats-grid'), document.querySelector('#page-content .dashboard-grid')].filter(Boolean);
    containers.forEach(c => {
      const items = [...c.children];
      items.sort((a, b) => {
        const ia = layout.order.indexOf(keyOf(a)), ib = layout.order.indexOf(keyOf(b));
        return (ia < 0 ? 999 : ia) - (ib < 0 ? 999 : ib);
      }).forEach(el => c.appendChild(el));
      items.forEach(el => { el.hidden = layout.hidden.includes(keyOf(el)); el.dataset.widget = keyOf(el); });
    });
    const heading = document.querySelector('#page-content .page-heading > div:last-child');
    if (heading && !document.getElementById('customize-dash')) {
      const b = document.createElement('button');
      b.id = 'customize-dash'; b.className = 'secondary-btn'; b.textContent = '⚙ Personalizar';
      b.onclick = () => toggleCustomize(containers);
      heading.prepend(b);
    }
  }
  function toggleCustomize(containers) {
    const on = document.body.classList.toggle('dash-editing');
    const btn = document.getElementById('customize-dash');
    btn.textContent = on ? '✓ Listo' : '⚙ Personalizar';
    const layout = store.get(DASH_KEY, { hidden: [], order: [] });
    containers.forEach(c => [...c.children].forEach(el => {
      if (on) {
        el.hidden = false;
        el.draggable = true;
        el.classList.toggle('widget-off', layout.hidden.includes(el.dataset.widget));
        if (!el.querySelector('.widget-tools')) {
          el.insertAdjacentHTML('afterbegin', `<div class="widget-tools"><span class="drag-handle" aria-hidden="true">⠿</span><button type="button" class="widget-eye" aria-label="Mostrar u ocultar">${layout.hidden.includes(el.dataset.widget) ? '🙈' : '👁'}</button></div>`);
          el.querySelector('.widget-eye').onclick = ev => {
            ev.stopPropagation();
            el.classList.toggle('widget-off');
            ev.currentTarget.textContent = el.classList.contains('widget-off') ? '🙈' : '👁';
          };
        }
        el.ondragstart = ev => { el.classList.add('dragging'); ev.dataTransfer.effectAllowed = 'move'; };
        el.ondragend = () => el.classList.remove('dragging');
        el.ondragover = ev => {
          ev.preventDefault();
          const dragging = c.querySelector('.dragging'); if (!dragging || dragging === el) return;
          const rect = el.getBoundingClientRect();
          const after = (ev.clientX - rect.left) / rect.width > 0.5;
          c.insertBefore(dragging, after ? el.nextSibling : el);
        };
      } else {
        el.draggable = false;
        el.querySelector('.widget-tools')?.remove();
      }
    }));
    if (!on) {
      const all = containers.flatMap(c => [...c.children]);
      store.set(DASH_KEY, { order: all.map(el => el.dataset.widget), hidden: all.filter(el => el.classList.contains('widget-off')).map(el => el.dataset.widget) });
      all.forEach(el => { el.classList.remove('widget-off'); });
      enhanceDashboard();
      toast('Diseño del panel guardado.', 'success');
    }
  }
  function resetDashboard() { localStorage.removeItem(DASH_KEY); render(); toast('Panel restablecido.', 'success'); }

  /* ───────────── Tutorial de bienvenida ───────────── */
  const TOUR_KEY = 'ipv.tour.done';
  const STEPS = [
    { sel: '#sidebar nav, #sidebar', title: 'Navegación', text: 'Cambie entre Resumen, Productos, Valores del IPV, Inventario, Fichas, Controles, Papelera y Licencia. También con las teclas 1 a 8.' },
    { sel: '#search-global', title: 'Búsqueda global', text: 'Encuentre cualquier producto, insumo, ficha o control. Atajo: Ctrl+K.' },
    { sel: '.topbar-actions .icon-button[title^="Paleta"]', title: 'Paleta de comandos', text: 'Todas las acciones en un solo lugar: importar CSV, PDF, tema, seguridad… Atajo: Ctrl+Shift+P.' },
    { sel: '.notif-bell', title: 'Notificaciones en tiempo real', text: 'Vea al instante los cambios que hacen otros usuarios en la web o en Android.' },
    { sel: '#customize-dash', title: 'Panel a su medida', text: 'Oculte y reordene los indicadores arrastrándolos.' },
    { sel: '.fab, #fab', title: 'Acción rápida', text: 'Cree productos, valores o fichas desde cualquier pantalla.' },
    { sel: '.user-badge:not([hidden])', title: 'Su cuenta', text: 'Active la verificación en dos pasos y cambie su contraseña.' },
  ];
  function startTour() {
    const steps = STEPS.filter(s => { const el = document.querySelector(s.sel); return el && el.offsetParent !== null; });
    if (!steps.length) return;
    let i = 0;
    const layer = document.createElement('div');
    layer.className = 'tour-layer';
    layer.innerHTML = `<div class="tour-spot"></div><div class="tour-card" role="dialog" aria-modal="true" aria-labelledby="tour-title">
      <small class="tour-step"></small><h3 id="tour-title"></h3><p></p>
      <div class="tour-actions"><button class="ghost-btn" data-t="skip">Saltar</button><span></span><button class="ghost-btn" data-t="prev">Anterior</button><button class="primary-btn" data-t="next">Siguiente</button></div></div>`;
    document.body.appendChild(layer);
    const spot = layer.querySelector('.tour-spot'), card = layer.querySelector('.tour-card');
    const show = () => {
      const s = steps[i], el = document.querySelector(s.sel);
      el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      const r = el.getBoundingClientRect(), pad = 8;
      Object.assign(spot.style, { top: `${r.top - pad}px`, left: `${r.left - pad}px`, width: `${r.width + pad * 2}px`, height: `${r.height + pad * 2}px` });
      card.querySelector('.tour-step').textContent = `Paso ${i + 1} de ${steps.length}`;
      card.querySelector('h3').textContent = s.title;
      card.querySelector('p').textContent = s.text;
      card.querySelector('[data-t="prev"]').disabled = i === 0;
      card.querySelector('[data-t="next"]').textContent = i === steps.length - 1 ? 'Terminar ✓' : 'Siguiente';
      const below = r.bottom + 220 < innerHeight;
      const left = Math.min(Math.max(12, r.left), innerWidth - card.offsetWidth - 12);
      Object.assign(card.style, { left: `${left}px`, top: below ? `${r.bottom + 16}px` : `${Math.max(12, r.top - card.offsetHeight - 16)}px` });
      card.querySelector('[data-t="next"]').focus();
    };
    const end = () => { layer.remove(); localStorage.setItem(TOUR_KEY, '1'); removeEventListener('resize', show); document.removeEventListener('keydown', keys, true); };
    const keys = e => {
      if (e.key === 'Escape') { e.stopPropagation(); end(); }
      else if (e.key === 'ArrowRight') card.querySelector('[data-t="next"]').click();
      else if (e.key === 'ArrowLeft' && i > 0) card.querySelector('[data-t="prev"]').click();
    };
    card.onclick = e => {
      const t = e.target.closest('[data-t]')?.dataset.t;
      if (t === 'skip') end();
      else if (t === 'prev') { i--; show(); }
      else if (t === 'next') { if (i === steps.length - 1) { end(); window.triggerConfetti?.(1800); } else { i++; show(); } }
    };
    addEventListener('resize', show);
    document.addEventListener('keydown', keys, true);
    show();
  }

  /* ───────────── Accesibilidad ───────────── */
  const A11Y_KEY = 'ipv.a11y';
  const a11y = store.get(A11Y_KEY, { contrast: false, scale: 100, motion: false });
  function applyA11y() {
    document.documentElement.classList.toggle('high-contrast', a11y.contrast);
    document.documentElement.classList.toggle('reduce-motion', a11y.motion);
    document.documentElement.style.fontSize = `${a11y.scale}%`;
  }
  applyA11y();
  function openA11y() {
    showModal('Accesibilidad', 'Ajuste la interfaz a sus necesidades', `
      <div class="a11y-options">
        <label class="switch-row"><input type="checkbox" id="a11y-contrast" ${a11y.contrast ? 'checked' : ''}><span><b>Alto contraste</b><small>Colores con contraste reforzado y bordes visibles</small></span></label>
        <label class="switch-row"><input type="checkbox" id="a11y-motion" ${a11y.motion ? 'checked' : ''}><span><b>Reducir animaciones</b><small>Desactiva confeti, parallax y transiciones</small></span></label>
        <label class="range-row"><span><b>Tamaño del texto</b><small id="a11y-scale-v">${a11y.scale}%</small></span><input type="range" id="a11y-scale" min="90" max="140" step="10" value="${a11y.scale}"></label>
      </div>
      <div class="form-actions"><button class="ghost-btn" id="a11y-tour">Ver tutorial</button><button class="primary-btn" data-action="close-modal">Listo</button></div>`);
    const save = () => { store.set(A11Y_KEY, a11y); applyA11y(); };
    document.getElementById('a11y-contrast').onchange = e => { a11y.contrast = e.target.checked; save(); };
    document.getElementById('a11y-motion').onchange = e => { a11y.motion = e.target.checked; save(); };
    document.getElementById('a11y-scale').oninput = e => { a11y.scale = +e.target.value; document.getElementById('a11y-scale-v').textContent = `${a11y.scale}%`; save(); };
    document.getElementById('a11y-tour').onclick = () => { closeModal(); setTimeout(startTour, 200); };
  }

  // Enlace «saltar al contenido»
  const skip = document.createElement('a');
  skip.href = '#page-content'; skip.className = 'skip-link'; skip.textContent = 'Saltar al contenido';
  skip.onclick = e => { e.preventDefault(); const c = document.getElementById('page-content'); c.tabIndex = -1; c.focus(); };
  document.body.prepend(skip);

  // Diálogos: rol, foco inicial, foco atrapado y retorno del foco
  const modal = document.getElementById('modal-layer');
  let lastFocus = null;
  new MutationObserver(() => {
    if (!modal.hidden && modal.firstElementChild) {
      const card = modal.querySelector('.modal-card');
      if (card && !card.hasAttribute('role')) {
        if (!lastFocus) lastFocus = document.activeElement;
        card.setAttribute('role', 'dialog'); card.setAttribute('aria-modal', 'true');
        const h = card.querySelector('h2'); if (h) { h.id = h.id || 'modal-title'; card.setAttribute('aria-labelledby', h.id); }
        requestAnimationFrame(() => (card.querySelector('input:not([type=hidden]),select,textarea,button:not(.modal-close)') || card.querySelector('button'))?.focus());
      }
    } else if (modal.hidden && lastFocus) { lastFocus.focus?.(); lastFocus = null; }
  }).observe(modal, { attributes: true, childList: true, attributeFilter: ['hidden'] });
  modal.addEventListener('keydown', e => {
    if (e.key !== 'Tab') return;
    const f = [...modal.querySelectorAll('a[href],button:not([disabled]),input:not([disabled]),select,textarea,[tabindex="0"]')].filter(x => x.offsetParent !== null);
    if (!f.length) return;
    if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
    else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
  });

  /* ───────────── Integración ───────────── */
  const content = document.getElementById('page-content');
  let pending = false;
  new MutationObserver(() => {
    if (pending) return;
    pending = true;
    queueMicrotask(() => { pending = false; enhanceToolbar(); enhanceTables(); enhanceDashboard(); });
  }).observe(content, { childList: true });

  // Comandos extra en la paleta
  const original = window.IPVEnterprise;
  window.IPVUX = { undo, redo, startTour, openA11y, resetDashboard };
  document.addEventListener('keydown', e => {
    if (e.altKey && e.shiftKey && e.key.toLowerCase() === 'a') { e.preventDefault(); openA11y(); }
  });
  if (original) {
    const btn = document.createElement('button');
    btn.className = 'icon-button'; btn.title = 'Accesibilidad (Alt+Shift+A)'; btn.setAttribute('aria-label', 'Accesibilidad'); btn.textContent = '♿';
    btn.onclick = openA11y;
    document.querySelector('.topbar-actions')?.insertBefore(btn, document.querySelector('.notif-bell'));
  }

  // Primera visita: tutorial tras cargar los datos
  if (!localStorage.getItem(TOUR_KEY)) {
    const wait = setInterval(() => { if (state.dashboard && !document.querySelector('.login-layer')) { clearInterval(wait); setTimeout(startTour, 700); } }, 500);
  }
})();
