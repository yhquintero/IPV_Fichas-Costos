/**
 * IPV · Fichas y Costos
 * Vista: sistema, diagnóstico técnico, respaldos y preferencias.
 * Autor: Ing. Yosvany Hernández Quintero
 */

import { clear, el, frag, icon, mount } from '../core/dom.js';
import { api } from '../core/api.js';
import { data } from '../core/data.js';
import { prefs, resolvedTheme } from '../core/prefs.js';
import { downloadJson, fmtBytes, fmtDateTime, fmtDuration, fmtNumber, timestampForFilename } from '../core/format.js';
import { button, card, confirmAction, copyText, field, metaRow, openModal, readForm, runAction, toast } from '../core/ui.js';

let unsubscribe = null;
let host = null;
let ctxRef = null;
let deepMeta = null;

const SHORTCUTS = [
  ['Ctrl + K', 'Abrir la búsqueda global'],
  ['G luego R', 'Ir al resumen'],
  ['G luego P', 'Ir a productos y servicios'],
  ['G luego V', 'Ir a valores del IPV'],
  ['G luego F', 'Ir a fichas de costo'],
  ['G luego C', 'Ir a controles de IPV'],
  ['R', 'Actualizar los datos'],
  ['T', 'Cambiar el tema claro u oscuro'],
  ['Esc', 'Cerrar ventanas y paneles'],
];

function applicationCard(meta) {
  return card({
    title: 'Aplicación',
    subtitle: 'Identidad del sistema en ejecución',
    actions: el('span', { class: 'system-card-icon' }, icon('info', { size: 17 })),
    body: el('div', { style: { padding: '0 var(--space-5) var(--space-5)' } },
      el('dl', { class: 'meta-list' },
        metaRow('Nombre', meta.application.name),
        metaRow('Versión', meta.application.version),
        metaRow('Publicación', meta.application.release),
        metaRow('Autor', meta.application.author),
        metaRow('Rol', meta.application.author_role),
        metaRow('Dirección del servicio', meta.application.url, { code: true }))),
  });
}

function serverCard(meta) {
  const server = meta.server;
  return card({
    title: 'Servidor y red',
    subtitle: 'Parámetros de publicación en la red local',
    actions: el('span', { class: 'system-card-icon' }, icon('server', { size: 17 })),
    body: el('div', { style: { padding: '0 var(--space-5) var(--space-5)' } },
      el('dl', { class: 'meta-list' },
        metaRow('Protocolo', server.scheme.toUpperCase()),
        metaRow('Dirección de escucha', `${server.host}:${server.port}`),
        metaRow('Python', server.python),
        metaRow('Sistema operativo', server.platform),
        metaRow('Iniciado', fmtDateTime(server.started_at)),
        metaRow('Tiempo en servicio', fmtDuration(server.uptime_seconds)),
        metaRow('Carpeta de respaldos', server.backup_dir, { code: true }))),
  });
}

function databaseCard(meta) {
  const database = deepMeta?.database || meta.database;
  const counts = database.counts || {};
  const body = el('div', { style: { padding: '0 var(--space-5) var(--space-5)' } },
    el('dl', { class: 'meta-list' },
      metaRow('Motor', `${database.engine} ${database.version}`),
      metaRow('Archivo', database.file, { code: true }),
      metaRow('Ruta completa', database.path, { code: true }),
      metaRow('Tamaño', fmtBytes(database.size_bytes)),
      metaRow('Modo de registro', database.journal_mode),
      metaRow('Productos', `${fmtNumber(counts.products)} · ${fmtNumber(counts.active_products)} activos`),
      metaRow('Valores del IPV', fmtNumber(counts.materials)),
      metaRow('Fichas de costo', `${fmtNumber(counts.fichas)} · ${fmtNumber(counts.approved_fichas)} aprobadas`),
      metaRow('Controles de IPV', `${fmtNumber(counts.controls)} · ${fmtNumber(counts.validated_controls)} validados`),
      metaRow('Asientos de auditoría', fmtNumber(counts.audit_events)),
      database.integrity ? metaRow('Integridad', database.integrity) : null),
    el('div', { class: 'row', style: { marginTop: 'var(--space-4)' } },
      button(deepMeta ? 'Volver a verificar integridad' : 'Verificar integridad', {
        iconName: 'shieldCheck',
        onClick: async () => {
          const result = await runAction(() => api.meta(true), { success: 'Verificación de integridad completada.' });
          if (result === null) return;
          deepMeta = result;
          render();
        },
      }),
      button('Copiar ruta', { iconName: 'copy', onClick: () => copyText(database.path, 'Ruta de la base de datos copiada.') })));
  return card({
    title: 'Base de datos',
    subtitle: 'Estado de la persistencia y verificación de integridad',
    actions: el('span', { class: 'system-card-icon' }, icon('database', { size: 17 })),
    body,
  });
}

function backupsCard(meta) {
  const fileInput = el('input', { type: 'file', accept: 'application/json,.json', style: { display: 'none' } });
  fileInput.addEventListener('change', async () => {
    const file = fileInput.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const payload = JSON.parse(text);
      const confirmed = await confirmAction({
        title: 'Restaurar respaldo',
        message: `Se reemplazará por completo la información actual con el contenido de «${file.name}».`,
        note: 'Antes de aplicar el respaldo el sistema guarda automáticamente una copia de seguridad del estado actual.',
        confirmLabel: 'Restaurar respaldo',
        tone: 'danger',
        requireText: 'REEMPLAZAR',
      });
      if (!confirmed) return;
      const result = await runAction(() => api.restore({ ...payload, confirm: 'REEMPLAZAR' }),
        { success: 'Respaldo restaurado. La información se actualizó.' });
      if (result === null) return;
      await data.reload({ silent: true });
      render();
    } catch (error) {
      toast(error instanceof SyntaxError ? 'El archivo seleccionado no es un respaldo JSON válido.' : error.message,
        { type: 'error', title: 'No se pudo restaurar el respaldo' });
    } finally {
      fileInput.value = '';
    }
  });

  return card({
    title: 'Respaldos',
    subtitle: 'Copia de seguridad y restauración de la información',
    actions: el('span', { class: 'system-card-icon' }, icon('archive', { size: 17 })),
    body: el('div', { style: { padding: '0 var(--space-5) var(--space-5)' } },
      el('p', { class: 'field-hint', style: { marginBottom: 'var(--space-4)' },
        text: 'El respaldo incluye productos, valores del IPV, fichas, controles y la bitácora de auditoría en un único archivo JSON.' }),
      el('div', { class: 'row' },
        button('Descargar respaldo', {
          variant: 'primary', iconName: 'download',
          onClick: async () => {
            const payload = await runAction(() => data.backup(), { success: 'Respaldo generado y descargado.' });
            if (payload === null) return;
            downloadJson(`ipv-respaldo-${timestampForFilename()}.json`, payload);
          },
        }),
        button('Restaurar desde archivo', { iconName: 'upload', onClick: () => fileInput.click() }),
        button('Verificar servicio', {
          iconName: 'refresh',
          onClick: async () => {
            const health = await runAction(() => data.checkHealth(), { success: 'El servicio respondió correctamente.' });
            if (health === null) return;
            toast(`Latencia ${health.latency} ms · base de datos ${health.database}`, { type: 'success', title: 'Diagnóstico' });
          },
        })),
      fileInput),
  });
}

function securityCard(meta) {
  const tls = meta.tls || {};
  return card({
    title: 'Seguridad y certificados',
    subtitle: 'Cifrado de la comunicación con los clientes',
    actions: el('span', { class: 'system-card-icon' }, icon('lock', { size: 17 })),
    body: el('div', { style: { padding: '0 var(--space-5) var(--space-5)' } },
      el('dl', { class: 'meta-list' },
        metaRow('HTTPS', tls.enabled ? 'Habilitado' : 'Deshabilitado (uso local)'),
        metaRow('Certificado', tls.file || 'No configurado', { code: Boolean(tls.file) }),
        metaRow('Nombre del certificado', tls.subject || '—'),
        metaRow('Vence', tls.not_after || '—')),
      el('div', { class: 'banner banner--neutral', style: { marginTop: 'var(--space-4)' } },
        icon('info', { size: 16 }),
        el('span', { text: 'El certificado local debe instalarse como entidad de confianza en cada equipo o dispositivo que acceda al servicio. No publique este puerto en Internet.' }))),
  });
}

function operatorCard() {
  const form = el('form', { style: { padding: '0 var(--space-5) var(--space-5)' } },
    field({
      label: 'Nombre del operador', name: 'operator', value: prefs.get('operator'), required: true,
      hint: 'Se registra como responsable en la bitácora y en la aprobación de fichas.',
    }),
    button('Guardar operador', {
      variant: 'primary', iconName: 'check',
      onClick: () => {
        if (!form.reportValidity()) return;
        const values = readForm(form);
        prefs.set('operator', values.operator);
        toast(`Operador registrado: ${values.operator}`, { type: 'success' });
      },
    }));
  return card({
    title: 'Operador del sistema',
    subtitle: 'Responsable que firma las operaciones',
    actions: el('span', { class: 'system-card-icon' }, icon('user', { size: 17 })),
    body: form,
  });
}

function preferencesCard() {
  const themeSelect = el('select', {
    class: 'select', 'aria-label': 'Tema de la interfaz',
    on: { change: (event) => { prefs.set('theme', event.target.value); syncThemeLabel(); } },
  },
    el('option', { value: 'auto', text: 'Automático según el sistema' }),
    el('option', { value: 'light', text: 'Claro' }),
    el('option', { value: 'dark', text: 'Oscuro' }));
  themeSelect.value = prefs.get('theme');

  const densitySelect = el('select', {
    class: 'select', 'aria-label': 'Densidad de las tablas',
    on: { change: (event) => { prefs.set('density', event.target.value); toast('Preferencia de densidad guardada.', { type: 'success', duration: 2200 }); } },
  },
    el('option', { value: 'comfortable', text: 'Cómoda' }),
    el('option', { value: 'compact', text: 'Compacta' }));
  densitySelect.value = prefs.get('density');

  const pageSizeSelect = el('select', {
    class: 'select', 'aria-label': 'Filas por página',
    on: { change: (event) => { prefs.set('pageSize', Number(event.target.value)); toast('Preferencia de paginación guardada.', { type: 'success', duration: 2200 }); } },
  }, ...[8, 12, 25, 50].map((size) => el('option', { value: size, text: `${size} filas` })));
  pageSizeSelect.value = String(prefs.get('pageSize'));

  const themeLabel = el('span', { class: 'tag' });
  function syncThemeLabel() { themeLabel.textContent = `Tema activo: ${resolvedTheme() === 'dark' ? 'oscuro' : 'claro'}`; }
  syncThemeLabel();

  return card({
    title: 'Preferencias de la interfaz',
    subtitle: 'Ajustes guardados en este navegador',
    actions: el('span', { class: 'system-card-icon' }, icon('settings', { size: 17 })),
    body: el('div', { style: { padding: '0 var(--space-5) var(--space-5)' } },
      el('div', { class: 'form-grid' },
        el('div', { class: 'field' }, el('label', { text: 'Tema de la interfaz' }), themeSelect),
        el('div', { class: 'field' }, el('label', { text: 'Densidad de tablas' }), densitySelect),
        el('div', { class: 'field' }, el('label', { text: 'Filas por página' }), pageSizeSelect)),
      el('div', { class: 'row', style: { marginTop: 'var(--space-2)' } },
        themeLabel,
        button('Restablecer preferencias', {
          iconName: 'refresh', variant: 'ghost',
          onClick: async () => {
            const confirmed = await confirmAction({
              title: 'Restablecer preferencias',
              message: 'Se restaurarán el tema automático, la densidad cómoda y el tamaño de página predeterminado.',
              confirmLabel: 'Restablecer',
            });
            if (!confirmed) return;
            prefs.reset();
            render();
          },
        }))),
  });
}

function shortcutsCard() {
  return card({
    title: 'Atajos de teclado',
    subtitle: 'Operación rápida desde el teclado',
    actions: el('span', { class: 'system-card-icon' }, icon('key', { size: 17 })),
    body: el('div', { style: { padding: '0 var(--space-5) var(--space-5)' } },
      el('div', { class: 'key-hint-grid' },
        ...SHORTCUTS.map(([keys, description]) => el('div', { class: 'key-hint' },
          el('span', { text: description }),
          el('kbd', { text: keys }))))),
  });
}

function apiCard(meta) {
  return card({
    title: 'Integración y API',
    subtitle: 'Servicios compartidos con el cliente Android',
    actions: el('span', { class: 'system-card-icon' }, icon('link', { size: 17 })),
    body: el('div', { style: { padding: '0 var(--space-5) var(--space-5)' } },
      el('p', { class: 'field-hint', style: { marginBottom: 'var(--space-4)' },
        text: 'Toda la aplicación funciona sobre la misma API JSON documentada. El cliente Android consume estos servicios desde la red local.' }),
      el('pre', { class: 'code-block', text: [
        'GET  /api/health          Estado del servicio',
        'GET  /api/meta            Información del sistema',
        'GET  /api/dashboard       Indicadores y alertas',
        'GET  /api/products        Catálogo de productos',
        'GET  /api/materials       Valores del IPV',
        'GET  /api/fichas          Fichas de costo',
        'GET  /api/controls        Controles de IPV',
        'GET  /api/audit           Bitácora de auditoría',
        'GET  /api/search?q=       Búsqueda global',
        'GET  /api/backup          Respaldo completo',
      ].join('\n') }),
      el('div', { class: 'row', style: { marginTop: 'var(--space-4)' } },
        button('Copiar dirección del servicio', { iconName: 'copy', onClick: () => copyText(meta.application.url, 'Dirección del servicio copiada.') }),
        button('Ver catálogo de rutas', {
          iconName: 'book',
          onClick: async () => {
            const routes = await runAction(() => data.routes());
            if (!routes) return;
            const modal = openModal({
              title: 'Catálogo de rutas de la API',
              subtitle: `${routes.length} servicios disponibles`,
              size: 'wide',
              content: el('pre', {
                class: 'code-block',
                text: routes.map((route) => `${route.method.padEnd(6)} ${route.path.padEnd(36)} ${route.description}`).join('\n'),
              }),
              actions: [el('button', { class: 'btn btn--primary', type: 'button', text: 'Cerrar', on: { click: () => modal.close() } })],
            });
          },
        }))),
  });
}

function render() {
  if (!host) return;
  const meta = deepMeta || data.state().meta;
  if (!meta) {
    mount(host, el('div', { class: 'stack' }, el('div', { class: 'skeleton', style: { height: '80px' } }), el('div', { class: 'skeleton', style: { height: '400px' } })));
    return;
  }
  mount(host, frag(
    el('header', { class: 'page-heading' },
      el('div', { class: 'page-heading-main' },
        el('p', { class: 'eyebrow', text: 'Administración' }),
        el('h1', { text: 'Sistema y respaldos' }),
        el('p', { text: 'Diagnóstico del servicio, estado de la base de datos, certificados, copias de seguridad y preferencias de la interfaz.' })),
      el('div', { class: 'page-heading-actions' },
        button('Actualizar diagnóstico', {
          iconName: 'refresh',
          onClick: async () => {
            const result = await runAction(() => api.meta(true), { success: 'Diagnóstico actualizado.' });
            if (result === null) return;
            deepMeta = result;
            render();
          },
        }))),
    el('div', { class: 'system-grid' },
      applicationCard(meta),
      serverCard(meta),
      databaseCard(meta),
      backupsCard(meta),
      securityCard(meta),
      operatorCard(),
      preferencesCard(),
      shortcutsCard(),
      apiCard(meta)),
    el('p', { class: 'subtle', style: { marginTop: 'var(--space-5)', fontSize: 'var(--text-2xs)' },
      text: 'La aplicación funciona íntegramente en la red local: no requiere servicios en Internet ni envía información a terceros.' })));
}

export const systemView = {
  id: 'system',
  title: 'Sistema y respaldos',
  crumb: 'Sistema y respaldos',
  description: 'Diagnóstico técnico y copias de seguridad.',
  mount(container, ctx) {
    host = container;
    ctxRef = ctx;
    deepMeta = null;
    render();
    unsubscribe = data.subscribe(render);
  },
  unmount() {
    if (unsubscribe) unsubscribe();
    unsubscribe = null;
    host = null;
    if (host) clear(host);
    host = null;
  },
};
