/**
 * IPV · Fichas y Costos
 * Vista: «Acerca de» — propósito, alcance, arquitectura y autoría.
 * Autor: Ing. Yosvany Hernández Quintero
 */

import { clear, el, frag, icon, mount } from '../core/dom.js';
import { data } from '../core/data.js';
import { prefs } from '../core/prefs.js';
import { button, card, copyText, metaRow } from '../core/ui.js';

let unsubscribe = null;
let host = null;

const FEATURES = [
  ['package', 'Catálogo único de productos y servicios',
    'Un solo registro para el cliente web y el cliente Android, con códigos irrepetibles, categorías, unidades de salida y control de vigencia.'],
  ['tag', 'Valores del IPV con procedencia documental',
    'Cada insumo, materia prima, tarifa o servicio guarda precio, moneda, unidad, vigencia, proveedor y documento de respaldo.'],
  ['file', 'Fichas de costo versionadas',
    'Elaboración por versiones, bloqueo al aprobar, recálculo de precios desde el catálogo y conservación del valor aplicado en cada componente.'],
  ['shield', 'Controles de IPV con informe de validación',
    'Instantánea del período, comprobación de subtotales, conciliación con la ficha aprobada y detección de variaciones de precios.'],
  ['history', 'Bitácora de auditoría',
    'Cada operación se registra con acción, entidad, responsable y fecha, y no puede modificarse desde la interfaz.'],
  ['archive', 'Respaldos y restauración',
    'Exportación completa en JSON, copia de seguridad automática antes de cada restauración y verificación de integridad de la base de datos.'],
  ['monitor', 'Operación en red local',
    'Servicio publicado por HTTPS en la red de la entidad, sin dependencia de servicios en Internet ni envío de información a terceros.'],
  ['users', 'Multicliente y multiusuario',
    'Interfaz web adaptable a cualquier dispositivo y aplicación Android nativa que consume la misma API JSON.'],
];

const CAPABILITIES = [
  'Catálogo de productos y servicios',
  'Registro de valores del IPV',
  'Fichas de costo versionadas',
  'Aprobación y reapertura controlada',
  'Controles de IPV por período',
  'Informe de validación y actas',
  'Bitácora de auditoría',
  'Exportación CSV y respaldo JSON',
  'API JSON compartida (web y Android)',
  'Tema claro y oscuro',
  'Documentos listos para imprimir',
  'Operación sin conexión a Internet',
];

const MODULES = [
  ['package', 'Productos y servicios', '/productos'],
  ['tag', 'Valores del IPV', '/valores'],
  ['file', 'Fichas de costo', '/fichas'],
  ['shield', 'Controles de IPV', '/controles'],
  ['history', 'Bitácora de auditoría', '/bitacora'],
  ['settings', 'Sistema y respaldos', '/sistema'],
];

function hero(meta) {
  const author = el('div', { class: 'about-author' },
    el('span', { class: 'about-author-mark', 'aria-hidden': 'true', text: 'YH' }),
    el('div', {},
      el('b', { text: meta.application.author }),
      el('small', { text: meta.application.author_role })),
    el('span', { class: 'pill pill--brand pill--plain', text: `Versión ${meta.application.version}` }));

  return el('section', { class: 'about-hero' },
    el('div', { class: 'about-hero-inner' },
      el('span', { class: 'about-tag' }, icon('sparkle', { size: 14 }), el('span', { text: 'Sistema de gestión de costos' })),
      el('h1', { text: meta.application.name }),
      el('p', { text: meta.application.description }),
      author));
}

function featureGrid() {
  const items = FEATURES.map(([iconName, title, description]) => el('article', { class: 'feature' },
    icon(iconName, { size: 18 }),
    el('div', {}, el('b', { text: title }), el('p', { text: description }))));
  return el('div', { class: 'feature-grid' }, ...items);
}

function moduleGrid() {
  const items = MODULES.map(([iconName, label, path]) => el('a', {
    class: 'feature', href: path, 'data-route': path, style: { textDecoration: 'none' },
  },
    icon(iconName, { size: 18 }),
    el('div', {}, el('b', { text: label }), el('p', { text: 'Abrir módulo' }))));
  return el('div', { class: 'feature-grid' }, ...items);
}

function padedBody(...children) {
  return el('div', { style: { padding: '0 var(--space-5) var(--space-5)' } }, ...children);
}

function metaList(...rows) {
  return el('dl', { class: 'meta-list' }, ...rows);
}

function render() {
  if (!host) return;
  const meta = data.state().meta;
  if (!meta) {
    mount(host, el('div', { class: 'stack' },
      el('div', { class: 'skeleton', style: { height: '260px' } }),
      el('div', { class: 'skeleton', style: { height: '220px' } })));
    return;
  }

  const scopeCard = card({
    title: 'Alcance funcional',
    subtitle: 'Módulos disponibles en esta versión',
    body: padedBody(el('div', { class: 'chip-list' }, ...CAPABILITIES.map((item) => el('span', { class: 'chip', text: item })))),
  });

  const techCard = card({
    title: 'Ficha técnica',
    subtitle: 'Arquitectura y componentes',
    body: padedBody(metaList(
      metaRow('Aplicación', meta.application.name),
      metaRow('Versión', meta.application.version),
      metaRow('Publicación', meta.application.release),
      metaRow('Servidor', `Python ${meta.server.python} · servicio HTTP(S) con biblioteca estándar`),
      metaRow('Base de datos', `${meta.database.engine} ${meta.database.version}`),
      metaRow('Protocolo', String(meta.server.scheme).toUpperCase()),
      metaRow('Cliente web', 'HTML, CSS y JavaScript sin dependencias externas'),
      metaRow('Cliente móvil', 'Aplicación Android nativa (Kotlin)'),
      metaRow('Autor', meta.application.author),
    )),
  });

  const modulesCard = card({
    title: 'Módulos del sistema',
    subtitle: 'Acceso directo a cada sección de trabajo',
    body: padedBody(moduleGrid()),
  });

  const noticeCard = card({
    title: 'Aviso de uso',
    subtitle: 'Información importante sobre los datos y los resultados',
    body: padedBody(
      el('div', { class: 'banner banner--warning' },
        icon('alert', { size: 17 }),
        el('span', {}, el('b', { text: 'Datos de ejemplo' }), el('span', { text: meta.application.notice }))),
      el('p', { class: 'field-hint', style: { marginTop: 'var(--space-4)' },
        text: 'El informe de validación de los controles de IPV es un instrumento de apoyo a la revisión: no sustituye la comprobación normativa, la documentación primaria del costo ni las firmas oficiales de la entidad.' }),
    ),
  });

  const supportCard = card({
    title: 'Soporte técnico',
    subtitle: 'Datos para la atención y el mantenimiento',
    body: padedBody(
      metaList(
        metaRow('Responsable técnico', meta.application.author),
        metaRow('Función', meta.application.author_role),
        metaRow('Dirección del servicio', meta.application.url, { code: true }),
        metaRow('Base de datos', meta.database.path, { code: true }),
        metaRow('Operador registrado', prefs.get('operator')),
      ),
      el('div', { class: 'row', style: { marginTop: 'var(--space-4)' } },
        button('Copiar dirección del servicio', {
          iconName: 'copy',
          onClick: () => copyText(meta.application.url, 'Dirección del servicio copiada.'),
        })),
    ),
  });

  mount(host, frag(
    hero(meta),
    el('div', { class: 'stack-lg', style: { marginTop: 'var(--space-6)' } },
      el('section', { class: 'stack' },
        el('h2', { text: 'Qué resuelve el sistema' }),
        featureGrid()),
      el('div', { class: 'panel-grid panel-grid--split' }, scopeCard, techCard),
      modulesCard,
      noticeCard,
      supportCard,
      el('p', { class: 'subtle', style: { fontSize: 'var(--text-2xs)' },
        text: `${meta.application.name} · versión ${meta.application.version} · ${meta.application.author}. Desarrollado para la gestión de costos en red local.` })),
  ));
}

export const aboutView = {
  id: 'about',
  title: 'Acerca de',
  crumb: 'Acerca de',
  description: 'Información del sistema y autoría.',
  mount(container) {
    host = container;
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
