/**
 * IPV · Fichas y Costos
 * Capa de acceso a datos: sincroniza la API con el almacén de estado.
 * Autor: Ing. Yosvany Hernández Quintero
 */

import { api, describeError } from './api.js';
import { store } from './store.js';
import { notifyError, progress } from './ui.js';

const MONITOR_INTERVAL = 25000;
let monitorTimer = 0;
let inFlight = null;

async function fetchSnapshot() {
  const [meta, dashboard, products, materials, fichas, controls, audit] = await Promise.all([
    api.meta(),
    api.dashboard(),
    api.products(),
    api.materials(),
    api.fichas(),
    api.controls(),
    api.audit(60),
  ]);
  return { meta, dashboard, products, materials, fichas, controls, audit };
}

export const data = {
  subscribe: store.subscribe,
  state: () => store.get(),

  /** Primer carga de la aplicación. */
  async bootstrap() {
    progress.start();
    store.set({ loading: true, error: null });
    try {
      const snapshot = await fetchSnapshot();
      store.set({ ...snapshot, loading: false, ready: true, error: null });
      await this.checkHealth();
      return snapshot;
    } catch (error) {
      store.set({ loading: false, error: describeError(error) });
      throw error;
    } finally {
      progress.done();
    }
  },

  /** Recarga la información; en modo silencioso no muestra la barra de progreso. */
  async reload({ silent = true } = {}) {
    if (inFlight) return inFlight;
    if (!silent) progress.start();
    inFlight = (async () => {
      try {
        const snapshot = await fetchSnapshot();
        store.set({ ...snapshot, loading: false, ready: true, error: null });
        this.setConnection({ online: true, status: 'Servicio operativo' });
        return snapshot;
      } catch (error) {
        const message = describeError(error);
        store.set({ loading: false, error: message });
        this.setConnection({ online: false, status: 'Sin conexión', error: message });
        if (!silent) notifyError(message, 'No se pudo actualizar la información');
        throw error;
      } finally {
        inFlight = null;
        if (!silent) progress.done();
      }
    })();
    return inFlight;
  },

  /** Consulta el estado del servicio y actualiza el indicador de conexión. */
  async checkHealth() {
    try {
      const health = await api.health();
      this.setConnection({ online: true, latency: health.latency, checkedAt: new Date().toISOString(), status: 'Servicio operativo' });
      return health;
    } catch (error) {
      this.setConnection({ online: false, latency: null, checkedAt: new Date().toISOString(), status: 'Sin conexión' });
      throw error;
    }
  },

  setConnection(patch) {
    const previous = store.get().connection;
    const next = { ...previous, checking: false, ...patch };
    if (previous.online === next.online && previous.status === next.status && previous.latency === next.latency) return;
    store.set({ connection: next });
  },

  /** Supervisa la conexión de forma periódica y ante cambios de red. */
  startMonitoring() {
    const tick = () => this.checkHealth().catch(() => {});
    clearInterval(monitorTimer);
    monitorTimer = setInterval(tick, MONITOR_INTERVAL);
    window.addEventListener('online', () => this.reload({ silent: true }).catch(() => {}));
    window.addEventListener('offline', () => this.setConnection({ online: false, status: 'Equipo sin red' }));
    document.addEventListener('visibilitychange', () => { if (!document.hidden) tick(); });
  },

  stopMonitoring() { clearInterval(monitorTimer); },

  audit: (limit = 120) => api.audit(limit),
  search: (query) => api.search(query),
  product: (id) => api.product(id),
  ficha: (id) => api.ficha(id),
  control: (id) => api.control(id),
  backup: () => api.backup(),
  restore: (payload) => api.restore(payload),
  routes: () => api.routes(),
};

export { api };
