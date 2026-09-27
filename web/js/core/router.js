/**
 * IPV · Fichas y Costos
 * Enrutado de la interfaz con rutas limpias (/fichas/12) e historial del navegador.
 * Autor: Ing. Yosvany Hernández Quintero
 */

/**
 * @typedef {object} RouteDefinition
 * @property {string} path Patrón, por ejemplo '/fichas/:id'.
 * @property {string} view Identificador de la vista.
 * @property {string} title Título de la pestaña.
 * @property {string} crumb Texto de la miga de pan.
 */

export function createRouter({ routes, fallback, onNavigate }) {
  const compiled = routes.map((route) => {
    const segments = route.path.split('/').filter(Boolean);
    return { ...route, segments };
  });

  function match(pathname) {
    const clean = `/${String(pathname).split('?')[0].split('/').filter(Boolean).join('/')}`;
    const segments = clean.split('/').filter(Boolean);
    for (const route of compiled) {
      if (route.segments.length !== segments.length) continue;
      const params = {};
      const matched = route.segments.every((segment, index) => {
        if (segment.startsWith(':')) { params[segment.slice(1)] = decodeURIComponent(segments[index]); return true; }
        return segment === segments[index];
      });
      if (matched) return { route, params, path: clean };
    }
    return null;
  }

  function current() {
    const found = match(window.location.pathname);
    const query = Object.fromEntries(new URLSearchParams(window.location.search).entries());
    if (found) return { ...found, query };
    const target = match(fallback) || { route: compiled[0], params: {}, path: fallback };
    return { ...target, query };
  }

  function navigate(path, { replace = false, query } = {}) {
    const [pathname, search] = String(path).split('?');
    const searchParams = new URLSearchParams(search || '');
    if (query) {
      Object.entries(query).forEach(([key, value]) => {
        if (value === undefined || value === null || value === '') searchParams.delete(key);
        else searchParams.set(key, value);
      });
    }
    const suffix = searchParams.toString();
    const target = `${pathname}${suffix ? `?${suffix}` : ''}`;
    if (`${window.location.pathname}${window.location.search}` === target) return;
    if (replace) window.history.replaceState({ ipv: true }, '', target);
    else window.history.pushState({ ipv: true }, '', target);
    onNavigate(current());
  }

  /** Actualiza solo los parámetros de consulta sin recargar la vista. */
  function updateQuery(query, { replace = true } = {}) {
    navigate(`${current().path}`, { replace, query });
  }

  function start() {
    window.addEventListener('popstate', () => onNavigate(current()));
    document.addEventListener('click', (event) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const link = event.target instanceof Element ? event.target.closest('a[data-route]') : null;
      if (!link) return;
      const href = link.getAttribute('href');
      if (!href || href.startsWith('http') || link.target === '_blank') return;
      event.preventDefault();
      navigate(href);
    });
    onNavigate(current());
  }

  return { start, navigate, updateQuery, current, match };
}
