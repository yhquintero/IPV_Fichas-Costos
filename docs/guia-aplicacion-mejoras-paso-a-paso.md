# Guía de aplicación de mejoras, una por una

**IPV · Fichas y Costos**  
**Objetivo:** convertir el estudio estratégico en cambios pequeños, comprobables y ordenados.  
**Regla:** no iniciar el paso siguiente hasta cerrar la prueba de aceptación del actual, documentar resultados y decidir si se continúa.

## Cómo trabajar cada mejora

Para cada paso:

1. Crear una copia de seguridad y trabajar en una rama de desarrollo/entorno de prueba.
2. Escribir el problema y la señal que confirmará que quedó resuelto.
3. Cambiar una sola cosa por vez; mantener compatibilidad y no modificar datos de clientes reales.
4. Ejecutar las pruebas indicadas y probar manualmente el flujo.
5. Revisar el diff, errores, seguridad y documentación.
6. Registrar fecha, versión, resultado, responsable y cualquier deuda pendiente.
7. Si falla una prueba o se pierden datos, detenerse y revertir antes de avanzar.

No publicar directamente en producción. Primero validar en una copia aislada de los datos y con el procedimiento de actualización correspondiente.

---

## Paso 1 — Copia de seguridad coherente y comprobable

**Estado:** implementación, pruebas automáticas y simulacro cronometrado con base sintética completados en modo normal y SQLCipher. El simulacro es reproducible con `scripts/simulacro_recuperacion.py`; no usa ni modifica la base real y desactiva réplicas externas.  
**Límite pendiente:** repetir con una base de prueba representativa y bajo el procedimiento operativo del entorno de despliegue para obtener RTO/RPO útiles para ese entorno. Las cifras de la base pequeña no son un SLA.

### Acciones

1. Instalar el motor SQLCipher en el entorno de prueba siguiendo `README.md` (`sqlcipher3-wheels` en Windows o `sqlcipher3-binary` en Linux).
2. Usar una copia no productiva de la base y una clave temporal fuerte. Nunca probar rekey/cifrado por primera vez sobre la única copia de datos reales.
3. Ejecutar el conjunto normal y el conjunto con `IPV_DB_KEY` activo; el job de CI ya contempla esta segunda modalidad.
4. Iniciar el servidor de prueba y comprobar que crea un archivo en `data/backups/`.
5. Restaurar la copia en una ubicación vacía, conectarla con la herramienta compatible y comprobar `PRAGMA integrity_check` = `ok`, tablas y registros de muestra.
6. Medir tiempo de recuperación y antigüedad de los datos recuperados. Registrar RTO/RPO observados; no prometerlos todavía como SLA.
7. Repetir con destino de réplica disponible y destino inaccesible; verificar que el backup local sigue disponible y que el fallo queda registrado.

### Aceptación

- CI normal y CI cifrado terminan en verde; ninguna prueba SQLCipher aparece omitida en el job cifrado.
- La copia se puede abrir con la clave correcta y no se abre como texto claro.
- Integridad y conteos de registros de muestra coinciden con la fuente.
- Restauración y falla de réplica quedan documentadas, con tiempo medido.

**Comandos de repetición:**

```bash
python scripts/simulacro_recuperacion.py
IPV_DB_KEY='clave-temporal-larga-solo-para-pruebas' python scripts/simulacro_recuperacion.py
python -m unittest discover -s tests
```

El modo cifrado necesita SQLCipher instalado. En PowerShell use `$env:IPV_DB_KEY = '...'` en una terminal de prueba y elimine la variable al terminar. Use una clave sintética; jamás publique claves reales en terminales compartidas, logs o archivos versionados. El simulacro crea su base dentro de una carpeta temporal, comprueba recuperación e integridad y elimina todo al acabar.

**Resultado del simulacro local sintético (2026-09-29):** base de 196 608 bytes; se recuperó la transacción anterior al backup y se perdió, como se esperaba, una transacción confirmada después del backup antes de simular la incidencia.

| Modalidad | RPO sintético observado | RTO sintético observado | Resultado |
|---|---:|---:|---|
| SQLite sin cifrar | 0,001268 s | 0,001253 s | OK; `integrity_check=ok` |
| SQLCipher | 0,001719 s | 0,002784 s | OK; `integrity_check=ok` |

> Son medidas del runner y de una base mínima; no estiman producción ni garantizan tiempos con volúmenes reales, discos remotos o hardware diferente.

---

## Paso 2 — Descubrimiento con usuarios antes de decidir funciones

**Responsable:** propietario/producto. Requiere acceso a usuarios reales; no se puede reemplazar con una decisión del código.

### Acciones

1. Elegir entre 8 y 12 personas del perfil que se quiere atender; incluir clientes actuales y personas que hoy usan hojas de cálculo u otra herramienta.
2. Entrevistar sobre el proceso actual, sin presentar primero una lista de funciones: cómo calculan costos, registran inventario, corrigen errores, comparten resultados y qué les cuesta más.
3. Observar, con permiso, a cinco personas haciendo una tarea real. No guiarlas salvo que queden bloqueadas.
4. Registrar tareas, tiempo, errores, solución alternativa, frecuencia e impacto. Anonimizar datos del negocio.
5. Formular una hipótesis de segmento y tres casos de uso prioritarios.
6. Validarla con al menos tres posibles organizaciones piloto y revisar quién decide y quién paga.

### Entregable y aceptación

Una página con perfil de usuario, problema frecuente, alternativa actual, evidencia/citas anonimizadas, tres trabajos prioritarios y dudas abiertas. No se toma como validación que alguien diga solamente «me gusta».

---

## Paso 3 — Medir y mejorar el primer uso (onboarding)

### Acciones

1. Definir el momento de «primer valor»: por ejemplo, una ficha creada correctamente cuyo costo el usuario entiende.
2. Preparar datos ficticios para no exponer información sensible en sesiones de prueba.
3. Pedir a cinco usuarios nuevos que instalen/abran la app y completen ese flujo sin instrucciones verbales.
4. Cronometrar; anotar errores, abandonos, preguntas y pasos repetidos.
5. Corregir solo los tres bloqueos más frecuentes: importación, conceptos poco claros, validación o mensajes de error.
6. Repetir la prueba con otras cinco personas y comparar tiempo y tasa de éxito.

### Aceptación

El usuario termina el flujo sin asistencia, comprende el resultado y puede recuperarse de errores previsibles. Registrar baseline y resultado; no fijar meta numérica antes de conocer la línea base.

---

## Paso 4 — Hacer seguras las publicaciones y actualizaciones

### Acciones

1. Confirmar en GitHub que todas las puertas necesarias estén requeridas antes de integrar cambios: tests, análisis, seguridad, cifrado, Docker y Android.
2. Revisar cobertura para rutas de alto riesgo (autenticación, permisos, costos, escritura, backup y licencias); priorizar huecos por impacto, no solo perseguir un porcentaje total.
3. Crear una copia de una base de cada versión soportada; probar actualización hacia la versión nueva y conservar una ruta de rollback.
4. Compilar una release Android de prueba con firma de test segura y verificar actualización desde versión previa; no usar la llave de producción en CI público.
5. Publicar checklist, número de versión, cambios incompatibles, respaldo previo y procedimiento de reversión.

### Aceptación

No se integra/publica si tests o escaneo requerido falla; instalación limpia y actualización desde la versión anterior pasan; rollback verificado sobre datos ficticios.

---

## Paso 5 — Validar tareas principales en web y Android

### Acciones

1. Usando evidencia del Paso 2, escoger los tres flujos más frecuentes; no asumir que tienen que ser los mismos en ambas plataformas.
2. Para cada flujo, documentar pasos, permisos necesarios, estados vacíos, error de red y resultado correcto.
3. Probar teclado, tamaño de texto, lector de pantalla, contraste, toque y pantallas pequeñas.
4. Probar Android en al menos dos dispositivos reales; incluir memoria limitada y red intermitente.
5. Comparar datos/resultados entre web y Android para el mismo usuario y permisos.
6. Corregir una fricción cada vez y repetir pruebas.

### Aceptación

Los participantes completan los tres flujos sin pérdida de datos; restricciones de permiso coinciden entre interfaz y API; defectos conocidos quedan registrados por plataforma.

---

## Paso 6 — Establecer límites de rendimiento conocidos

### Acciones

1. Construir un dataset ficticio representativo y guardar cómo se generó.
2. Elegir hardware/red de referencia y las rutas más importantes.
3. Medir carga inicial, p50/p95 de API, errores, uso de memoria y concurrencia de escritura; repetir tres veces.
4. Anotar resultados por versión y tamaño de datos. No mezclar hardware o condiciones distintas.
5. Identificar el cuello de botella más importante y optimizarlo sin cambiar arquitectura primero.
6. Repetir el benchmark y confirmar que no se dañó la exactitud de cálculos ni permisos.

### Aceptación

Existe un benchmark repetible y una descripción explícita de usuarios/datos/despliegue soportados. Las cifras publicadas tienen fecha, método y entorno.

---

### Benchmark sintético de referencia (2026-09-29)

Se ejecutó `python scripts/benchmark_api.py --rows 500 --iterations 20` sobre loopback, Linux x86_64, Python 3.11.2, 2 CPU lógicas, código de trabajo basado en `bd3454d` (árbol con cambios locales). La base y usuario fueron temporales; los 500 productos eran sintéticos. Tiempos en ms:

| Ruta | SQLite p50 / p95 | SQLCipher p50 / p95 | Respuesta |
|---|---:|---:|---:|
| `GET /api/health` | 1,268 / 1,556 | 1,523 / 1,905 | 140 bytes |
| `GET /api/products` | 6,393 / 7,352 | 11,783 / 13,616 | 195 963 bytes |
| `GET /api/dashboard` | 3,061 / 3,415 | 3,954 / 4,623 | 2 529 bytes |

Estos números son una **línea base de laboratorio**, no un objetivo ni una garantía de capacidad. Limitaciones: loopback elimina latencia de red real; dataset solo tiene 500 productos y no incluye fichas/inventario representativos; las medidas se ejecutaron en runner compartido y con 20 iteraciones. Para comparar versiones, ejecutar tres veces, guardar la salida JSON y mantener fijo el equipo, datos y configuración.

**Repetición:**

```bash
python scripts/benchmark_api.py --rows 500 --iterations 20
IPV_DB_KEY='clave-temporal-larga-solo-para-pruebas' python scripts/benchmark_api.py --rows 500 --iterations 20
```

El benchmark cifra si `IPV_DB_KEY` está configurada al arrancar el proceso y se dispone de SQLCipher. El usuario, base y servidor se crean en memoria temporal/local y se limpian al terminar.

## Paso 7 — Ejecutar pilotos y validar soporte/precio

### Acciones

1. Invitar de tres a cinco organizaciones que representen el segmento elegido; acordar alcance, duración, privacidad y expectativas.
2. Acompañar instalación/importación inicial y registrar horas de soporte.
3. Revisar cada semana tareas completadas, problemas, frecuencia de uso y datos perdidos (esperado: ninguno).
4. Preguntar por decisión de renovación y disposición real a pagar; medir costos de venta, instalación y soporte.
5. Cerrar piloto con decisión explícita: convertir, iterar o detener. Documentar motivos, no solo testimonios positivos.

### Aceptación

Cada piloto tiene resultado, costo de atenderlo y decisión documentados. La renovación o pago, no las licencias emitidas sin uso, es evidencia comercial.

---

## Paso 8 — Decidir si construir multi-sucursal u offline editable

**No empezar antes de los pasos 2, 5 y 7.**

1. Comprobar que varios usuarios/organizaciones identificaron esa necesidad de forma recurrente.
2. Para multi-sucursal, definir identidad de organización, aislamiento, roles, consolidación y auditoría.
3. Para offline editable, definir conflictos, orden de cambios, duplicados, borrado, caducidad de credenciales y cifrado local.
4. Escribir pruebas de amenaza y recuperación antes de implementar sincronización.
5. Estimar costo de desarrollo, soporte y migración; comparar con la alternativa de mejorar conexión/importación.
6. Implementar un prototipo acotado y probar con datos ficticios antes de ampliar.

### Aceptación

Demanda demostrada, modelo de datos y amenazas revisados, resolución de conflictos probada y soporte operativo definido.

---

## Registro de avance

| Paso | Estado | Evidencia / enlace | Fecha | Decisión siguiente |
|---|---|---|---|---|
| 1. Backups y restauración | Cerrado para base sintética; pendiente medición con dataset representativo/entorno operativo | Suite 105/105 normal y cifrada; simulacro y cifras arriba | 2026-09-29 | Repetir con tamaño realista antes de fijar objetivos operativos |
| 2. Descubrimiento | Protocolo listo; entrevistas no realizadas | `docs/validacion-producto-y-piloto.md`; hipótesis explícitamente provisionales | 2026-09-29 | Propietario debe reclutar y entrevistar personas del segmento |
| 3. Onboarding | Mejora heurística implementada; pruebas con personas y dispositivo Android pendientes | Checklist web con siguiente acción y estructura semántica (`node --check` OK); Android con progreso, CTA a la sección sugerida y distinción entre lista vacía y ausencia de cambios recientes (`web/app.js`, `web/styles.css`, `MainActivity.kt`). Sin Java/Gradle local para compilar Android. | 2026-09-29 | Ejecutar CI Android y validar el orden/comprensión en sesiones moderadas |
| 4. Releases seguras | CI ampliado; verificación local incompleta | `pip-audit` añadido y CI compila debug/release y conserva APK de validación | 2026-09-29 | Revisar CI en GitHub, proteger rama y confirmar firma/upgrade Android |
| 5. Flujos web/Android | Contraste base y estados de desconexión implementados parcialmente; pruebas manuales/paridad real pendientes | Tokens con contraste base >=4,5:1, etiquetas Android, `tests/test_accessibility_tokens.py` (3 pruebas); aviso de conexión y datos cacheados en ambas (`web/app.js`, `MainActivity.kt`) | 2026-09-29 | Probar cortes/red lenta; seguir con teclado/lector/dispositivos físicos |
| 6. Rendimiento | Línea base sintética ejecutada; representatividad pendiente | `scripts/benchmark_api.py`; resultados arriba | 2026-09-29 | Repetir con dataset de fichas/inventario y equipo de referencia |
| 7. Pilotos y precio | Protocolo listo; pilotos no realizados | Plantilla de 4 semanas en `docs/validacion-producto-y-piloto.md` | 2026-09-29 | Seleccionar organizaciones y documentar acuerdos |
| 8. Escala/offline | Decisión provisional de aplazar | `docs/decision-sin-multisucursal-offline.md` | 2026-09-29 | Reabrir al contar con evidencia de pilotos |

> Tras cerrar cada paso, actualizar el registro y elegir solo el siguiente. Si no hay evidencia suficiente, el estado correcto es «pendiente», no «completado».

## Solicitud posterior registrada — Generador de licencias por período

Al cerrar las mejoras priorizadas de ambas aplicaciones, ampliar y probar el Creador de Licencias para que permita emitir por 1 semana, 1 mes, 3 meses, 6 meses, 1 año, 2 años y por fechas «desde–hasta». La revisión del código confirma que los planes fijos ya existen (`1S`, `1M`, `3M`, `6M`, `1A`, `2A`); queda pendiente implementar el rango personalizado de fechas, reflejarlo en la interfaz/API/CLI donde corresponda y probar firma, activación, vencimiento, límites de fechas y compatibilidad. Esta solicitud queda en cola para después de las mejoras de producto indicadas, no se considera terminada por los planes fijos existentes.
