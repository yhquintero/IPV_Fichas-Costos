'use strict';
/* ==========================================================================
   IPV Keygen Web — interfaz (JavaScript puro, sin dependencias).
   Nota: no hay atajos de teclado de una sola tecla, así que se puede teclear con
   normalidad (números incluidos) en cualquier campo.
   ========================================================================== */
(() => {
  /* ───────────── utilidades ───────────── */
  const $ = (s, e = document) => e.querySelector(s);
  const $$ = (s, e = document) => Array.from(e.querySelectorAll(s));
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const pad = n => String(n).padStart(2, '0');
  const nf = (n, d = 2) => Number(n).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
  const isNil = v => v === null || v === undefined;
  const usd = n => (isNil(n) ? '—' : `${nf(n, Number.isInteger(+n) ? 0 : 2)} USD`);
  const cup = n => (isNil(n) ? '—' : `$ ${nf(n)} CUP`);
  const pd = iso => { const d = new Date(iso); return Number.isNaN(d.getTime()) ? null : d; };
  const fdate = iso => { const d = pd(iso); return d ? `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}` : (iso ? esc(iso) : '—'); };
  const ftime = iso => { const d = pd(iso); return d ? `${pad(d.getHours())}:${pad(d.getMinutes())}` : ''; };
  const fdt = iso => (iso ? `${fdate(iso)} ${ftime(iso)}` : '—');
  const fepoch = sec => (sec ? fdate(new Date(sec * 1000).toISOString()) : '—');
  const ymd = s => (s ? s.split('-').reverse().join('/') : '');
  const mmss = s => `${Math.floor(s / 60)}:${pad(s % 60)}`;
  const MONTHS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
  const monthLabel = ym => MONTHS[Number(ym.slice(5, 7)) - 1] || ym;
  function ago(iso) {
    const d = pd(iso); if (!d) return '';
    const s = Math.max(0, (Date.now() - d.getTime()) / 1000);
    if (s < 60) return 'hace un momento';
    if (s < 3600) return `hace ${Math.floor(s / 60)} min`;
    if (s < 86400) return `hace ${Math.floor(s / 3600)} h`;
    if (s < 86400 * 30) return `hace ${Math.floor(s / 86400)} d`;
    return fdate(iso);
  }

  const STATE = { vigente: 'Vigente', por_vencer: 'Por vencer', programada: 'Programada', vencida: 'Vencida', revocada: 'Anulada' };
  const APPS = { W: ['🖥️', 'Web'], A: ['📱', 'Android'] };
  const EVENTS = { ISSUED: ['🆕', 'Emitida'], RENEWED: ['🔁', 'Renovada'], RESENT: ['📤', 'Reenviada'], REVOKED: ['🚫', 'Anulada'],
    REACTIVATED: ['♻️', 'Reactivada'], PAID: ['💵', 'Cobrada'], UNPAID: ['↩️', 'Cobro deshecho'], NOTE: ['📝', 'Datos editados'],
    IMPORTED: ['📥', 'Importada'] };
  const ROLE_NAMES = { ADMINISTRADOR: 'Administrador', JEFE: 'Jefe', ECONOMICO: 'Económico', ALMACENERO: 'Almacenero' };
  const PAY_METHODS = ['Efectivo', 'Transferencia', 'Zelle', 'MLC', 'CLA', 'Otro'];

  const stateBadge = (st, label) => `<span class="badge ${esc(st)}">${esc(label || STATE[st] || st)}</span>`;
  const appBadge = a => `<span class="badge app">${(APPS[a] || ['', a]).join(' ')}</span>`;
  const roleLabel = r => ROLE_NAMES[r] || r;
  const roleBadge = r => `<span class="badge role">${esc(roleLabel(r))}</span>`;
  const planName = code => state.status?.plans?.[code]?.name || code;
  const vence = i => (i.valid_until ? ymd(i.valid_until) : fepoch(i.expires_at));
  function daysText(i) {
    if (i.state === 'revocada') return 'anulada';
    if (i.state === 'vencida') return 'vencida';
    if (i.state === 'programada') return `inicia ${ymd(i.valid_from)}`;
    return i.days_left === 0 ? 'vence hoy' : `${i.days_left} d restantes`;
  }

  /* ───────────── estado y sesión ───────────── */
  const state = {
    status: null, user: null, caps: new Set(), deadline: 0, routeSeq: 0, timer: null,
    hist: { q: '', state: '', plan: '', app: '', paid: '', from: '', to: '', sort: 'created_at', dir: 'desc', limit: 25, offset: 0 },
    audit: { action: '', search: '', offset: 0 },
  };
  const has = c => state.caps.has(c);
  const hasAny = (...c) => c.some(has);
  const S = { get: k => sessionStorage.getItem('kg.' + k), set: (k, v) => sessionStorage.setItem('kg.' + k, v), del: k => sessionStorage.removeItem('kg.' + k) };
  class ApiErr extends Error { constructor(msg, status, data = {}) { super(msg); this.status = status; this.data = data; } }
  class Cancelled extends Error {}

  const saveSession = d => { S.set('access', d.access_token); S.set('refresh', d.refresh_token); };
  const clearSession = () => { S.del('access'); S.del('refresh'); };
  let refreshing = null;
  async function refreshTokens() {
    if (refreshing) return refreshing;
    refreshing = (async () => {
      const rt = S.get('refresh'); if (!rt) return false;
      try {
        const r = await fetch('/api/auth/refresh', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh_token: rt }) });
        if (!r.ok) return false;
        saveSession(await r.json()); return true;
      } catch { return false; }
    })();
    try { return await refreshing; } finally { refreshing = null; }
  }

  async function api(path, { method = 'GET', body, raw = false, retry = true } = {}) {
    const headers = {};
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    const token = S.get('access'); if (token) headers.Authorization = `Bearer ${token}`;
    let r;
    try { r = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) }); }
    catch { throw new ApiErr('Sin conexión con el Keygen. ¿Sigue en marcha?', 0); }
    if (r.status === 401 && retry && token && !path.startsWith('/api/auth/')) {
      if (await refreshTokens()) return api(path, { method, body, raw, retry: false });
      clearSession(); renderAuth('Su sesión caducó. Inicie sesión de nuevo.');
      throw new Cancelled('sesión caducada');
    }
    if (raw && r.ok) return r;
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new ApiErr(data.error || `Error ${r.status}`, r.status, data);
    return data;
  }

  /* ───────────── componentes: avisos, ventanas, panel lateral ───────────── */
  function toast(msg, type = '') {
    const t = document.createElement('div'); t.className = `toast ${type}`; t.textContent = msg;
    $('#toasts').appendChild(t); setTimeout(() => t.remove(), type === 'error' ? 7000 : 4200);
  }
  const fail = e => { if (!(e instanceof Cancelled)) toast(e.message || String(e), 'error'); };

  function modal(html, { wide = false, onMount, onClose } = {}) {
    const ov = document.createElement('div'); ov.className = 'overlay';
    ov.innerHTML = `<div class="modal${wide ? ' wide' : ''}" role="dialog" aria-modal="true">${html}</div>`;
    const onKey = e => { if (e.key === 'Escape') close(); };
    function close() { ov.remove(); document.removeEventListener('keydown', onKey); onClose?.(); }
    ov.addEventListener('mousedown', e => { if (e.target === ov) close(); });
    document.addEventListener('keydown', onKey);
    document.body.appendChild(ov);
    $$('[data-close]', ov).forEach(b => b.addEventListener('click', close));
    ($('input:not([type=hidden]):not([type=checkbox]), select, textarea', ov))?.focus();
    onMount?.(ov, close);
    return { el: ov, close };
  }

  /** Cuadro de diálogo con campos. Devuelve los valores (o false si se cancela). */
  function ask({ title, message = '', confirm = 'Aceptar', danger = false, fields = [], wide = false }) {
    return new Promise(resolve => {
      let done = false;
      const inputs = fields.map(f => {
        const common = `name="${esc(f.name)}" placeholder="${esc(f.placeholder || '')}" autocomplete="${esc(f.autocomplete || 'off')}"`;
        let control;
        if (f.type === 'textarea') control = `<textarea ${common}>${esc(f.value || '')}</textarea>`;
        else if (f.type === 'select') control = `<select name="${esc(f.name)}">${f.options.map(([v, t]) => `<option value="${esc(v)}" ${v === f.value ? 'selected' : ''}>${esc(t)}</option>`).join('')}</select>`;
        else if (f.type === 'checkbox') return `<label class="check"><input type="checkbox" name="${esc(f.name)}" ${f.value ? 'checked' : ''}> ${esc(f.label)}</label>`;
        else control = `<input ${common} type="${esc(f.type || 'text')}" value="${esc(f.value || '')}">`;
        return `<label class="f"><span${f.required ? ' class="req"' : ''}>${esc(f.label)}</span>${control}${f.hint ? `<small class="hint">${esc(f.hint)}</small>` : ''}</label>`;
      }).join('');
      modal(`<h2>${esc(title)}</h2>${message ? `<p class="sub">${esc(message)}</p>` : ''}
        <form class="stack" novalidate>${inputs}<p class="error" hidden></p>
        <div class="row end"><button type="button" class="btn ghost" data-close>Cancelar</button>
        <button class="btn ${danger ? 'danger' : 'primary'}" type="submit">${esc(confirm)}</button></div></form>`, {
        wide,
        onMount: (el, close) => {
          const form = $('form', el), err = $('.error', form);
          form.addEventListener('submit', e => {
            e.preventDefault();
            const values = {};
            for (const f of fields) {
              const control = form.elements[f.name];
              values[f.name] = f.type === 'checkbox' ? control.checked : control.value;
              const v = f.type === 'checkbox' ? '' : String(values[f.name]).trim();
              let problem = '';
              if (f.required && !v) problem = `${f.label}: campo obligatorio.`;
              else if (f.minLength && v && v.length < f.minLength) problem = `${f.label}: mínimo ${f.minLength} caracteres.`;
              else if (f.match && v !== f.match) problem = f.matchError || 'El texto no coincide.';
              else if (f.same && v !== form.elements[f.same].value.trim()) problem = f.sameError || 'Los campos no coinciden.';
              if (problem) { err.textContent = problem; err.hidden = false; return; }
            }
            done = true; close(); resolve(fields.length ? values : true);
          });
        },
        onClose: () => { if (!done) resolve(false); },
      });
    });
  }

  function drawer(html) {
    const wrap = document.createElement('div'); wrap.className = 'drawer-wrap';
    wrap.innerHTML = `<aside class="drawer" role="dialog" aria-modal="true">${html}</aside>`;
    const onKey = e => { if (e.key === 'Escape') close(); };
    function close() { wrap.remove(); document.removeEventListener('keydown', onKey); }
    wrap.addEventListener('mousedown', e => { if (e.target === wrap) close(); });
    document.addEventListener('keydown', onKey);
    document.body.appendChild(wrap);
    return { el: $('.drawer', wrap), close };
  }

  async function copyText(text, msg = 'Copiado al portapapeles') {
    try { await navigator.clipboard.writeText(text); }
    catch {
      const ta = document.createElement('textarea'); ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select(); try { document.execCommand('copy'); } catch { /* sin portapapeles */ } ta.remove();
    }
    toast(msg);
  }
  function download(name, content, type = 'text/plain;charset=utf-8') {
    const url = URL.createObjectURL(content instanceof Blob ? content : new Blob([content], { type }));
    const a = document.createElement('a'); a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }
  function genPassword(n = 14) {
    const sets = ['ABCDEFGHJKLMNPQRSTUVWXYZ', 'abcdefghijkmnpqrstuvwxyz', '23456789', '#$%&*+-=?@'];
    const all = sets.join('');
    const rnd = m => { const a = new Uint32Array(1); let x; do { crypto.getRandomValues(a); x = a[0]; } while (x >= Math.floor(4294967296 / m) * m); return x % m; };
    const out = sets.map(s => s[rnd(s.length)]);
    while (out.length < n) out.push(all[rnd(all.length)]);
    for (let i = out.length - 1; i > 0; i--) { const j = rnd(i + 1); [out[i], out[j]] = [out[j], out[i]]; }
    return out.join('');
  }
  const debounce = (fn, ms = 300) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
  const showErr = (form, msg) => { const e = $('.error', form); if (e) { e.textContent = msg; e.hidden = false; } };
  const applyTheme = t => { document.documentElement.dataset.theme = t; localStorage.setItem('kg.theme', t); };
  applyTheme(localStorage.getItem('kg.theme') || (matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'));

  /* ───────────── pantallas de acceso ───────────── */
  function authShell(inner) {
    $('#app').innerHTML = `<div class="auth-wrap"><div class="card auth-card">
      <div class="brand"><div class="logo">🔑</div><div><h1>IPV Keygen</h1><p>Licencias de IPV Web e IPV Android</p></div></div>${inner}
      <p class="auth-foot">🔒 Sesión protegida · bloqueo tras 5 intentos fallidos</p></div></div>`;
  }

  async function renderAuth(message = '') {
    stopTimer(); state.user = null; state.status = null;
    let info;
    try { info = await api('/api/bootstrap'); } catch (e) { authShell(`<div class="error">${esc(e.message)}</div>`); return; }
    if (info.needs_setup) return renderSetup(info);
    authShell(`<form id="login" class="stack" novalidate>
      ${message ? `<div class="callout warn"><span class="ico">ℹ️</span><div>${esc(message)}</div></div>` : ''}
      <label class="f"><span class="req">Usuario</span><input name="username" autocomplete="username" autocapitalize="none" spellcheck="false"></label>
      <label class="f"><span class="req">Contraseña</span><input name="password" type="password" autocomplete="current-password"></label>
      <label class="f" id="otpbox" hidden><span>Código de verificación (2FA)</span><input name="otp" inputmode="numeric" autocomplete="one-time-code" maxlength="20" placeholder="123456 o código de recuperación"></label>
      <p class="error" hidden></p><button class="btn primary" type="submit">Entrar</button></form>`);
    const form = $('#login'); form.elements.username.focus();
    form.addEventListener('submit', async e => {
      e.preventDefault(); $('.error', form).hidden = true;
      const btn = $('button', form); btn.disabled = true;
      try {
        const d = await api('/api/auth/login', { method: 'POST', retry: false, body: {
          username: form.elements.username.value.trim(), password: form.elements.password.value, otp: form.elements.otp.value.trim() } });
        saveSession(d); await boot();
      } catch (ex) {
        if (ex.data?.mfa_required) { $('#otpbox').hidden = false; form.elements.otp.focus(); showErr(form, ex.message); }
        else showErr(form, ex.message);
      } finally { btn.disabled = false; }
    });
  }

  function renderSetup(info) {
    authShell(`<form id="setup" class="stack" novalidate>
      <div class="callout ok"><span class="ico">🚀</span><div><b>Primer arranque.</b> Cree el usuario ADMINISTRADOR de este Keygen; después podrá crear más usuarios con sus roles.</div></div>
      <label class="f"><span class="req">Usuario</span><input name="username" autocomplete="username" autocapitalize="none" spellcheck="false" placeholder="admin"></label>
      <label class="f"><span>Nombre completo</span><input name="name" autocomplete="name"></label>
      <div class="grid2"><label class="f"><span class="req">Contraseña</span><input name="password" type="password" autocomplete="new-password"></label>
        <label class="f"><span class="req">Repetir contraseña</span><input name="repeat" type="password" autocomplete="new-password"></label></div>
      <small class="hint">Mínimo 10 caracteres, combinando mayúsculas, minúsculas, números o símbolos.</small>
      ${info.setup_token_required ? '<label class="f"><span class="req">Código de instalación</span><input name="token" autocomplete="off"><small class="hint">Aparece en la consola donde inició el Keygen.</small></label>' : ''}
      <p class="error" hidden></p><button class="btn primary" type="submit">Crear administrador y entrar</button></form>`);
    const form = $('#setup'); form.elements.username.focus();
    form.addEventListener('submit', async e => {
      e.preventDefault(); $('.error', form).hidden = true;
      const f = form.elements;
      if (f.password.value !== f.repeat.value) return showErr(form, 'Las contraseñas no coinciden.');
      const btn = $('button', form); btn.disabled = true;
      try {
        await api('/api/setup', { method: 'POST', body: { username: f.username.value.trim(), name: f.name.value.trim(), password: f.password.value, token: f.token?.value.trim() || '' } });
        const d = await api('/api/auth/login', { method: 'POST', retry: false, body: { username: f.username.value.trim(), password: f.password.value } });
        saveSession(d); toast('Administrador creado. ¡Bienvenido!'); await boot();
      } catch (ex) { showErr(form, ex.message); } finally { btn.disabled = false; }
    });
  }

  function renderForcedPassword() {
    authShell(`<form id="forced" class="stack" novalidate>
      <div class="callout warn"><span class="ico">🔑</span><div><b>Cambie su contraseña.</b> Caducó o el administrador exige cambiarla para continuar.</div></div>
      <label class="f"><span class="req">Contraseña actual</span><input name="current" type="password" autocomplete="current-password"></label>
      <div class="grid2"><label class="f"><span class="req">Nueva contraseña</span><input name="new" type="password" autocomplete="new-password"></label>
        <label class="f"><span class="req">Repetir nueva</span><input name="repeat" type="password" autocomplete="new-password"></label></div>
      <p class="error" hidden></p><div class="row"><button class="btn primary" type="submit">Guardar y continuar</button>
      <button class="btn ghost" type="button" data-act="logout">Cerrar sesión</button></div></form>`);
    const form = $('#forced'); form.elements.current.focus();
    form.addEventListener('submit', async e => {
      e.preventDefault(); $('.error', form).hidden = true;
      if (form.elements.new.value !== form.elements.repeat.value) return showErr(form, 'Las contraseñas nuevas no coinciden.');
      try {
        const d = await api('/api/auth/password', { method: 'POST', body: { current: form.elements.current.value, new: form.elements.new.value } });
        saveSession(d); toast('Contraseña actualizada.'); await boot();
      } catch (ex) { showErr(form, ex.message); }
    });
  }

  function renderForcedMfa() {
    authShell('<div class="callout warn"><span class="ico">🛡️</span><div><b>Verificación en dos pasos obligatoria.</b> Este Keygen exige activarla antes de trabajar.</div></div><div id="mfa" class="stack" style="margin-top:14px"></div><div class="row" style="margin-top:12px"><button class="btn ghost" data-act="logout">Cerrar sesión</button></div>');
    mfaSetup($('#mfa'));
  }

  /* ───────────── verificación en dos pasos (activación) ───────────── */
  async function mfaSetup(box) {
    box.innerHTML = '<button class="btn primary" data-start>Generar código QR</button>';
    $('[data-start]', box).addEventListener('click', async () => {
      try {
        const d = await api('/api/auth/2fa/setup', { method: 'POST', body: {} });
        const qr = window.IPVQR ? window.IPVQR.svg(d.otpauth_uri, { size: 200 }) : '';
        box.innerHTML = `<div class="row" style="align-items:flex-start">${qr ? `<div class="qrbox">${qr}</div>` : ''}
          <div class="stack" style="flex:1;min-width:220px"><p class="hint">Escanee el código con Google Authenticator, Microsoft Authenticator, Aegis u otra aplicación TOTP,
          o escriba esta clave a mano:</p><code class="mono" style="word-break:break-all">${esc(d.secret)}</code>
          <form class="stack" novalidate><label class="f"><span class="req">Código de 6 dígitos</span><input name="code" inputmode="numeric" maxlength="8" autocomplete="one-time-code"></label>
          <p class="error" hidden></p><button class="btn primary" type="submit">Activar</button></form></div></div>`;
        const form = $('form', box); form.elements.code.focus();
        form.addEventListener('submit', async e => {
          e.preventDefault();
          try {
            const r = await api('/api/auth/2fa/enable', { method: 'POST', body: { code: form.elements.code.value.trim() } });
            showRecoveryCodes(r.recovery_codes);
          } catch (ex) { showErr(form, ex.message); }
        });
      } catch (ex) { fail(ex); }
    });
  }

  function showRecoveryCodes(codes) {
    modal(`<h2>✅ Verificación en dos pasos activada</h2>
      <p class="sub">Guarde estos códigos de recuperación en un lugar seguro: cada uno sirve <b>una sola vez</b> si pierde el teléfono.</p>
      <div class="codes">${codes.map(c => `<div>${esc(c)}</div>`).join('')}</div>
      <div class="row" style="margin-top:14px"><button class="btn" data-copy>📋 Copiar</button><button class="btn" data-save>⬇ Descargar .txt</button>
      <span class="spacer"></span><button class="btn primary" data-done>Ya los guardé</button></div>`, {
      onMount: (el, close) => {
        $('[data-copy]', el).addEventListener('click', () => copyText(codes.join('\n'), 'Códigos copiados'));
        $('[data-save]', el).addEventListener('click', () => download('ipv-keygen-codigos-recuperacion.txt', `IPV Keygen — códigos de recuperación\n${state.user?.username || ''}\n\n${codes.join('\n')}\n`));
        $('[data-done]', el).addEventListener('click', () => { close(); });
      },
      onClose: () => { clearSession(); renderAuth('Verificación en dos pasos activada: inicie sesión con su código.'); },
    });
  }

  /* ───────────── estructura principal ───────────── */
  const NAV = [
    ['panel', '📊', 'Panel', () => hasAny('history_all', 'history_own')],
    ['emitir', '🔑', 'Emitir licencia', () => has('emit')],
    ['historial', '🗂️', 'Historial', () => hasAny('history_all', 'history_own')],
    ['usuarios', '👥', 'Usuarios y roles', () => has('users')],
    ['clave', '🛡️', 'Clave y ajustes', () => true],
    ['auditoria', '📜', 'Auditoría', () => has('audit')],
    ['cuenta', '👤', 'Mi cuenta', () => true],
  ];
  const remaining = () => Math.max(0, Math.round((state.deadline - Date.now()) / 1000));

  function keyPillHtml() {
    const k = state.status?.key;
    if (!k || !k.configured) return '<span class="dot"></span><span><b>Sin clave de firma</b><br><small>Créela para poder emitir</small></span>';
    if (k.unlocked && remaining() > 0) return `<span class="dot"></span><span><b>Clave desbloqueada</b><br><small>Se bloquea en ${mmss(remaining())}</small></span>`;
    return '<span class="dot"></span><span><b>Clave bloqueada</b><br><small>Desbloquéela para emitir</small></span>';
  }
  function updateKeyPill() {
    const k = state.status?.key;
    if (k?.unlocked && remaining() === 0) k.unlocked = false;
    const pill = $('#keypill'); if (!pill) return;
    pill.className = `keypill ${!k?.configured ? 'none' : (k.unlocked ? 'open' : '')}`;
    pill.innerHTML = keyPillHtml();
  }
  function setKey(k) { state.status.key = k; state.deadline = Date.now() + (k.seconds_left || 0) * 1000; updateKeyPill(); }
  async function refreshStatus() { const s = await api('/api/status'); applyStatus(s); updateKeyPill(); return s; }
  function startTimer() { stopTimer(); state.timer = setInterval(updateKeyPill, 1000); }
  function stopTimer() { if (state.timer) clearInterval(state.timer); state.timer = null; }
  function applyStatus(s) {
    state.status = s; state.user = s.user; state.caps = new Set(s.caps);
    state.deadline = Date.now() + (s.key.seconds_left || 0) * 1000;
  }

  function renderShell() {
    const u = state.user;
    $('#app').innerHTML = `<div class="topbar"><button class="btn icon ghost" data-act="menu" aria-label="Abrir menú"><span class="hamb" aria-hidden="true"></span></button><b>IPV Keygen</b></div>
      <div class="shell"><aside class="side" id="side">
        <div class="brand" style="margin:0"><div class="logo">🔑</div><div><h1 style="font-size:17px">IPV Keygen</h1><p>Licencias Web y Android</p></div></div>
        <nav class="nav">${NAV.filter(n => n[3]()).map(n => `<a href="#/${n[0]}" data-nav="${n[0]}"><span class="ico">${n[1]}</span>${n[2]}</a>`).join('')}</nav>
        <a class="keypill" href="#/clave" id="keypill"></a>
        <div class="userbox"><div class="who"><div class="avatar">${esc((u.name || u.username)[0].toUpperCase())}</div>
          <div><b>${esc(u.name || u.username)}</b><br><small>${esc(u.username)} · ${esc(roleLabel(u.role))}</small></div></div>
          <div class="row"><button class="btn sm" data-act="theme">🌓 Tema</button><button class="btn sm ghost" data-act="logout">Salir</button></div></div>
      </aside><main class="main" id="view"></main></div>`;
    updateKeyPill();
  }

  const GUARD = {
    panel: () => hasAny('history_all', 'history_own'), emitir: () => has('emit'), historial: () => hasAny('history_all', 'history_own'),
    usuarios: () => has('users'), clave: () => true, auditoria: () => has('audit'), cuenta: () => true,
  };
  const firstView = () => (NAV.find(n => n[3]()) || NAV[4])[0];

  async function route() {
    if (!state.user) return;
    const m = location.hash.match(/^#\/([a-z]+)(?:\?(.*))?$/);
    let name = m ? m[1] : firstView();
    if (!VIEWS[name] || !GUARD[name]()) name = firstView();
    const params = new URLSearchParams(m?.[2] || '');
    const seq = ++state.routeSeq;
    $$('.nav a').forEach(a => a.classList.toggle('active', a.dataset.nav === name));
    $('#side')?.classList.remove('open');
    const el = document.createElement('div');
    try { await VIEWS[name](el, params); }
    catch (e) {
      if (e instanceof Cancelled) return;
      if (e.data?.password_expired) return renderForcedPassword();
      if (e.data?.mfa_setup_required) return renderForcedMfa();
      el.innerHTML = `<div class="callout danger"><span class="ico">⚠️</span><div><b>No se pudo cargar esta sección.</b><br>${esc(e.message)}<br><button class="btn sm" style="margin-top:8px" data-act="reload">Reintentar</button></div></div>`;
    }
    if (seq !== state.routeSeq) return;  // el usuario ya navegó a otra sección
    $('#view')?.replaceChildren(el);
    window.scrollTo(0, 0);
  }

  async function boot() {
    try { applyStatus(await api('/api/status')); }
    catch (e) {
      if (e instanceof Cancelled) return;
      if (e.data?.password_expired) return renderForcedPassword();
      if (e.data?.mfa_setup_required) return renderForcedMfa();
      if (e.status === 401) return renderAuth();
      authShell(`<div class="error">${esc(e.message)}</div><p><button class="btn" data-act="reload">Reintentar</button></p>`);
      return;
    }
    renderShell(); startTimer();
    if (!location.hash) location.hash = `#/${firstView()}`; else route();
  }

  async function logout() {
    const rt = S.get('refresh');
    try { if (rt) await fetch('/api/auth/logout', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh_token: rt }) }); } catch { /* sin red */ }
    clearSession(); location.hash = ''; renderAuth();
  }

  document.addEventListener('click', e => {
    // Pulsar en el menú la sección que ya está abierta la recarga (p. ej. volver al formulario tras emitir)
    const nav = e.target.closest('a[data-nav]');
    if (nav && nav.getAttribute('href') === location.hash.split('?')[0]) { e.preventDefault(); route(); return; }
    const t = e.target.closest('[data-act]'); if (!t) return;
    const act = t.dataset.act;
    if (act === 'menu') { $('#side')?.classList.toggle('open'); e.preventDefault(); }
    else if (act === 'theme') { applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'); }
    else if (act === 'logout') { e.preventDefault(); logout(); }
    else if (act === 'reload') { e.preventDefault(); route(); }
  });
  window.addEventListener('hashchange', route);

  /* ───────────── vista: Panel ───────────── */
  const kpi = (icon, label, value, sub = '', tone = '') => `<div class="kpi ${tone}"><div class="lbl"><span>${icon}</span>${esc(label)}</div><div class="val">${esc(value)}</div><div class="sub">${esc(sub)}</div></div>`;
  function barsHtml(rows) {
    const max = Math.max(1, ...rows.map(r => r[1]));
    return `<div class="bars">${rows.map(([label, n]) => `<div class="bar"><span>${esc(label)}</span><div class="track"><div class="fill" style="width:${(n / max * 100).toFixed(1)}%"></div></div><b>${n}</b></div>`).join('')}</div>`;
  }
  function chartHtml(months, money) {
    const W = 600, H = 190, p = { l: 8, r: 8, t: 18, b: 26 };
    const max = Math.max(1, ...months.map(m => m.count));
    const bw = (W - p.l - p.r) / months.length;
    const bars = months.map((m, i) => {
      const h = (H - p.t - p.b) * (m.count / max);
      const x = p.l + i * bw + bw * 0.18, w = bw * 0.64, y = H - p.b - h;
      return `<g><title>${esc(m.month)}: ${m.count} licencia(s)${money && !isNil(m.usd) ? ` · ${usd(m.usd)}` : ''}</title>
        <rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${w.toFixed(1)}" height="${Math.max(h, m.count ? 3 : 0).toFixed(1)}" rx="4" fill="url(#kgbar)"/>
        ${m.count ? `<text x="${(x + w / 2).toFixed(1)}" y="${(y - 5).toFixed(1)}" text-anchor="middle" font-size="11" fill="currentColor">${m.count}</text>` : ''}
        <text x="${(x + w / 2).toFixed(1)}" y="${H - 8}" text-anchor="middle" font-size="10.5" fill="#92a3c2">${monthLabel(m.month)}</text></g>`;
    }).join('');
    return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Licencias emitidas por mes"><defs><linearGradient id="kgbar" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" style="stop-color:#34d399"/><stop offset="1" style="stop-color:#059669"/></linearGradient></defs>
      <line x1="${p.l}" x2="${W - p.r}" y1="${H - p.b}" y2="${H - p.b}" stroke="#263653"/>${bars}</svg>`;
  }
  function timelineHtml(events) {
    if (!events.length) return '<div class="empty">Sin actividad todavía.</div>';
    return `<div class="timeline">${events.map(ev => {
      const [ic, label] = EVENTS[ev.action] || ['•', ev.action];
      return `<div class="ev"><div class="ic">${ic}</div><div><b>${esc(label)}</b>${ev.customer ? ` · ${esc(ev.customer)}` : ''}${ev.serial ? ` <span class="mono muted">${esc(ev.serial)}</span>` : ''}
        ${ev.detail ? `<div class="hint">${esc(ev.detail)}</div>` : ''}<div class="hint">${esc(ev.actor || 'sistema')} · ${esc(ago(ev.at))}</div></div></div>`;
    }).join('')}</div>`;
  }

  async function viewPanel(el) {
    const s = await api('/api/stats');
    const st = s.by_state, m = s.money;
    const active = st.vigente + st.por_vencer + st.programada;
    const planRows = Object.keys(state.status.plans).map(c => [`${c} · ${planName(c)}`, s.by_plan[c] || 0]);
    el.innerHTML = `<div class="pagehead"><div><h1>Panel</h1><div class="sub">${has('history_all') ? 'Resumen de todas las licencias emitidas' : 'Resumen de las licencias que usted emitió'}</div></div>
        ${has('emit') ? '<a class="btn primary" href="#/emitir">🔑 Emitir licencia</a>' : ''}</div>
      <div class="kpis">
        ${kpi('🧾', 'Emitidas', s.total, 'en total')}
        ${kpi('✅', 'Activas', active, `${st.programada} programada(s)`, 'good')}
        ${kpi('⏳', 'Por vencer', st.por_vencer, 'en 7 días o menos', st.por_vencer ? 'warn' : '')}
        ${kpi('⌛', 'Vencidas', st.vencida, 'sin renovar')}
        ${kpi('🚫', 'Anuladas', st.revocada, 'fuera de cómputo', st.revocada ? 'bad' : '')}
        ${m ? kpi('💵', 'Ingresos', usd(m.revenue_usd), cup(m.revenue_cup), 'good') : ''}
        ${m ? kpi('📅', 'Este mes', usd(m.month_usd), cup(m.month_cup)) : ''}
        ${m ? kpi('🧮', 'Por cobrar', usd(m.unpaid_usd), `${m.unpaid_count} sin cobrar`, m.unpaid_count ? 'warn' : '') : ''}
      </div>
      <div class="cols"><section class="card"><header><h2>Licencias emitidas por mes</h2><small>últimos 12 meses</small></header>${chartHtml(s.months, !!m)}</section>
        <section class="card"><header><h2>Por plan</h2></header>${barsHtml(planRows)}
          <h3 style="margin:18px 0 10px">Por aplicación</h3>${barsHtml([['🖥️ IPV Web', s.by_app.W || 0], ['📱 IPV Android', s.by_app.A || 0]])}</section></div>
      <div class="cols"><section class="card"><header><h2>Próximos vencimientos</h2><small>30 días</small></header>
          ${s.expiring.length ? `<div class="tablewrap"><table><thead><tr><th>Cliente</th><th>App</th><th>Plan</th><th>Vence</th><th></th></tr></thead><tbody>
          ${s.expiring.map(x => `<tr><td><div class="cust">${esc(x.customer)}</div><div class="sm">${esc(x.contact || '')}</div></td><td>${appBadge(x.app)}</td><td>${esc(x.plan)}</td>
            <td>${esc(x.valid_until ? ymd(x.valid_until) : fepoch(x.expires_at))}<div class="sm">${x.days_left} d</div></td>
            <td>${has('emit') ? `<a class="btn sm" href="#/emitir?renew=${x.id}">Renovar</a>` : ''}</td></tr>`).join('')}</tbody></table></div>`
            : '<div class="empty">Ninguna licencia vence en los próximos 30 días. 🎉</div>'}</section>
        <section class="card"><header><h2>Actividad reciente</h2></header>${timelineHtml(s.recent)}</section></div>`;
  }

  /* ───────────── vista: Emitir licencia ───────────── */
  async function ensureUnlocked() {
    const k = state.status.key;
    if (!k.configured) throw new Error(has('keys') ? 'Cree primero la clave de firma en «Clave y ajustes».' : 'Aún no existe la clave de firma: pida a un administrador que la cree.');
    if (k.unlocked && remaining() > 0) return;
    const v = await ask({ title: '🔓 Desbloquear la clave de firma', confirm: 'Desbloquear',
      message: `Escriba la contraseña de la clave. Se volverá a bloquear tras ${state.status.unlock_minutes} min sin uso.`,
      fields: [{ name: 'passphrase', label: 'Contraseña de la clave de firma', type: 'password', required: true }] });
    if (!v) throw new Cancelled('cancelado');
    const r = await api('/api/key/unlock', { method: 'POST', body: { passphrase: v.passphrase } });
    setKey(r.key); toast('🔓 Clave desbloqueada.');
  }

  async function viewEmit(el, params) {
    const s = state.status, money = has('prices');
    let renew = null;
    if (params.get('renew')) {
      try { renew = (await api(`/api/licenses/${encodeURIComponent(params.get('renew'))}`)).license; } catch (e) { fail(e); }
    }
    const planOpts = Object.entries(s.plans).map(([c, p]) => {
      const label = c === 'PX' ? `${c} · ${p.name}` : `${c} · ${p.name}${money ? ` — ${usd(p.usd_web)} Web / ${usd(p.usd_android)} Android` : ''}`;
      return `<option value="${esc(c)}" ${(renew && renew.plan === c) || (!renew && c === '1M') ? 'selected' : ''}>${esc(label)}</option>`;
    }).join('');
    const banner = !s.key.configured
      ? `<div class="callout danger"><span class="ico">🛡️</span><div><b>Aún no hay clave de firma.</b> ${has('keys') ? 'Créela en <a href="#/clave">Clave y ajustes</a> antes de emitir.' : 'Pida a un administrador que la cree.'}</div></div>`
      : (!s.key.unlocked ? '<div class="callout warn"><span class="ico">🔒</span><div>La clave de firma está bloqueada: se le pedirá su contraseña al emitir (o desbloquéela en <a href="#/clave">Clave y ajustes</a>).</div></div>' : '');
    el.innerHTML = `<div class="pagehead"><div><h1>Emitir licencia</h1><div class="sub">Pegue el código de solicitud que el cliente envió por WhatsApp</div></div></div>
      <div id="emitbox" class="stack">${banner}
      <section class="card"><form id="emit" class="stack" novalidate>
        ${renew ? `<div class="callout ok"><span class="ico">🔁</span><div><b>Renovación</b> de la licencia <span class="mono">${esc(renew.serial)}</span> (${esc(renew.customer)}). Se conservan cliente, código y contacto. <a href="#/emitir" data-act="noop">Quitar</a></div></div>` : ''}
        <div class="grid2">
          <label class="f"><span class="req">Cliente / usuario</span><input name="customer" maxlength="80" value="${esc(renew?.customer || '')}" placeholder="Nombre que saldrá en la licencia" autocomplete="off"></label>
          <label class="f"><span>Contacto (WhatsApp, teléfono o correo)</span><input name="contact" maxlength="120" value="${esc(renew?.contact || '')}" placeholder="+53 5555 5555" autocomplete="off"></label>
        </div>
        <label class="f"><span class="req">Código de solicitud</span><input name="code" class="mono" value="${esc(renew?.request_code || '')}" placeholder="IPVW-XXXXX-XXXXX-XXXXX-XXXXX-XX (PC) o IPVA-… (móvil)" autocomplete="off" spellcheck="false" autocapitalize="characters"><small class="hint" id="appchip">Escriba o pegue el código que muestra la app del cliente.</small></label>
        <div class="grid2">
          <label class="f"><span class="req">Plan</span><select name="plan">${planOpts}</select></label>
          <div class="price-box" id="pricebox" ${money ? '' : 'hidden'}></div>
        </div>
        <div class="grid3" id="pxbox" hidden>
          <label class="f"><span class="req">Desde (AAAA-MM-DD)</span><input name="start_date" type="date"></label>
          <label class="f"><span class="req">Hasta (AAAA-MM-DD)</span><input name="end_date" type="date"></label>
          <label class="f"><span class="req">Precio acordado (USD)</span><input name="custom_price_usd" inputmode="decimal" placeholder="25.00"></label>
        </div>
        <label class="f"><span>Notas internas</span><textarea name="notes" maxlength="1000" placeholder="Opcional: observaciones sobre el cliente o el acuerdo"></textarea></label>
        ${money ? `<div class="grid2"><label class="check"><input type="checkbox" name="paid"> Ya está cobrada</label>
          <label class="f"><span>Método de pago</span><select name="pay_method"><option value="">—</option>${PAY_METHODS.map(m => `<option>${m}</option>`).join('')}</select></label></div>` : ''}
        <p class="error" hidden></p>
        <div class="row"><button class="btn primary" type="submit">🔑 Crear licencia</button><span class="hint">La licencia queda firmada y registrada en el historial.</span></div>
      </form></section></div>`;

    const form = $('#emit', el), f = form.elements;
    function refresh() {
      const code = f.code.value.trim().toUpperCase();
      const app = code.startsWith('IPVA-') ? 'A' : (code.startsWith('IPVW-') ? 'W' : '');
      $('#appchip', el).innerHTML = app ? `Aplicación detectada: <b>${APPS[app].join(' ')}</b> · ${esc(s.app_names?.[app] || '')}` : 'Escriba o pegue el código que muestra la app del cliente.';
      const px = f.plan.value === 'PX';
      $('#pxbox', el).hidden = !px;
      if (!money) return;
      let price = null;
      if (px) price = parseFloat(String(f.custom_price_usd.value).replace(',', '.'));
      else if (app) price = s.plans[f.plan.value][app === 'W' ? 'usd_web' : 'usd_android'];
      const box = $('#pricebox', el);
      if (isNil(price) || Number.isNaN(price)) { box.innerHTML = '<span class="muted">El precio aparece al indicar el código (o el precio acordado en PX).</span>'; return; }
      const r = s.rates, c = price * r.USD;
      box.innerHTML = `<b>${usd(price)}</b> = ${cup(c)}<br><small class="muted">${nf(c / r.EUR)} EUR · ${nf(c / r.ZELLE)} Zelle · ${nf(c / r.MLC)} MLC · ${nf(c / r.CLA)} CLA</small>`;
    }
    ['input', 'change'].forEach(ev => form.addEventListener(ev, refresh)); refresh();

    function payload() {
      const b = { customer: f.customer.value.trim(), contact: f.contact.value.trim(), code: f.code.value.trim(), plan: f.plan.value, notes: f.notes.value.trim() };
      if (f.plan.value === 'PX') Object.assign(b, { start_date: f.start_date.value, end_date: f.end_date.value, custom_price_usd: f.custom_price_usd.value.trim() });
      if (money) Object.assign(b, { paid: f.paid.checked, pay_method: f.pay_method.value });
      if (renew) b.renews = renew.serial;
      return b;
    }
    form.addEventListener('submit', async e => {
      e.preventDefault(); $('.error', form).hidden = true;
      const btn = $('button[type=submit]', form); btn.disabled = true;
      try {
        await ensureUnlocked();
        let res;
        try { res = await api('/api/licenses', { method: 'POST', body: payload() }); }
        catch (ex) {
          if (ex.status !== 423) throw ex;
          state.status.key.unlocked = false; await ensureUnlocked();  // la clave se bloqueó por inactividad
          res = await api('/api/licenses', { method: 'POST', body: payload() });
        }
        await refreshStatus();
        showResult($('#emitbox', el), res);
      } catch (ex) { if (!(ex instanceof Cancelled)) showErr(form, ex.message); } finally { btn.disabled = false; }
    });
  }

  function showResult(box, res) {
    const l = res.license;
    box.innerHTML = `<section class="result stack">
      <div class="row"><span style="font-size:26px">✅</span><div><div class="big">Licencia creada</div><div class="muted">Serie <span class="mono">${esc(l.serial)}</span> · ${esc(res.app_name)}</div></div></div>
      ${res.warnings.map(w => `<div class="callout warn"><span class="ico">⚠️</span><div>${esc(w)}</div></div>`).join('')}
      <dl class="kv"><dt>Cliente</dt><dd><b>${esc(l.customer)}</b></dd><dt>Plan</dt><dd>${esc(l.plan)} · ${esc(planName(l.plan))}</dd>
        <dt>Vigencia</dt><dd>${l.valid_from ? `${ymd(l.valid_from)} → ` : ''}${esc(vence(l))}</dd>
        ${isNil(l.price_usd) ? '' : `<dt>Precio</dt><dd>${usd(l.price_usd)} = ${cup(l.price_cup)}</dd>`}</dl>
      <label class="f"><span>Licencia (cópiela completa)</span><textarea class="token" readonly>${esc(res.token)}</textarea></label>
      <div class="row"><button class="btn primary" data-a="copy">📋 Copiar licencia</button><button class="btn" data-a="msg">💬 Copiar mensaje</button>
        <a class="btn wa" href="${esc(res.whatsapp_url)}" target="_blank" rel="noopener noreferrer">Enviar por WhatsApp</a>
        <button class="btn" data-a="dl">⬇ Descargar .lic</button></div>
      <div class="row"><a class="btn ghost" href="#/historial">Ver en el historial</a><a class="btn ghost" href="#/emitir" data-a="again">➕ Emitir otra</a></div></section>`;
    $('.token', box).addEventListener('focus', e => e.target.select());
    box.addEventListener('click', e => {
      const a = e.target.closest('[data-a]')?.dataset.a; if (!a) return;
      if (a === 'copy') copyText(res.token, 'Licencia copiada');
      if (a === 'msg') copyText(res.reply, 'Mensaje copiado');
      if (a === 'dl') download(`licencia-${l.serial}.lic`, `${res.token}\n`);
      if (a === 'again') { e.preventDefault(); if (location.hash === '#/emitir') route(); else location.hash = '#/emitir'; }
    });
  }

  /* ───────────── vista: Historial ───────────── */
  const histQuery = (extra = {}) => {
    const h = { ...state.hist, ...extra }, q = new URLSearchParams();
    for (const k of ['q', 'state', 'plan', 'app', 'paid', 'from', 'to', 'sort', 'dir', 'limit', 'offset']) if (h[k] !== '' && !isNil(h[k])) q.set(k, h[k]);
    return q.toString();
  };

  async function viewHistory(el) {
    const money = has('prices'), h = state.hist;
    const planOptions = Object.entries(state.status.plans).map(([c, p]) => `<option value="${esc(c)}" ${h.plan === c ? 'selected' : ''}>${esc(c)} · ${esc(p.name)}</option>`).join('');
    el.innerHTML = `<div class="pagehead"><div><h1>Historial de licencias</h1><div class="sub">${has('history_all') ? 'Todas las licencias creadas, con su estado y su línea de tiempo' : 'Las licencias que usted emitió'}</div></div>
        ${has('export') ? '<button class="btn" data-a="csv">⬇ Exportar CSV</button>' : ''}${has('emit') ? '<a class="btn primary" href="#/emitir">🔑 Emitir licencia</a>' : ''}</div>
      <div class="chips" id="chips"></div>
      <div class="toolbar">
        <label class="f grow"><span>Buscar</span><input id="q" type="search" value="${esc(h.q)}" placeholder="Cliente, serie, código, contacto o notas" autocomplete="off"></label>
        <label class="f"><span>Plan</span><select id="plan"><option value="">Todos</option>${planOptions}</select></label>
        <label class="f"><span>Aplicación</span><select id="app"><option value="">Todas</option><option value="W" ${h.app === 'W' ? 'selected' : ''}>🖥️ Web</option><option value="A" ${h.app === 'A' ? 'selected' : ''}>📱 Android</option></select></label>
        ${money ? `<label class="f"><span>Cobro</span><select id="paid"><option value="">Todos</option><option value="1" ${h.paid === '1' ? 'selected' : ''}>Cobradas</option><option value="0" ${h.paid === '0' ? 'selected' : ''}>Pendientes</option></select></label>` : ''}
        <label class="f"><span>Desde</span><input id="from" type="date" value="${esc(h.from)}"></label>
        <label class="f"><span>Hasta</span><input id="to" type="date" value="${esc(h.to)}"></label>
        <button class="btn ghost" data-a="clear">Limpiar</button></div>
      <div class="tablewrap" id="table"></div><div class="pager" id="pager"></div>`;

    const cols = [['created_at', 'Emitida', true], ['serial', 'Serie', false], ['customer', 'Cliente', true], ['app', 'App', false], ['plan', 'Plan', true],
      ['expires_at', 'Vence', true], ['state', 'Estado', false], ...(money ? [['price_usd', 'Precio', true], ['paid', 'Cobro', false]] : []), ['created_by', 'Emitida por', false]];

    async function load() {
      const [page, stats] = await Promise.all([api(`/api/licenses?${histQuery()}`), api('/api/stats')]);
      const total = stats.total, by = stats.by_state;
      $('#chips', el).innerHTML = [['', 'Todas', total], ['vigente', 'Vigentes', by.vigente], ['por_vencer', 'Por vencer', by.por_vencer], ['programada', 'Programadas', by.programada],
        ['vencida', 'Vencidas', by.vencida], ['revocada', 'Anuladas', by.revocada]]
        .map(([v, label, n]) => `<button class="chip ${h.state === v ? 'on' : ''}" data-state="${v}">${label}<span class="n">${n}</span></button>`).join('');
      const arrow = k => (h.sort === k ? `<span class="arrow">${h.dir === 'asc' ? ' ▲' : ' ▼'}</span>` : '');
      const rows = page.items.map(i => `<tr class="click" data-id="${i.id}">
        <td>${fdate(i.created_at)}<div class="sm">${esc(ftime(i.created_at))}</div></td><td class="mono">${esc(i.serial)}</td>
        <td><div class="cust">${esc(i.customer)}</div><div class="sm">${esc(i.contact || '')}</div></td><td>${appBadge(i.app)}</td>
        <td>${esc(i.plan)}<div class="sm">${esc(planName(i.plan))}</div></td><td>${esc(vence(i))}<div class="sm">${esc(daysText(i))}</div></td>
        <td>${stateBadge(i.state, i.state_label)}</td>
        ${money ? `<td class="num">${usd(i.price_usd)}</td><td>${i.state === 'revocada' ? '—' : (i.paid ? '<span class="badge ok">Cobrada</span>' : '<span class="badge por_vencer">Pendiente</span>')}</td>` : ''}
        <td>${esc(i.created_by || '—')}</td></tr>`).join('');
      $('#table', el).innerHTML = page.items.length
        ? `<table><thead><tr>${cols.map(([k, label, sortable]) => `<th class="${sortable ? 'sort' : ''} ${k === 'price_usd' ? 'num' : ''}" ${sortable ? `data-sort="${k}"` : ''}>${label}${arrow(k)}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table>`
        : '<div class="empty">No hay licencias que coincidan con los filtros.</div>';
      const from = page.total ? page.offset + 1 : 0, to = Math.min(page.offset + page.limit, page.total);
      $('#pager', el).innerHTML = `<span>${from}–${to} de ${page.total}</span>
        <select id="limit" aria-label="Filas por página">${[25, 50, 100].map(n => `<option ${h.limit === n ? 'selected' : ''}>${n}</option>`).join('')}</select>
        <button class="btn sm" data-a="prev" ${page.offset <= 0 ? 'disabled' : ''}>‹ Anterior</button>
        <button class="btn sm" data-a="next" ${to >= page.total ? 'disabled' : ''}>Siguiente ›</button>`;
    }
    const reload = () => load().catch(fail);
    const setFilter = (k, v) => { h[k] = v; h.offset = 0; reload(); };

    $('#q', el).addEventListener('input', debounce(e => setFilter('q', e.target.value.trim())));
    for (const id of ['plan', 'app', 'paid', 'from', 'to']) $(`#${id}`, el)?.addEventListener('change', e => setFilter(id, e.target.value));
    el.addEventListener('change', e => { if (e.target.id === 'limit') setFilter('limit', Number(e.target.value)); });
    el.addEventListener('click', async e => {
      const chip = e.target.closest('[data-state]'); if (chip) return setFilter('state', chip.dataset.state);
      const th = e.target.closest('th[data-sort]');
      if (th) {  // columnas de texto: primero A→Z; fechas e importes: primero lo más reciente/alto; pulsar de nuevo invierte
        const k = th.dataset.sort;
        h.dir = h.sort === k ? (h.dir === 'desc' ? 'asc' : 'desc') : (['customer', 'serial', 'plan', 'app'].includes(k) ? 'asc' : 'desc');
        h.sort = k; h.offset = 0; return reload();
      }
      const row = e.target.closest('tr[data-id]'); if (row) return openLicense(row.dataset.id, reload);
      const a = e.target.closest('[data-a]')?.dataset.a; if (!a) return;
      if (a === 'prev') { h.offset = Math.max(0, h.offset - h.limit); reload(); }
      if (a === 'next') { h.offset += h.limit; reload(); }
      if (a === 'clear') {
        Object.assign(h, { q: '', state: '', plan: '', app: '', paid: '', from: '', to: '', offset: 0 });
        for (const id of ['q', 'plan', 'app', 'paid', 'from', 'to']) { const c = $(`#${id}`, el); if (c) c.value = ''; }
        reload();
      }
      if (a === 'csv') {
        try {
          const r = await api(`/api/export.csv?${histQuery({ limit: '', offset: '' })}`, { raw: true });
          const name = /filename="([^"]+)"/.exec(r.headers.get('Content-Disposition') || '')?.[1] || 'historial-licencias.csv';
          download(name, await r.blob()); toast('Historial exportado');
        } catch (ex) { fail(ex); }
      }
    });
    await load();
  }

  /* ───────────── detalle de una licencia (panel lateral) ───────────── */
  async function openLicense(id, onChange = () => {}) {
    const dr = drawer('<div class="empty">Cargando…</div>');
    const root = dr.el;
    async function render() {
      let d;
      try { d = await api(`/api/licenses/${encodeURIComponent(id)}`); } catch (e) { root.innerHTML = `<div class="error">${esc(e.message)}</div>`; return; }
      const l = d.license, can = d.can, v = d.verification;
      const sigBadge = { valida: '<span class="badge ok">Firma válida ✔</span>', invalida: '<span class="badge bad">Firma no válida</span>' }[v.signature] || '<span class="badge">Sin verificar</span>';
      root.innerHTML = `<div class="dhead"><div class="t"><h2>${esc(l.customer)}</h2><div class="row" style="margin-top:6px">${stateBadge(l.state, l.state_label)}${appBadge(l.app)}<span class="mono muted">${esc(l.serial)}</span></div></div>
          <button class="btn icon ghost" data-close aria-label="Cerrar">×</button></div>
        ${l.status === 'revoked' ? `<div class="callout danger"><span class="ico">🚫</span><div><b>Anulada</b> el ${fdt(l.revoked_at)} por ${esc(l.revoked_by || '—')}.<br>Motivo: ${esc(l.revoked_reason)}</div></div>` : ''}
        ${d.warning ? `<div class="callout warn" style="margin-top:10px"><span class="ico">⚠️</span><div>${esc(d.warning)}</div></div>` : ''}
        <div class="section"><dl class="kv">
          <dt>Plan</dt><dd>${esc(l.plan)} · ${esc(planName(l.plan))}</dd>
          <dt>Vigencia</dt><dd>${l.valid_from ? `${ymd(l.valid_from)} → ` : 'hasta '}${esc(vence(l))} <span class="muted">(${esc(daysText(l))})</span></dd>
          <dt>Emitida</dt><dd>${fdt(l.created_at)} por ${esc(l.created_by || '—')} <span class="muted">· ${esc(l.source)}</span></dd>
          <dt>Código de solicitud</dt><dd class="mono">${esc(l.request_code || '—')}</dd>
          <dt>Contacto</dt><dd>${esc(l.contact || '—')}</dd>
          ${l.renewed_from ? `<dt>Renueva a</dt><dd class="mono">${esc(l.renewed_from)}</dd>` : ''}
          ${can.money && !isNil(l.price_usd) ? `<dt>Precio</dt><dd>${usd(l.price_usd)} = ${cup(l.price_cup)}</dd><dt>Cobro</dt><dd>${l.paid ? `<span class="badge ok">Cobrada</span> ${fdt(l.paid_at)} ${esc(l.pay_method || '')}` : '<span class="badge por_vencer">Pendiente</span>'}</dd>` : ''}
          <dt>Verificación</dt><dd>${sigBadge} <span class="hint">${esc(v.message)}</span></dd></dl></div>
        ${l.token ? `<div class="section"><h3>Licencia</h3><textarea class="token" readonly>${esc(l.token)}</textarea>
          <div class="row" style="margin-top:8px"><button class="btn sm" data-a="copy">📋 Copiar</button><button class="btn sm" data-a="dl">⬇ .lic</button>
          ${can.resend && d.whatsapp_url ? `<a class="btn sm wa" data-a="resent" href="${esc(d.whatsapp_url)}" target="_blank" rel="noopener noreferrer">💬 Reenviar por WhatsApp</a>` : ''}</div></div>` : ''}
        <div class="section"><h3>Acciones</h3><div class="row">
          ${has('emit') ? `<a class="btn sm" href="#/emitir?renew=${l.id}" data-a="renew">🔁 Renovar</a>` : ''}
          ${can.revoke && l.status !== 'revoked' ? '<button class="btn sm danger" data-a="revoke">🚫 Anular</button>' : ''}
          ${can.revoke && l.status === 'revoked' ? '<button class="btn sm" data-a="reactivate">♻️ Reactivar</button>' : ''}</div></div>
        ${can.edit ? `<div class="section"><h3>Datos de gestión</h3><form class="stack" id="edit" novalidate>
          <label class="f"><span>Contacto</span><input name="contact" maxlength="120" value="${esc(l.contact || '')}"></label>
          <label class="f"><span>Notas internas</span><textarea name="notes" maxlength="1000">${esc(l.notes || '')}</textarea></label>
          <div class="row"><button class="btn sm primary" type="submit">Guardar datos</button></div></form></div>` : ''}
        ${can.money && l.status !== 'revoked' ? `<div class="section"><h3>Cobro</h3><form class="row" id="pay" novalidate>
          <label class="check"><input type="checkbox" name="paid" ${l.paid ? 'checked' : ''}> Cobrada</label>
          <select name="pay_method" style="width:auto"><option value="">Método…</option>${PAY_METHODS.map(m => `<option ${l.pay_method === m ? 'selected' : ''}>${m}</option>`).join('')}</select>
          <button class="btn sm" type="submit">Guardar cobro</button></form></div>` : ''}
        <div class="section"><h3>Línea de tiempo</h3>${d.events.length ? `<div class="timeline">${d.events.map(ev => {
          const [ic, label] = EVENTS[ev.action] || ['•', ev.action];
          return `<div class="ev"><div class="ic">${ic}</div><div><b>${esc(label)}</b>${ev.detail ? ` — ${esc(ev.detail)}` : ''}<div class="hint">${esc(ev.actor || 'sistema')} · ${fdt(ev.at)}</div></div></div>`;
        }).join('')}</div>` : '<div class="empty">Sin eventos.</div>'}</div>`;

      const again = async () => { await render(); onChange(); };
      $$('[data-close]', root).forEach(b => b.addEventListener('click', dr.close));
      root.addEventListener('click', async e => {
        const t = e.target.closest('[data-a]'); if (!t) return;
        const a = t.dataset.a;
        try {
          if (a === 'copy') copyText(l.token, 'Licencia copiada');
          else if (a === 'dl') download(`licencia-${l.serial}.lic`, `${l.token}\n`);
          else if (a === 'renew') dr.close();
          else if (a === 'resent') { api(`/api/licenses/${l.id}/resend`, { method: 'POST', body: {} }).then(() => { onChange(); }).catch(() => {}); }
          else if (a === 'revoke') {
            const r = await ask({ title: 'Anular licencia', danger: true, confirm: 'Anular licencia', message: `Se marcará como anulada la licencia ${l.serial} de ${l.customer}. Queda registrado quién y por qué. Podrá reactivarla después.`,
              fields: [{ name: 'reason', label: 'Motivo de la anulación', type: 'textarea', required: true, minLength: 3 }] });
            if (r) { await api(`/api/licenses/${l.id}/revoke`, { method: 'POST', body: { reason: r.reason.trim() } }); toast('Licencia anulada'); await again(); }
          } else if (a === 'reactivate') {
            if (await ask({ title: 'Reactivar licencia', confirm: 'Reactivar', message: `La licencia ${l.serial} volverá a estado activo.` })) {
              await api(`/api/licenses/${l.id}/reactivate`, { method: 'POST', body: {} }); toast('Licencia reactivada'); await again();
            }
          }
        } catch (ex) { fail(ex); }
      });
      $('#edit', root)?.addEventListener('submit', async e => {
        e.preventDefault();
        try { await api(`/api/licenses/${l.id}`, { method: 'PATCH', body: { contact: e.target.elements.contact.value, notes: e.target.elements.notes.value } }); toast('Datos guardados'); await again(); } catch (ex) { fail(ex); }
      });
      $('#pay', root)?.addEventListener('submit', async e => {
        e.preventDefault();
        try { await api(`/api/licenses/${l.id}`, { method: 'PATCH', body: { paid: e.target.elements.paid.checked, pay_method: e.target.elements.pay_method.value } }); toast('Cobro guardado'); await again(); } catch (ex) { fail(ex); }
      });
    }
    await render();
  }

  /* ───────────── vista: Usuarios y roles ───────────── */
  const canManage = (actor, target) => actor === 'ADMINISTRADOR' || (actor === 'JEFE' && (target === 'ECONOMICO' || target === 'ALMACENERO'));
  const manageableRoles = actor => Object.keys(ROLE_NAMES).filter(r => canManage(actor, r));

  async function viewUsers(el) {
    const users = await api('/api/users'), me = state.user, cat = state.status.roles;
    const rows = users.map(u => {
      const mine = u.id === me.id, ok = !mine && canManage(me.role, u.role);
      const btn = (a, label, title, extra = '') => `<button class="btn sm ghost" data-a="${a}" data-id="${u.id}" title="${title}" aria-label="${title}" ${extra}>${label}</button>`;
      return `<tr><td><div class="cust">${esc(u.username)}${mine ? ' <span class="badge ok">usted</span>' : ''}</div><div class="sm">${esc(u.name)}${u.email ? ` · ${esc(u.email)}` : ''}</div></td>
        <td>${roleBadge(u.role)}</td><td>${u.mfa ? '<span class="badge ok">2FA</span>' : '<span class="badge">sin 2FA</span>'}</td>
        <td>${u.active ? (u.locked ? '<span class="badge bad">Bloqueado</span>' : '<span class="badge ok">Activo</span>') : '<span class="badge">Inactivo</span>'}${u.must_change_password ? ' <span class="badge por_vencer">cambiar clave</span>' : ''}</td>
        <td class="sm">${u.last_login ? `${fdt(u.last_login)}` : 'Nunca'}</td>
        <td><div class="row acts">${ok ? `${btn('edit', 'Editar', 'Editar nombre, rol o correo')}${btn('pass', 'Nueva clave', 'Restablecer contraseña (genera una temporal)')}${u.locked ? btn('unlock', 'Desbloquear', 'Quitar el bloqueo por intentos fallidos') : ''}${u.mfa ? btn('mfa', 'Quitar 2FA', 'Restablecer la verificación en dos pasos') : ''}${btn('sessions', 'Cerrar sesiones', 'Cerrar todas sus sesiones abiertas')}${btn('toggle', u.active ? 'Desactivar' : 'Activar', u.active ? 'Impedir que entre' : 'Permitir que entre')}` : ''}</div></td></tr>`;
    }).join('');
    const capRows = [['emit', 'Emitir licencias'], ['history', 'Ver el historial'], ['prices', 'Ver precios y registrar cobros'], ['revoke', 'Anular y reactivar'],
      ['export', 'Exportar a CSV'], ['users', 'Gestionar usuarios'], ['keys', 'Clave de firma y copias de seguridad'], ['rates', 'Tasas de cambio'], ['audit', 'Ver la auditoría']];
    const cell = (r, cap) => {
      const c = r.capabilities;
      if (cap === 'history') return c.includes('history_all') ? '<span class="yes">Todo</span>' : (c.includes('history_own') ? '<span class="yes">Lo suyo</span>' : '<span class="no">—</span>');
      return c.includes(cap) ? '<span class="yes">Sí</span>' : '<span class="no">—</span>';
    };
    el.innerHTML = `<div class="pagehead"><div><h1>Usuarios y roles</h1><div class="sub">Quién puede entrar al Keygen y qué puede hacer</div></div><button class="btn primary" data-a="new">➕ Nuevo usuario</button></div>
      <section class="card"><div class="tablewrap"><table><thead><tr><th>Usuario</th><th>Rol</th><th>2FA</th><th>Estado</th><th>Último acceso</th><th>Acciones</th></tr></thead><tbody>${rows}</tbody></table></div></section>
      <section class="card" style="margin-top:16px"><header><h2>Roles y permisos</h2></header>
        <div class="stack" style="margin-bottom:14px">${cat.map(r => `<div>${roleBadge(r.id)} <span class="muted">${esc(r.description)}</span></div>`).join('')}</div>
        <div class="tablewrap"><table class="matrix"><thead><tr><th>Capacidad</th>${cat.map(r => `<th>${esc(r.label)}</th>`).join('')}</tr></thead>
        <tbody>${capRows.map(([cap, label]) => `<tr><td>${label}</td>${cat.map(r => `<td>${cell(r, cap)}</td>`).join('')}</tr>`).join('')}</tbody></table></div></section>`;

    const byId = id => users.find(u => String(u.id) === String(id));
    const put = async (u, body, okMsg) => { await api(`/api/users/${u.id}`, { method: 'PUT', body }); toast(okMsg); route(); };
    const roleOptions = (current = '') => manageableRoles(me.role).map(r => [r, `${roleLabel(r)} — ${(cat.find(c => c.id === r) || {}).description || ''}`]).map(([v, t]) => [v, t]).concat(current && !manageableRoles(me.role).includes(current) ? [[current, roleLabel(current)]] : []);
    el.addEventListener('click', async e => {
      const t = e.target.closest('[data-a]'); if (!t) return;
      const a = t.dataset.a, u = byId(t.dataset.id);
      try {
        if (a === 'new') {
          const v = await ask({ title: 'Nuevo usuario', confirm: 'Crear usuario', wide: true, fields: [
            { name: 'username', label: 'Usuario', required: true, minLength: 3, hint: 'Letras, números, punto, guion o guion bajo (3–40).' },
            { name: 'name', label: 'Nombre completo' }, { name: 'email', label: 'Correo de contacto (opcional)', type: 'email' },
            { name: 'role', label: 'Rol', type: 'select', value: 'ALMACENERO', options: roleOptions() },
            { name: 'password', label: 'Contraseña inicial', required: true, value: genPassword(), hint: 'Generada al azar: cópiela y entréguela al usuario. Mínimo 10 caracteres.' },
            { name: 'must_change_password', label: 'Exigir que la cambie en su primer acceso', type: 'checkbox', value: true }] });
          if (v) {
            const c = await api('/api/users', { method: 'POST', body: { username: v.username.trim(), name: v.name.trim(), email: v.email.trim(), role: v.role, password: v.password, must_change_password: v.must_change_password } });
            toast(`Usuario ${c.username} creado`); route();
          }
        } else if (a === 'edit') {
          const v = await ask({ title: `Editar a ${u.username}`, confirm: 'Guardar', fields: [{ name: 'name', label: 'Nombre completo', value: u.name, required: true },
            { name: 'email', label: 'Correo de contacto', type: 'email', value: u.email }, { name: 'role', label: 'Rol', type: 'select', value: u.role, options: roleOptions(u.role) }] });
          if (v) { const body = { name: v.name.trim(), email: v.email.trim() }; if (v.role !== u.role) body.role = v.role; await put(u, body, 'Usuario actualizado'); }
        } else if (a === 'pass') {
          const v = await ask({ title: `Restablecer la contraseña de ${u.username}`, confirm: 'Restablecer', danger: true,
            message: 'Se cerrarán sus sesiones y tendrá que cambiarla en su próximo acceso.', fields: [{ name: 'password', label: 'Contraseña temporal', required: true, value: genPassword() }] });
          if (v) await put(u, { password: v.password }, 'Contraseña restablecida: entregue la temporal al usuario');
        } else if (a === 'unlock') await put(u, { unlock: true }, 'Cuenta desbloqueada');
        else if (a === 'mfa') { if (await ask({ title: 'Restablecer 2FA', danger: true, confirm: 'Restablecer', message: `${u.username} tendrá que volver a configurar su verificación en dos pasos.` })) await put(u, { reset_mfa: true }, '2FA restablecida'); }
        else if (a === 'sessions') { if (await ask({ title: 'Cerrar sesiones', confirm: 'Cerrar sesiones', message: `Se cerrarán todas las sesiones abiertas de ${u.username}.` })) await put(u, { revoke_sessions: true }, 'Sesiones cerradas'); }
        else if (a === 'toggle') { if (await ask({ title: u.active ? 'Desactivar usuario' : 'Activar usuario', danger: u.active, confirm: u.active ? 'Desactivar' : 'Activar', message: `${u.username} ${u.active ? 'ya no podrá iniciar sesión' : 'podrá volver a iniciar sesión'}.` })) await put(u, { active: !u.active }, 'Estado actualizado'); }
      } catch (ex) { fail(ex); }
    });
  }

  /* ───────────── vista: Clave de firma y ajustes ───────────── */
  async function viewKey(el) {
    const s = await refreshStatus(), k = s.key;
    const canKeys = has('keys'), prices = has('prices');
    el.innerHTML = `<div class="pagehead"><div><h1>Clave y ajustes</h1><div class="sub">La clave de firma es lo que hace válidas las licencias: cuídela</div></div></div><div class="stack">
      <section class="card"><header><h2>🛡️ Clave de firma</h2>${k.configured ? (k.unlocked ? '<span class="badge ok">Desbloqueada</span>' : '<span class="badge">Bloqueada</span>') : '<span class="badge bad">No creada</span>'}</header>
        ${k.configured ? `<dl class="kv"><dt>Huella</dt><dd class="mono"><b>${esc(k.fingerprint)}</b></dd><dt>Creada</dt><dd>${esc(k.created || '—')}</dd>
          <dt>Archivo de clave</dt><dd>${k.has_key_file ? '✔ keygen/clave_privada.json (cifrado)' : '<span class="badge bad">No está en este equipo: no se puede firmar aquí</span>'}</dd>
          <dt>WhatsApp de solicitudes</dt><dd>${esc(k.whatsapp || '—')} ${canKeys ? '<button class="btn sm" data-a="wa">Cambiar</button>' : ''}</dd>
          <dt>Bloqueo automático</dt><dd>${s.unlock_minutes} min sin uso</dd></dl>`
          : `<div class="callout warn"><span class="ico">⚠️</span><div>Todavía no existe la clave de firma. ${canKeys ? 'Créela para empezar a emitir licencias.' : 'Pida a un administrador que la cree.'}</div></div>`}
        <div class="row" style="margin-top:14px">
          ${k.configured && has('emit') ? (k.unlocked ? '<button class="btn" data-a="lock">🔒 Bloquear ahora</button>' : '<button class="btn primary" data-a="unlock">🔓 Desbloquear</button>') : ''}
          ${canKeys ? `<button class="btn ${k.configured ? 'danger' : 'primary'}" data-a="init">${k.configured ? '♻️ Reemplazar clave…' : '✨ Crear clave de firma'}</button>` : ''}</div>
        ${k.configured ? '<p class="hint" style="margin-top:12px">Haga una copia de <code>keygen/clave_privada.json</code> y de su contraseña en lugares seguros: sin ellas no podrá renovar licencias.</p>' : ''}</section>
      ${prices ? `<section class="card"><header><h2>💱 Tasas de cambio (CUP)</h2></header>${has('rates') ? `<form id="rates" class="stack" novalidate><div class="grid3">${Object.entries(s.rates).map(([c, v]) => `<label class="f"><span>1 ${esc(c)}</span><input name="${esc(c)}" inputmode="decimal" value="${esc(v)}"></label>`).join('')}</div>
        <div class="row"><button class="btn primary" type="submit">Guardar tasas</button><span class="hint">Se usan para calcular los precios en CUP de cada licencia.</span></div></form>` : '<p class="muted">Su rol puede consultarlas pero no cambiarlas.</p>'}</section>` : ''}
      <section class="card"><header><h2>🔎 Verificar una licencia</h2></header><form id="verify" class="stack" novalidate>
        <label class="f"><span>Pegue la licencia (IPV1.…)</span><textarea name="license" class="token" style="min-height:80px"></textarea></label>
        <div class="row"><button class="btn" type="submit">Verificar firma</button></div><div id="verifyout"></div></form></section>
      ${canKeys ? `<section class="card"><header><h2>🗄️ Historial y copias de seguridad</h2></header><div class="row">
        <button class="btn" data-a="backup">⬇ Descargar copia (licencias.db)</button><button class="btn" data-a="import">📥 Importar registro antiguo (CSV)</button>
        <input type="file" id="csvfile" accept=".csv,text/csv" hidden></div>
        <p class="hint" style="margin-top:10px">La copia incluye usuarios, historial y auditoría (no la clave privada: esa es <code>clave_privada.json</code>).
        El registro antiguo se importa sin duplicar licencias.</p></section>` : ''}</div>`;

    el.addEventListener('click', async e => {
      const a = e.target.closest('[data-a]')?.dataset.a; if (!a) return;
      try {
        if (a === 'unlock') { await ensureUnlocked(); route(); }
        else if (a === 'lock') { setKey((await api('/api/key/lock', { method: 'POST', body: {} })).key); toast('🔒 Clave bloqueada'); route(); }
        else if (a === 'wa') {
          const v = await ask({ title: 'WhatsApp de solicitudes', confirm: 'Guardar', fields: [{ name: 'whatsapp', label: 'Número internacional sin «+»', value: k.whatsapp, required: true, placeholder: '5355555555' }],
            message: 'Se escribe en licencia.py y License.kt: reinicie el servidor y recompile el APK para que lo usen.' });
          if (v) { await api('/api/key/whatsapp', { method: 'POST', body: { whatsapp: v.whatsapp.trim() } }); toast('Número actualizado'); route(); }
        } else if (a === 'init') {
          const replacing = k.configured;
          const v = await ask({ title: replacing ? '♻️ Reemplazar la clave de firma' : '✨ Crear la clave de firma', danger: replacing, confirm: replacing ? 'Reemplazar clave' : 'Crear clave', wide: true,
            message: replacing ? 'ATENCIÓN: reemplazar la clave INVALIDA todas las licencias emitidas hasta hoy. Solo hágalo si la clave fue comprometida.' : 'Se genera un par de claves ECDSA P-256. La privada se guarda cifrada con la contraseña que elija.',
            fields: [{ name: 'passphrase', label: 'Contraseña de la clave (mín. 10)', type: 'password', required: true, minLength: 10, autocomplete: 'new-password' },
              { name: 'repeat', label: 'Repetir contraseña', type: 'password', required: true, same: 'passphrase', sameError: 'Las contraseñas no coinciden.', autocomplete: 'new-password' },
              { name: 'whatsapp', label: 'WhatsApp de solicitudes (opcional)', value: k.whatsapp, placeholder: '5355555555' },
              ...(replacing ? [{ name: 'confirm', label: 'Escriba REEMPLAZAR para confirmar', required: true, match: 'REEMPLAZAR', matchError: 'Escriba exactamente REEMPLAZAR.' }] : [])] });
          if (v) {
            const r = await api('/api/key/init', { method: 'POST', body: { passphrase: v.passphrase, whatsapp: v.whatsapp.trim(), force: replacing } });
            setKey(r.key);
            modal(`<h2>✅ Clave de firma lista</h2><p class="sub">Huella <b class="mono">${esc(r.key.fingerprint)}</b></p><div class="stack">
              <div class="callout warn"><span class="ico">💾</span><div><b>Haga copia</b> de <code>keygen/clave_privada.json</code> y de su contraseña en dos lugares seguros. Sin ellas no podrá renovar licencias; con ellas cualquiera podría emitirlas.</div></div>
              <div class="callout"><span class="ico">📲</span><div>La clave pública se escribió en: <b>${esc(r.patched.join(', ') || '—')}</b>. <b>Redistribuya el servidor y recompile el APK</b> para que usen la nueva clave.</div></div>
              <div class="row end"><button class="btn primary" data-close>Entendido</button></div></div>`, { onClose: () => route() });
          }
        } else if (a === 'backup') {
          const r = await api('/api/backup', { raw: true });
          download(/filename="([^"]+)"/.exec(r.headers.get('Content-Disposition') || '')?.[1] || 'licencias.db', await r.blob()); toast('Copia descargada');
        } else if (a === 'import') {
          const choice = await ask({ title: 'Importar registro antiguo', confirm: 'Importar', message: 'Indique de dónde leer el CSV. Las licencias que ya estén en el historial no se duplican.',
            fields: [{ name: 'src', label: 'Origen', type: 'select', value: 'server', options: [['server', 'Archivo keygen/registro_licencias.csv de este equipo'], ['file', 'Elegir un archivo CSV…']] }] });
          if (!choice) return;
          let body = {};
          if (choice.src === 'file') {
            const input = $('#csvfile', el);
            body = await new Promise((resolve, reject) => {
              input.onchange = () => { const f = input.files[0]; if (!f) return reject(new Cancelled('sin archivo')); f.text().then(t => resolve({ csv: t })).catch(reject); input.value = ''; };
              input.click();
            });
          }
          const r = await api('/api/import-csv', { method: 'POST', body });
          toast(r.found === false ? 'No se encontró registro_licencias.csv' : `Importadas ${r.imported} · ya estaban ${r.skipped} · no válidas ${r.invalid}`);
        }
      } catch (ex) { fail(ex); }
    });
    $('#rates', el)?.addEventListener('submit', async e => {
      e.preventDefault();
      try { const rates = Object.fromEntries(new FormData(e.target).entries()); await api('/api/rates', { method: 'POST', body: { rates } }); await refreshStatus(); toast('Tasas guardadas'); } catch (ex) { fail(ex); }
    });
    $('#verify', el).addEventListener('submit', async e => {
      e.preventDefault(); const out = $('#verifyout', el);
      try {
        const r = await api('/api/verify', { method: 'POST', body: { license: e.target.elements.license.value } });
        out.innerHTML = `<div class="callout ok"><span class="ico">✅</span><div><b>${esc(r.signature)}</b><br>Usuario: ${esc(r.user)} · ${esc(r.app_name)} · Plan ${esc(r.plan_name)}<br>Serie ${esc(r.serial)} · vence ${fepoch(r.expires_at)} (${r.days_left} d)
          ${r.history ? `<br>Historial: ${stateBadge(r.history.state, r.history.state_label)} ${r.history.revoked_reason ? `· ${esc(r.history.revoked_reason)}` : ''}` : ''}</div></div>`;
      } catch (ex) { out.innerHTML = `<div class="callout danger"><span class="ico">❌</span><div>${esc(ex.message)}</div></div>`; }
    });
  }

  /* ───────────── vista: Auditoría ───────────── */
  async function viewAudit(el) {
    const a = state.audit, limit = 50;
    el.innerHTML = `<div class="pagehead"><div><h1>Auditoría</h1><div class="sub">Registro encadenado de todo lo que ocurre en el Keygen</div></div><button class="btn" data-a="verify">🔗 Verificar integridad</button></div>
      <div class="toolbar"><label class="f grow"><span>Buscar</span><input id="as" type="search" value="${esc(a.search)}" placeholder="Usuario, IP, detalle…"></label>
        <label class="f"><span>Acción</span><select id="aa"><option value="">Todas</option></select></label></div>
      <div id="vout"></div><div class="tablewrap" id="atable"></div><div class="pager" id="apager"></div>`;
    async function load() {
      const q = new URLSearchParams({ limit, offset: a.offset }); if (a.action) q.set('action', a.action); if (a.search) q.set('search', a.search);
      const d = await api(`/api/audit?${q}`);
      const sel = $('#aa', el); sel.innerHTML = `<option value="">Todas</option>${d.actions.map(x => `<option ${a.action === x ? 'selected' : ''}>${esc(x)}</option>`).join('')}`;
      $('#atable', el).innerHTML = d.entries.length ? `<table><thead><tr><th>Fecha</th><th>Acción</th><th>Usuario</th><th>IP</th><th>Detalle</th></tr></thead><tbody>
        ${d.entries.map(x => `<tr><td class="sm">${fdt(x.timestamp)}</td><td><span class="badge ${/FAIL|LOCK|REVOKED/.test(x.action) ? 'bad' : ''}">${esc(x.action)}</span></td><td>${esc(x.user_email || '—')}</td><td class="mono sm">${esc(x.client)}</td><td class="sm">${esc(x.details)}</td></tr>`).join('')}</tbody></table>` : '<div class="empty">Sin eventos.</div>';
      const from = d.total ? d.offset + 1 : 0, to = Math.min(d.offset + d.limit, d.total);
      $('#apager', el).innerHTML = `<span>${from}–${to} de ${d.total}</span><button class="btn sm" data-a="prev" ${d.offset <= 0 ? 'disabled' : ''}>‹ Anterior</button><button class="btn sm" data-a="next" ${to >= d.total ? 'disabled' : ''}>Siguiente ›</button>`;
    }
    const reload = () => load().catch(fail);
    $('#as', el).addEventListener('input', debounce(e => { a.search = e.target.value.trim(); a.offset = 0; reload(); }));
    el.addEventListener('change', e => { if (e.target.id === 'aa') { a.action = e.target.value; a.offset = 0; reload(); } });
    el.addEventListener('click', async e => {
      const t = e.target.closest('[data-a]')?.dataset.a; if (!t) return;
      if (t === 'prev') { a.offset = Math.max(0, a.offset - limit); reload(); }
      if (t === 'next') { a.offset += limit; reload(); }
      if (t === 'verify') {
        try { const r = await api('/api/audit/verify'); $('#vout', el).innerHTML = `<div class="callout ${r.valid ? 'ok' : 'danger'}" style="margin-bottom:12px"><span class="ico">${r.valid ? '✅' : '❌'}</span><div>${esc(r.message)}</div></div>`; } catch (ex) { fail(ex); }
      }
    });
    await load();
  }

  /* ───────────── vista: Mi cuenta ───────────── */
  async function viewAccount(el) {
    const me = state.user, sessions = await api('/api/auth/sessions');
    const role = (state.status.roles.find(r => r.id === me.role) || {});
    el.innerHTML = `<div class="pagehead"><div><h1>Mi cuenta</h1><div class="sub">${esc(me.username)} · ${esc(roleLabel(me.role))}</div></div></div><div class="stack">
      <section class="card"><header><h2>👤 Perfil</h2></header><dl class="kv"><dt>Usuario</dt><dd><b>${esc(me.username)}</b></dd><dt>Nombre</dt><dd>${esc(me.name)}</dd>
        <dt>Correo</dt><dd>${esc(me.email || '—')}</dd><dt>Rol</dt><dd>${roleBadge(me.role)} <span class="muted">${esc(role.description || '')}</span></dd></dl></section>
      <section class="card"><header><h2>🔑 Cambiar contraseña</h2></header><form id="pw" class="stack" novalidate>
        <div class="grid3"><label class="f"><span class="req">Actual</span><input name="current" type="password" autocomplete="current-password"></label>
          <label class="f"><span class="req">Nueva</span><input name="new" type="password" autocomplete="new-password"></label>
          <label class="f"><span class="req">Repetir nueva</span><input name="repeat" type="password" autocomplete="new-password"></label></div>
        <p class="error" hidden></p><div class="row"><button class="btn primary" type="submit">Cambiar contraseña</button><span class="hint">Se cerrarán sus sesiones en otros dispositivos.</span></div></form></section>
      <section class="card"><header><h2>🛡️ Verificación en dos pasos (2FA)</h2>${me.mfa ? '<span class="badge ok">Activa</span>' : '<span class="badge">Desactivada</span>'}</header>
        ${me.mfa ? `<p class="muted">Al iniciar sesión se pide el código de su aplicación autenticadora.</p>${state.status.require_mfa ? '<p class="hint">Este Keygen exige 2FA: no se puede desactivar.</p>' : '<button class="btn danger" data-a="mfaoff">Desactivar 2FA</button>'}`
          : '<p class="muted">Protege su cuenta con un código temporal de su teléfono. Muy recomendable para quien emite licencias.</p><div id="mfabox"></div>'}</section>
      <section class="card"><header><h2>💻 Sesiones abiertas</h2><button class="btn sm" data-a="others">Cerrar las demás</button></header>
        <div class="tablewrap"><table><thead><tr><th>Dispositivo</th><th>IP</th><th>Último uso</th><th></th></tr></thead><tbody>
        ${sessions.map(s => `<tr><td>${esc(s.device)} ${s.current ? '<span class="badge ok">esta sesión</span>' : ''}</td><td class="mono sm">${esc(s.ip)}</td><td class="sm">${fdt(s.last_seen)}</td>
          <td>${s.current ? '' : `<button class="btn sm" data-a="close" data-sid="${esc(s.id)}">Cerrar</button>`}</td></tr>`).join('')}</tbody></table></div></section></div>`;
    if (!me.mfa) mfaSetup($('#mfabox', el));
    $('#pw', el).addEventListener('submit', async e => {
      e.preventDefault(); const f = e.target.elements; $('.error', e.target).hidden = true;
      if (f.new.value !== f.repeat.value) return showErr(e.target, 'Las contraseñas nuevas no coinciden.');
      try { saveSession(await api('/api/auth/password', { method: 'POST', body: { current: f.current.value, new: f.new.value } })); toast('Contraseña actualizada'); e.target.reset(); } catch (ex) { showErr(e.target, ex.message); }
    });
    el.addEventListener('click', async e => {
      const t = e.target.closest('[data-a]'); if (!t) return;
      try {
        if (t.dataset.a === 'close') { await api(`/api/auth/sessions/${encodeURIComponent(t.dataset.sid)}`, { method: 'DELETE' }); toast('Sesión cerrada'); route(); }
        else if (t.dataset.a === 'others') { const r = await api('/api/auth/sessions/revoke-others', { method: 'POST', body: {} }); toast(`${r.closed} sesión(es) cerradas`); route(); }
        else if (t.dataset.a === 'mfaoff') {
          const v = await ask({ title: 'Desactivar 2FA', danger: true, confirm: 'Desactivar', fields: [{ name: 'password', label: 'Su contraseña', type: 'password', required: true }, { name: 'code', label: 'Código de 6 dígitos o de recuperación', required: true }] });
          if (v) { await api('/api/auth/2fa/disable', { method: 'POST', body: { password: v.password, code: v.code.trim() } }); toast('2FA desactivada'); state.user.mfa = false; await refreshStatus(); route(); }
        }
      } catch (ex) { fail(ex); }
    });
  }

  const VIEWS = { panel: viewPanel, emitir: viewEmit, historial: viewHistory, usuarios: viewUsers, clave: viewKey, auditoria: viewAudit, cuenta: viewAccount };

  /* ───────────── arranque ───────────── */
  if (S.get('access')) boot(); else renderAuth();
})();
