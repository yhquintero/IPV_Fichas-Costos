# Validación de producto, onboarding y piloto (provisional)

**Estado:** protocolo preparado; aún no hay entrevistas ni pilotos realizados. Las hipótesis siguientes son supuestos de trabajo, no hallazgos de usuarios.

## Hipótesis iniciales a comprobar

- **Usuario principal provisional:** persona que registra insumos/valores del IPV y mantiene fichas de costo; puede ser responsable de almacén, cocina/producción o administración.
- **Problema provisional:** la información de productos, cantidades, precios y controles puede estar dispersa; actualizar un costo exige localizar datos y volver a hacer cálculos.
- **Valor que se quiere comprobar:** completar una ficha consistente y detectar qué cambió sin rehacer cálculos manuales.
- **Flujo de primer valor:** crear producto → registrar valor/insumo y precio → crear ficha con rendimiento/cantidades → revisar total → consultar inventario o exportar.
- **Alternativas que se deben preguntar, no presumir:** cuaderno, hoja de cálculo, sistema existente, cálculo manual u otra combinación.

## Entrevista de descubrimiento — 30 minutos

No enseñar una demo antes de conocer el proceso actual. Preguntar por un ejemplo reciente y permitir que la persona muestre datos anonimizados si lo autoriza.

1. Cuénteme la última vez que calculó o actualizó el costo de un producto. ¿Qué inició la tarea?
2. ¿Qué pasos hizo, en qué orden y con qué herramientas/personas?
3. ¿Qué datos tuvo que buscar? ¿Dónde estaban y cuál fue difícil de conseguir?
4. ¿Qué error o diferencia recuerda de la última semana/mes? ¿Qué impacto tuvo?
5. ¿Con qué frecuencia hace este trabajo y cuánto tarda normalmente?
6. ¿Qué ocurre cuando cambia el precio de un insumo o el rendimiento de una receta/lote?
7. ¿Cómo revisa, aprueba, comparte o conserva el cálculo?
8. ¿Qué hace sin conexión o desde el teléfono? ¿Qué necesita imprimir/exportar?
9. ¿Qué solución intentó antes y por qué la mantuvo o abandonó?
10. Si pudiera eliminar una parte del proceso, ¿cuál elegiría? ¿Qué evidencia le haría confiar en el resultado?
11. ¿Quién usa, aprueba y paga por una herramienta así? ¿Qué condiciones impedirían adoptarla?
12. ¿Aceptaría participar en una prueba controlada y cuánto tiempo podría dedicar?

**Registrar:** rol/contexto anonimizados, frecuencia, duración aproximada, pasos, errores, impacto, alternativas, citas textuales anonimizadas, consentimiento y dudas. Evitar datos personales, precios confidenciales o datos de clientes en las notas.

### Matriz de síntesis

| Observación | Frecuencia en entrevistas | Impacto | Evidencia concreta | Confianza | Oportunidad / experimento |
|---|---:|---|---|---|---|
|  |  |  |  | Baja / media / alta |  |

Una hipótesis gana prioridad si aparece en contextos independientes y la persona puede describir un caso reciente; una opinión positiva sobre una demo no cuenta como prueba de demanda.

## Prueba de usabilidad del primer valor — 20 minutos

### Preparación

- Usar una instalación/dataset ficticio restaurable; nunca proyectar datos reales sin permiso.
- Probar por separado web escritorio, web móvil/PWA y Android.
- Dar a cada participante la misma consigna, sin explicar dónde están los botones.
- Contar éxito solo si la persona completa y puede explicar el resultado.

### Consigna neutral

> «Registra este producto y estos insumos con los datos de ejemplo, crea una ficha para el rendimiento indicado, comprueba el costo y dime qué harías si cambia el precio de uno de los insumos».

### Datos ficticios

- Producto: `PRUEBA-001`, nombre «Producto de práctica», categoría «Prueba», rendimiento 4 unidades.
- Insumo: `INS-001`, nombre «Ingrediente de práctica», unidad «kg», precio 12,50 CUP, cantidad de prueba 0,5 kg.
- Aclarar que las cifras son didácticas y no representan valores comerciales.

### Hoja de observación

| Métrica | Resultado |
|---|---|
| Plataforma / versión / dispositivo |  |
| Tiempo hasta primera ficha entendida |  |
| Terminó sin ayuda (sí/no) |  |
| Errores / retrocesos / campos confusos |  |
| ¿Entendió qué incluye el costo? |  |
| ¿Encontró precio/rendimiento y pudo explicar su impacto? |  |
| Bloqueo principal y frase textual anonimizada |  |
| Severidad (bloquea / dificulta / menor) |  |

Hacer cinco sesiones iniciales, corregir primero los tres bloqueos repetidos o de alto impacto y repetir con cinco personas nuevas. Hasta realizar las sesiones, no asignar una tasa de éxito como resultado real.

## Revisión heurística provisional aplicada al flujo

Una limitación observable por inspección del código: en la web la acción «crear ficha» puede aparecer aunque falten productos o valores; el formulario informa del prerrequisito después del intento. Se añadió un checklist de primeros pasos cuando no hay fichas, que indica el siguiente requisito pendiente y respeta permisos de lectura/edición; en web se usa una sección con encabezado y lista semánticos. Android ahora muestra progreso básico según productos/valores reportados por el resumen, añade accesos a la sección sugerida y distingue «sin fichas» de «sin fichas recientes».

**No equivale a una prueba de usabilidad ni se ha compilado/validado en un dispositivo Android en este entorno.** Revisar con participantes si el orden «producto → valor → ficha» coincide con su trabajo, si los permisos dejan una salida clara y si el mensaje resuelve la duda sin asistencia.

## Piloto controlado — plantilla de 4 semanas

### Antes de invitar

- Confirmar que la organización pertenece al segmento elegido y tiene una tarea real repetida.
- Acordar por escrito alcance, responsables, duración, datos permitidos, exportación/borrado al cierre y canal de soporte.
- No cargar datos reales hasta completar respaldo, acceso/roles, instalación y consentimiento aplicables.
- Definir qué tareas se evaluarán y la línea base actual (tiempo/errores/proceso alternativo).

### Semana 0 — instalación y preparación

- Administrador, dispositivo, versión y configuración registrados.
- Backup inicial y restauración de prueba verificados.
- Usuarios/roles mínimos y capacitación breve documentados.
- Dataset inicial importado/validado; comprobar una ficha contra cálculo independiente.

### Semanas 1–3 — uso acompañado

Revisión semanal de tareas completadas, errores, caídas, tickets, tiempo de soporte, datos faltantes y motivos de abandono. Registrar sin recopilar información personal innecesaria.

### Semana 4 — decisión

Entrevistar usuario y responsable económico por separado. Decidir **convertir**, **iterar** o **detener**. Anotar disposición real a pagar/renovar, costo de instalación y soporte, riesgos y qué valor se obtuvo frente a la alternativa previa.

| Organización (seudónimo) | Tareas/semana | Activación | Retención/uso | Incidentes | Horas de soporte | Pago/renovación | Decisión/motivo |
|---|---:|---|---|---|---:|---|---|
|  |  |  |  |  |  |  |  |

## Revisión de accesibilidad y paridad

**Mejora estática aplicada (parcial):** se oscurecieron los tokens de texto secundario de la web en temas claro/oscuro y el texto MUTED de Android; se añadieron nombres accesibles a los botones de icono de Estadísticas, Acerca de y Configuración. `tests/test_accessibility_tokens.py` comprueba contraste WCAG AA (4,5:1) de esos tokens sobre superficies base. Esta comprobación automatizada no cubre todos los componentes, estados, colores de acento ni el renderizado real, por lo que no es una auditoría WCAG completa.

Por cada flujo elegido, anotar plataforma, versión, dispositivo, hallazgo y severidad.

- [ ] Completar con teclado, sin perder foco; foco visible y orden lógico.
- [ ] Probar lector de pantalla en navegación, formularios, errores y diálogos.
- [ ] Comprobar nombre accesible de botones solo con icono y controles dinámicos.
- [ ] Aumentar texto/zoom; confirmar que no se cortan acciones o importes.
- [ ] Revisar contraste y no depender solo del color para estados/errores.
- [ ] Probar viewport pequeño y orientación horizontal en móvil.
- [ ] Desconectar/red lenta durante lectura y envío; verificar mensaje y recuperación.
- [ ] Comparar cálculo, permisos y datos entre web y Android.
- [ ] En Android, probar al menos un dispositivo de gama baja y otro reciente.

## Estados de red y datos desactualizados (mejora técnica aplicada parcialmente)

- **Web:** el navegador avisa al perder/recuperar conectividad; al reconectar vuelve a consultar el servidor. Si falla el API, muestra reintento y aclara que la web no conserva una copia local de los datos. El evento `online` solo indica que hay red, no que IPV esté disponible.
- **Android:** si usa datos GET cifrados de la caché, conserva la antigüedad máxima de las respuestas utilizadas y muestra una advertencia de posible desactualización y de que las modificaciones necesitan confirmación del servidor.
- **Límite:** estas modificaciones se revisaron estáticamente; no se han probado cortes reales de red ni la recuperación en dispositivos. No hay cola de escrituras offline ni promesa de edición sin conexión.

### Prueba manual pendiente

| Plataforma | Preparación | Verificar | Criterio de aceptación |
|---|---|---|---|
| Web | Abrir con servidor accesible; después cortar red o detener el servidor | Estado de conexión, mensaje de error, botón de reintento y actualización al recuperar la red | No afirma que cambios estén guardados; solo muestra conexión restablecida tras responder el servidor |
| Android | Cargar datos con conexión, cortar red y forzar actualización; repetir con una ruta sin caché | Antigüedad máxima mostrada, aviso de caché, comportamiento de rutas sin respaldo y fallos de escritura | Etiqueta los datos cacheados como posiblemente obsoletos y no reporta cambios exitosos sin confirmación |

## Registro y decisión

| Sesión/piloto | Hipótesis | Evidencia | Resultado | Cambio propuesto | Estado |
|---|---|---|---|---|---|
|  |  |  |  |  | Pendiente |

**Aviso:** no hay evidencia de usuarios reales registrada en este documento; las secciones de resultados deben completarse solo después de las sesiones, sin rellenar valores supuestos como si fueran observaciones.
