# IPV · Fichas y Costos

Sistema para la gestión de costos en red local: catálogo de productos y servicios, valores de referencia del IPV, Fichas de Costo versionadas y Controles de IPV con trazabilidad completa. Incluye un cliente web adaptable y una aplicación Android nativa (Kotlin); ambos consumen la misma API JSON y comparten los datos maestros almacenados en un archivo SQLite en el servidor.

| | |
|---|---|
| **Versión** | 2.0.0 |
| **Publicación** | 2026-09-27 |
| **Autor** | Ing. Yosvany Hernández Quintero — diseño, desarrollo e implementación |
| **Servidor** | Python 3.10+ (solo biblioteca estándar) |
| **Clientes** | Navegador web y aplicación Android (Kotlin) |
| **Datos** | SQLite con registro de escritura anticipada (WAL) en `data/ipv.db` |

## Alcance funcional

- **Productos y servicios:** catálogo único con código irrepetible, categoría, unidad de salida, descripción y control de vigencia.
- **Valores del IPV:** insumos, materias primas, mano de obra y servicios con precio, moneda, unidad, proveedor, documento de respaldo, vigencia y estado operativo (Vigente, Por vencer, Vencido, Suspendido, Descontinuado).
- **Fichas de costo:** elaboración por versiones, cálculo automático del total, bloqueo al aprobar, reapertura controlada y recálculo de precios desde el catálogo conservando el valor aplicado en cada componente.
- **Controles de IPV:** instantánea del período, informe de validación (cuadre de importes, conciliación con la ficha aprobada, vigencia de los valores y variaciones de precios), acta imprimible y estados Pendiente, Validado y Con diferencias.
- **Bitácora de auditoría:** cada operación se registra con acción, entidad, responsable y fecha; los registros no se modifican desde la interfaz.
- **Respaldos:** exportación completa en JSON, copia de seguridad automática antes de cada restauración y verificación de integridad de la base de datos.

## Requisitos

- **Windows** con PowerShell 5.1 o superior para el inicio por HTTPS (el servidor también funciona en Linux/macOS con Python).
- **Python 3.10 o superior** en la computadora servidor.
- **Navegador moderno** (Chrome, Edge, Firefox o Safari) para el cliente web.
- **Node 18+** solo para ejecutar las pruebas del cliente web.
- **JDK 17, Android SDK Platform 35 y Gradle 8.9** solo para compilar la aplicación Android.

## Inicio por HTTPS en una red local (Windows)

1. Desde PowerShell, en la raíz del proyecto, ejecuta:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\iniciar-https.ps1
   ```

   Si hace falta, el script solicita permisos de administrador **solo** para los cambios de `hosts` y firewall; el servidor Python se ejecuta con los permisos normales del usuario.

2. El script crea una autoridad certificadora local, emite el certificado del servidor con los nombres e IP de la PC, confía la CA en el perfil de Windows, abre el puerto TCP 8443 solo para la subred local y perfiles privados/de dominio, y arranca el servicio HTTPS.

3. En la computadora del servidor abre **`https://sqlserver:8443`**.

4. El script imprime además las direcciones IPv4 detectadas. Desde otro equipo puedes abrir **`https://IP_DE_LA_COMPUTADORA:8443`**.

```
Servidor HTTPS listo en la red local.
En esta PC:       https://sqlserver:8443
También:          https://localhost:8443
Desde la red:     https://192.168.x.x:8443
```

El certificado raíz público que debe instalarse en otros dispositivos está en `certs/ipv-local-root-ca.cer`; instálalo como **CA/raíz de confianza** antes de navegar o conectar la aplicación Android. El archivo `certs/ipv-server-key.pem` es la clave privada del servidor: **no se copia ni se comparte**.

### El nombre `sqlserver` en otras PC o móviles

El script agrega el alias `sqlserver` al archivo `hosts` de la PC servidor. Para usar exactamente `https://sqlserver:8443` desde otros equipos, la red debe resolver ese nombre hacia la IP local del servidor: configura un registro DNS en el router o servidor DNS, o una entrada `hosts` en cada cliente. Si no puedes configurar DNS, usa la IP que imprime el script; el certificado incluye todas las IP locales detectadas.

Los clientes deben estar en la misma LAN o tener una ruta hacia el servidor. El firewall se limita a la subred local y a los perfiles privados/de dominio; si Windows marca la red confiable como *Pública*, cámbiala a *Privada* antes de probar. **No** configures reenvío de puerto desde Internet ni lo uses en una Wi-Fi pública.

## Ejecución de desarrollo sin HTTPS

Para desarrollo local únicamente:

```bash
python server.py
```

El servicio queda en `http://localhost:8000`. Opciones disponibles:

```bash
python server.py --host 0.0.0.0 --port 8443 \
  --db data/ipv.db --cert certs/ipv-server-cert.pem --key certs/ipv-server-key.pem \
  --operator "Nombre del operador" --log-level INFO

python server.py --check --db /tmp/ipv-check.db   # verifica configuración, base de datos y certificado sin iniciar
```

El servidor crea automáticamente `data/ipv.db` y carga un conjunto de datos de ejemplo la primera vez que se ejecuta. El archivo se conserva entre reinicios y está excluido de Git. Para usar otra ubicación define la variable de entorno `IPV_DB_PATH`.

## Cliente web

Aplicación de una sola página escrita en HTML, CSS y JavaScript con módulos nativos, **sin dependencias externas ni recursos de Internet** (cumple una política de seguridad de contenido restrictiva).

| Ruta | Vista |
|---|---|
| `/resumen` | Tablero de control: indicadores, gráficos, alertas y actividad reciente |
| `/productos` | Catálogo de productos y servicios |
| `/valores` | Valores de referencia del IPV |
| `/fichas` · `/fichas/:id` | Fichas de costo y detalle de la composición del costo |
| `/controles` · `/controles/:id` | Controles de IPV e informe de validación |
| `/bitacora` | Bitácora de auditoría con filtros y exportación CSV |
| `/sistema` | Diagnóstico, respaldos, restauración y preferencias |
| `/acerca-de` | Propósito, alcance, ficha técnica y autoría |

**Atajos de teclado**

- `Ctrl`/`Cmd` + `K`: búsqueda global de productos, valores, fichas y controles.
- `G` y luego `R`, `P`, `V`, `F`, `C`, `B`, `S`, `A`: navegación directa a Resumen, Productos, Valores, Fichas, Controles, Bitácora, Sistema y Acerca de.
- `R`: actualizar los datos; `T`: alternar tema claro/oscuro; `Esc`: cerrar diálogos y paneles.

**Otras prestaciones:** tema claro y oscuro automático, densidad de tabla configurable, tamaño de página, operador registrado en la bitácora, documentos de ficha y acta de control listos para imprimir, exportación CSV/JSON y restauración guiada con confirmación textual.

Para volver al conjunto inicial de ejemplo basta con restaurar un respaldo desde **Sistema** o con retirar `data/ipv.db` (el servidor lo regenera en el siguiente arranque; la copia retirada puede conservarse como archivo histórico).

## Aplicación Android

1. Abre la carpeta `android/` en Android Studio (JDK 17, Android SDK Platform 35, Gradle 8.9).
2. Ejecuta `iniciar-https.ps1` en la computadora que aloja el servidor.
3. **Emulador:** la aplicación usa por defecto `https://10.0.2.2:8443`. Instala `certs/ipv-local-root-ca.cer` en el emulador como certificado de CA de usuario.
4. **Teléfono físico:** instala en el teléfono `ipv-local-root-ca.cer` y cambia la dirección desde **⚙ Conexión con la base SQLite** a `https://IP_DE_LA_COMPUTADORA:8443` (o `https://sqlserver:8443` si la red resuelve el alias).

Algunas versiones de Android solicitan el PIN del dispositivo para instalar una CA. La aplicación confía en los certificados de usuario instalados y mantiene deshabilitado el tráfico HTTP sin cifrar.

## API JSON

El servidor expone una API REST con respuestas JSON en UTF-8. La cabecera opcional `X-IPV-Operator` registra el responsable de cada operación en la bitácora.

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/health` · `/api/meta` | Estado del servicio y metadatos de la aplicación |
| GET | `/api/dashboard` | Indicadores, alertas y actividad reciente |
| GET/POST | `/api/products` | Listado y registro de productos y servicios |
| GET/PUT/PATCH/DELETE | `/api/products/{id}` | Detalle, actualización, activación y desactivación lógica |
| GET/POST | `/api/materials` | Listado y registro de valores del IPV |
| PUT | `/api/materials/{id}` | Actualización de un valor del IPV |
| GET/POST | `/api/fichas` | Listado y creación de fichas de costo |
| GET/PUT | `/api/fichas/{id}` | Detalle y edición de borradores |
| POST | `/api/fichas/{id}/approve` · `/reopen` · `/duplicate` · `/refresh-prices` | Aprobar, reabrir, versionar y recalcular precios |
| GET/POST | `/api/controls` | Listado y generación de controles de IPV |
| GET/PATCH | `/api/controls/{id}` | Detalle y actualización de un control |
| POST | `/api/controls/{id}/validate` | Ejecutar el informe de validación |
| GET | `/api/audit` · `/api/search` | Bitácora de auditoría y búsqueda global |
| GET | `/api/backup` · POST `/api/restore` | Respaldo completo y restauración verificada |
| GET | `/api/routes` | Catálogo de rutas disponibles |

## Pruebas

Flujo completo de negocio (producto → valor → ficha → aprobación → control validado):

```bash
python -m unittest discover -s tests -v
```

Cliente web (levanta el servidor real sobre una base temporal, carga la interfaz en un DOM simulado y verifica las ocho vistas, el enrutado, la búsqueda global, la paleta de comandos, los documentos imprimibles y el cambio de tema):

```bash
cd tests/web
npm install
npm test
```

La prueba del cliente web requiere Node 18 o superior y `python3` disponibles en el `PATH` (puedes indicar otro intérprete con la variable `PYTHON`).

## Datos, respaldos y seguridad

- La base de datos vive en `data/ipv.db` (excluida de Git). Los respaldos manuales se guardan en `data/backups/`.
- Antes de cada restauración el servidor genera una copia de seguridad y exige la confirmación explícita `REEMPLAZAR`.
- El servicio no incorpora autenticación de usuarios: está pensado para una red local confiable y perfiles privados. Publicarlo en Internet queda fuera del alcance de esta versión.
- El conjunto de datos de ejemplo (productos, valores, recetas y controles de septiembre de 2026) es ficticio y sirve para conocer el flujo de trabajo; no debe usarse para decisiones comerciales o administrativas.

---

**IPV · Fichas y Costos** — Ing. Yosvany Hernández Quintero · diseño, desarrollo e implementación.
