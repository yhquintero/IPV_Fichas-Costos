# ⚡ Inicio rápido — arrancar IPV por HTTPS en local

> IPV · Fichas y Costos — Autor: Ing. Yosvany Hernández Quintero
> Versión corta y verificable. Si algo falla, la guía larga es [acceso-seguro-https.md](acceso-seguro-https.md).

---

## 1. Windows (camino recomendado)

Tres órdenes en PowerShell, **dentro de la carpeta del repositorio**:

```powershell
# 0) Solo si PowerShell bloquea los scripts (afecta únicamente a esta ventana)
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

# 1) Una sola vez: crea .env con el secreto JWT y el usuario administrador
.\iniciar-https.ps1 -InitSecurity

# 2) Arrancar cifrado (la primera vez crea la CA local y el certificado)
.\iniciar-https.ps1 -Open
```

Al terminar verá un panel como este y el navegador abierto en **https://sqlserver:8443**:

```
  IPV · Fichas y Costos
  https://0.0.0.0:8443
  TLS: ✓ 1.2   Certificado: sqlserver · caduca en 730 día(s)
  Redirección: http://…:8080 → https://…:8443
```

> La primera ejecución pide **elevación una sola vez** para añadir el alias `sqlserver` al
> archivo `hosts` y abrir el puerto en el firewall (perfil privado, solo su subred).

### Comprobar que funciona de verdad

```powershell
.\iniciar-https.ps1 -Check      # 0 = correcto · 2 = avisos · 1 = problemas
.\iniciar-https.ps1 -Status     # estado del servidor y de la base de datos
```

`-Check` valida requisitos, CA instalada, **handshake TLS real**, HSTS, `.env`,
cifrado de la base de datos y copias de seguridad. Si sale con código 0, el acceso
seguro está bien montado.

---

## 2. Arranque manual (sin el script)

Desde la versión actual, **`server.py` lee el archivo `.env` al arrancar** (módulo
[`entorno.py`](../entorno.py)). Antes solo lo hacía `iniciar-https.ps1`, así que
lanzar `python server.py` a mano dejaba el servidor **sin TLS y sin inicio de
sesión** sin avisar. Ahora basta con tener el `.env` relleno:

```ini
# .env  — lo crea .\iniciar-https.ps1 -InitSecurity
IPV_JWT_SECRET=<48 bytes aleatorios>
IPV_ADMIN_EMAIL=admin@empresa.cu
IPV_ADMIN_PASSWORD=<contraseña fuerte>
IPV_TLS_CERT=certs/ipv-server-cert.pem
IPV_TLS_KEY=certs/ipv-server-key.pem
IPV_PORT=8443
IPV_HTTP_REDIRECT_PORT=8080
IPV_REQUIRE_TLS=1
```

```powershell
python server.py
```

Reglas de precedencia: **lo que ya esté en el entorno gana sobre `.env`**, de modo
que `iniciar-https.ps1`, Docker o un `set`/`export` manual siguen mandando.
Se admiten comentarios con `#`, comillas y el prefijo `export`.

### Linux / macOS / WSL (certificado de desarrollo)

```bash
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
  -keyout certs/dev-key.pem -out certs/dev-cert.pem \
  -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"

cat >> .env <<'EOF'
IPV_TLS_CERT=certs/dev-cert.pem
IPV_TLS_KEY=certs/dev-key.pem
IPV_PORT=8443
IPV_HTTP_REDIRECT_PORT=8080
EOF

python3 server.py
```

Comprobación rápida (el `-k` es porque el certificado es propio, no de una CA pública):

```bash
curl -ks https://localhost:8443/api/health
# {"ok":true, ... "tls":true, "tls_min_version":"1.2", "tls_days_left":364}

curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' http://localhost:8080/
# 308 https://localhost:8443/
```

---

## 3. Señales de que está **bien** montado

| Señal | Dónde se ve |
|---|---|
| Candado sin advertencias | Barra del navegador (tras instalar la CA local) |
| `"tls": true` y `tls_days_left` | `GET /api/health` |
| `308` hacia `https://` | `http://…:8080` |
| `Strict-Transport-Security` | Cabeceras de respuesta |
| «✓ TLS 1.2» en el panel | Consola al arrancar |

---

## 4. Problemas frecuentes

| Síntoma | Causa | Solución |
|---|---|---|
| `ERR_CERT_AUTHORITY_INVALID` | La CA local no está instalada en **ese** equipo/navegador | `.\iniciar-https.ps1 -ExportCa D:\CA` e instalar `ipv-local-root-ca.cer` como *entidad de certificación raíz de confianza* |
| `ERR_SSL_PROTOCOL_ERROR` | Está entrando por `http://` al puerto HTTPS | Use `https://sqlserver:8443`, o el puerto 8080 que redirige |
| «Configure IPV_JWT_SECRET…» al arrancar | Falta `.env` o está vacío | `.\iniciar-https.ps1 -InitSecurity` |
| El servidor arranca **sin** TLS | `IPV_TLS_CERT` / `IPV_TLS_KEY` vacíos o con ruta incorrecta | Rellénelos en `.env`; ponga `IPV_REQUIRE_TLS=1` para que se niegue a arrancar en claro |
| «Dirección ya en uso» / puerto ocupado | Otra instancia sigue viva | `.\iniciar-https.ps1 -Stop` y vuelva a arrancar |
| Firefox sigue desconfiando | Firefox usa su propio almacén de certificados | Actívele *Importar certificados raíz de Windows* o importe la CA en su almacén |
| Desde otro equipo no entra | Firewall o red marcada como pública | Red en modo **privada** y regla del firewall creada en el primer arranque |
| Se ve el diseño antiguo tras actualizar | Caché del *service worker* (PWA) | Recargue con `Ctrl+F5`; la versión de caché se sube en `web/sw.js` con cada cambio |

---

## 5. Nota sobre `https://yhquintero.github.io/IPV-Gestion-Costos/`

Esa dirección devuelve **404** porque el repositorio `IPV-Gestion-Costos` **no tiene
GitHub Pages activado** (`has_pages: false`), no porque falte el contenido.

Importante: **GitHub Pages solo sirve archivos estáticos**. La web de IPV necesita el
servidor Python (`server.py`) para la API, la autenticación y SQLite, así que *no puede
funcionar entera* en Pages; como mucho serviría una página de presentación o una demo
con datos simulados.

Para publicar una página de presentación ahí: *Settings → Pages → Build and deployment
→ Source: Deploy from a branch* (p. ej. `main` / carpeta `/docs`) y esperar al despliegue.
El uso real del sistema sigue siendo **local por HTTPS**, como se describe arriba.
