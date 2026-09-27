/**
 * IPV · Fichas y Costos
 * Cliente HTTP de la API JSON (mismo origen por defecto, sin dependencias).
 * Autor: Ing. Yosvany Hernández Quintero
 */

import { prefs } from './prefs.js';

const DEFAULT_TIMEOUT = 20000;
const IDEMPOTENT_METHODS = new Set(['GET', 'HEAD']);

export class ApiError extends Error {
  constructor(message, { status = 0, code = 'error', requestId = '', payload = null } = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.payload = payload;
  }

  /** Indica si el fallo se debe a la falta de conexión con el servicio. */
  get isNetworkFailure() { return this.status === 0; }
}

function baseUrl() {
  const configured = document.documentElement.dataset.apiBase || '';
  return configured.replace(/\/$/, '');
}

async function rawRequest(path, { method = 'GET', body, headers = {}, timeout = DEFAULT_TIMEOUT, retries = 1 } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort('timeout'), timeout);
  const finalHeaders = {
    Accept: 'application/json',
    'X-IPV-Operator': prefs.get('operator') || 'Operador local',
    ...headers,
  };
  if (body !== undefined && body !== null) finalHeaders['Content-Type'] = 'application/json; charset=utf-8';

  try {
    const response = await fetch(`${baseUrl()}${path}`, {
      method,
      headers: finalHeaders,
      body: body === undefined || body === null ? undefined : JSON.stringify(body),
      signal: controller.signal,
      credentials: 'same-origin',
      cache: 'no-store',
    });
    const contentType = response.headers.get('content-type') || '';
    const payload = contentType.includes('json')
      ? await response.json().catch(() => null)
      : await response.text();
    if (!response.ok) {
      const message = (payload && typeof payload === 'object' && payload.error)
        || `El servicio respondió con el código ${response.status}.`;
      throw new ApiError(message, {
        status: response.status,
        code: (payload && payload.code) || 'error_http',
        requestId: (payload && payload.request_id) || response.headers.get('x-request-id') || '',
        payload,
      });
    }
    return payload;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    const aborted = error && error.name === 'AbortError';
    const canRetry = IDEMPOTENT_METHODS.has(method) && retries > 0;
    if (canRetry) {
      await new Promise((resolve) => setTimeout(resolve, 350));
      return rawRequest(path, { method, body, headers, timeout, retries: retries - 1 });
    }
    const message = aborted
      ? 'El servicio tardó demasiado en responder. Verifique el servidor e intente de nuevo.'
      : 'No se pudo establecer comunicación con el servidor. Compruebe la conexión de red.';
    throw new ApiError(message, { status: 0, code: aborted ? 'tiempo_agotado' : 'sin_conexion' });
  } finally {
    clearTimeout(timer);
  }
}

export const api = {
  baseUrl,
  request: rawRequest,
  get: (path, options) => rawRequest(path, { ...options, method: 'GET' }),
  post: (path, body, options) => rawRequest(path, { ...options, method: 'POST', body: body ?? {} }),
  put: (path, body, options) => rawRequest(path, { ...options, method: 'PUT', body: body ?? {} }),
  patch: (path, body, options) => rawRequest(path, { ...options, method: 'PATCH', body: body ?? {} }),
  del: (path, options) => rawRequest(path, { ...options, method: 'DELETE' }),

  /** Consulta de estado con medición de latencia. */
  async health(deep = false) {
    const started = performance.now();
    const payload = await rawRequest(`/api/health${deep ? '?deep=1' : ''}`, { method: 'GET', retries: 0, timeout: 8000 });
    return { ...payload, latency: Math.round(performance.now() - started) };
  },

  meta: (deep = false) => rawRequest(`/api/meta${deep ? '?deep=1' : ''}`, { method: 'GET' }),
  dashboard: () => rawRequest('/api/dashboard', { method: 'GET' }),
  products: () => rawRequest('/api/products', { method: 'GET' }),
  product: (id) => rawRequest(`/api/products/${id}`, { method: 'GET' }),
  materials: () => rawRequest('/api/materials', { method: 'GET' }),
  fichas: () => rawRequest('/api/fichas', { method: 'GET' }),
  ficha: (id) => rawRequest(`/api/fichas/${id}`, { method: 'GET' }),
  controls: () => rawRequest('/api/controls', { method: 'GET' }),
  control: (id) => rawRequest(`/api/controls/${id}`, { method: 'GET' }),
  audit: (limit = 120) => rawRequest(`/api/audit?limit=${limit}`, { method: 'GET' }),
  search: (query) => rawRequest(`/api/search?q=${encodeURIComponent(query)}`, { method: 'GET' }),
  backup: () => rawRequest('/api/backup', { method: 'GET', timeout: 60000 }),
  restore: (payload) => rawRequest('/api/restore', { method: 'POST', body: payload, timeout: 60000 }),
  routes: () => rawRequest('/api/routes', { method: 'GET' }),
};

export function describeError(error) {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return 'Ocurrió un error inesperado.';
}
