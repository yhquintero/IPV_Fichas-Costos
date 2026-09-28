# 🔐 Acceso seguro por HTTPS — guía completa desde cero

> IPV · Fichas y Costos — Autor: Ing. Yosvany Hernández Quintero
> Todo lo necesario para pasar de «no tengo nada instalado» a «entro cifrado desde la PC, desde otra PC de la red y desde el móvil».

---

## 0. Qué vamos a montar

```
        ┌──────────────────────────── PC servidor (Windows) ────────────────────────────┐
        │  iniciar-https.ps1                                                            │
        │    · crea la CA local  ──►  certs\ipv-local-root-ca.cer  (se instala en los    │
        │                                                           clientes)           │
        │    · emite el certificado del servidor (certs\ipv-server-cert.pem + key)      │
        │    · arranca server.py con TLS 1.2+ en el puerto 8443                         │
        │    · deja el puerto 8080 redirigiendo a HTTPS                                 │
        └───────────────────────────────────────────────────────────────────────────────┘
                │                          │                              │
        https://sqlserver:8443      https://192.168.x.x:8443      https://192.168.x.x:8443
          (esta misma PC)             (otra PC de la red)             (móvil Android)
```

- El tráfico va **cifrado (TLS 1.2 o 1.3)**, con **HSTS** y **cabeceras de seguridad** estrictas.
- La CA y el certificado son **para su red local**. No sirven en Internet ni deben publicarse.
- La base de datos vive **solo en la PC servidor**; la web y el móvil son dos caras del mismo dato.

---

## 1. Antes de empezar

| Necesita | Cómo comprobarlo |
|---|---|
| Windows 10/11 | — |
| Python 3.10 o superior | `python --version` |
| PowerShell 5.1 o superior | `$PSVersionTable.PSVersion` |
| Permisos de administrador (solo la primera vez) | Para el alias `sqlserver` y la regla del firewall |
| Red **privada** (casa/oficina), nunca Wi-Fi público | Configuración → Red → «Red privada» |

> Si PowerShell se niega a ejecutar el script:
> `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` y vuelva a intentarlo.

---

## 2. Paso a paso (primera instalación)

### Paso 1 · Obtener el proyecto

```powershell
git clone https://github.com/yhquintero/IPV_Fichas-Costos.git
cd IPV_Fichas-Costos
```

### Paso 2 · Crear las credenciales

```powershell
.\iniciar-https.ps1 -InitSecurity
```

- Pide **correo** y **contraseña** del administrador (mínimo 10 caracteres, mayúsculas, números y símbolos).
- Crea `.env` con un **secreto JWT de 384 bits** y permisos restringidos a su usuario de Windows.
- Sin este paso el servidor arranca en **modo abierto** (sin inicio de sesión): úselo solo para probar.

### Paso 3 · Primer arranque

```powershell
.\iniciar-https.ps1
```

La primera vez el script:

1. Pide elevación **solo** para añadir el alias `sqlserver` al archivo `hosts` y abrir el puerto en el firewall (perfil privado, únicamente su subred).
2. Crea la **autoridad certificadora local** (RSA 3072, 8 años) y la instala como raíz de confianza de su usuario.
3. Emite el **certificado del servidor** (RSA 2048, 2 años) con todos los nombres e IP de este equipo.
4. Arranca el servidor con **TLS 1.2+**, HSTS y la redirección `http://…:8080 → https://…:8443`.

Verá un panel como este:

```
═══════════════════════════════════════════════════
  Servidor HTTPS listo para la red local
═══════════════════════════════════════════════════
  En esta PC:      https://sqlserver:8443
  También:         https://localhost:8443
  Desde la red:    https://192.168.1.50:8443
  HTTP (redirige): http://sqlserver:8080 → HTTPS
  TLS mínimo:      1.2

  CA para instalar en móviles u otras PC: …\certs\ipv-local-root-ca.cer
  Huella SHA-256 de la CA: 3F2A…
```

> **Detener el servidor:** `Ctrl+C` en esa ventana, o `.\iniciar-https.ps1 -Stop` desde otra.

### Paso 4 · Entrar desde esta PC

1. Abra **https://sqlserver:8443** (o use `.\iniciar-https.ps1 -Open`, que lo abre solo).
2. El candado debe aparecer **cerrado**: la CA ya está instalada en su usuario.
3. Inicie sesión con el correo y la contraseña del paso 2.
4. Si es el primer acceso, el sistema le exigirá **cambiar la contraseña**.
5. Recomendado: active la **verificación en dos pasos** (menú → Seguridad de mi cuenta → Activar).

### Paso 5 · Activar la licencia

Si el sistema de licencias está activo, la aplicación pide la licencia **antes del inicio de sesión**:

- Es usted el proveedor → menú **Creador de Licencias** (solo administradores) y emita la licencia de este equipo.
- Es usted el cliente → pulse **Solicitar por WhatsApp**, pegue la licencia recibida y **Activar**.

Guía completa: [precios-y-licencias.md](precios-y-licencias.md).

### Paso 6 · Cifrar la base de datos (muy recomendado)

```powershell
.\iniciar-https.ps1 -Stop        # el servidor debe estar detenido
.\iniciar-https.ps1 -EncryptDb   # SQLCipher AES-256, genera IPV_DB_KEY en .env
.\iniciar-https.ps1 -Status      # debe decir «Base de datos cifrada»
```

⚠ **Guarde una copia de `IPV_DB_KEY` fuera del equipo.** Sin esa clave no se recuperan ni la base de datos ni las copias de seguridad.

### Paso 7 · Borrar la contraseña inicial

Una vez que ha entrado y cambiado la contraseña, edite `.env` y deje vacío:

```ini
IPV_ADMIN_PASSWORD=
```

`-Check` se lo recuerda mientras siga escrita.

---

## 3. Entrar desde **otra PC** de la misma red

1. En el servidor, copie la CA a un USB o carpeta compartida:

   ```powershell
   .\iniciar-https.ps1 -ExportCa 'E:\'
   ```

   Se copian `ipv-local-root-ca.cer` y un `COMO-INSTALAR-LA-CA.txt` con estas mismas instrucciones.

2. En la otra PC: doble clic en `ipv-local-root-ca.cer` → **Instalar certificado** → *Usuario actual* →
   *Colocar todos los certificados en el siguiente almacén* → **Entidades de certificación raíz de confianza** → Finalizar.

3. Abra `https://IP-DEL-SERVIDOR:8443` (la IP que mostró el panel, p. ej. `https://192.168.1.50:8443`).

   Para usar el nombre `sqlserver` también en esa PC, añada a su archivo
   `C:\Windows\System32\drivers\etc\hosts` (como administrador):

   ```
   192.168.1.50   sqlserver
   ```

4. Opcional: en el navegador, menú → **Instalar aplicación** (PWA). Queda como un programa más, con icono propio y modo sin conexión.

---

## 4. Entrar desde el **móvil Android**

1. **Instalar la CA** en el teléfono:
   - Copie `ipv-local-root-ca.cer` al móvil (cable, correo, USB).
   - Ajustes → **Seguridad** → *Cifrado y credenciales* → **Instalar un certificado** → *Certificado de CA* → seleccione el archivo.
   - Android avisará de que la red puede ser supervisada: es normal con una CA propia.

2. **Instalar la app**: compile el APK (`cd android` → `.\gradlew assembleDebug`) e instálelo, o copie el APK ya firmado.

3. **Configurar la conexión** (en la app: ⚙ Configuración):
   - URL del servidor: `https://192.168.1.50:8443` (la IP real del servidor). **Debe empezar por `https://`**.
   - Emulador de Android Studio: `https://10.0.2.2:8443`.

4. **Fijar el certificado (pinning)** para que nadie pueda suplantar al servidor:

   ```powershell
   .\iniciar-https.ps1 -ShowPin
   ```

   Copie la huella SHA-256 y péguela en ⚙ Configuración → *Nueva huella*.
   Si la deja vacía, la app fija automáticamente el certificado de la **primera** conexión (TOFU) y avisará si alguna vez cambia.

5. Inicie sesión con el mismo usuario de la web. Web y móvil comparten datos, licencia y auditoría.

> Si renueva la CA (`-Renew`), debe **reinstalarla en cada cliente** y volver a fijar la huella en el móvil.

---

## 5. Uso diario

| Acción | Comando |
|---|---|
| Arrancar el servidor | `.\iniciar-https.ps1` |
| Arrancar y abrir el navegador | `.\iniciar-https.ps1 -Open` |
| Ver el estado | `.\iniciar-https.ps1 -Status` |
| Diagnóstico completo | `.\iniciar-https.ps1 -Check` |
| Detener | `Ctrl+C` o `.\iniciar-https.ps1 -Stop` |
| Copia de seguridad | `.\iniciar-https.ps1 -Backup` |
| Últimos eventos de auditoría | `.\iniciar-https.ps1 -AuditLog` |
| Salud en JSON (para scripts) | `.\iniciar-https.ps1 -HealthCheck` |
| Huella de la CA (móvil) | `.\iniciar-https.ps1 -ShowPin` |
| Copiar la CA a un USB | `.\iniciar-https.ps1 -ExportCa 'E:\'` |
| Renovar certificados | `.\iniciar-https.ps1 -Renew` |
| Ver toda la ayuda | `.\iniciar-https.ps1 -Help` |

Opciones útiles: `-Port 9443` (otro puerto), `-RedirectPort 0` o `-NoRedirect` (sin redirección HTTP),
`-Tls13Only` (exigir TLS 1.3 cuando todos los clientes son modernos).

---

## 6. Comprobarlo todo con `-Check`

```powershell
.\iniciar-https.ps1 -Check
```

Revisa en un solo paso:

- Versión de Python y de PowerShell.
- CA local: vigencia y si está instalada como raíz de confianza.
- Certificado del servidor: días restantes y si cubre **todas** las IP actuales del equipo.
- Archivos `certs\*.pem` presentes.
- Alias `sqlserver` en `hosts`, reglas de firewall y perfil de red (avisa si hay una red *Pública*).
- **Handshake TLS real**: protocolo negociado (debe ser `Tls12`/`Tls13`), cifrado y vigencia del certificado.
- API viva (`/api/health`), TLS mínimo y cabecera **HSTS**.
- `.env`: secreto JWT presente y aviso si `IPV_ADMIN_PASSWORD` sigue escrito.
- Base de datos cifrada y última copia de seguridad.

Termina con un resumen: `acceso seguro correcto`, `N aviso(s)` o `N problema(s)`.

---

## 7. Cuando algo falla

| Síntoma | Causa probable | Solución |
|---|---|---|
| «No es seguro» / candado tachado en el navegador | La CA no está instalada en ese equipo o perfil | Instale `ipv-local-root-ca.cer` en *Entidades de certificación raíz de confianza* (usuario actual) |
| `sqlserver` no resuelve desde otra PC | El alias solo existe en el servidor | Use la IP, o añada `IP   sqlserver` al `hosts` del cliente |
| No se ve el servidor desde el móvil | Firewall, red distinta o red «Pública» | `-Check`, misma Wi-Fi, marque la red como privada, compruebe la regla del puerto 8443 |
| «El puerto 8443 ya está en uso» | Ya hay un servidor arrancado | `.\iniciar-https.ps1 -Stop` o `-Port 9443` |
| La app Android dice que la huella cambió | Se renovó el certificado (o alguien suplanta el servidor) | Si fue usted: ⚙ Configuración → *Olvidar la huella* y vuelva a fijarla con `-ShowPin` |
| Cambió la IP del equipo y el certificado no la cubre | DHCP asignó otra dirección | Arranque de nuevo: el script lo detecta y reemite solo si hace falta (o fuerce con `-Renew`) |
| Escribió `http://` y no cargaba | Falta el esquema seguro | Ya no hace falta: `http://…:8080` redirige solo a HTTPS |
| El servidor no arranca: «IPV_REQUIRE_TLS=1 exige HTTPS» | Se intentó arrancar `server.py` a mano sin certificados | Use `.\iniciar-https.ps1` (o defina `IPV_TLS_CERT`/`IPV_TLS_KEY`) |
| Olvidó la contraseña del administrador | — | Borre `.env`, ejecute `-InitSecurity` de nuevo y vuelva a arrancar |

---

## 8. Reglas de oro

1. **Nunca** abra el puerto 8443 hacia Internet ni lo publique en el router. Si necesita acceso remoto, use una **VPN** (WireGuard/Tailscale) y siga entrando por la IP privada.
2. `certs\ipv-server-key.pem` es la clave privada del servidor: **no se copia, no se comparte, no se sube al repositorio**.
3. Instale la CA **solo** en los dispositivos que la necesitan.
4. Mantenga la base de datos cifrada y `IPV_DB_KEY` guardada **fuera** del equipo.
5. Verifique el acceso con `-Check` **una vez al mes** y tras cada cambio de red.
6. Renueve los certificados antes de que caduquen: el propio servidor avisa 30 días antes al arrancar.
7. Cada usuario con su cuenta y su rol (admin / editor / consulta); 2FA obligatorio para administradores (`IPV_REQUIRE_ADMIN_MFA=1`).

---

## 9. Lista de verificación (imprimible)

```
[ ] Python 3.10+ y PowerShell 5.1+
[ ] .\iniciar-https.ps1 -InitSecurity          (correo + contraseña del administrador)
[ ] .\iniciar-https.ps1                        (primer arranque: CA + certificado + servidor)
[ ] Entro en https://sqlserver:8443 con el candado cerrado
[ ] Cambié la contraseña inicial y activé la verificación en dos pasos
[ ] Licencia activada (si aplica)
[ ] .\iniciar-https.ps1 -EncryptDb             (base de datos cifrada)
[ ] IPV_DB_KEY guardada fuera del equipo
[ ] IPV_ADMIN_PASSWORD borrada de .env
[ ] CA instalada en las otras PC (-ExportCa) y en el móvil
[ ] Huella fijada en la app Android (-ShowPin)
[ ] .\iniciar-https.ps1 -Check sin problemas
[ ] Copia de seguridad probada (-Backup) y copia fuera del equipo
```

---

## 10. Variables de entorno relacionadas

| Variable | Valor por defecto | Para qué sirve |
|---|---|---|
| `IPV_TLS_CERT` / `IPV_TLS_KEY` | (las pone el script) | Certificado y clave en PEM |
| `IPV_TLS_MIN` | `1.2` | Versión mínima de TLS (`1.2` o `1.3`) |
| `IPV_REQUIRE_TLS` | `0` | `1` = el servidor se niega a arrancar sin cifrado |
| `IPV_HTTP_REDIRECT_PORT` | `0` | Puerto HTTP que responde `308` hacia HTTPS |
| `IPV_HSTS_MAX_AGE` | `31536000` | Duración de la cabecera HSTS (segundos) |
| `IPV_ALLOWED_ORIGINS` | *(vacío)* | Orígenes permitidos por CORS; vacío = sin CORS (la web es del mismo origen) |
| `IPV_IP_ALLOWLIST` | (vacío) | Redes que pueden conectarse, p. ej. `192.168.1.0/24` |

`iniciar-https.ps1` define automáticamente las cuatro primeras: no hace falta tocarlas a mano.
