/**
 * IPV · Fichas y Costos
 * Almacén de estado reactivo compartido por todas las vistas.
 * Autor: Ing. Yosvany Hernández Quintero
 */

/**
 * Crea un almacén observable sencillo.
 * @param {object} initial Estado inicial.
 */
export function createStore(initial) {
  let state = initial;
  const listeners = new Set();

  return {
    get() { return state; },
    select(selector) { return selector(state); },
    set(patch) {
      const next = typeof patch === 'function' ? patch(state) : { ...state, ...patch };
      if (next === state) return state;
      state = next;
      listeners.forEach((listener) => {
        try { listener(state); } catch (error) { console.error('Error en un suscriptor del estado:', error); }
      });
      return state;
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

/** Estado global de la aplicación. */
export const store = createStore({
  // Datos de la API
  meta: null,
  dashboard: null,
  products: [],
  materials: [],
  fichas: [],
  controls: [],
  audit: [],
  // Estado de la interfaz
  ready: false,
  loading: false,
  error: null,
  connection: { online: false, checking: true, latency: null, checkedAt: null, status: 'Conectando…' },
  route: { path: '/resumen', view: 'dashboard', params: {} },
});

/** Consultas derivadas reutilizables. */
export const selectors = {
  activeProducts: (state) => state.products.filter((product) => product.active),
  productById: (state, id) => state.products.find((product) => Number(product.id) === Number(id)) || null,
  materialById: (state, id) => state.materials.find((material) => Number(material.id) === Number(id)) || null,
  fichaById: (state, id) => state.fichas.find((ficha) => Number(ficha.id) === Number(id)) || null,
  controlById: (state, id) => state.controls.find((control) => Number(control.id) === Number(id)) || null,
  categories: (state) => [...new Set(state.products.map((product) => product.category).filter(Boolean))].sort(),
  periods: (state) => [...new Set(state.controls.map((control) => control.period).filter(Boolean))].sort().reverse(),
  counts: (state) => ({
    products: state.products.filter((product) => product.active).length,
    materials: state.materials.length,
    fichas: state.fichas.length,
    controls: state.controls.length,
    pending: state.controls.filter((control) => control.status !== 'Validado').length,
  }),
};
