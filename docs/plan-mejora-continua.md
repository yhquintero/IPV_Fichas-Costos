# 🚀 Plan de mejora continua — App Web y App Móvil

> IPV · Fichas y Costos — Autor: Ing. Yosvany Hernández Quintero
> Plan de trabajo para que las dos aplicaciones (web y Android) crezcan **juntas, seguras y sin sorpresas**.
> Versión del plan: 1.0 · Revisión: cada trimestre.

---

## 1. Principios (no se negocian)

| # | Principio | Qué significa en la práctica |
|---|---|---|
| 1 | **Seguridad primero** | Ninguna mejora entra si baja el listón: HTTPS, JWT, 2FA, auditoría encadenada, BD cifrada y licencia siguen funcionando igual o mejor. |
| 2 | **Sin dependencias externas** | Servidor y keygen usan **solo la librería estándar de Python**; la web, JS puro sin frameworks; el móvil, APIs de la plataforma. Cero `npm install`, cero cadenas de suministro ajenas. |
| 3 | **Paridad web ↔ móvil** | Toda función nueva se planifica en las **dos** aplicaciones. Si en una no es viable todavía, se anota como deuda con fecha. |
| 4 | **En español y para el usuario real** | Textos, mensajes de error y documentación en español claro; nada de jerga innecesaria. |
| 5 | **Nada se pierde** | Papelera, versiones de ficha, auditoría y copias 3-2-1: ningún cambio puede destruir datos de forma irreversible. |
| 6 | **Se demuestra con pruebas** | Cada mejora llega con su prueba automática; si no se puede probar, se documenta cómo verificarla a mano. |

---

## 2. Cómo trabajamos: el ciclo IPV (2 semanas)

```
Día 1-2    Recoger        → incidencias, ideas del usuario, avisos de -Check y de la auditoría
Día 3      Priorizar      → tabla de impacto/esfuerzo, se eligen 3-5 mejoras (máximo)
Día 4-9    Construir      → una rama por mejora, pruebas incluidas, web y móvil a la vez
Día 10-11  Verificar      → CI verde, checklist de calidad, prueba manual en PC y en teléfono
Día 12     Publicar       → versión etiquetada, notas de versión, caché del PWA subida, APK firmado
Día 13-14  Estabilizar    → correcciones rápidas, actualizar documentación y este plan
```

**Regla del 70/20/10** en cada ciclo: 70 % mejoras pedidas por el usuario · 20 % seguridad y mantenimiento · 10 % deuda técnica.

### Ritmos fijos

| Frecuencia | Tarea | Comando / lugar |
|---|---|---|
| Cada arranque | Revisar avisos del servidor (certificado, BD sin cifrar) | consola de `iniciar-https.ps1` |
| Diario | Copia de seguridad automática + réplica fuera del equipo | automática (`IPV_BACKUP_INTERVAL_HOURS`) |
| Semanal | Revisar auditoría y accesos desde IP nueva | `-AuditLog` · web → Registro de auditoría |
| Mensual | Diagnóstico completo del acceso seguro | `.\iniciar-https.ps1 -Check` |
| Mensual | Restaurar una copia de seguridad **de prueba** | `python dbcrypt.py status` + copia a carpeta temporal |
| Trimestral | Revisar este plan, métricas y hoja de ruta | `docs/plan-mejora-continua.md` |
| Semestral | Escaneo ZAP completo + revisión de permisos de usuarios | CI (`zap`) y web → Usuarios |
| Anual | Renovar la CA local y reinstalarla en los clientes | `.\iniciar-https.ps1 -Renew` |

---

## 3. Puertas de calidad (Definition of Done)

Una mejora **no está terminada** hasta que cumple todo esto:

- [ ] Funciona en la **web** y en el **móvil** (o hay una deuda anotada con fecha).
- [ ] `python -m unittest discover -s tests` en verde (86 pruebas y subiendo).
- [ ] `ruff check --select E9,F63,F7,F82 .` sin errores.
- [ ] `bandit -ll -ii` sin hallazgos de severidad media/alta.
- [ ] CI completo en verde, incluida la tanda con **base de datos cifrada** y el escaneo **ZAP**.
- [ ] Sin scripts en línea en la web (la CSP es estricta: `script-src 'self'`).
- [ ] Textos en español, con mayúsculas y tildes correctas.
- [ ] Accesibilidad: navegable con teclado, contraste suficiente, `aria-label` en los controles con icono.
- [ ] Documentación actualizada (`README.md` y la guía que corresponda en `docs/`).
- [ ] Caché del Service Worker subida de versión si cambió algo de `web/`.
- [ ] Probado a mano en: Chrome/Edge escritorio, móvil (PWA) y app Android.

---

## 4. Métricas que vigilamos

| Métrica | Hoy | Objetivo | Cómo se mide |
|---|---|---|---|
| Pruebas automáticas | 86 | +6 por trimestre | `unittest discover -s tests` |
| Cobertura del servidor | ~70 % | ≥ 80 % | `coverage report` en CI |
| Vulnerabilidades medias/altas | 0 | 0 | Bandit + ZAP en CI |
| Peso de la web (JS+CSS) | ~180 KB | < 250 KB | tamaño de `web/` |
| Primer pintado (LAN) | < 1 s | < 1 s | DevTools → Network |
| Tiempo de arranque del servidor | < 2 s | < 3 s | consola al iniciar |
| Tamaño del APK | ~2 MB | < 5 MB | `app-debug.apk` |
| Paridad de funciones web ↔ móvil | 8/11 | 11/11 | tabla del punto 5 |
| Incidencias abiertas > 30 días | 0 | 0 | issues de GitHub |
| Copias de seguridad verificadas | diaria | diaria | auditoría `BACKUP_*` |

> Anote los valores al cerrar cada trimestre: la tendencia importa más que el número.

---

## 5. Paridad Web ↔ Móvil

| Función | Web | Móvil | Próximo paso |
|---|---|---|---|
| Productos, valores del IPV, inventario, fichas, controles | ✅ | ✅ | — |
| Columna **Id** y contador de ítems | ✅ | ✅ | — |
| Papelera (restaurar / borrar) | ✅ | ✅ | — |
| Licencia al arrancar + renovación | ✅ | ✅ | — |
| Creador de Licencias | ✅ | ❌ | T2: consulta del historial desde el móvil |
| Auditoría y gestión de usuarios | ✅ | ❌ | T2: vista de solo lectura en el móvil |
| Importar/Exportar CSV | ✅ | ⚠ (solo exportar al portapapeles) | T1: exportar CSV a «Descargas» |
| Modo sin conexión | ✅ (PWA) | ⚠ (caché de lectura) | T3: cola de cambios pendientes |
| Gráficos e informes | ✅ | ⚠ (estadísticas básicas) | T2: gráfico de costos por categoría |
| 2FA y dispositivos conectados | ✅ | ✅ | — |
| Búsqueda global | ✅ | ⚠ (por pantalla) | T1: buscador único |

Leyenda: ✅ completo · ⚠ parcial · ❌ pendiente.

---

## 6. Hoja de ruta

### T1 · Consolidar lo que ya existe (próximas 6 semanas)

**Web**
- Buscador único que abarque productos, valores, fichas y controles desde cualquier vista.
- Exportar a CSV respetando los filtros activos (hoy exporta todo).
- Recordar por usuario la última vista, los filtros y el orden.
- Impresión de una ficha en una página (hoja de costo lista para firmar).

**Móvil**
- Buscador único equivalente.
- Exportar CSV a la carpeta *Descargas* (además del portapapeles).
- Pantalla de detalle de ficha con los componentes en tabla numerada y su total.
- Aviso visible cuando se trabaja con datos en caché (sin conexión).

**Transversal**
- `-Check` ampliado con prueba de escritura en la carpeta de copias de seguridad.
- Guía rápida de 1 página para el usuario final (PDF imprimible).

### T2 · Información para decidir

**Web**
- Informe mensual: costo por categoría, variación de precios y productos sin ficha vigente.
- Comparador de versiones de ficha (v1 vs v2, línea a línea).
- Alertas configurables de bajo mínimo por categoría.

**Móvil**
- Gráfico de costos por categoría (nativo, sin librerías).
- Vista de solo lectura de auditoría y usuarios para administradores.
- Historial de licencias emitidas (consulta al Creador de Licencias).

**Transversal**
- API `v1` documentada al 100 % en `docs/openapi.yaml` y verificada por prueba automática.

### T3 · Trabajo sin conexión y calidad de vida

**Web**
- Cola de cambios sin conexión con sincronización al volver la red.
- Deshacer/rehacer ampliado a fichas y controles.

**Móvil**
- Cola de cambios pendientes con reintento y resolución de conflictos.
- Escanear con la cámara el **QR de la licencia** para activarla sin teclear.
- Widget de inicio con el valor del inventario y los ítems bajo mínimo.

**Transversal**
- Firma del APK y canal de actualización interno (verificación por SHA-256).

### T4 · Escala y profesionalización

- Multi-almacén / multi-sucursal (inventarios separados que consolidan).
- Roles finos por módulo (quién ve costos, quién aprueba fichas).
- Panel de administración del servidor desde la web (estado, backups, certificado, licencias).
- Exportación contable (formato acordado con el cliente).

---

## 7. Seguridad continua

| Control | Frecuencia | Responsable | Evidencia |
|---|---|---|---|
| `-Check` completo | Mensual | Administrador | Captura o salida guardada |
| Revisión de usuarios, roles y sesiones activas | Mensual | Administrador | Web → Usuarios |
| Revisión de la cadena de auditoría (HMAC) | Mensual | Administrador | Web → Auditoría → Verificar |
| Rotación de la contraseña del administrador | Trimestral | Administrador | Política `IPV_PASSWORD_MAX_AGE_DAYS=90` |
| Prueba de restauración de copia | Trimestral | Administrador | Base restaurada en carpeta temporal |
| Escaneo ZAP completo | Semestral | Desarrollo | Informe en CI |
| Revisión de la clave de firma de licencias | Semestral | Proveedor | `keygen/clave_privada.json` respaldada |
| Renovación de la CA y certificados | Anual (o `-Renew`) | Administrador | CA reinstalada en los clientes |

**Respuesta ante incidentes (resumen de 5 pasos):**
1. Detener el servidor (`-Stop`) y aislar el equipo de la red.
2. Conservar `data\ipv.db`, `.env` y la auditoría (copia en frío, sin sobrescribir).
3. Revocar sesiones y rotar `IPV_JWT_SECRET` y contraseñas.
4. Restaurar la última copia verificada y comparar con la auditoría.
5. Anotar causa, impacto y corrección en las notas de la versión siguiente.

---

## 8. Versiones y publicación

- **Versionado semántico** `MAYOR.MENOR.PARCHE` (hoy `1.1.0`).
  - *Parche*: correcciones sin cambios visibles de flujo.
  - *Menor*: funciones nuevas compatibles.
  - *Mayor*: cambios que obligan a migrar datos o a recompilar el APK.
- Puntos que **siempre** se tocan juntos al publicar:
  - `APP_VERSION` en `web/app.js` y la versión mostrada en «Acerca de».
  - `CACHE` de `web/sw.js` (subir el número → los clientes reciben la versión nueva).
  - `versionName` / `versionCode` del APK.
  - `version` de `docs/openapi.yaml`.
  - Notas de versión en `README.md`.

### Checklist de publicación — Web
```
[ ] CI en verde (pruebas, ruff, bandit, ZAP)
[ ] APP_VERSION y caché del Service Worker actualizadas
[ ] Probado en Chrome/Edge y en móvil (PWA instalada)
[ ] Atajos de teclado y accesibilidad sin regresiones
[ ] Formato de dinero «$ 3,163,138.00 CUP» intacto
[ ] Copia de seguridad hecha antes de actualizar el servidor
```

### Checklist de publicación — Android
```
[ ] Compila en release y arranca en un dispositivo real
[ ] Licencia: pantalla inicial, activación y renovación funcionan
[ ] Huella del certificado (pinning) sigue validando
[ ] Listados numerados y contadores correctos
[ ] Sin conexión: la app avisa y no pierde datos
[ ] versionCode incrementado y APK firmado
[ ] SHA-256 del APK publicado junto al archivo
```

---

## 9. Cómo pedir una mejora (para el usuario)

1. **Describa el caso real**: «cuando cierro el mes necesito…». No hace falta proponer la solución técnica.
2. **Indique dónde**: web, móvil o ambas; y en qué pantalla.
3. **Diga qué duele hoy**: cuántos minutos cuesta, con qué frecuencia y qué riesgo tiene equivocarse.

Cada petición se clasifica así:

| Prioridad | Criterio | Respuesta |
|---|---|---|
| 🔴 Crítica | Impide trabajar, pierde datos o afecta a la seguridad | Se atiende en el día |
| 🟠 Alta | Bloquea una tarea diaria; hay rodeo incómodo | Ciclo en curso |
| 🟡 Media | Ahorra tiempo o evita errores | Siguiente ciclo |
| 🟢 Baja | Comodidad o estética | Cuando toque el área |

---

## 10. Plantillas

**Propuesta de mejora**
```
Título:
Aplicación:     [ ] Web   [ ] Móvil   [ ] Ambas
Problema actual:
Cómo se hace hoy (pasos):
Cómo debería ser:
Beneficio (tiempo/errores/dinero):
Prioridad sugerida: 🔴 🟠 🟡 🟢
```

**Nota de versión**
```
## v1.2.0 — 2026-XX-XX
### Nuevo
- …
### Mejorado
- …
### Corregido
- …
### Seguridad
- …
### Para actualizar
- Web: recargue con Ctrl+F5 (caché ipv-fichas-costos-vN).
- Móvil: instale el APK vN (SHA-256: …).
```

**Cierre de trimestre**
```
Métricas (punto 4):      pruebas ___  cobertura ___  paridad ___/11
Objetivos cumplidos:     ___ de ___
Deuda técnica pendiente: …
Incidentes de seguridad: …
Ajustes al plan:         …
```

---

## 11. Documentos relacionados

- [README.md](../README.md) — panorama general, instalación y API.
- [acceso-seguro-https.md](acceso-seguro-https.md) — pasos completos de acceso cifrado.
- [precios-y-licencias.md](precios-y-licencias.md) — planes, precios y Creador de Licencias.
- [openapi.yaml](openapi.yaml) — contrato de la API.
