/**
 * IPV · Fichas y Costos
 * Aplica el tema guardado antes del primer pintado para evitar el destello
 * de tema claro cuando el usuario prefiere el oscuro.
 * Se carga como script clásico (no módulo) al final del <head>.
 * Autor: Ing. Yosvany Hernández Quintero
 */
(function applyStoredTheme() {
  'use strict';
  var DARK_COLOR = '#0d1513';
  var LIGHT_COLOR = '#0d3a2f';
  try {
    var stored = JSON.parse(window.localStorage.getItem('ipv.prefs.v1') || '{}') || {};
    var theme = stored.theme;
    if (theme !== 'light' && theme !== 'dark') {
      theme = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    document.documentElement.setAttribute('data-theme', theme);
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', theme === 'dark' ? DARK_COLOR : LIGHT_COLOR);
  } catch (error) {
    /* Almacenamiento no disponible (modo privado): se conserva el tema por omisión. */
  }
})();
