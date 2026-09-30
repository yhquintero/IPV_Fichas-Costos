'use strict';
/* ==========================================================================
   IPV · Fichas y Costos — Módulo Enterprise (web)
   Autor: Ing. Yosvany Hernández Quintero

   · Sesión JWT con renovación automática y cierre de sesión seguro
   · Tiempo real (Server-Sent Events) con sincronización automática
   · Centro de notificaciones persistente
   · Paleta de comandos (Ctrl+Shift+P)
   · Personalizador de tema en vivo
   · Importación CSV por arrastrar y soltar (valores del IPV)
   · Exportación a PDF (impresión optimizada)
   · Visor de auditoría (administradores)
   · Modo sin conexión (Service Worker)
   ========================================================================== */
(() => {
  const S = sessionStorage;
  const K = { access: 'ipv.access', refresh: 'ipv.refresh', user: 'ipv.user', perms: 'ipv.perms' };
  const NOTIF_KEY = 'ipv.notifications';
  const THEME_KEY = 'ipv.theme.custom';

  /* ───────────── Sesión JWT ───────────── */
  let pendingLogin = null;
  const Auth = {
    get user() { try { return JSON.parse(S.getItem(K.user) || 'null'); } catch { return null; } },
    /* Sistema de Seguridad por Usuarios: permisos por módulo (view / edit / costs)
       recibidos del servidor al iniciar sesión. Sin ellos (servidor en modo abierto)
       se permite todo, igual que en el API. */
    permissions() { try { return JSON.parse(S.getItem(K.perms) || 'null'); } catch { return null; } },
    can(module, perm) {
      const p = Auth.permissions();
      if (!p) return true;
      return !!(p[module] && p[module][perm]);
    },
    headers() { const t = S.getItem(K.access); return t ? { Authorization: `Bearer ${t}` } : {}; },
    save(d) {
      S.setItem(K.access, d.access_token); S.setItem(K.refresh, d.refresh_token); S.setItem(K.user, JSON.stringify(d.user));
      const permisos = d.permissions || d.user?.permissions;
      if (permisos) S.setItem(K.perms, JSON.stringify(permisos)); else S.removeItem(K.perms);
      renderUserBadge(); connectEvents(); try { document.dispatchEvent(new CustomEvent('ipv:auth')); } catch {}
    },
    clear() { Object.values(K).forEach(k => S.removeItem(k)); renderUserBadge(); try { document.dispatchEvent(new CustomEvent('ipv:auth')); } catch {} },
    /** Refresca los permisos guardados (los cambia el administrador en caliente). */
    async reloadPermissions() {
      if (!Auth.user) { S.removeItem(K.perms); return null; }
      try {
        const r = await fetch('/api/auth/me', { headers: Auth.headers() });
        if (!r.ok) return Auth.permissions();  // sesión caída o sin red: no se pierden los permisos conocidos
        const me = await r.json();
        if (me && me.permissions) S.setItem(K.perms, JSON.stringify(me.permissions));
        return me.permissions || null;
      } catch { return Auth.permissions(); }
    },
    async tryRefresh() {
      const rt = S.getItem(K.refresh);
      if (!rt) return false;
      const r = await fetch('/api/auth/refresh', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh_token: rt }) });
      if (!r.ok) { Auth.clear(); return false; }
      Auth.save(await r.json());
      return true;
    },
    async recover() {
      if (await Auth.tryRefresh()) return true;
      if (!pendingLogin) pendingLogin = showLogin().finally(() => { pendingLogin = null; });
      return pendingLogin;
    },
    async logout() {
      const rt = S.getItem(K.refresh);
      if (rt) await fetch('/api/auth/logout', { method: 'POST', headers: { 'Content-Type': 'application/json', ...Auth.headers() }, body: JSON.stringify({ refresh_token: rt }) }).catch(() => {});
      Auth.clear();
      closeEvents();
      location.reload();
    },
  };
  let pendingPwChange = null;
  Auth.forcePasswordChange = () => {
    if (!pendingPwChange) pendingPwChange = showForcedPasswordChange().finally(() => { pendingPwChange = null; });
    return pendingPwChange;
  };
  window.IPVAuth = Auth;

  async function afterLogin(d) {
    if (d.new_ip) toast('🔐 Inicio de sesión desde una red nueva. Si no fue usted, cambie su contraseña y cierre las demás sesiones.', 'info');
    const fails = d.failed_attempts_since_last_login || 0;
    if (fails > 0) toast(`⚠ Hubo ${fails} intento${fails === 1 ? '' : 's'} fallido${fails === 1 ? '' : 's'} de entrar en su cuenta desde su último acceso${d.last_failed_ip ? ` (IP ${d.last_failed_ip})` : ''}. Si no fue usted, cambie su contraseña.`, fails >= 3 ? 'error' : 'info');
    if (d.password_expired) { await Auth.forcePasswordChange(); return; }
    const left = d.password_expires_in_days;
    if (left !== null && left !== undefined && left <= 7) {
      toast(`⏳ Su contraseña caduca en ${left} día${left === 1 ? '' : 's'}. Cámbiela en «Seguridad de mi cuenta».`, 'info');
    }
  }

  /** Pantalla bloqueante: contraseña caducada o cambio exigido por el administrador. */
  function showForcedPasswordChange() {
    return new Promise(resolve => {
      const layer = document.createElement('div');
      layer.className = 'login-layer';
      layer.innerHTML = `
        <form class="login-card" autocomplete="off" novalidate>
          <div class="login-brand"><span class="login-logo">🔑</span><div><h1>Cambie su contraseña</h1><p>Su contraseña ha caducado o el administrador exige cambiarla</p></div></div>
          <label>Contraseña actual<input name="current" type="password" required autocomplete="current-password" maxlength="200"></label>
          <label>Nueva contraseña<input name="new" type="password" required minlength="10" autocomplete="new-password" maxlength="200"></label>
          <label>Repetir nueva<input name="repeat" type="password" required autocomplete="new-password" maxlength="200"></label>
          <div class="pw-meter"><i></i><span>Mínimo 10 caracteres · no puede repetir contraseñas anteriores</span></div>
          <p class="login-error" role="alert" hidden></p>
          <button class="primary-btn login-submit" type="submit">Guardar y continuar</button>
          <button class="ghost-btn" type="button" data-logout>Cerrar sesión</button>
        </form>`;
      document.body.appendChild(layer);
      const form = layer.querySelector('form'), err = layer.querySelector('.login-error');
      form.elements.current.focus();
      form.elements.new.oninput = () => paintMeter(form);
      layer.querySelector('[data-logout]').onclick = () => Auth.logout();
      form.onsubmit = async e => {
        e.preventDefault();
        err.hidden = true;
        if (form.elements.new.value !== form.elements.repeat.value) { err.textContent = 'Las contraseñas nuevas no coinciden.'; err.hidden = false; return; }
        const btn = form.querySelector('.login-submit'); btn.disabled = true;
        try {
          const r = await fetch('/api/auth/password', { method: 'POST', headers: { 'Content-Type': 'application/json', ...Auth.headers() }, body: JSON.stringify({ current: form.elements.current.value, new: form.elements.new.value }) });
          const d = await r.json().catch(() => ({}));
          if (!r.ok) throw new Error(d.error || 'No se pudo cambiar la contraseña.');
          Auth.save(d);
          layer.remove();
          toast('Contraseña actualizada. Ya puede continuar.', 'success');
          resolve(true);
        } catch (ex) { err.textContent = ex.message; err.hidden = false; } finally { btn.disabled = false; }
      };
    });
  }
  function paintMeter(form) {
    const n = strength(form.elements.new.value), bar = form.querySelector('.pw-meter i');
    bar.style.width = `${n * 20}%`;
    bar.style.background = ['#ef4444', '#ef4444', '#f59e0b', '#f59e0b', '#10b981', '#10b981'][n];
  }

  function showLogin() {
    return new Promise(resolve => {
      const layer = document.createElement('div');
      layer.className = 'login-layer';
      layer.innerHTML = `
        <form class="login-card" autocomplete="on" novalidate>
          <div class="login-brand"><span class="login-logo">IPV</span><div><h1>Fichas y Costos</h1><p>Acceso seguro al sistema</p></div></div>
          <label>Correo electrónico<input name="email" type="email" required autocomplete="username" maxlength="200"></label>
          <label>Contraseña<input name="password" type="password" required autocomplete="current-password" maxlength="200"></label>
          <label class="otp-field" hidden>Código de verificación<input name="otp" inputmode="numeric" autocomplete="one-time-code" maxlength="20" placeholder="123456 o código de recuperación"></label>
          <p class="login-error" role="alert" hidden></p>
          <button class="primary-btn login-submit" type="submit">Iniciar sesión</button>
          <small>🔒 Conexión cifrada · Sesión protegida con JWT · Bloqueo tras 5 intentos fallidos</small>
        </form>`;
      document.body.appendChild(layer);
      const form = layer.querySelector('form');
      const err = layer.querySelector('.login-error');
      form.elements.email.focus();
      form.addEventListener('submit', async e => {
        e.preventDefault();
        err.hidden = true;
        const btn = form.querySelector('button');
        btn.disabled = true; btn.textContent = 'Verificando…';
        try {
          const r = await fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email: form.elements.email.value.trim(), password: form.elements.password.value, otp: form.elements.otp.value.trim() }) });
          const d = await r.json().catch(() => ({}));
          if (d.mfa_required) {
            const f = layer.querySelector('.otp-field');
            if (f.hidden) { f.hidden = false; form.elements.otp.focus(); err.textContent = d.error; err.hidden = false; err.classList.add('info'); return; }
          }
          if (r.status === 402 && d.license_required && window.IPVLicense) { layer.remove(); window.IPVLicense.enter(); resolve(false); return; }
          if (!r.ok) throw new Error(d.error || 'No se pudo iniciar sesión.');
          Auth.save(d);
          layer.remove();
          toast(`Bienvenido, ${d.user.name}`, 'success');
          await afterLogin(d);
          resolve(true);
        } catch (ex) {
          err.classList.remove('info');
          err.textContent = ex.message; err.hidden = false;
          if (layer.querySelector('.otp-field').hidden) { form.elements.password.value = ''; form.elements.password.focus(); }
          else { form.elements.otp.value = ''; form.elements.otp.focus(); }
        } finally { btn.disabled = false; btn.textContent = 'Iniciar sesión'; }
      });
    });
  }

  /* ───────────── Barra superior: usuario + notificaciones ───────────── */
  const actions = document.querySelector('.topbar-actions');
  const bell = document.createElement('button');
  bell.className = 'icon-button notif-bell';
  bell.title = 'Notificaciones';
  bell.setAttribute('aria-label', 'Notificaciones');
  bell.innerHTML = '🔔<span class="notif-count" hidden></span>';
  const userBadge = document.createElement('div');
  userBadge.className = 'user-badge';
  actions?.insertBefore(bell, actions.lastElementChild);
  actions?.appendChild(userBadge);

  function renderUserBadge() {
    const u = Auth.user;
    userBadge.hidden = !u;
    if (!u) { userBadge.innerHTML = ''; return; }
    const roles = { admin: 'Administrador', editor: 'Editor', viewer: 'Consulta' };
    userBadge.innerHTML = `<span class="user-avatar">${esc((u.name || u.email)[0].toUpperCase())}</span>
      <span class="user-meta"><b>${esc(u.name || u.email)}</b><small>${esc(roles[u.role] || u.role)}</small></span>
      <button class="user-logout" title="Cerrar sesión" aria-label="Cerrar sesión">⎋</button>`;
    userBadge.querySelector('.user-logout').onclick = e => { e.stopPropagation(); Auth.logout(); };
    userBadge.querySelector('.user-meta').onclick = () => openAccountSecurity();
    userBadge.querySelector('.user-meta').style.cursor = 'pointer';
    userBadge.querySelector('.user-avatar').dataset.mfa = u.mfa ? '1' : '0';
  }
  renderUserBadge();
  try { document.dispatchEvent(new CustomEvent('ipv:auth')); } catch {}  // sincroniza la visibilidad del Creador

  /* ───────────── Centro de notificaciones ───────────── */
  const ACTION_LABELS = {
    CREATE_PRODUCT: 'Producto creado', CREATE_MATERIAL: 'Valor IPV registrado', CREATE_FICHA: 'Ficha creada',
    UPDATE_FICHA: 'Ficha actualizada', APPROVE_FICHA: 'Ficha aprobada', CREATE_CONTROL: 'Control creado',
    VALIDATE_CONTROL: 'Control validado', DEACTIVATE_PRODUCT: 'Producto desactivado',
    DEACTIVATE_MATERIAL: 'Valor IPV desactivado', BULK_UPDATE: 'Actualización masiva de precios', CREATE_USER: 'Usuario creado',
  };
  const loadNotifs = () => { try { return JSON.parse(localStorage.getItem(NOTIF_KEY) || '[]'); } catch { return []; } };
  let notifs = loadNotifs();
  function pushNotif(n) {
    notifs = [{ ...n, read: false }, ...notifs].slice(0, 50);
    localStorage.setItem(NOTIF_KEY, JSON.stringify(notifs));
    renderBell();
  }
  function renderBell() {
    const unread = notifs.filter(n => !n.read).length;
    const c = bell.querySelector('.notif-count');
    c.hidden = !unread; c.textContent = unread > 9 ? '9+' : unread;
  }
  bell.onclick = () => {
    const list = notifs.length ? notifs.map(n => `
      <li class="notif-item ${n.read ? '' : 'unread'}"><b>${esc(ACTION_LABELS[n.action] || n.action)}</b>
      <span>${esc(n.details || '')}</span><time>${esc(new Date(n.time).toLocaleString('es'))}</time></li>`).join('')
      : '<li class="notif-empty">No hay notificaciones todavía.</li>';
    showModal('Centro de notificaciones', 'Cambios recibidos en tiempo real', `
      <ul class="notif-list">${list}</ul>
      <div class="form-actions"><button class="ghost-btn" id="notif-clear">Vaciar</button><button class="primary-btn" data-action="close-modal">Cerrar</button></div>`);
    notifs = notifs.map(n => ({ ...n, read: true }));
    localStorage.setItem(NOTIF_KEY, JSON.stringify(notifs));
    renderBell();
    document.getElementById('notif-clear').onclick = () => { notifs = []; localStorage.removeItem(NOTIF_KEY); renderBell(); closeModal(); };
  };
  renderBell();

  /* ───────────── Tiempo real (SSE) ───────────── */
  let source = null, syncTimer = null;
  function closeEvents() { source?.close(); source = null; }
  function connectEvents() {
    closeEvents();
    if (!('EventSource' in window)) return;
    const t = S.getItem(K.access);
    source = new EventSource(t ? `/api/events?access_token=${encodeURIComponent(t)}` : '/api/events');
    source.addEventListener('ready', () => document.body.classList.add('realtime-on'));
    source.addEventListener('change', ev => {
      let data = {}; try { data = JSON.parse(ev.data); } catch { return; }
      pushNotif(data);
      clearTimeout(syncTimer);
      syncTimer = setTimeout(() => refreshData(true), 600);
    });
    source.onerror = () => {
      document.body.classList.remove('realtime-on');
      // Si el token expiró, renovar y reconectar
      if (source?.readyState === EventSource.CLOSED) setTimeout(async () => { if (S.getItem(K.refresh)) await Auth.tryRefresh(); else connectEvents(); }, 5000);
    };
  }
  connectEvents();

  /* ───────────── Personalizador de tema ───────────── */
  const PRESETS = {
    'Bosque IPV': { primary: '#183b34', light: '#2a7057', accent: '#d7e78d' },
    'Océano': { primary: '#0c3b66', light: '#1d74c4', accent: '#7dd3fc' },
    'Aurora': { primary: '#3b1a6b', light: '#7c3aed', accent: '#f0abfc' },
    'Atardecer': { primary: '#6b1d1d', light: '#dc2626', accent: '#fdba74' },
    'Grafito': { primary: '#1f2937', light: '#4b5563', accent: '#facc15' },
  };
  function applyTheme(t) {
    if (!t) return;
    const r = document.documentElement.style;
    r.setProperty('--primary', t.primary); r.setProperty('--primary-light', t.light); r.setProperty('--accent', t.accent);
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', t.primary);
  }
  try { applyTheme(JSON.parse(localStorage.getItem(THEME_KEY) || 'null')); } catch { /* tema por defecto */ }
  function openThemeBuilder() {
    const cur = JSON.parse(localStorage.getItem(THEME_KEY) || 'null') || PRESETS['Bosque IPV'];
    showModal('Personalizar tema', 'Los cambios se aplican al instante y se guardan en este navegador', `
      <div class="theme-presets">${Object.entries(PRESETS).map(([n, p]) => `<button class="theme-preset" data-preset="${esc(n)}" style="--p:${p.primary};--l:${p.light};--a:${p.accent}"><i></i>${esc(n)}</button>`).join('')}</div>
      <div class="form-grid">
        <label>Color principal<input type="color" id="tb-primary" value="${cur.primary}"></label>
        <label>Color secundario<input type="color" id="tb-light" value="${cur.light}"></label>
        <label>Color de acento<input type="color" id="tb-accent" value="${cur.accent}"></label>
      </div>
      <div class="form-actions"><button class="ghost-btn" id="tb-reset">Restablecer</button><button class="primary-btn" data-action="close-modal">Listo</button></div>`);
    const read = () => ({ primary: tb('primary'), light: tb('light'), accent: tb('accent') });
    const tb = k => document.getElementById(`tb-${k}`).value;
    const save = t => { applyTheme(t); localStorage.setItem(THEME_KEY, JSON.stringify(t)); };
    ['primary', 'light', 'accent'].forEach(k => document.getElementById(`tb-${k}`).addEventListener('input', () => save(read())));
    document.querySelectorAll('.theme-preset').forEach(b => b.onclick = () => {
      const p = PRESETS[b.dataset.preset]; save(p);
      ['primary', 'light', 'accent'].forEach(k => { document.getElementById(`tb-${k}`).value = p[k]; });
    });
    document.getElementById('tb-reset').onclick = () => { localStorage.removeItem(THEME_KEY); location.reload(); };
  }

  /* ───────────── Importación CSV (arrastrar y soltar) ───────────── */
  function parseCSV(text) {
    const sep = (text.split('\n')[0].match(/;/g) || []).length >= (text.split('\n')[0].match(/,/g) || []).length ? ';' : ',';
    const rows = []; let row = [], cell = '', q = false;
    for (let i = 0; i < text.length; i++) {
      const ch = text[i];
      if (q) { if (ch === '"' && text[i + 1] === '"') { cell += '"'; i++; } else if (ch === '"') q = false; else cell += ch; }
      else if (ch === '"') q = true;
      else if (ch === sep) { row.push(cell.trim()); cell = ''; }
      else if (ch === '\n' || ch === '\r') { if (ch === '\r' && text[i + 1] === '\n') i++; row.push(cell.trim()); if (row.some(Boolean)) rows.push(row); row = []; cell = ''; }
      else cell += ch;
    }
    row.push(cell.trim()); if (row.some(Boolean)) rows.push(row);
    return rows;
  }
  const norm = s => s.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
  function mapRows(rows) {
    const head = rows[0].map(norm);
    const idx = keys => head.findIndex(h => keys.some(k => h.includes(k)));
    const col = { code: idx(['codigo', 'code']), name: idx(['nombre', 'name', 'descripcion']), unit: idx(['unidad', 'unit', 'um']),
      unit_price: idx(['precio', 'price', 'valor']), currency: idx(['moneda', 'currency']), source: idx(['fuente', 'source', 'proveedor']) };
    if (col.code < 0 || col.name < 0 || col.unit_price < 0) throw new Error('El CSV debe tener columnas Código, Nombre y Precio.');
    return rows.slice(1, 501).map(r => ({
      code: r[col.code], name: r[col.name], unit: col.unit >= 0 ? r[col.unit] || 'unidad' : 'unidad',
      unit_price: String(r[col.unit_price] || '').replace(/\s/g, '').replace(',', '.'),
      currency: col.currency >= 0 ? (r[col.currency] || 'CUP').toUpperCase() : 'CUP', source: col.source >= 0 ? r[col.source] : 'Importación CSV',
    })).filter(m => m.code && m.name);
  }
  function openImporter(file) {
    if (!ver('materials', 'edit')) {
      toast('Su usuario no tiene permiso para importar valores del IPV.', 'error');
      return;
    }
    showModal('Importar valores del IPV', 'Arrastre un archivo CSV (separado por ; o ,) con columnas Código, Nombre, Unidad, Precio', `
      <div class="drop-zone" id="drop-zone" tabindex="0"><div class="drop-icon">⇪</div><b>Suelte aquí su archivo CSV</b><span>o haga clic para seleccionarlo · máximo 500 filas</span>
      <input type="file" id="csv-input" accept=".csv,text/csv" hidden></div><div id="csv-preview"></div>`);
    const zone = document.getElementById('drop-zone'), input = document.getElementById('csv-input');
    zone.onclick = () => input.click();
    zone.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') input.click(); };
    ['dragenter', 'dragover'].forEach(t => zone.addEventListener(t, e => { e.preventDefault(); zone.classList.add('over'); }));
    ['dragleave', 'drop'].forEach(t => zone.addEventListener(t, e => { e.preventDefault(); zone.classList.remove('over'); }));
    zone.addEventListener('drop', e => e.dataTransfer.files[0] && handleFile(e.dataTransfer.files[0]));
    input.onchange = () => input.files[0] && handleFile(input.files[0]);
    if (file) handleFile(file);
  }
  async function handleFile(file) {
    const box = document.getElementById('csv-preview');
    if (file.size > 400_000) { toast('El archivo supera 400 KB.', 'error'); return; }
    let items;
    try { items = mapRows(parseCSV(await file.text())); } catch (e) { toast(e.message, 'error'); return; }
    if (!items.length) { toast('No se encontraron filas válidas.', 'error'); return; }
    box.innerHTML = `<div class="table-wrap"><table><thead><tr>${idTh()}<th>Código</th><th>Nombre</th><th>Unidad</th><th>Precio</th><th>Moneda</th></tr></thead><tbody>
      ${items.slice(0, 8).map((m, i) => `<tr>${idTd(i)}<td>${esc(m.code)}</td><td>${esc(m.name)}</td><td>${esc(m.unit)}</td><td>${esc(m.unit_price)}</td><td>${esc(m.currency)}</td></tr>`).join('')}
      </tbody></table></div><p class="muted">${items.length} filas listas${items.length > 8 ? ' (vista previa de 8)' : ''}.</p>
      <div class="progress-bar" hidden><div class="progress-fill" style="width:0"></div></div>
      <div class="form-actions"><button class="primary-btn" id="csv-go">Importar ${items.length} valores</button></div>`;
    document.getElementById('csv-go').onclick = async ev => {
      ev.target.disabled = true;
      const bar = box.querySelector('.progress-bar'), fill = box.querySelector('.progress-fill'); bar.hidden = false;
      let ok = 0; const errors = [];
      for (let i = 0; i < items.length; i++) {
        try { await api('/api/materials', { method: 'POST', body: JSON.stringify(items[i]) }); ok++; }
        catch (e) { errors.push(`${items[i].code}: ${e.message}`); }
        fill.style.width = `${Math.round(((i + 1) / items.length) * 100)}%`;
      }
      toast(`Importados ${ok} de ${items.length} valores.`, errors.length ? 'error' : 'success');
      if (errors.length) box.insertAdjacentHTML('beforeend', `<details class="import-errors"><summary>${errors.length} filas con error</summary><ul>${errors.slice(0, 50).map(e => `<li>${esc(e)}</li>`).join('')}</ul></details>`);
      refreshData(true);
    };
  }
  // Soltar un CSV en cualquier parte de la aplicación abre el importador
  document.addEventListener('dragover', e => { if ([...(e.dataTransfer?.types || [])].includes('Files')) e.preventDefault(); });
  document.addEventListener('drop', e => {
    if (document.getElementById('drop-zone')) return;
    const f = e.dataTransfer?.files?.[0];
    if (f && /\.csv$/i.test(f.name)) {
      e.preventDefault();
      if (!ver('materials', 'edit')) { toast('Su usuario no puede importar valores del IPV (permiso de edición).', 'error'); return; }
      openImporter(f);
    }
  });

  /* ───────────── Exportar PDF ───────────── */
  function exportPDF() {
    const title = document.getElementById('crumb-current')?.textContent || 'Reporte';
    document.body.dataset.printTitle = `IPV · Fichas y Costos — ${title} — ${new Date().toLocaleString('es')}`;
    closeModal();
    setTimeout(() => window.print(), 100);
  }

  /* ───────────── Auditoría (admin) ───────────── */
  async function openAudit(q = '', action = '') {
    try {
      const d = await api(`/api/audit?limit=100&q=${encodeURIComponent(q)}&action=${encodeURIComponent(action)}`);
      showModal('Registro de auditoría', `${d.total} eventos registrados`, `
        <div class="audit-filters"><input type="search" id="audit-q" placeholder="Buscar en detalles, IP o usuario…" value="${esc(q)}">
        <select id="audit-action"><option value="">Todas las acciones</option>${d.actions.map(a => `<option ${a === action ? 'selected' : ''}>${esc(a)}</option>`).join('')}</select></div>
        <div class="table-wrap"><table><thead><tr>${idTh()}<th>Fecha</th><th>Acción</th><th>Usuario</th><th>IP</th><th>Detalles</th></tr></thead><tbody>
        ${d.entries.map((e, i) => `<tr>${idTd(i, e.id)}<td>${esc(new Date(e.timestamp).toLocaleString('es'))}</td><td><span class="status ${/FAIL|FORBID|DENIED|RATE/.test(e.action) ? 'difference' : 'approved'}">${esc(e.action)}</span></td><td>${esc(e.user_email || '—')}</td><td>${esc(e.client)}</td><td>${esc(e.details)}</td></tr>`).join('') || '<tr><td colspan="6">Sin eventos.</td></tr>'}
        </tbody></table></div>`);
      let t;
      document.getElementById('audit-q').oninput = ev => { clearTimeout(t); t = setTimeout(() => openAudit(ev.target.value, document.getElementById('audit-action').value), 400); };
      document.getElementById('audit-action').onchange = ev => openAudit(document.getElementById('audit-q').value, ev.target.value);
    } catch (e) { toast(e.message, 'error'); }
  }

  /* ───────────── Seguridad de la cuenta ───────────── */
  const post = (path, body) => api(path, { method: 'POST', body: JSON.stringify(body) });
  function strength(p) {
    let n = 0; if (p.length >= 10) n++; if (p.length >= 14) n++; if (/[a-z]/.test(p) && /[A-Z]/.test(p)) n++; if (/\d/.test(p)) n++; if (/[^\w]/.test(p)) n++;
    return n;
  }
  /** Lo que este usuario puede hacer en cada apartado, según el administrador. */
  function permSummary(perms) {
    if (!perms) return '<p class="muted">El servidor no exige sesión: todos los apartados están disponibles en esta red.</p>';
    return `<div class="table-wrap"><table class="perm-table"><thead><tr>${idTh()}<th>Módulo</th>
      <th class="center">Ver</th><th class="center">Editar</th><th class="center">Ver costos</th></tr></thead><tbody>
      ${Object.entries(MODULES).map(([m, label], i) => `<tr>${idTd(i, m)}<td>${label}</td>
        ${['view', 'edit', 'costs'].map(k => `<td class="center">${perms[m] && perms[m][k]
          ? '<span class="status approved">Sí</span>' : '<span class="status pending">No</span>'}</td>`).join('')}</tr>`).join('')}
      </tbody></table></div>
      <p class="muted">Los ajusta el administrador en Usuarios → 🔐 Permisos y se aplican al instante,
      sin cerrar su sesión. Sin «Ver costos» los precios e importes no se descargan a su equipo.</p>`;
  }

  async function openAccountSecurity() {
    if (!Auth.user) { toast('La gestión de cuenta requiere que el servidor tenga JWT activado.', 'error'); return; }
    let meData; try { meData = await api('/api/auth/me'); } catch (e) { toast(e.message, 'error'); return; }
    const me = meData.user || {};
    const misPermisos = meData.permissions || me.permissions || null;
    const mfa = Auth.user.mfa;
    showModal('Seguridad de mi cuenta', Auth.user.email, `
      <section class="sec-card ${mfa ? 'ok' : 'warn'}">
        <div class="sec-icon">${mfa ? '🛡' : '⚠'}</div>
        <div><b>Verificación en dos pasos ${mfa ? 'activa' : 'desactivada'}</b>
        <p>${mfa ? 'Su cuenta pide un código de su aplicación autenticadora en cada inicio de sesión.' : 'Añada una segunda capa: aunque roben su contraseña, no podrán entrar sin su teléfono.'}</p></div>
        <button class="${mfa ? 'ghost-btn' : 'primary-btn'}" id="mfa-toggle">${mfa ? 'Desactivar' : 'Activar'}</button>
      </section>
      <div id="mfa-area"></div>
      <h3 class="sec-title">Cambiar contraseña</h3>
      <form id="pw-form" class="form-grid" autocomplete="off">
        <label>Contraseña actual<input type="password" name="current" required autocomplete="current-password"></label>
        <label>Nueva contraseña<input type="password" name="new" required minlength="10" autocomplete="new-password"></label>
        <label>Repetir nueva<input type="password" name="repeat" required autocomplete="new-password"></label>
        <div class="pw-meter"><i></i><span>Mínimo 10 caracteres combinando mayúsculas, minúsculas, números y símbolos</span></div>
        <div class="form-actions"><button class="primary-btn" type="submit">Actualizar contraseña</button></div>
      </form>
      <p class="muted">Al cambiar la contraseña se cierran automáticamente las sesiones abiertas en otros dispositivos. Rol: <b>${esc(ROLE_LABEL[me?.role] || me?.role || '')}</b></p>
      <h3 class="sec-title">Mis permisos por módulo</h3>
      ${permSummary(misPermisos)}
      <h3 class="sec-title">Dispositivos con sesión abierta</h3>
      <div id="devices" class="devices" aria-live="polite"><div class="typing-indicator"><span></span><span></span><span></span></div></div>`);
    loadDevices();
    const pf = document.getElementById('pw-form');
    pf.elements.new.oninput = () => paintMeter(pf);
    pf.onsubmit = async e => {
      e.preventDefault();
      if (pf.elements.new.value !== pf.elements.repeat.value) { toast('Las contraseñas nuevas no coinciden.', 'error'); return; }
      try {
        const r = await post('/api/auth/password', { current: pf.elements.current.value, new: pf.elements.new.value });
        Auth.save(r);
        pf.reset(); paintMeter(pf);
        toast('Contraseña actualizada. Se cerraron las sesiones de sus otros dispositivos.', 'success');
        loadDevices();
      } catch (ex) { toast(ex.message, 'error'); }
    };
    document.getElementById('mfa-toggle').onclick = () => (mfa ? mfaDisableForm() : mfaSetup());
  }
  function ago(iso) {
    const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
    if (s < 90) return 'ahora mismo';
    if (s < 3600) return `hace ${Math.round(s / 60)} min`;
    if (s < 86400) return `hace ${Math.round(s / 3600)} h`;
    return `hace ${Math.round(s / 86400)} días`;
  }
  const DEVICE_ICON = d => (/Android|iPhone|iPad/.test(d) ? '📱' : d === 'Desconocido' ? '❔' : '💻');
  async function loadDevices() {
    const box = document.getElementById('devices');
    if (!box) return;
    let list; try { list = await api('/api/auth/sessions'); } catch (e) { box.innerHTML = `<p class="muted">${esc(e.message)}</p>`; return; }
    const others = list.filter(x => !x.current).length;
    box.innerHTML = `<ul class="device-list">${list.map(x => `
      <li class="${x.current ? 'current' : ''}">
        <span class="device-icon" aria-hidden="true">${DEVICE_ICON(x.device)}</span>
        <div><b>${esc(x.device)}</b>${x.current ? ' <span class="status approved">Este dispositivo</span>' : ''}
          <small>IP ${esc(x.ip || '—')} · última actividad ${esc(ago(x.last_seen))} · desde ${esc(new Date(x.created_at).toLocaleDateString('es'))}</small></div>
        <button class="ghost-btn" data-sid="${esc(x.id)}" aria-label="Cerrar sesión en ${esc(x.device)}">${x.current ? 'Salir' : 'Cerrar'}</button>
      </li>`).join('')}</ul>
      ${others ? `<div class="form-actions"><button class="ghost-btn danger" id="revoke-others">Cerrar las ${others} sesiones de otros dispositivos</button></div>` : '<p class="muted">No hay sesiones abiertas en otros dispositivos.</p>'}`;
    box.querySelectorAll('[data-sid]').forEach(b => b.onclick = async () => {
      const cur = b.closest('li').classList.contains('current');
      if (cur) { Auth.logout(); return; }
      try { await api(`/api/auth/sessions/${encodeURIComponent(b.dataset.sid)}`, { method: 'DELETE' }); toast('Sesión cerrada en ese dispositivo.', 'success'); loadDevices(); }
      catch (e) { toast(e.message, 'error'); }
    });
    document.getElementById('revoke-others')?.addEventListener('click', async () => {
      if (!confirm('¿Cerrar la sesión en todos sus otros dispositivos?')) return;
      try { const r = await post('/api/auth/sessions/revoke-others', {}); toast(`${r.closed} sesión(es) cerrada(s).`, 'success'); loadDevices(); }
      catch (e) { toast(e.message, 'error'); }
    });
  }

  async function mfaSetup() {
    const area = document.getElementById('mfa-area');
    let d; try { d = await post('/api/auth/2fa/setup', {}); } catch (e) { toast(e.message, 'error'); return; }
    const grouped = d.secret.match(/.{1,4}/g).join(' ');
    area.innerHTML = `<div class="mfa-setup">
      <ol>
        <li>Abra su aplicación autenticadora (Google Authenticator, Microsoft Authenticator, Aegis, 2FAS…).</li>
        <li>Escanee este código con la app:
          <div class="qr-box">${window.IPVQR ? window.IPVQR.svg(d.otpauth_uri, { size: 210 }) : ''}</div>
          <small class="muted">¿No puede escanear? Introduzca la clave manualmente <em>(tipo: basada en tiempo)</em>:</small>
          <div class="secret-box"><code>${esc(grouped)}</code><button class="ghost-btn" id="copy-secret">Copiar</button></div>
          <a class="otp-link" href="${esc(d.otpauth_uri)}">📱 Abrir directamente en la app autenticadora (desde el móvil)</a></li>
        <li>Escriba el código de 6 dígitos que muestra la app:</li>
      </ol>
      <div class="otp-confirm"><input id="mfa-code" inputmode="numeric" maxlength="6" placeholder="000000" autocomplete="one-time-code"><button class="primary-btn" id="mfa-confirm">Confirmar y activar</button></div></div>`;
    document.getElementById('copy-secret').onclick = () => navigator.clipboard?.writeText(d.secret).then(() => toast('Clave copiada.', 'success'));
    const input = document.getElementById('mfa-code'); input.focus();
    document.getElementById('mfa-confirm').onclick = async () => {
      try {
        const r = await post('/api/auth/2fa/enable', { code: input.value });
        await Auth.tryRefresh();
        area.innerHTML = `<div class="recovery">
          <b>✅ Verificación en dos pasos activada</b>
          <p>Guarde estos <b>códigos de recuperación</b> en un lugar seguro. Cada uno sirve <b>una sola vez</b> si pierde el teléfono. No se volverán a mostrar.</p>
          <div class="recovery-grid">${r.recovery_codes.map(c => `<code>${esc(c)}</code>`).join('')}</div>
          <div class="form-actions"><button class="ghost-btn" id="rc-download">Descargar .txt</button><button class="primary-btn" data-action="close-modal">Ya los guardé</button></div></div>`;
        document.getElementById('rc-download').onclick = () => {
          const blob = new Blob([`IPV · Fichas y Costos — Códigos de recuperación\n${Auth.user.email}\n${new Date().toLocaleString('es')}\n\n${r.recovery_codes.join('\n')}\n`], { type: 'text/plain' });
          const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: 'ipv-codigos-recuperacion.txt' }); a.click(); URL.revokeObjectURL(a.href);
        };
        document.getElementById('mfa-toggle').remove();
        triggerConfettiSafe();
      } catch (e) { toast(e.message, 'error'); input.select(); }
    };
  }
  function mfaDisableForm() {
    document.getElementById('mfa-area').innerHTML = `<form class="form-grid mfa-setup" id="mfa-off">
      <label>Contraseña<input type="password" name="password" required autocomplete="current-password"></label>
      <label>Código actual o de recuperación<input name="code" required inputmode="numeric" autocomplete="one-time-code"></label>
      <div class="form-actions"><button class="primary-btn danger" type="submit">Desactivar verificación</button></div></form>`;
    document.getElementById('mfa-off').onsubmit = async e => {
      e.preventDefault();
      try { await post('/api/auth/2fa/disable', { password: e.target.elements.password.value, code: e.target.elements.code.value }); await Auth.tryRefresh(); toast('Verificación en dos pasos desactivada.', 'success'); openAccountSecurity(); }
      catch (ex) { toast(ex.message, 'error'); }
    };
  }
  const triggerConfettiSafe = () => { try { window.triggerConfetti?.(2000); } catch { /* opcional */ } };

  /* ───────────── Gestión de usuarios (admin) ───────────── */
  const ROLE_LABEL = { admin: 'Administrador', editor: 'Editor', viewer: 'Consulta' };

  /* ───────────── Sistema de Seguridad por Usuarios: permisos por módulo ─────────────
     «Valores del IPV» es una sola entrada con dos pestañas (Valores e Inventario) y un
     único permiso de módulo. Cada usuario puede ver, editar y/o ver costos por apartado;
     los cambios se aplican al instante, sin cerrar sesiones. */
  const MODULES = {
    materials: 'Valores del IPV e Inventario', products: 'Productos y servicios',
    fichas: 'Fichas de costo', controls: 'Controles de IPV', trash: 'Papelera de reciclaje',
  };
  const PERM_COLS = [['view', 'Ver'], ['edit', 'Editar'], ['costs', 'Ver costos']];
  const PERM_PRESETS = [
    ['completo', 'Acceso completo'], ['consulta', 'Solo consulta'],
    ['almacen', 'Almacén (sin costos)'], ['costos', 'Todo menos costos'],
  ];
  function presetPerms(kind) {
    const mods = Object.keys(MODULES);
    const make = (view, edit, costs) => Object.fromEntries(mods.map(m => [m, { view, edit, costs }]));
    if (kind === 'completo') return make(true, true, true);
    if (kind === 'consulta') return { ...make(true, false, true), materials: { view: true, edit: false, costs: false } };
    if (kind === 'almacen') return { ...make(false, false, false), materials: { view: true, edit: true, costs: false } };
    if (kind === 'costos') return make(true, true, false);
    return null;
  }
  function resumenPermisos(perms, role) {
    if (role === 'admin') return 'acceso completo (administrador)';
    if (!perms) return 'según su rol';
    const notas = [];
    Object.entries(perms).forEach(([m, q]) => {
      if (!q.view) notas.push(`sin ${MODULES[m] || m}`);
      else if (!q.edit && !q.costs) notas.push(`${MODULES[m] || m}: solo consulta`);
      else if (!q.costs) notas.push(`${MODULES[m] || m}: sin costos`);
      else if (!q.edit) notas.push(`${MODULES[m] || m}: sin edición`);
    });
    if (!notas.length) return 'acceso completo';
    return notas.length > 2 ? `${notas.slice(0, 2).join(' · ')} · +${notas.length - 2}` : notas.join(' · ');
  }

  async function openPermissions(u) {
    if (u.role === 'admin') {
      showModal('Permisos por módulo', `${u.name} · ${u.email}`, `
        <section class="sec-card ok"><div class="sec-icon">🛡</div>
        <div><b>Los administradores siempre tienen acceso completo</b>
        <p>Nadie puede limitar a un administrador: así nunca queda fuera del sistema ni de la
        gestión de usuarios. Si necesita restringirle los costos o la edición, cámbiele el rol a
        Editor o Consulta y ajuste ahí sus permisos.</p></div></section>
        <div class="form-actions"><button class="primary-btn" data-action="close-modal">Entendido</button></div>`);
      return;
    }
    let draft = JSON.parse(JSON.stringify(u.permissions || presetPerms('consulta')));
    const paint = () => {
      document.querySelectorAll('.perm-table tr[data-mod]').forEach(tr => {
        const mod = tr.dataset.mod;
        tr.querySelectorAll('input[type="checkbox"]').forEach(cb => { cb.checked = !!(draft[mod] && draft[mod][cb.dataset.perm]); });
      });
    };
    showModal('Permisos por módulo', `${u.name} · rol ${ROLE_LABEL[u.role] || u.role} — se aplican al instante, sin cerrar sus sesiones`, `
      <div class="perm-presets">${PERM_PRESETS.map(([k, label]) => `<button class="ghost-btn" data-preset="${k}">${label}</button>`).join('')}
        <button class="ghost-btn" data-preset="rol" title="Borra los ajustes y deja los permisos de su rol">Restablecer según rol</button></div>
      <div class="table-wrap"><table class="perm-table"><thead><tr>${idTh()}<th>Módulo</th>${PERM_COLS.map(([, l]) => `<th class="center">${l}</th>`).join('')}</tr></thead>
      <tbody>${Object.entries(MODULES).map(([mod, label], i) => `
        <tr data-mod="${mod}">${idTd(i, mod)}<td><b>${label}</b><br><small>${mod === 'materials' ? 'incluye las pestañas Valores e Inventario' : mod}</small></td>
        ${PERM_COLS.map(([perm]) => `<td class="center"><label class="check-inline"><input type="checkbox" data-perm="${perm}" aria-label="${label}: ${perm}"></label></td>`).join('')}</tr>`).join('')}
      </tbody></table></div>
      <p class="muted">«Ver costos» controla precios, importes y valores en dinero: sin ese permiso el
      servidor no los envía (en la web aparecen como 🔒 y en el API como <code>null</code>). «Editar» y
      «Ver costos» implican «Ver». Los cambios surten efecto en la siguiente petición del usuario.</p>
      <div class="form-actions"><button class="primary-btn" id="perm-save">Guardar permisos</button></div>`);
    paint();
    document.querySelectorAll('.perm-presets [data-preset]').forEach(b => b.onclick = () => {
      const preset = presetPerms(b.dataset.preset);
      draft = preset || JSON.parse(JSON.stringify(u.permissions || presetPerms('consulta')));
      if (!preset) { savePerms(true); return; }  // «según rol»: borra los ajustes guardados
      paint();
    });
    document.querySelectorAll('.perm-table input[type="checkbox"]').forEach(cb => cb.onchange = () => {
      const mod = cb.closest('tr').dataset.mod;
      draft[mod] = draft[mod] || { view: true, edit: false, costs: true };
      draft[mod][cb.dataset.perm] = cb.checked;
      if (!draft[mod].view) { draft[mod].edit = false; draft[mod].costs = false; }  // sin acceso no hay nada que editar
      paint();
    });
    async function savePerms(reset = false) {
      try {
        const body = reset ? { reset_permissions: true } : { permissions: draft };
        await api(`/api/users/${u.id}`, { method: 'PUT', body: JSON.stringify(body) });
        toast(reset ? `Permisos de ${u.name} restablecidos según su rol.` : `Permisos de ${u.name} actualizados.`, 'success');
        closeModal(); openUsers();
      } catch (e) { toast(e.message, 'error'); }
    }
    document.getElementById('perm-save').onclick = () => savePerms(false);
  }
  async function openUsers() {
    let users; try { users = await api('/api/users'); } catch (e) { toast(e.message, 'error'); return; }
    showModal('Usuarios y permisos', `${users.length} cuentas · los cambios de rol o estado cierran sus sesiones al instante`, `
      <div class="table-wrap"><table class="users-table"><thead><tr>${idTh()}<th>Usuario</th><th>Rol</th><th>2FA</th><th>Estado</th><th>Último acceso</th><th>Acciones</th></tr></thead><tbody>
      ${users.map((u, i) => `<tr data-id="${u.id}">${idTd(i, u.id)}
        <td><b>${esc(u.name)}</b><br><small>${esc(u.email)}</small><br><small class="perm-resume" title="Permisos por módulo">🔐 ${esc(resumenPermisos(u.permissions, u.role))}</small></td>
        <td><select data-role>${Object.entries(ROLE_LABEL).map(([k, v]) => `<option value="${k}" ${k === u.role ? 'selected' : ''}>${v}</option>`).join('')}</select></td>
        <td>${u.mfa ? '<span class="status approved">Activa</span>' : '<span class="status pending">No</span>'}</td>
        <td>${u.locked ? '<span class="status difference">Bloqueado</span>' : u.active ? '<span class="status validated">Activo</span>' : '<span class="status">Inactivo</span>'}${u.must_change_password ? '<br><span class="status pending">Debe cambiar contraseña</span>' : ''}</td>
        <td><small>${u.last_login ? esc(new Date(u.last_login).toLocaleString('es')) : '—'}</small></td>
        <td class="user-actions">
          <button class="ghost-btn" data-perm title="Permisos por módulo (ver, editar, ver costos)">🔐</button>
          <button class="ghost-btn" data-op="active" title="${u.active ? 'Desactivar' : 'Activar'}">${u.active ? '⏸' : '▶'}</button>
          ${u.locked ? '<button class="ghost-btn" data-op="unlock" title="Desbloquear">🔓</button>' : ''}
          ${u.mfa ? '<button class="ghost-btn" data-op="reset_mfa" title="Restablecer 2FA">♻</button>' : ''}
          <button class="ghost-btn" data-op="revoke_sessions" title="Cerrar todas sus sesiones">⎋</button>
          ${u.must_change_password ? '' : '<button class="ghost-btn" data-op="force_password_change" title="Exigir cambio de contraseña en el próximo acceso">🔑</button>'}
        </td></tr>`).join('')}
      </tbody></table></div>
      <h3 class="sec-title">Nuevo usuario</h3>
      <form id="new-user" class="form-grid" autocomplete="off">
        <label>Nombre<input name="name" required maxlength="120"></label>
        <label>Correo<input name="email" type="email" required maxlength="200"></label>
        <label>Rol<select name="role">${Object.entries(ROLE_LABEL).map(([k, v]) => `<option value="${k}" ${k === 'viewer' ? 'selected' : ''}>${v}</option>`).join('')}</select></label>
        <label>Permisos por módulo<select name="preset"><option value="">Según su rol (recomendado)</option>${PERM_PRESETS.map(([k, l]) => `<option value="${k}">${l}</option>`).join('')}</select></label>
        <label>Contraseña inicial<input name="password" type="password" required minlength="10" autocomplete="new-password"></label>
        <label class="check-row"><input type="checkbox" name="must_change_password" checked> Debe cambiarla en su primer acceso (recomendado)</label>
        <div class="form-actions"><button class="ghost-btn" type="button" id="gen-pw">Generar segura</button><button class="primary-btn" type="submit">Crear usuario</button></div>
      </form>`);
    const byId = id => users.find(u => String(u.id) === String(id));
    const update = async (id, body, msg) => { try { await api(`/api/users/${id}`, { method: 'PUT', body: JSON.stringify(body) }); toast(msg, 'success'); openUsers(); } catch (e) { toast(e.message, 'error'); openUsers(); } };
    document.querySelectorAll('.users-table select[data-role]').forEach(sel => sel.onchange = () => {
      const id = sel.closest('tr').dataset.id;
      if (confirm(`¿Cambiar el rol de ${byId(id).email} a ${ROLE_LABEL[sel.value]}?`)) update(id, { role: sel.value }, 'Rol actualizado.'); else openUsers();
    });
    document.querySelectorAll('.users-table button[data-perm]').forEach(b => b.onclick = () => openPermissions(byId(b.closest('tr').dataset.id)));
    document.querySelectorAll('.user-actions button[data-op]').forEach(b => b.onclick = () => {
      const id = b.closest('tr').dataset.id, u = byId(id), op = b.dataset.op;
      const ops = {
        active: [{ active: !u.active }, `¿${u.active ? 'Desactivar' : 'Activar'} a ${u.email}?`, 'Estado actualizado.'],
        unlock: [{ unlock: true }, `¿Desbloquear a ${u.email}?`, 'Cuenta desbloqueada.'],
        reset_mfa: [{ reset_mfa: true }, `¿Restablecer la verificación en dos pasos de ${u.email}? Tendrá que configurarla de nuevo.`, '2FA restablecida.'],
        revoke_sessions: [{ revoke_sessions: true }, `¿Cerrar todas las sesiones de ${u.email}?`, 'Sesiones cerradas.'],
        force_password_change: [{ force_password_change: true }, `¿Exigir a ${u.email} que cambie su contraseña en el próximo acceso?`, 'Se exigirá el cambio de contraseña.'],
      }[op];
      if (confirm(ops[1])) update(id, ops[0], ops[2]);
    });
    const f = document.getElementById('new-user');
    document.getElementById('gen-pw').onclick = () => {
      const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789#$%&*+-=?@';
      const rnd = crypto.getRandomValues(new Uint32Array(16));
      const pw = 'Aa1#' + [...rnd].map(n => chars[n % chars.length]).join('');
      f.elements.password.type = 'text'; f.elements.password.value = pw;
      navigator.clipboard?.writeText(pw); toast('Contraseña generada y copiada. Entréguela por un canal seguro.', 'success');
    };
    f.onsubmit = async e => {
      e.preventDefault();
      const body = { ...Object.fromEntries(new FormData(f)), must_change_password: f.elements.must_change_password.checked };
      const preset = presetPerms(body.preset || '');
      delete body.preset;
      if (preset) body.permissions = preset;
      try { await post('/api/users', body); toast('Usuario creado.', 'success'); openUsers(); }
      catch (ex) { toast(ex.message, 'error'); }
    };
  }

  async function verifyAudit() {
    try {
      const r = await api('/api/audit/verify');
      showModal('Integridad de la auditoría', 'Cadena de sellos HMAC-SHA256', `
        <section class="sec-card ${r.valid ? 'ok' : 'danger'}"><div class="sec-icon">${r.valid ? '✅' : '🚨'}</div>
        <div><b>${esc(r.message)}</b><p>${r.valid ? 'Ningún evento ha sido modificado, insertado ni eliminado fuera del sistema.' : `Se detectó una alteración a partir del evento #${esc(r.broken_at)}. Conserve una copia de la base de datos y revise el acceso al servidor.`}${r.legacy ? ` (${r.legacy} eventos previos a la activación de la cadena no se verifican.)` : ''}</p></div></section>
        <div class="form-actions"><button class="primary-btn" data-action="close-modal">Cerrar</button></div>`);
    } catch (e) { toast(e.message, 'error'); }
  }

  /* ───────────── Paleta de comandos ───────────── */
  /* «Inventario» es ahora la segunda pestaña de «Valores del IPV»: setView lo resuelve */
  const go = v => () => { closePalette(); setView(v); };
  const ver = (m, q = 'view') => Auth.can(m, q);
  const commands = () => [
    { icon: '◈', label: 'Ir a Resumen', run: go('dashboard') },
    { icon: '▦', label: 'Ir a Productos y servicios', run: go('products'), perm: ['products'] },
    { icon: '◇', label: 'Ir a Valores del IPV (pestaña Valores)', run: go('materials'), perm: ['materials'] },
    { icon: '▣', label: 'Ir a Inventario (pestaña de Valores del IPV)', run: go('inventory'), perm: ['materials'] },
    { icon: '▤', label: 'Ir a Fichas de costo', run: go('fichas'), perm: ['fichas'] },
    { icon: '✓', label: 'Ir a Controles de IPV', run: go('controls'), perm: ['controls'] },
    { icon: '🗑', label: 'Ir a Papelera de reciclaje', run: go('trash'), perm: ['trash'] },
    { icon: '🔑', label: 'Ir a Licencia', run: go('license') },
    { icon: '＋', label: 'Crear valor del IPV (desde cualquier apartado)', run: () => { closePalette(); runAction?.('create-material'); }, perm: ['materials', 'edit'] },
    { icon: '＋', label: 'Crear producto o servicio', run: () => { closePalette(); runAction?.('create-product'); }, perm: ['products', 'edit'] },
    { icon: '＋', label: 'Crear ficha de costo', run: () => { closePalette(); runAction?.('create-ficha'); }, perm: ['fichas', 'edit'] },
    { icon: '🧪', label: 'Cargar datos de prueba (comidas, bebidas e inventario)', run: () => { closePalette(); runAction?.('seed-demo'); },
      show: () => ver('materials', 'edit') && ver('products', 'edit') && ver('fichas', 'edit') },
    { icon: '↻', label: 'Actualizar datos', run: () => { closePalette(); refreshData(); } },
    { icon: '📊', label: 'Ver estadísticas avanzadas', run: () => { closePalette(); window.showStatisticsModal?.(); }, perm: ['fichas'] },
    { icon: '⇪', label: 'Importar valores IPV desde CSV', run: () => { closePalette(); openImporter(); }, perm: ['materials', 'edit'] },
    { icon: '⎙', label: 'Exportar vista actual a PDF', run: () => { closePalette(); exportPDF(); } },
    { icon: '⬇', label: 'Descargar reporte de fichas (CSV)', run: () => { closePalette(); window.exportReport?.('fichas_summary'); }, perm: ['fichas'] },
    { icon: '⬇', label: 'Descargar inventario de valores (CSV)', run: () => { closePalette(); window.exportReport?.('materials_inventory'); }, perm: ['materials'] },
    { icon: '🎨', label: 'Personalizar tema y colores', run: () => { closePalette(); openThemeBuilder(); } },
    { icon: '◐', label: 'Alternar modo oscuro/claro', run: () => { closePalette(); document.getElementById('theme-toggle')?.click(); } },
    { icon: '🔔', label: 'Abrir centro de notificaciones', run: () => { closePalette(); bell.click(); } },
    { icon: '↶', label: 'Deshacer última eliminación (Ctrl+Z)', run: () => { closePalette(); window.IPVUX?.undo(); } },
    { icon: '↷', label: 'Rehacer (Ctrl+Shift+Z)', run: () => { closePalette(); window.IPVUX?.redo(); } },
    { icon: '♿', label: 'Accesibilidad: contraste, texto y animaciones', run: () => { closePalette(); window.IPVUX?.openA11y(); } },
    { icon: '🧭', label: 'Ver tutorial de bienvenida', run: () => { closePalette(); window.IPVUX?.startTour(); } },
    { icon: '⚙', label: 'Restablecer diseño del panel de resumen', run: () => { closePalette(); window.IPVUX?.resetDashboard(); } },
    { icon: '🔑', label: 'Licencia: estado, planes y renovación', run: () => { closePalette(); setView('license'); } },
    ...(Auth.user ? [{ icon: '🔐', label: 'Seguridad de mi cuenta (2FA y contraseña)', run: () => { closePalette(); openAccountSecurity(); } }] : []),
    ...(Auth.user?.role === 'admin' ? [
      { icon: '🛠', label: 'Creador de Licencias: crear clave y emitir licencias', run: () => { closePalette(); setView('creator'); } },
      { icon: '👥', label: 'Gestionar usuarios y permisos', run: () => { closePalette(); openUsers(); } },
      { icon: '✅', label: 'Verificar integridad de la auditoría', run: () => { closePalette(); verifyAudit(); } },
      { icon: '🛡', label: 'Registro de auditoría', run: () => { closePalette(); openAudit(); } },
      { icon: '🔓', label: 'Renovar licencia ahora', run: () => { closePalette(); window.IPVLicense?.renew(); } },
      { icon: '💾', label: 'Crear copia de seguridad', run: async () => { closePalette(); try { const b = await api('/api/backup'); toast(`Copia creada: ${b.filename}`, 'success'); } catch (e) { toast(e.message, 'error'); } } },
    ] : []),
    ...(Auth.user ? [{ icon: '⎋', label: 'Cerrar sesión', run: () => Auth.logout() }] : []),
  ];
  let palette = null;
  function closePalette() { palette?.remove(); palette = null; }
  function openPalette() {
    if (palette) return closePalette();
    palette = document.createElement('div');
    palette.className = 'palette-layer';
    palette.innerHTML = `<div class="palette" role="dialog" aria-label="Paleta de comandos"><input placeholder="Escriba un comando…" aria-label="Comando"><ul role="listbox"></ul><footer>↑↓ navegar · ↵ ejecutar · Esc cerrar</footer></div>`;
    document.body.appendChild(palette);
    const input = palette.querySelector('input'), ul = palette.querySelector('ul');
    let sel = 0, list = [];
    const draw = () => {
      const q = norm(input.value);
      list = commands().filter(c => (!c.perm || ver(c.perm[0], c.perm[1] || 'view')) && (!c.show || c.show()))
        .filter(c => q.split(' ').every(w => norm(c.label).includes(w)));
      sel = Math.min(sel, Math.max(0, list.length - 1));
      ul.innerHTML = list.map((c, i) => `<li role="option" class="${i === sel ? 'active' : ''}" data-i="${i}"><span>${c.icon}</span>${esc(c.label)}</li>`).join('') || '<li class="empty">Sin resultados</li>';
    };
    input.oninput = () => { sel = 0; draw(); };
    input.onkeydown = e => {
      if (e.key === 'ArrowDown') { sel = (sel + 1) % Math.max(1, list.length); draw(); e.preventDefault(); }
      else if (e.key === 'ArrowUp') { sel = (sel - 1 + list.length) % Math.max(1, list.length); draw(); e.preventDefault(); }
      else if (e.key === 'Enter') list[sel]?.run();
      else if (e.key === 'Escape') closePalette();
    };
    ul.onclick = e => { const li = e.target.closest('li[data-i]'); if (li) list[+li.dataset.i].run(); };
    palette.onclick = e => { if (e.target === palette) closePalette(); };
    draw(); input.focus();
  }
  document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'p') { e.preventDefault(); openPalette(); }
  });
  const palBtn = document.createElement('button');
  palBtn.className = 'icon-button'; palBtn.title = 'Paleta de comandos (Ctrl+Shift+P)'; palBtn.setAttribute('aria-label', 'Paleta de comandos'); palBtn.textContent = '⌘';
  palBtn.onclick = openPalette;
  actions?.insertBefore(palBtn, bell);
  window.IPVEnterprise = { openPalette, openThemeBuilder, openImporter, exportPDF, openAudit, openAccountSecurity, openUsers, verifyAudit };

  /* ───────────── Modo sin conexión ───────────── */
  if ('serviceWorker' in navigator && location.protocol === 'https:') {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  }
  window.addEventListener('offline', () => { toast('Sin conexión: se muestran los últimos datos disponibles.', 'error'); document.body.classList.add('is-offline'); });
  window.addEventListener('online', () => { toast('Conexión restablecida.', 'success'); document.body.classList.remove('is-offline'); refreshData(true); connectEvents(); });
})();
