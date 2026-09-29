# Decisión técnica provisional: posponer multi-sucursal y edición sin conexión

**Fecha:** 2026-09-29 · **Estado:** aceptada provisionalmente · **Revisión:** tras primeros pilotos o nueva evidencia verificable.

## Contexto

La guía estratégica contempla multi-sucursal y sincronización offline editable. No se aportaron entrevistas, pilotos ni incidentes que prueben que sean hoy bloqueos prioritarios. El producto tiene API/SQLite local, permisos por módulo, auditoría y caché PWA; la app Android mantiene almacenamiento/caché propios. Convertir una instalación local en multi-organización o sincronizar escrituras entre dispositivos cambia el modelo de seguridad y datos, no es una función aislada.

## Decisión

**No implementar todavía sincronización editable ni multi-sucursal en producción.** Primero completar entrevistas y pilotos, medir incidentes de conectividad y confirmar qué despliegue/aislamiento requiere el segmento. Se puede probar un prototipo aislado con datos sintéticos cuando exista una hipótesis concreta.

## Por qué

- No hay evidencia de frecuencia/impacto que permita ordenar estas funciones frente a onboarding, exportación, confiabilidad y soporte.
- Offline editable necesita resolver conflictos concurrentes, borrados/restauraciones, cambios de permisos mientras el dispositivo está desconectado, expiración/revocación de credenciales y reintentos idempotentes.
- Multi-sucursal requiere pertenencia a organización/sucursal en todas las tablas y rutas, límites de aislamiento en consultas, consolidación, auditoría y migración de datos existentes.
- Un error de aislamiento o sincronización puede divulgar costos, duplicar movimientos o perder cambios; el riesgo excede una iteración de interfaz.

## Supuestos de diseño para una futura evaluación

1. La instalación conserva un `organization_id` único aun antes de multi-tenant, si una futura migración puede hacerse con bajo riesgo. No crear ese cambio de esquema ahora sin validar impacto.
2. Los movimientos de inventario y aprobaciones no se fusionan silenciosamente: se conservan autor, hora, versión base y un estado de conflicto revisable.
3. Una respuesta del servidor prevalece solo tras verificación de permisos vigentes; no se guarda en cola una acción ya revocada como válida.
4. Los clientes sin conexión deben mostrar claramente edad de los datos y cambios pendientes.
5. Cada operación sincronizada tendrá identificador idempotente, orden explícito, reintento con límite y bitácora de resolución.
6. La primera prueba debe limitarse a un tipo de dato no crítico, un dispositivo por usuario y datos ficticios; excluir eliminación y aprobación hasta validar el modelo.

## Condiciones para reabrir decisión

- Varias organizaciones independientes reportan un caso reciente repetido que bloquea activación/retención.
- Se define si el producto será instalación local, alojamiento gestionado o ambos.
- Hay diseño de aislamiento, matriz de amenazas, política de conflicto y recuperación revisados.
- Existe prueba que simula desconexión, cambios concurrentes, permiso revocado, repetición de solicitudes y restauración.
- Costo de soporte/operación y criterio de salida del piloto son aceptables.

## Consecuencias

Se evita añadir complejidad y riesgo prematuros. Como contrapartida, IPV no se presenta todavía como multi-sucursal ni promete edición offline. Las características actuales de lectura/caché deben describirse con precisión. Este documento registra una decisión por falta de evidencia; no constituye validación de mercado.
