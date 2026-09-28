/* IPV — Activación de licencia por período (web / servidor PC).
   Muestra el código de solicitud (ID del equipo cifrado con SHA-256), permite pedirlo
   por WhatsApp y pegar la licencia firmada que devuelve el Keygen. */
(() => {
  'use strict';
  let layer = null;

  const el = (tag, props = {}, ...children) => {
    const n = document.createElement(tag);
    Object.entries(props).forEach(([k, v]) => {
      if (k === 'class') n.className = v; else if (k === 'on') Object.entries(v).forEach(([e, f]) => n.addEventListener(e, f));
      else n.setAttribute(k, v);
    });
    children.flat().forEach((c) => n.append(c instanceof Node ? c : document.createTextNode(String(c))));
    return n;
  };
  const fmtDate = (ts) => new Date(ts * 1000).toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit', year: 'numeric' });
  const notify = (msg, kind = 'info') => (typeof window.toast === 'function' ? window.toast(msg, kind) : alert(msg));

  async function status() {
    const r = await fetch('/api/license', { headers: { Accept: 'application/json' } });
    if (!r.ok) throw new Error(`Error ${r.status}`);
    return r.json();
  }

  function waLink(info, plan) {
    const text = [
      '🔑 *Solicitud de licencia — IPV Fichas de Costo*',
      `Usuario: ${info._user || '(escriba su nombre)'}`,
      `ID Dispositivo: ${info.request_code}`,
      `Plan: ${plan}`,
      'Aplicación: IPV Web (servidor/PC)',
    ].join('\n');
    return `https://wa.me/${encodeURIComponent(info.whatsapp || '')}?text=${encodeURIComponent(text)}`;
  }

  function show(info = null, { closable = false } = {}) {
    if (layer) return;
    const render = (data) => {
      const plans = Object.entries(data.plans || {});
      const user = el('input', { class: 'lic-input', placeholder: 'Nombre o empresa', maxlength: '80', autocomplete: 'organization' });
      const plan = el('select', { class: 'lic-input' }, plans.map(([k, p]) => el('option', { value: `${p.name} (${k})` }, `${p.name} — ${p.usd} USD`)));
      plan.selectedIndex = Math.min(1, plans.length - 1);
      const code = el('code', { class: 'lic-code' }, data.request_code);
      const copy = el('button', { class: 'btn btn-secondary', type: 'button', on: { click: async () => {
        try { await navigator.clipboard.writeText(data.request_code); notify('Código copiado', 'success'); }
        catch { notify('Seleccione el código y cópielo manualmente'); }
      } } }, '📋 Copiar');
      const wa = el('button', { class: 'btn lic-wa', type: 'button', on: { click: () => {
        if (!data.whatsapp) { notify('El proveedor no configuró un número de WhatsApp. Envíe el código manualmente.'); return; }
        window.open(waLink({ ...data, _user: user.value.trim() }, plan.value), '_blank', 'noopener');
      } } }, '💬 Solicitar por WhatsApp');
      const token = el('textarea', { class: 'lic-input lic-token', rows: '4', placeholder: 'Pegue aquí la licencia completa (empieza por IPV1.)', spellcheck: 'false' });
      const msg = el('div', { class: 'lic-msg', role: 'alert', hidden: '' });
      const activate = el('button', { class: 'btn btn-primary', type: 'submit' }, '🔓 Activar licencia');
      const form = el('form', { class: 'lic-card', on: { submit: async (e) => {
        e.preventDefault();
        activate.disabled = true; msg.hidden = true;
        try {
          const auth = window.IPVAuth ? window.IPVAuth.headers() : {};
          const r = await fetch('/api/license', { method: 'POST', headers: { 'Content-Type': 'application/json', ...auth }, body: JSON.stringify({ license: token.value }) });
          const d = await r.json().catch(() => ({}));
          if (!r.ok) throw new Error(d.error || `Error ${r.status}`);
          close();
          notify(`Licencia activada: ${d.plan_name}, vence el ${fmtDate(d.expires_at)}`, 'success');
          setTimeout(() => location.reload(), 900);
        } catch (ex) {
          msg.textContent = ex.message; msg.hidden = false;
        } finally { activate.disabled = false; }
      } } },
        el('div', { class: 'lic-head' }, el('span', { class: 'lic-icon' }, '🔐'), el('div', {},
          el('h2', {}, data.valid ? 'Renovar licencia' : 'Activar licencia'),
          el('p', {}, data.valid ? `Licencia vigente: ${data.plan_name}, vence el ${fmtDate(data.expires_at)} (${data.days_left} días).` : (data.reason || 'Este equipo necesita una licencia.')))),
        el('ol', { class: 'lic-steps' },
          el('li', {}, 'Escriba su nombre y elija el plan.'),
          el('li', {}, 'Envíe la solicitud por WhatsApp (incluye el ID cifrado de este equipo).'),
          el('li', {}, 'Pegue la licencia que recibirá y pulse Activar.')),
        el('label', { class: 'lic-label' }, 'Usuario', user),
        el('label', { class: 'lic-label' }, 'Plan', plan),
        el('div', { class: 'lic-label' }, 'ID Dispositivo (cifrado)', el('div', { class: 'lic-code-row' }, code, copy)),
        wa,
        el('label', { class: 'lic-label' }, 'Licencia', token),
        msg,
        el('div', { class: 'lic-actions' }, closable ? el('button', { class: 'btn btn-secondary', type: 'button', on: { click: close } }, 'Cerrar') : '', activate),
        el('small', { class: 'lic-foot' }, 'La licencia está firmada digitalmente y solo funciona en este equipo. · Ing. Yosvany Hernández Quintero'));
      layer = el('div', { class: 'lic-layer', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Activación de licencia' }, form);
      document.body.append(layer);
      user.focus();
    };
    if (info && info.plans) render(info);
    else status().then(render).catch((e) => notify(`No se pudo consultar la licencia: ${e.message}`, 'error'));
  }

  function close() { layer?.remove(); layer = null; }

  async function boot() {
    try {
      const st = await status();
      if (!st.enforced) return;
      if (!st.valid) { document.querySelector('.login-layer')?.remove(); show(st); return; }
      if (st.days_left <= 7) {
        const bar = el('div', { class: 'lic-banner', role: 'status' },
          `⏳ Su licencia (${st.plan_name}) vence el ${fmtDate(st.expires_at)}: quedan ${st.days_left} día(s). `,
          el('button', { class: 'btn btn-secondary', type: 'button', on: { click: () => show(st, { closable: true }) } }, 'Renovar'));
        document.body.prepend(bar);
      }
    } catch { /* servidor sin conexión: lo gestiona app.js */ }
  }

  window.IPVLicense = { show: (info) => show(info, { closable: !!info?.valid }), status, renew: async () => show(await status(), { closable: true }) };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
