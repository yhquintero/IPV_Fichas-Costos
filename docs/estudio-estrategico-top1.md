# Estudio estratégico y técnico para llevar IPV a la primera categoría

**IPV · Fichas y Costos — evaluación del repositorio**  
**Fecha:** 29 de septiembre de 2026 · **Alcance:** servidor/API, web/PWA, Android, seguridad, calidad y estrategia de producto.

> **Conclusión ejecutiva.** IPV parte de una base funcional y técnicamente ambiciosa: gestión de productos, valores e inventario, fichas, controles, usuarios/permisos, auditoría, licencias y aplicación Android; incorpora además automatización de pruebas, CI y opciones de despliegue seguro. La oportunidad principal ya no es acumular funciones: es convertir esa amplitud en una experiencia sencilla, confiable, medible y respaldada por usuarios reales. Este estudio propone una secuencia verificable. «Top 1» no se puede prometer ni medir sin definir categoría, mercado, geografía, competidores y período; se puede, en cambio, construir una trayectoria para competir por liderazgo.

## Avance de aplicación — primera mejora técnica

Como primer paso del P0 de resiliencia, el helper activo `enterprise.sqlite_backup()` crea la copia mediante la API de SQLite/SQLCipher (no copia el archivo principal de forma potencialmente inconsistente con WAL), valida `PRAGMA integrity_check` y publica el archivo final solo tras validar. Se añadieron unicidad temporal, limpieza de copias parciales y una prueba de integración que reabre la copia, verifica un dato testigo y la réplica.

**Validación posterior:** la suite completa pasó con 105 pruebas tanto en modo normal como con `IPV_DB_KEY` y SQLCipher instalado; el caso verifica copia cifrada/restaurable. Además, se ejecutó `scripts/simulacro_recuperacion.py` en ambos modos sobre una base temporal sintética; comprobó integridad y transacción recuperada, e informó RPO/RTO de milisegundos para ese dataset mínimo. Las mediciones y sus límites están en `docs/guia-aplicacion-mejoras-paso-a-paso.md`; no son un SLA y falta repetir con volumen representativo.

## 1. Resumen de hallazgos

| Dimensión | Lectura actual basada en el repositorio | Prioridad |
|---|---|---|
| Propuesta de valor | La cadena producto → ficha → costo → inventario → control responde a una tarea de negocio concreta. | Alta: explicar el beneficio en lenguaje del cliente y medir el tiempo/errores ahorrados. |
| Cobertura funcional | Amplia en web; Android comparte flujos importantes, con brechas documentadas en paridad, exportación, administración y trabajo sin conexión. | Alta: cerrar los flujos cotidianos antes de sumar módulos complejos. |
| Calidad automatizada | En la revisión inicial faltaba SQLCipher; en la validación posterior se ejecutaron 105 pruebas satisfactoriamente tanto normal como con SQLCipher + `IPV_DB_KEY`. CI contempla Python 3.10–3.12, cobertura, Bandit, ZAP, Docker y compilación Android. | Alta: probar también UX real, migraciones, dispositivos, recuperación y publicación release. |
| Seguridad | Se observan controles relevantes: autenticación, MFA, permisos en servidor, TLS, auditoría, rate limiting, backups y cifrado opcional. | Crítica: verificar configuración real, recuperación de secretos, límites operativos y pruebas independientes. El código y la suite no equivalen a una certificación. |
| Rendimiento y escala | El servidor usa `http.server`/SQLite y la SPA incluye archivos grandes (aprox. 401 KB en `web/`, 135 KB en `app.js`; Android Kotlin fuente aprox. 113 KB). Se añadió benchmark sintético reproducible; falta dataset representativo y carga/concurrencia realista. | Alta: ampliar la medición antes de optimizar; definir límites de usuarios, volumen, concurrencia y despliegue soportado. |
| Diseño/experiencia | Aplicación funcional de una sola página con CSS/JS propios y Android nativo. No se encontró evidencia de pruebas de usabilidad, accesibilidad automatizada ni analítica de producto en este estudio. | Crítica: observar usuarios y arreglar fricciones, no decidir por intuición. |
| Comercialización | Hay documentación de precios/licencias y distribución por licencia. El repositorio no demuestra conversión, retención, satisfacción, costos de soporte ni ajuste producto-mercado. | Crítica: entrevistas, pilotos, onboarding y economía unitaria antes de escalar ventas. |

## 2. Lo que ya es una ventaja

1. **Problema vertical reconocible:** relacionar insumos, rendimientos, fichas, costos e inventario ofrece más valor que una hoja aislada cuando el flujo está bien integrado.
2. **Dominio de datos sensibles:** permisos por módulo y por costos, auditoría, sesiones, MFA, licenciamiento y copias indican una intención empresarial valiosa.
3. **Bajo costo operativo potencial:** Python estándar, SQLite y frontend sin framework reducen complejidad de instalación y dependencias. Esa sencillez es ventaja en entornos con conectividad o recursos limitados, siempre que se expliciten sus límites.
4. **Cobertura del ciclo operativo:** web, PWA y Android permiten explorar diferentes contextos de trabajo.
5. **Base de calidad reproducible:** hay tests, workflow CI, especificación OpenAPI y documentación de mejora continua. Los 105 tests verdes son evidencia de regresión funcional, no de aceptación de mercado ni de ausencia de vulnerabilidades.

## 3. Riesgos y brechas estratégicas

### Producto y diferenciación
- «Fichas y Costos» debe posicionarse frente a alternativas concretas (hojas de cálculo, sistemas de inventario/ERP y herramientas verticales). Aún falta documentar segmentos objetivo y el motivo por el que migrarían.
- El alcance puede volverse disperso. Multi-sucursal, widgets, offline con sincronización y paneles deben competir con mejoras de incorporación, claridad, confiabilidad y exportación.
- La promesa de paridad total web/móvil puede elevar demasiado el costo. Es preferible declarar una matriz de capacidades por plataforma y mantener completos los flujos esenciales.

### Fiabilidad, seguridad y operación
- La suite cifrada y el simulacro cronometrado sintético quedaron verificados localmente; falta repetir recuperación con dataset representativo, documentar procedimiento de operador y confirmar el gate obligatorio en GitHub.
- Backups replicados no bastan: se midió RPO/RTO en un simulacro sintético, pero falta repetir con volumen realista y guías operativas probadas por una persona distinta al desarrollador.
- El servicio basado en servidor estándar de Python y SQLite puede ser apropiado para una instalación local o equipos acotados. Antes de venderlo como multiempresa/alta concurrencia hay que medir contención de escrituras, operación, aislamiento de clientes, actualización y soporte. No asumir que crecerá horizontalmente sin cambios.
- Debe definirse ciclo de vida de claves: generación, custodia, rotación, recuperación y consecuencias de pérdida; especialmente clave de base de datos, JWT y firma de licencias.
- Las declaraciones del README/plan (por ejemplo, metas de cobertura y tiempos) deben marcarse como **medidas** solo cuando hay método, fecha, dispositivo y resultado adjunto. En la validación posterior pasaron Ruff, Bandit, pip-audit y tests normal/cifrados; ZAP y compilación Android/release no se ejecutaron localmente.

### Experiencia y adopción
- Una interfaz rica en funciones puede intimidar a usuarios nuevos. Medir cuánto toma completar tareas comunes y cuántas requieren ayuda.
- Es necesario probar teclado, lector de pantalla, contraste, escalado de texto, formularios en móvil y recuperación ante error/red intermitente.
- Android necesita validación sobre dispositivos físicos y distribución firmada. La compilación debug del CI no acredita una release lista para usuarios.
- No incorporar telemetría invasiva por defecto. Si se instrumenta uso, obtener consentimiento, minimizar datos y documentar retención y finalidad.

## 4. Priorización recomendada

Puntuación cualitativa: impacto en cliente, reducción de riesgo, costo y dependencia. Ejecutar máximo 3 iniciativas simultáneas; confirmar cada una con clientes.

| Prioridad | Iniciativa | Resultado/medida de aceptación | Orden |
|---|---|---|---|
| P0 | Descubrimiento con usuarios y definición de segmento | 8–12 entrevistas con personas que preparan costos/inventario; síntesis de tareas, alternativas, presupuesto y fricciones. Acordar un segmento inicial y 3 casos de uso. | Inmediato |
| P0 | Onboarding de punta a punta | Usuario nuevo crea/importa datos, completa primera ficha y entiende su costo sin asistencia; medir tiempo y tasa de éxito en 5 sesiones moderadas. | Inmediato |
| P0 | Resiliencia de datos | Prueba automatizada y documentada de backup → restauración, también con SQLCipher; registrar RPO/RTO real y alerta de backup fallido. | Inmediato |
| P0 | Observabilidad de calidad | CI obligatorio; umbrales definidos para cobertura crítica, seguridad, migraciones y Android release; publicación con artefactos/versiones y rollback. | Inmediato |
| P1 | Flujos principales web y Android | Búsqueda, ficha, exportación útil y detalle legible; comprobar consistencia y accesibilidad con usuarios y dispositivos reales. | Después de P0 |
| P1 | Rendimiento y límites | Dataset representativo; medir p50/p95 de API, carga inicial, memoria, SQLite con concurrencia y sincronización. Publicar límites soportados. | Después de línea base |
| P1 | Confianza comercial | Pilotos de 3–5 organizaciones, canal de soporte, guía de importación, acuerdo de tratamiento de datos y mecanismo de feedback. | Paralelo a P0 |
| P2 | Analítica avanzada / multi-sucursal / offline editable | Solo después de demostrar demanda y definir resolución de conflictos, seguridad, respaldo y soporte. | Evidencia primero |

## 5. Hoja de ruta de 12 meses

### Fase A — Evidencia y reducción de riesgo (semanas 1–6)
- Elegir un perfil objetivo (por ejemplo, negocio con elaboración de productos y control de insumos; validar el segmento antes de fijarlo).
- Entrevistas y pruebas de tareas; registrar baseline de onboarding, errores, soporte y tiempo de operación.
- Probar el flujo de instalación desde una máquina limpia; ejecutar cifrado, backup y restauración desde cero.
- Definir modelo de amenaza, datos tratados, responsabilidades del operador, límites de despliegue y matriz de soporte.
- Resolver primero fallos de severidad alta y fricciones de primeros pasos.

### Fase B — Producto confiable y fácil de adoptar (semanas 7–16)
- Simplificar alta inicial e importación, validación previa y mensajes de error recuperables.
- Completar los 3 flujos más frecuentes en web/móvil; priorizar búsqueda y exportación CSV filtrada si los pilotos confirman su utilidad.
- Aplicar pruebas de accesibilidad y pruebas Android en dispositivos de gama baja/media, pantallas distintas y conectividad débil.
- Definir esquema de migraciones y compatibilidad de versiones. Añadir smoke tests de instalación/actualización.
- Publicar guía rápida, ayuda contextual y procedimiento de soporte/recuperación.

### Fase C — Pilotos y ajuste producto-mercado (meses 5–8)
- Pilotos controlados, acuerdos claros y revisión periódica; medir activación, uso recurrente, renovación, tickets y motivos de abandono.
- Priorizar por impacto observado y frecuencia, no por volumen de solicitudes de una sola cuenta.
- Establecer release Android firmado, distribución, actualización, notas, rollback y canal para incidencias.
- Validar precio con disposición real a pagar, costos de implementación/soporte y margen; no confundir emisión de licencias con demanda sostenible.

### Fase D — Escala deliberada (meses 9–12)
- Decidir, con datos, si se mantiene la instalación local o se ofrece alojamiento gestionado. Para servicio multiempresa se requiere aislamiento comprobable, operación, monitoreo, gestión de incidentes, privacidad y disponibilidad.
- Desarrollar multi-sucursal, offline editable o integraciones solo si aparecen entre los principales bloqueos de adopción y retención.
- Evaluación externa de seguridad previa a expansión de clientes o exposición pública.
- Revisar posicionamiento y comparación competitiva en el segmento y región elegidos; adaptar producto y soporte.

## 6. Cuadro de mando: definir antes de perseguir

No se asignan cifras objetivo sin baseline y segmento. Durante el primer mes registrar valor actual, método, propietario y cohorte; después acordar metas trimestrales.

| Indicador | Definición recomendada | Por qué importa |
|---|---|---|
| Activación | % de cuentas que completan la primera ficha correcta dentro de 1 día/7 días desde instalación. | Valor inicial percibido. |
| Tiempo a valor | Mediana de minutos desde inicio hasta primera ficha/costo confiable. | Fricción de onboarding. |
| Éxito de tarea | % de participantes que completan sin ayuda: importar, editar ficha, consultar costos, exportar. | Calidad de UX. |
| Retención | Cuentas activas por cohorte a 4/8/12 semanas; definir «activa» con una tarea de negocio, no solo login. | Valor recurrente. |
| Fiabilidad | Disponibilidad del servicio (donde aplique), errores 5xx, fallos de sincronización y pérdida/corrupción de datos. | Confianza. |
| Rendimiento | p50/p95 de rutas críticas y carga inicial en hardware/red definidos. | Sensación de rapidez y límites claros. |
| Seguridad operativa | Restauraciones exitosas/intentadas, tiempo de recuperación, incidencias y cierre de hallazgos. | Capacidad real de recuperación. |
| Soporte | Tickets por organización, tiempo a primera respuesta/resolución y causas repetidas. | Costo de servicio y fricción. |
| Negocio | Conversión de piloto a pago, renovación, cancelación y margen después de soporte. | Sostenibilidad. |
| Recomendación | Entrevista/NPS opcional con contexto; no usar una puntuación aislada como sustituto de retención. | Confianza y referencias. |

**Reglas de medición:** instrumentación mínima, consentimiento y protección de datos; distinguir cuentas de usuarios; anotar versión, plataforma, tamaño de muestra y período; no promediar cohortes incompatibles; complementar métricas cuantitativas con entrevistas.

## 7. Recomendaciones técnicas concretas

1. **CI como puerta de lanzamiento:** conservar pruebas actuales; volver obligatoria la suite cifrada, validar que no se omita silenciosamente en release y publicar informe de cobertura por módulos críticos. Ejecutar análisis estático y escaneo con política de severidad/baseline explícita.
2. **Pruebas de extremo a extremo:** automatizar pocos flujos de máximo valor (crear producto → ficha → aprobar → control; permiso sin costos; exportación; actualización/restauración). Agregar pruebas browser/móvil en un pipeline separado si los recursos lo permiten.
3. **Migraciones:** llevar cambios de esquema a migraciones versionadas y probar upgrades desde bases antiguas con fixtures; copia previa y recuperación ante fallo.
4. **Seguridad:** revisar controles con checklist OWASP ASVS apropiado al riesgo; revisión de dependencias/herramientas de build Android, secretos, cabeceras y permisos; evaluación externa antes de exposición pública. Mantener secretos fuera del repositorio y ensayar rotación.
5. **Rendimiento:** crear dataset sintético realista y benchmarks repetibles. No reescribir ni adoptar una base de datos nueva hasta medir cuello de botella y perfil objetivo.
6. **Frontend:** dividir `app.js` en módulos con límites claros cuando reduzca riesgo de cambio; mantener compatibilidad offline y CSP estricta. Medir tamaño transferido/comprimido y carga en móvil.
7. **API:** usar OpenAPI como contrato ejecutable: validar ejemplos, códigos de error, permisos y paginación; detectar divergencias de contrato en CI.
8. **Android:** separar configuración de debug/release, firmar con custodia adecuada, probar upgrade de datos, accesibilidad, consumo/batería, pérdida de red y manejo seguro de credenciales.
9. **Operación:** health/readiness, logs estructurados sin datos sensibles, identificador de incidente, guía de actualización/rollback y checklist de respuesta. Definir soporte por modalidad de instalación.
10. **Datos y privacidad:** inventario de datos, finalidad/retención, exportación y borrado, consentimiento y política de incidentes; confirmar obligaciones legales en cada país donde se ofrezca.

## 8. Decisiones que el propietario debe tomar

- ¿Qué categoría y mercado significan «Top 1» (país, sector, tipo de empresa, web, Android, adopción, ventas o satisfacción)?
- ¿Quién es el usuario prioritario y cuál es la alternativa actual que más le duele?
- ¿La primera oferta será instalable local, servicio alojado o ambas? ¿Quién administra backups, actualizaciones y soporte?
- ¿Qué evidencia define éxito del piloto y qué precio/margen hacen viable atenderlo?
- ¿Qué nivel de disponibilidad, pérdida tolerable de datos y tiempo de recuperación se promete?

## 9. Veredicto

**Madurez observable:** prototipo/solución funcional avanzada con fundamentos de seguridad y automatización por encima de un prototipo típico; todavía sin evidencia aportada aquí de producto-mercado, operación a escala, accesibilidad/usabilidad medida ni resultados comerciales. La brecha para liderar está menos en «tener más pantallas» y más en probar que el público objetivo obtiene valor rápido, vuelve, confía sus datos y recomienda/paga.

**La siguiente mejor acción:** no comenzar por multi-sucursal ni por más analítica. Ejecutar una ronda breve de entrevistas y pruebas de onboarding, cerrar restauración cifrada de punta a punta y elegir tres bloqueos de pilotos. Revisar el cuadro de mando al cabo de seis semanas y reordenar la hoja de ruta según evidencia.

---

## Apéndice A — Evidencia y límites de esta revisión

- Lectura del código, documentación y CI del repositorio `yhquintero/IPV_Fichas-Costos`, en la rama de trabajo de Arena, el 29-09-2026.
- Ejecución inicial de `python -m unittest discover -s tests`: **105 ejecutadas, OK, 3 omitidas** por ausencia de SQLCipher (aprox. 20,6 s). Validación posterior: **105/105 OK** en modo normal y **105/105 OK** con `IPV_DB_KEY` y SQLCipher instalado; prueba de backup revisa integridad, restauración de dato testigo y réplica.
- Tamaño fuente medido: archivos web aprox. **401 KB** y fuente Kotlin aprox. **113 KB**; esto no es tamaño de descarga/minificado ni rendimiento percibido.
- CI actualizado: añade `pip-audit`, compilación Android debug/release sin firma y retención breve de APKs de validación. La compilación release debe confirmarse en GitHub CI; esta máquina no tiene Java/Gradle disponible.
- En la revisión inicial no se ejecutaron ZAP, Bandit, Ruff, build Android, benchmarks, revisión manual en dispositivos o pruebas con clientes. Después pasaron localmente Ruff, Bandit, pip-audit, tests normal/cifrados, simulacro de backup y benchmark sintético. No se ejecutaron ZAP ni build Android en este entorno y no se accedió a producción, analítica, ventas, incidencias ni información de organizaciones.
- Esta es una revisión técnica/estratégica orientativa, no auditoría de seguridad certificada, asesoría legal, valoración financiera ni garantía de ranking.
