# IPV · Fichas y Costos v1.1

**Sistema profesional de gestión de Fichas de Costo y Controles de IPV**

Autor: **Ing. Yosvany Hernández Quintero**

---

## 🎯 Características Principales

### 🎨 Interfaz Web
- **Ajuste a la ventana**: la barra lateral ya no duplica el ancho; la aplicación cabe al 100 % sin reducir el zoom
- **Valores del IPV con CRUD completo** (crear, ver, editar, eliminar) desde cualquier apartado, con categorías, existencias y precio
- **Inventario**: existencias, mínimo, valor en almacén y recetas que usa cada insumo; se ve cuántos comensales o copas se pueden preparar
- **Rendimiento de fichas**: cada plato indica comensales (o copas/vasos) y el costo por unidad; el inventario calcula cuántas raciones salen
- **Papelera de reciclaje** en todos los módulos: restaurar o borrar definitivamente
- **Columna «Id»** al principio de cada tabla y lista (1, 2, 3 …) con el contador de ítems en la barra de herramientas: se sabe al instante cuántos productos, valores, fichas o controles hay
- **Licencia**: pantalla propia con ID del equipo, planes, WhatsApp y activación/renovación
- **Creador de Licencias** (web, administradores): crea la clave de firma, activa las licencias al instante y emite, verifica y registra licencias para PC y móvil
- **Datos de prueba**: catálogo amplio de comidas, licores, bebidas e inventario para aprender
- **La app Android replica la web** y comparte la misma base de datos SQLite del servidor
- **Diseño moderno** con glassmorphism, neumorphism y efectos 3D
- **Modo oscuro/claro** con transiciones suaves
- **Animaciones avanzadas**: confetti, parallax, morphing shapes, ripple effects
- **Gráficos interactivos**: barras, donuts, líneas de tiempo
- **Búsqueda global** con API dedicada y debounce
- **Atajos de teclado** completos (Ctrl+K, F5, 1-5, ?, s)
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
- **TLS 1.2+** con cifrados ECDHE/AES-GCM/ChaCha20
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

# 2. Iniciar servidor HTTPS
.\iniciar-https.ps1

# 3. Abrir en navegador
# https://sqlserver:8443
```

### Seguridad (recomendado antes del primer inicio)

```powershell
.\iniciar-https.ps1 -InitSecurity   # crea .env con secreto JWT y administrador
.\iniciar-https.ps1                 # inicia el servidor HTTPS (lee .env)
```

Sin `IPV_JWT_SECRET` el servidor funciona en **modo abierto** (solo para redes de confianza y pruebas).

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

1. La app muestra **Activar licencia** con el *ID Dispositivo* cifrado (`IPVW-…` en PC, `IPVA-…` en móvil) y un botón **Solicitar por WhatsApp**. La web y el móvil lo hacen **al arrancar, antes del inicio de sesión**.
2. El proveedor crea la licencia con el **Creador de Licencias** integrado (menú lateral, solo administradores): pega el código de solicitud, elige el plan y pulsa *Crear licencia*. También puede usar el **Keygen** de escritorio (`python keygen\keygen.py`, GUI o CLI); ambos comparten clave y registro.
3. El cliente pega la licencia y pulsa **Activar**. Sin licencia vigente la API responde `402` y la app queda bloqueada; 7 días antes del vencimiento se avisa.

**Primera vez (activar el sistema de licencias):** abra **Creador de Licencias** en la web, escriba una contraseña (mín. 10) y su WhatsApp, y pulse *Crear clave de firma y activar licencias*. Las licencias quedan **activadas al instante**, sin reiniciar: la clave pública se escribe en `licencia.py` y `License.kt` (recompile el APK para el móvil). El equivalente en consola es `python keygen\keygen.py init --whatsapp 53XXXXXXXX`. La clave privada se guarda cifrada en `keygen/clave_privada.json`; la contraseña **no** se guarda en el servidor. Si el propio servidor se queda sin licencia, las rutas `/api/keygen` siguen accesibles para que el administrador se la emita a sí mismo. Precios, estudio de mercado y guía completa: **[docs/precios-y-licencias.md](docs/precios-y-licencias.md)**.

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

### Comandos de administración

```powershell
.\iniciar-https.ps1 -Status        # estado del servidor y la base de datos
.\iniciar-https.ps1 -Backup        # copia de seguridad consistente
.\iniciar-https.ps1 -HealthCheck   # salud en JSON
.\iniciar-https.ps1 -AuditLog      # últimos 40 eventos de auditoría
.\iniciar-https.ps1 -ShowPin       # huella de la CA para fijarla en Android
.\iniciar-https.ps1 -EncryptDb     # cifra la base de datos (SQLCipher AES-256)
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
- `POST /api/products/:id/restore` - Restaurar (404 si ya está activo)

### Materiales (Valores IPV)
- `GET /api/materials` - Listar materiales
- `GET /api/materials/:id` - Detalle, existencias y recetas que lo usan
- `POST /api/materials` - Crear material
- `PUT /api/materials/:id` - Actualizar (precio, categoría, existencias, vigencia…)
- `POST /api/materials/:id/stock` - Entrada/salida de existencias (`delta` o `set`)
- `POST /api/materials/bulk-update` - Actualización masiva
- `DELETE /api/materials/:id` - Enviar a la papelera
- `POST /api/materials/:id/restore` · `POST /api/trash/materials/:id/restore` - Restaurar

### Inventario y papelera
- `GET /api/inventory` - Existencias, valor y raciones posibles por receta
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
- `GET/POST /api/users` - Gestión de usuarios (admin) · `PUT /api/users/:id` (`force_password_change`, `revoke_sessions`…)
- `POST /api/auth/password` - Cambiar contraseña (devuelve tokens nuevos para este dispositivo)
- `GET /api/auth/sessions` · `DELETE /api/auth/sessions/:sid` · `POST /api/auth/sessions/revoke-others` - Dispositivos conectados
- `GET /api/events` - Cambios en tiempo real (SSE)
- `GET /api/version` · `GET /api/openapi.yaml`

---

## 🎹 Atajos de Teclado

| Tecla | Acción |
|-------|--------|
| `1-9` | Navegar entre vistas (Resumen, Productos, Valores, Inventario, Fichas, Controles, Papelera, Licencia, Creador de Licencias) |
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
1. Instalar CA root en el dispositivo
2. Configurar URL: `https://IP_DEL_SERVIDOR:8443`

---

## 🧪 Pruebas

```bash
python -m unittest discover -s tests -v   # flujo completo + JWT, roles, bloqueo, rate limit, backup, sesiones, cifrado

# Toda la batería sobre la base de datos cifrada:
pip install sqlcipher3-binary            # (Windows: sqlcipher3-wheels)
IPV_DB_KEY="una-clave-de-pruebas-larga" python -m unittest discover -s tests
```

La integración continua (`.github/workflows/ci-cd.yml`) ejecuta Ruff, Bandit y las pruebas en Python 3.10–3.12 (también con la BD cifrada), un escaneo **OWASP ZAP** (baseline de la web + API autenticada a partir de OpenAPI), construye la imagen Docker y compila la app Android.

---

## 📈 Próximos pasos

Ver la sección de mejoras sugeridas en el historial del proyecto: paquetes **Seguridad Máxima**, **UX/UI Premium**, **IA/ML** y **Multi-Tenancy**.

---

## 📄 Licencia

Proyecto de uso profesional. Todos los derechos reservados.

**© 2026 Ing. Yosvany Hernández Quintero**

---

**Hecho con ❤️ en Cuba**
