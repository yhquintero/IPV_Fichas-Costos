# IPV · Fichas y Costos v1.1

**Sistema profesional de gestión de Fichas de Costo y Controles de IPV**

Autor: **Ing. Yosvany Hernández Quintero**

---

## 🎯 Características Principales

### 🎨 Interfaz Web
- **Ajuste a la ventana**: la barra lateral ya no duplica el ancho; la aplicación cabe al 100 % sin reducir el zoom
- **Valores del IPV: una sola entrada con dos pestañas** (`3` Valores · `4` Inventario), gobernada por el Sistema de Seguridad por Usuarios
  - **Valores**: CRUD completo (crear, ver, editar, eliminar) desde cualquier apartado, con categorías, existencias y precio
  - **Inventario**: existencias, mínimo, valor en almacén y recetas que usa cada insumo; se ve cuántos comensales o copas se pueden preparar
- **Rendimiento de fichas**: cada plato indica comensales (o copas/vasos) y el costo por unidad; el inventario calcula cuántas raciones salen
- **Papelera de reciclaje** en todos los módulos: restaurar o borrar definitivamente
- **Columna «Id»** al principio de cada tabla y lista (1, 2, 3 …) con el contador de ítems en la barra de herramientas: se sabe al instante cuántos productos, valores, fichas o controles hay
- **Licencia**: pantalla propia (la primera que se ve si la licencia no está activada o venció) con ID del equipo, planes, solicitud por WhatsApp y activación/renovación
- **Creador de Licencias** (web, administradores): crea la clave de firma, activa las licencias al instante y emite, verifica y registra licencias para PC y móvil
- **Datos de prueba**: catálogo amplio de comidas, licores, bebidas e inventario para aprender
- **La app Android replica la web** y comparte la misma base de datos SQLite del servidor
- **Diseño moderno** con glassmorphism, neumorphism y efectos 3D
- **Modo oscuro/claro** con transiciones suaves
- **Animaciones avanzadas**: confetti, parallax, morphing shapes, ripple effects
- **Gráficos interactivos**: barras, donuts, líneas de tiempo
- **Búsqueda global** con API dedicada y debounce
- **Atajos de teclado** completos (Ctrl+K, F5, 6-9, ?, s) — las teclas `1`-`5` y cualquier otra tecla suelta quedan libres para escribir en los campos
- **PWA ready** con manifest.json
- **Responsive design** optimizado para móvil
- **Skeleton loading** para mejor UX
- **Auto-refresh** configurable
- **Deshacer / Rehacer** desactivaciones de productos y valores del IPV (toast con botón, `Ctrl+Z` / `Ctrl+Shift+Z`)
- **Filtros guardados** por vista (búsqueda + selectores), reutilizables con un clic
- **Tablas fluidas**: carga progresiva de 100 en 100 filas a partir de 150 registros y navegación por teclado
- **Dashboard personalizable**: reordenar arrastrando y ocultar tarjetas (se guarda por navegador)
- **Tour interactivo** de bienvenida (repetible desde la paleta de comandos)
- **Accesibilidad WCAG 2.1 AA**: enlace “saltar al contenido”, diálogos con `role="dialog"` y foco atrapado, alto contraste, reducción de movimiento y escala de texto (`Alt+Shift+A` o botón ♿)
- **Código QR** para activar la verificación en dos pasos (generado localmente, sin servicios externos)

### 📱 App Android
- **Material Design 3** con colores vibrantes
- **Listas numeradas** igual que la web: cada tarjeta lleva su Id delante y la lista muestra «▤ 33 ítems»
- **Gradientes animados** y efectos visuales
- **Estadísticas avanzadas** con gráficos nativos
- **Haptic feedback** en interacciones
- **Acciones rápidas** con FAB
- **Exportación de datos** al portapapeles
- **Pantalla Acerca de** profesional

### 🔒 Seguridad Enterprise
- **JWT HS256** (librería estándar) con roles **admin / editor / viewer**, rotación y revocación de refresh tokens
- **Sistema de Seguridad por Usuarios**: permisos finos por módulo (`view` / `edit` / `costs`) que el administrador ajusta persona a persona en Web → Usuarios → 🔐 Permisos. Rigen la entrada **Valores del IPV** (pestañas Valores e Inventario) y el resto de apartados: sin `view` la ruta responde **403** y la entrada desaparece del menú; sin `costs` los precios e importes **no se descargan** (viajan como `null` y se ven como 🔒). Se comprueban en cada petición, así que un cambio surte efecto al instante sin cerrar sesiones. Los administradores conservan siempre todos los permisos
- **Contraseñas PBKDF2-SHA256** (310 000 iteraciones) y política de complejidad
- **Bloqueo de cuenta** 15 min tras 5 intentos fallidos
- **Verificación en dos pasos (TOTP, RFC 6238)** con 8 códigos de recuperación de un solo uso y protección anti-reutilización; obligatoria para administradores con `IPV_REQUIRE_ADMIN_MFA=1`
- **Revocación inmediata de sesiones** al desactivar un usuario, cambiar su rol o su contraseña
- **Gestión de usuarios** (admin): roles, activar/desactivar, desbloquear, restablecer 2FA, cerrar sesiones
- **Auditoría a prueba de manipulación**: cada evento se sella con HMAC-SHA256 encadenado; verificación desde la web
- **Lista de redes permitidas** (`IPV_IP_ALLOWLIST`) y `X-Forwarded-For` aceptado solo desde proxies de confianza
- **Base de datos cifrada en reposo** (opcional): SQLCipher AES-256 con `IPV_DB_KEY`; los backups quedan cifrados con la misma clave. El servidor se niega a arrancar si hay clave pero la BD está en claro o la clave es incorrecta
- **Dispositivos conectados**: cada inicio de sesión es una sesión propia (navegador, sistema, IP, última actividad) que el usuario puede cerrar individualmente o todas a la vez
- **Alertas de acceso desde IP nueva**: se auditan (`LOGIN_NEW_IP`), se avisa al usuario en pantalla y por correo (y a `IPV_NOTIFY_EMAIL`)
- **Caducidad de contraseñas** (`IPV_PASSWORD_MAX_AGE_DAYS`), aviso 7 días antes, **historial** que impide reutilizar las últimas 5 y **cambio obligatorio** en el primer acceso o cuando lo exige el administrador
- **Alertas de intentos fallidos**: al entrar, el usuario ve cuántos intentos fallidos hubo contra su cuenta y desde qué IP; el administrador recibe un correo a partir de `IPV_FAILED_LOGIN_ALERT` fallos seguidos
- **Detección de *password spraying***: una IP que falla contra muchas cuentas distintas en 15 min se audita (`SUSPICIOUS_IP`) y se notifica
- **CSP estricta** sin scripts ni estilos en línea y **fuentes alojadas en el propio servidor** (sin peticiones a terceros)
- **Copias fuera del equipo (3-2-1)**: cada backup se replica a carpetas espejo (USB / red) y/o a un almacenamiento S3 (firma SigV4, solo https), verificando el SHA-256
- **Licencias por período** firmadas con ECDSA P-256, atadas al equipo (PC) o al teléfono, con Keygen y solicitud por WhatsApp
- **OWASP ZAP en CI**: escaneo dinámico de la web y de la API autenticada en cada push (`.zap/rules.tsv`)
- **Rate limiting granular**: login 5/min, exportaciones 10/5 min, masivas 10/min, escritura 60/min, lectura 300/min, con cabeceras `X-RateLimit-*`
- **Auditoría persistente** en SQLite (usuario, IP, acción, detalle) con visor web para administradores
- **Cabeceras**: CSP, HSTS, COOP, CORP, X-Frame-Options, nosniff, Referrer-Policy, Permissions-Policy
- **TLS 1.2+** (o **1.3 exclusivo**) con cifrados ECDHE/AES-GCM/ChaCha20, sin compresión ni renegociación y con las curvas modernas seleccionadas por el servidor
- **Redirección HTTP → HTTPS** opcional (308) para que nadie entre por error en claro, y **modo estricto** (`IPV_REQUIRE_TLS=1`) que impide arrancar sin certificado válido
- **Vigilancia del certificado**: aviso al arrancar y en `/api/health` (`tls_expires_at`, `tls_days_left`) cuando faltan menos de 30 días, con reemisión automática desde `iniciar-https.ps1`
- **Diagnóstico `-Check`**: comprueba requisitos, CA instalada, handshake TLS real, HSTS, `.env`, cifrado de la BD y copias de seguridad
- **Android**: sesión cifrada con AES-256-GCM en Android Keystore, **fijación de certificado** (huella de la CA, verificada en el handshake TLS), login con 2FA, cambio obligatorio de contraseña caducada, lista de dispositivos con cierre remoto de sesiones, avisos de IP nueva e intentos fallidos, bloqueo biométrico, `FLAG_SECURE`, sin copias en la nube

### ⚙️ Backend
- API REST con **versionado** (`/api/v1/...` ≡ `/api/...`) y **OpenAPI 3** en `/api/openapi.yaml`
- **Tiempo real** mediante Server-Sent Events (`/api/events`)
- **Backups consistentes** (API de backup de SQLite) al iniciar y cada `IPV_BACKUP_INTERVAL_HOURS`
- **Borrado lógico** de productos y valores de referencia
- **Notificaciones por correo** al aprobar fichas y validar controles (SMTP opcional)
- Estadísticas, reportes, operaciones masivas y búsqueda global
- **Sin dependencias externas** en producción: solo Python estándar + SQLite

---

## 📚 Documentación

| Guía | Para qué |
|---|---|
| [Acceso seguro por HTTPS](docs/acceso-seguro-https.md) | **Todos los pasos desde el principio**: CA, certificado, primer inicio, otro equipo de la red, móvil Android, uso diario y solución de problemas |
| [Plan de mejora continua](docs/plan-mejora-continua.md) | Cómo evolucionan la web y el móvil: ciclo de trabajo, criterios de calidad, métricas, hoja de ruta y cómo pedir una mejora |
| [Estudio estratégico para competir por el liderazgo](docs/estudio-estrategico-top1.md) | Diagnóstico técnico y de producto, riesgos, prioridades, hoja de ruta de 12 meses y cuadro de mando |
| [Guía paso a paso para aplicar mejoras](docs/guia-aplicacion-mejoras-paso-a-paso.md) | Secuencia ejecutable, criterios de aceptación y registro para avanzar una mejora por vez |
| [Validación de producto y piloto](docs/validacion-producto-y-piloto.md) | Hipótesis provisionales, entrevistas, usabilidad, accesibilidad y protocolo de piloto sin inventar resultados |
| [Decisión sobre multi-sucursal y modo offline](docs/decision-sin-multisucursal-offline.md) | Riesgos, supuestos y condiciones para diseñar esas funciones con seguridad |
| [Precios y licencias](docs/precios-y-licencias.md) | Planes, precios y uso del Creador de Licencias |
| [OpenAPI](docs/openapi.yaml) | Contrato de la API REST |

---

## 🚀 Instalación y Uso

### Requisitos
- Windows 10/11
- Python 3.8+
- PowerShell 5.1+
- Android Studio (para app móvil)

### Inicio Rápido

```powershell
# 1. Clonar el repositorio
git clone <repo-url>
cd IPV_Fichas-Costos

# 2. Preparar la seguridad (una sola vez): .env, secreto JWT y administrador
.\iniciar-https.ps1 -InitSecurity

# 3. Iniciar el servidor HTTPS (crea la CA y el certificado si faltan)
.\iniciar-https.ps1 -Open

# 4. Abrir en navegador
# https://sqlserver:8443
```

> 📘 **¿Primera vez?** La guía [docs/acceso-seguro-https.md](docs/acceso-seguro-https.md) explica **todos los pasos desde cero**: instalar la CA, entrar desde la propia PC, desde otro equipo de la red y desde el móvil Android, cifrar la base de datos y resolver los errores más comunes.

El servidor **no inicia** sin `IPV_JWT_SECRET` de al menos 32 bytes ni un administrador activo. La contraseña inicial debe cumplir la política de contraseñas fuertes. Configure `IPV_ADMIN_EMAIL` y `IPV_ADMIN_PASSWORD` para crearlo en la primera ejecución; en instalaciones existentes basta con un administrador activo. El modo abierto solo existe en pruebas que instancian `Handler` sin iniciar el servidor.

### Acceso seguro (HTTPS)

```powershell
.\iniciar-https.ps1 -Check             # diagnóstico completo del acceso seguro
.\iniciar-https.ps1 -Port 8443         # cambiar el puerto HTTPS
.\iniciar-https.ps1 -RedirectPort 8080 # redirigir http://…:8080 → https://…:8443 (308)
.\iniciar-https.ps1 -NoRedirect        # no levantar el redirector HTTP
.\iniciar-https.ps1 -Tls13Only         # exigir TLS 1.3 (clientes modernos)
.\iniciar-https.ps1 -Renew             # reemitir la CA y el certificado
.\iniciar-https.ps1 -ExportCa D:\CA    # copiar la CA para instalarla en otros equipos
.\iniciar-https.ps1 -Help              # ayuda con todos los comandos
```

- El certificado se **reemite solo** cuando hace falta: si caduca en menos de 30 días, si cambian las IP del equipo o si lo emitió otra CA.
- `-Check` verifica requisitos, certificados, red, **handshake TLS real**, `/api/health`, HSTS, `.env`, cifrado de la BD y copias de seguridad, y resume los problemas y avisos encontrados.

### Cifrar la base de datos (SQLCipher, AES-256)

```powershell
# Con el servidor detenido:
.\iniciar-https.ps1 -EncryptDb   # instala sqlcipher3-wheels si falta, genera IPV_DB_KEY en .env y cifra data\ipv.db
.\iniciar-https.ps1 -Status      # debe mostrar «🔒 Base de datos cifrada»
```

- Se conserva una copia en claro `data\ipv.db.plain-<fecha>.bak`: **muévala fuera del equipo o bórrela**.
- **Guarde una copia de `IPV_DB_KEY`** en lugar seguro: sin ella ni la base de datos ni los backups se pueden recuperar.
- Otras operaciones: `python dbcrypt.py status | rekey | decrypt <destino>`.

### Copias de seguridad fuera del equipo (regla 3-2-1)

Configure en `.env` uno o ambos destinos; cada copia automática o manual (`-Backup`) se replica y se verifica:

```ini
IPV_BACKUP_MIRROR_DIRS=E:\CopiasIPV;\\servidor\copias\ipv   # USB y/o carpeta de red
IPV_BACKUP_S3_ENDPOINT=https://s3.us-east-1.amazonaws.com     # o MinIO / Wasabi
IPV_BACKUP_S3_BUCKET=mi-bucket
IPV_BACKUP_S3_ACCESS_KEY=...                                  # credencial con solo s3:PutObject
IPV_BACKUP_S3_SECRET_KEY=...
```

- Si la BD está cifrada, las copias remotas **también lo están** (nunca se sube nada en claro).
- Un destino caído no interrumpe el backup local: queda registrado en la auditoría (`BACKUP_OFFSITE_FAILED`).

### Licencias por período (1 semana … 2 años) y Creador de Licencias

El servidor y la app Android se activan con una **licencia firmada (ECDSA P-256)** atada al dispositivo:

1. **La app entra primero en la vista de Licencia** (web y Android) cuando la licencia no está activada o está vencida, **antes del inicio de sesión** y del resto de pantallas. Allí se **genera la solicitud** con el *ID Dispositivo* cifrado (`IPVW-…` en PC, `IPVA-…` en móvil), usuario y plan, y se **envía por WhatsApp** con un botón único.
2. El proveedor crea la licencia con el **Creador de Licencias** integrado (menú lateral, solo administradores): pega el código de solicitud, elige el plan y pulsa *Crear licencia*; después la **envía por WhatsApp** al cliente desde el propio botón *Enviar licencia por WhatsApp*. También puede usar el **Keygen** de escritorio (`python keygen\keygen.py`, GUI o CLI); ambos comparten clave y registro.
3. El cliente pega la licencia en la misma vista de Licencia y pulsa **Activar**. Sin licencia vigente la API responde `402` y la app queda bloqueada; 7 días antes del vencimiento se avisa.

#### ¿Dónde se hace la licencia? (resumen de un minuto)

Los dos sitios comparten la misma clave privada (`keygen\clave_privada.json`) y el mismo registro
(`keygen\registro_licencias.csv`), así que puede alternar entre ellos:

| Dónde | Cómo se abre | Para qué sirve |
|---|---|---|
| **Creador de Licencias** (recomendado, dentro de la app) | Inicie sesión como **administrador** → menú lateral 🛠 **Creador de Licencias** (o `Ctrl+Shift+P` → *Creador de Licencias*) | Crear la clave de firma la primera vez, emitir licencias `IPVW-…` (servidor/PC) e `IPVA-…` (móvil), verificarlas, fijar tasas y ver el historial. **Activa las licencias al instante, sin reiniciar el servidor** |
| **Keygen de escritorio** | `python keygen\keygen.py` (GUI) o `python keygen\keygen.py init` y luego `keygen.py emitir --usuario … --codigo IPV… --plan 1M` | Lo mismo por consola. Escribe la clave pública solo en disco (`licencia.py`, `License.kt`): **hay que reiniciar el servidor y recompilar el APK** |

Y **dónde se pega**: en la vista 🔑 **Licencia** de cada aplicación — allí se genera el código de solicitud
(`IPVW-…` en el servidor/PC, `IPVA-…` en cada teléfono) y allí mismo se pega la licencia `IPV1.…` para activarla.

Orden correcto la primera vez: **1)** `.\iniciar-https.ps1 -InitSecurity` (crea `.env` con el JWT y el administrador)
→ **2)** inicie el servidor y entre con ese correo → **3)** cree la clave en el **Creador de Licencias**
→ **4)** emita una licencia para el código `IPVW-…` que muestra la vista Licencia y actívela
→ **5)** para el móvil, emita una licencia con el código `IPVA-…` del teléfono; si creó la clave con el Keygen
de escritorio, **recompile el APK** antes de instalarlo (la clave pública viaja dentro de `License.kt`).

**Primera vez (activar el sistema de licencias):** genere la clave con `python keygen/keygen.py init --whatsapp 53XXXXXXXX` **antes de arrancar** (en Docker, antes de construir la imagen); alternativamente un administrador puede iniciar sesión y crear la clave desde la API `/api/keygen/init` durante el bootstrap. Las licencias quedan **activadas al instante**, sin reiniciar: la clave pública se escribe en `licencia.py` y `License.kt` (recompile el APK para el móvil). La clave privada se guarda cifrada en `keygen/clave_privada.json`; la contraseña **no** se guarda en el servidor. Si el propio servidor se queda sin licencia, las rutas `/api/keygen` siguen accesibles para que el administrador se la emita a sí mismo. Precios, estudio de mercado y guía completa: **[docs/precios-y-licencias.md](docs/precios-y-licencias.md)**.

### Formato monetario

Todos los importes se muestran como **$ 3,163,138.00 CUP**: símbolo `$` delante, miles separados con coma y decimales con punto (igual en la web y en la app Android).

### Numeración de ítems (columna «Id»)

Todas las tablas empiezan por la columna **Id**, que numera las filas de 1 a N delante del resto de los encabezados
(*Valor · Categoría · Existencias · Mínimo · Precio · Valor total · Entradas / salidas · Se usa en · Acciones*).
El último número dice cuántos ítems hay y la barra de herramientas lo repite en un contador —
**▤ 33 ítems** o **▤ 5 de 33 ítems** cuando hay un filtro o una búsqueda activa.

- Alcance: productos, valores del IPV, inventario, fichas, controles, papelera, fichas recientes del resumen,
  componentes de una ficha, historial del Creador de Licencias, auditoría, usuarios y vista previa de importación CSV.
- El `Id` de la fila es su número de orden; al pasar el ratón por encima se muestra el **Id interno** (el de la base de datos).
- Las **exportaciones CSV** incluyen la columna `Id` como primera columna.
- La **app Android** numera igual sus tarjetas y muestra el total de cada listado.

### Sistema de Seguridad por Usuarios (permisos por módulo)

Cada usuario tiene permisos propios, independientes de su rol, sobre cada apartado. El módulo
**`materials`** es la entrada única **Valores del IPV**, que incluye sus dos pestañas
(*Valores* e *Inventario*).

| Permiso | Qué autoriza | Sin él… |
|---|---|---|
| `view` | Abrir el apartado y consultar sus datos | La entrada se oculta del menú y el API responde `403 {"permission_denied":"materials.view"}` |
| `edit` | Crear, editar, ajustar existencias, restaurar, purgar, importar CSV y cargar datos de prueba | Se ocultan los botones y el servidor rechaza la escritura con `403` |
| `costs` | Ver importes y administrar precios o costos manuales (junto con `edit`) | Los importes **no se envían**: `unit_price`, `stock_value` y `totals.stock_value` llegan como `null`, con `costs_hidden: true`; la web muestra 🔒 |

El permiso `costs` existe en los cinco módulos: en *Valores del IPV* tapa `unit_price` y el valor de
las existencias; en *Fichas de costo* tapa `total_cost`, `unit_cost` y `subtotal`; en *Controles de IPV*
tapa `snapshot_total` y `checked_total`; y en la analítica (`/api/statistics`, `/api/report/*`) tapa los
promedios y los costos por categoría.

Permisos por defecto según el rol (se pueden cambiar usuario a usuario):

| Rol | Valores del IPV e Inventario | Productos, fichas, controles, papelera |
|---|---|---|
| **Administrador** | ver · editar · costos (siempre, no se puede limitar) | ver · editar · costos |
| **Editor** | ver · editar · costos | ver · editar · costos |
| **Consulta (viewer)** | ver, **sin costos**: ve existencias, mínimos y recetas, pero no precios | ver (sin editar) |

**El resumen también se recorta.** `/api/dashboard` mezcla datos de todos los apartados, así que cada
tarjeta y cada panel dependen del módulo que los alimenta: sin `view` sobre *Productos y servicios* los
contadores y el catálogo por categoría llegan en `null` / `[]`; sin `view` sobre *Fichas de costo* no
llegan las fichas recientes ni la distribución de costos; y la línea de actividad solo incluye los
apartados que el usuario puede consultar. La web dibuja 🔒 en lugar de las tarjetas bloqueadas.

Almacén puede editar existencias sin ver costos, pero no enviar `unit_price` ni `currency`
(incluida la actualización masiva de precios); esos campos se omiten del formulario.
Las líneas libres de fichas con costo manual exigen `fichas.costs`. Restaurar o
purgar un elemento exige `trash.edit` **y** el permiso `edit` de su módulo; vaciar
la papelera exige `trash.edit` y `edit` en todos los módulos. Los datos de prueba
requieren `edit` en materiales, productos, fichas y controles, más `materials.costs`
porque crean precios de ejemplo.

**Solo se envía lo que cambia.** Los permisos ausentes en la petición conservan el valor del rol, así
que `{ "permissions": { "fichas": { "costs": false } } }` quita los importes de las fichas sin cerrar el
apartado. `edit` y `costs` siempre se descuentan de `view`: si se niega la vista, el resto queda negado.

**Cómo se administra** — Web → paleta de comandos (`Ctrl+Shift+P`) → *Gestionar usuarios y permisos* →
🔐 en la fila del usuario. Hay plantillas listas (*Acceso completo*, *Solo consulta*,
*Almacén (sin costos)*, *Todo menos costos*) y *Restablecer según rol*. Los cambios se guardan en la
tabla `user_permissions`, se auditan (`UPDATE_USER_PERMISSIONS`) y se aplican en la siguiente petición
del usuario, sin cerrar sus sesiones. Cada acceso denegado queda auditado como `PERMISSION_DENIED`
con el módulo y el permiso que faltaron.

**Ejemplo** — usuario de almacén que mueve existencias pero no ve dinero:

```json
PUT /api/users/7
{ "permissions": {
    "materials": { "view": true,  "edit": true,  "costs": false },
    "products":  { "view": false }, "fichas": { "view": false },
    "controls":  { "view": false }, "trash":  { "view": true, "edit": false }
} }
```

### Comandos de administración

```powershell
.\iniciar-https.ps1 -Status        # estado del servidor y la base de datos
.\iniciar-https.ps1 -Backup        # copia de seguridad consistente
.\iniciar-https.ps1 -HealthCheck   # salud en JSON
.\iniciar-https.ps1 -AuditLog      # últimos 40 eventos de auditoría
.\iniciar-https.ps1 -ShowPin       # huella de la CA para fijarla en Android
.\iniciar-https.ps1 -EncryptDb     # cifra la base de datos (SQLCipher AES-256)
.\iniciar-https.ps1 -Check         # diagnóstico del acceso seguro (certificado, TLS, red, .env)
.\iniciar-https.ps1 -Stop          # detiene el servidor
```

### Docker

```bash
cp .env.example .env    # complete IPV_JWT_SECRET, IPV_ADMIN_EMAIL, IPV_ADMIN_PASSWORD
docker compose up -d    # contenedor de solo lectura, sin privilegios, usuario no root
```

---

## 📊 Endpoints de la API

### Core
- `GET /api/health` - Estado del servidor
- `GET /api/dashboard` - Resumen general
- `GET /api/search?q=...` - Búsqueda global

### Productos
- `GET /api/products` - Listar productos
- `GET /api/products/:id` - Detalle y fichas asociadas
- `POST /api/products` - Crear producto
- `PUT /api/products/:id` - Actualizar (incluido el rendimiento del lote)
- `DELETE /api/products/:id` - Enviar a la papelera
- `POST /api/trash/products/:id/restore` - Restaurar (404 si ya está activo; exige `trash.edit` y `products.edit`)

### Valores del IPV (módulo `materials`: pestañas Valores e Inventario)
- `GET /api/materials` - Listar materiales (`materials.view`; sin `materials.costs`, `unit_price` llega como `null`)
- `GET /api/materials/:id` - Detalle, existencias y recetas que lo usan
- `POST /api/materials` - Crear material
- `PUT /api/materials/:id` - Actualizar (precio, categoría, existencias, vigencia…)
- `POST /api/materials/:id/stock` - Entrada/salida de existencias (`delta` o `set`)
- `POST /api/materials/bulk-update` - Actualización masiva
- `DELETE /api/materials/:id` - Enviar a la papelera
- `POST /api/trash/materials/:id/restore` - Restaurar (exige `trash.edit` y `materials.edit`)

### Inventario y papelera
- `GET /api/inventory` - Existencias, valor y raciones posibles por receta (pestaña *Inventario* de la misma entrada; sin `materials.costs` los importes llegan como `null` y `costs_hidden: true`)
- `GET /api/trash` - Elementos en la papelera
- `POST /api/trash/:kind/:id/restore` - Restaurar
- `DELETE /api/trash/:kind/:id` - Borrado definitivo
- `POST /api/trash/empty` - Vaciar la papelera
- `POST /api/demo/seed` - Cargar (o completar) el catálogo de demostración

### Fichas de Costo
- `GET /api/fichas` - Listar fichas
- `GET /api/fichas/:id` - Detalle de ficha
- `POST /api/fichas` - Crear ficha
- `PUT /api/fichas/:id` - Actualizar ficha
- `POST /api/fichas/:id/approve` - Aprobar ficha

### Controles IPV
- `GET /api/controls` - Listar controles
- `GET /api/controls/:id` - Detalle de control
- `POST /api/controls` - Crear control
- `POST /api/controls/:id/validate` - Validar control

### Avanzados
- `GET /api/statistics` - Estadísticas completas
- `GET /api/backup` - Crear backup (admin)
- `GET /api/audit?limit=&offset=&action=&q=` - Auditoría (admin)
- `GET /api/report/:type` - Reportes (fichas_summary, materials_inventory, controls_pending)
- `DELETE /api/materials/:id` - Borrado lógico de un valor de referencia

### Autenticación y sistema
- `POST /api/auth/login` · `POST /api/auth/refresh` · `POST /api/auth/logout` · `GET /api/auth/me`
- `GET/POST /api/users` - Gestión de usuarios (admin), con los permisos efectivos de cada uno · `PUT /api/users/:id` (`role`, `force_password_change`, `revoke_sessions`, **`permissions`**, **`reset_permissions`**…)
- `GET /api/auth/me` - Usuario actual **y sus permisos por módulo** (los usa la web para dibujar el menú)
- `POST /api/auth/password` - Cambiar contraseña (devuelve tokens nuevos para este dispositivo)
- `GET /api/auth/sessions` · `DELETE /api/auth/sessions/:sid` · `POST /api/auth/sessions/revoke-others` - Dispositivos conectados
- `GET /api/events` - Cambios en tiempo real (SSE)
- `GET /api/version` · `GET /api/openapi.yaml`

---

## 🎹 Atajos de Teclado

| Tecla | Acción |
|-------|--------|
| `6-9` | Navegar entre vistas (Controles `6`, Papelera `7`, Licencia `8`, Creador de Licencias `9`). Las teclas `1`-`5` **no** son atajos: están libres para escribir números en los formularios |
| `Ctrl+K` | Búsqueda global |
| `F5` | Actualizar datos |
| `Esc` | Cerrar modal |
| `?` | Ver ayuda de atajos |
| `s` | Estadísticas avanzadas |
| `Ctrl+Shift+P` | Paleta de comandos (tema, importar CSV, PDF, auditoría, backup, tour, accesibilidad) |
| `Ctrl+Z` | Deshacer la última desactivación |
| `Ctrl+Shift+Z` / `Ctrl+Y` | Rehacer |
| `Alt+Shift+A` | Opciones de accesibilidad |
| `↑` / `↓` | Moverse entre filas de una tabla con foco |

---

## 🎨 Paleta de Colores

```css
--primary: #183b34 (Verde bosque)
--accent: #d7e78d (Lima)
--blue: #3b82f6 (Azul)
--purple: #8b5cf6 (Púrpura)
--orange: #f59e0b (Naranja)
--red: #ef4444 (Rojo)
--green: #10b981 (Verde)
```

---

## 🔧 Configuración Avanzada

### Variables de entorno

Consulte `.env.example`. Las principales: `IPV_JWT_SECRET`, `IPV_ADMIN_EMAIL`, `IPV_ADMIN_PASSWORD`, `IPV_API_TOKEN` (integraciones), `IPV_ALLOWED_ORIGINS`, `IPV_ACCESS_TTL`, `IPV_REFRESH_TTL`, `IPV_BACKUP_INTERVAL_HOURS`, `IPV_BACKUP_KEEP`, `IPV_NOTIFY_EMAIL` y `SMTP_*`.

**Acceso seguro (HTTPS):**

| Variable | Por defecto | Para qué sirve |
|---|---|---|
| `IPV_TLS_CERT` / `IPV_TLS_KEY` | `certs\ipv-server.crt` / `.key` | Certificado y clave privada del servidor |
| `IPV_TLS_MIN` | `1.2` | Versión mínima de TLS (`1.2` o `1.3`); nunca baja de 1.2 |
| `IPV_REQUIRE_TLS` | `0` | `1` = el servidor **se niega a arrancar** sin certificado válido |
| `IPV_HTTP_REDIRECT_PORT` | `0` | Puerto HTTP que redirige a HTTPS con 308 (`0` = desactivado) |
| `IPV_HSTS_MAX_AGE` | `31536000` | Duración de HSTS en segundos (`0` = sin cabecera) |

`iniciar-https.ps1` fija estas variables automáticamente según los parámetros que se le pasen.

---

## 📱 App Android

### Compilación

```bash
cd android
./gradlew assembleDebug
```

### Instalación en Emulador
1. Instalar CA root: `certs/ipv-local-root-ca.cer`
2. Configurar URL: `https://10.0.2.2:8443`

### Instalación en Dispositivo Físico
1. Instalar CA root en el dispositivo (`.\iniciar-https.ps1 -ExportCa` para copiarla)
2. Configurar URL: `https://IP_DEL_SERVIDOR:8443`
3. Comprobar la huella con `.\iniciar-https.ps1 -ShowPin`: la app la fija en la primera conexión y avisa si cambia

Pasos detallados con capturas de cada pantalla: [docs/acceso-seguro-https.md](docs/acceso-seguro-https.md#4-entrar-desde-el-móvil-android).

---

## 🧪 Pruebas

```bash
python -m unittest discover -s tests -v   # flujo completo + JWT, roles, bloqueo, rate limit, backup, sesiones, cifrado

# Toda la batería sobre la base de datos cifrada:
pip install sqlcipher3-binary            # (Windows: sqlcipher3-wheels)
IPV_DB_KEY="una-clave-de-pruebas-larga" python -m unittest discover -s tests
```

### Prueba E2E del Creador de Licencias (Chromium)

La CI inicia un servidor aislado con JWT y administrador sintéticos, crea una clave de firma descartable y recorre en Chromium el flujo `PX`: validación de rango invertido, emisión, verificación e historial. Para ejecutarla localmente, inicia primero el servidor en otra terminal con una base temporal y credenciales de prueba; no uses datos reales:

```bash
npm ci
npx playwright install chromium
IPV_PORT=8011 IPV_DB_PATH=/tmp/ipv-e2e.db IPV_ADMIN_EMAIL=admin-e2e@ipv.local IPV_ADMIN_PASSWORD='E2E-solo-CI-password-2026' IPV_JWT_SECRET='e2e-only-jwt-secret-not-for-production-2026-abcdef0123456789' python server.py
```

En otra terminal, dentro del repositorio (el bootstrap activa una licencia efímera propia para que el modal de licencia no tape el inicio de sesión):

```bash
export IPV_ADMIN_EMAIL=admin-e2e@ipv.local IPV_ADMIN_PASSWORD='E2E-solo-CI-password-2026'
export IPV_E2E_REQUEST_CODE="$(python -c 'import licencia; print(licencia.request_code(licencia.APP_WEB, "browser-e2e-client"))')"
python tests/e2e/bootstrap.py
npm run test:e2e
```

La integración continua (`.github/workflows/ci-cd.yml`) ejecuta Ruff, Bandit y las pruebas en Python 3.10–3.12 (también con la BD cifrada), un escaneo **OWASP ZAP** (baseline de la web + API autenticada a partir de OpenAPI), la prueba E2E de Chromium, construye la imagen Docker y compila variantes debug/release de Android. Las claves, la base de datos y las cuentas del E2E son efímeras y solo para pruebas.

---

## 📈 Próximos pasos

La evolución de las dos aplicaciones se gestiona con el **[Plan de mejora continua](docs/plan-mejora-continua.md)**: ciclo de trabajo de dos semanas, criterios de «terminado», métricas trimestrales, tabla de paridad **Web ↔ Móvil** y hoja de ruta (informes y comparador de fichas, trabajo sin conexión con cola de cambios, multi-almacén y roles finos por módulo).

---

## 📄 Licencia

Proyecto de uso profesional. Todos los derechos reservados.

**© 2026 Ing. Yosvany Hernández Quintero**

---

**Hecho con ❤️ en Cuba**

### Orden de acceso seguro (Web y Android)

En producción, configure JWT y un administrador **antes** de arrancar. Durante la primera instalación, genere la clave de firma en el equipo de confianza con `python keygen/keygen.py init` antes de iniciar la interfaz web (o use la API del Creador con un JWT de administrador). Hasta configurar la clave, la API de datos responde `402` (solo se permite login, configurar MFA/contraseña y el Creador). Después, active la licencia web del equipo con `/api/license` y una licencia firmada para el código IPVW mostrado. La activación inicial admite el token firmado sin sesión; con licencia vigente la renovación requiere administrador. La app Android exige además su propia licencia IPVA; el servidor vuelve a verificar JWT, permisos y licencia web en cada petición. Con la licencia vencida, la vista de Licencia ofrece **Entrar como administrador**: usa `/api/auth/maintenance-login` (contraseña y MFA si procede) y permite abrir el Creador y emitir una renovación. Los usuarios de otros roles no pueden usar ese acceso; cualquier consulta o modificación de datos sigue devolviendo `402` hasta activar una licencia válida. La renovación del token de mantenimiento usa `/api/auth/maintenance-refresh`. Las conexiones de eventos en tiempo real también dejan de enviar datos cuando vence la licencia, se revoca la sesión o se pierde el permiso del módulo.

No use `IPV_API_TOKEN` como sustituto de usuarios: el token heredado es de **solo lectura** y no administra claves, usuarios ni licencias. La app móvil no muestra datos offline: sin servidor no puede comprobar cambios de rol o vencimiento de la licencia web. Antes de distribuir el APK, asegúrese de haber generado la clave pública en `License.kt` (un APK sin ella no exige licencia Android).

**Docker con sistema de archivos de solo lectura:** genere la clave con el Keygen en el equipo de compilación *antes* de `docker compose build`, incorpore la clave pública en el código, y conserve la clave privada fuera de la imagen. La creación/rotación de claves desde la web necesita archivos de código y directorio `keygen/` escribibles: no está disponible dentro del contenedor `read_only`. Emita licencias desde el Keygen fuera del contenedor y péguelas en la pantalla de activación. No monte la clave privada en el servidor público salvo que sea imprescindible.
