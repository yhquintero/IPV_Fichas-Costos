# IPV · Fichas y Costos

Prototipo funcional para probar el flujo de productos y servicios, valores de referencia del IPV, Fichas de Costo versionadas y Controles de IPV. Incluye una aplicación web y una aplicación Android nativa en Kotlin. Ambas consumen la misma API y los datos maestros se guardan en un archivo SQLite `.db` en el servidor.

> **Importante:** los registros, precios y cálculos precargados son ficticios para demostración. Este prototipo no implementa ni certifica fórmulas, requisitos normativos, firmas oficiales, autenticación ni controles de seguridad para producción.

## Inicio por HTTPS en una red local (Windows)

Requisitos: Windows, PowerShell, Python 3.10 o superior y una red local confiable.

1. Desde PowerShell, en la raíz del proyecto, ejecuta `powershell -ExecutionPolicy Bypass -File .\iniciar-https.ps1` (o `pwsh -File .\iniciar-https.ps1`). Si hace falta, solicitará permisos de administrador solo para los cambios de hosts/firewall.
2. El script crea una autoridad certificadora local y un certificado con nombres/IP de la PC, confía la CA en tu perfil de Windows, configura el firewall para TCP 8443 en perfiles privados/de dominio y arranca el servidor HTTPS con los permisos normales de tu usuario.
3. En la computadora del servidor abre **`https://sitioweb:8443`**.
4. El script también imprime las direcciones IPv4 disponibles. Desde otro equipo puedes abrir **`https://IP_DE_LA_COMPUTADORA:8443`**.

El archivo raíz público que hay que instalar en otros dispositivos está en `certs/ipv-local-root-ca.cer`. Instálalo como certificado de CA/raíz de confianza antes de navegar o conectar Android. El archivo `certs/ipv-server-key.pem` es la clave privada del servidor: **no la copies ni la compartas**.

### Nombre `sitioweb` en otras PC o móviles

El script agrega el alias `sitioweb` al archivo `hosts` de la PC donde corre. Para usar exactamente `https://sitioweb:8443` desde otras máquinas, la red debe resolver ese nombre hacia la IP local del servidor: configura un registro DNS en el router/servidor DNS o una entrada `hosts` en cada cliente. Si no puedes configurar DNS, usa la IP que imprime el script; el certificado incluye las IP locales detectadas.

Los clientes deben estar en la misma LAN o tener una ruta hacia el servidor. El firewall se limita a la subred local y perfiles privados/de dominio; si Windows marca la red confiable como Pública, cámbiala a Privada antes de probar. No configures reenvío de puerto desde Internet ni lo uses en Wi-Fi público.

### Android Studio y teléfonos

1. Abre `android/` en Android Studio. Usa JDK 17, Android SDK Platform 35 y Gradle 8.9.
2. Ejecuta `iniciar-https.ps1` en la computadora que alojará el backend.
3. **Emulador:** la app usa `https://10.0.2.2:8443` por defecto. Instala `certs/ipv-local-root-ca.cer` en el emulador como certificado de CA de usuario.
4. **Teléfono físico:** instala en el teléfono `ipv-local-root-ca.cer` y cambia la URL desde **⚙ Conexión con la base SQLite** a `https://IP_DE_LA_COMPUTADORA:8443`. Si quieres usar `https://sitioweb:8443`, configura también la resolución DNS de ese alias en la red.

Algunas versiones de Android piden el PIN del dispositivo para instalar una CA. La app permite confiar en certificados de usuario instalados, pero mantiene deshabilitado el tráfico HTTP sin cifrar.

## Ejecución de desarrollo sin HTTPS

Para desarrollo local únicamente, se puede iniciar el servidor directamente:

```bash
python server.py
```

Esto usa HTTP en `http://localhost:8000`; no es el modo de acceso recomendado para otros dispositivos. Para probar en la LAN, utiliza `iniciar-https.ps1`.

El servidor crea automáticamente `data/ipv.db` y carga datos de muestra la primera vez. El archivo se conserva entre reinicios y está excluido de Git. Para seleccionar otra ubicación define `IPV_DB_PATH`. El servidor escucha en `0.0.0.0`; por defecto usa el puerto 8000 en modo de desarrollo y el script HTTPS lo configura en 8443.

Comprueba el flujo principal con:

```bash
python -m unittest discover -s tests -v
```

La API incluye endpoints de salud, resumen, productos, valores, fichas y controles; creación de productos, valores y fichas; aprobación de borradores; generación de controles como instantáneas; validación de totales y exportación CSV desde la web.

## Recorrido de prueba sugerido

1. En **Productos y servicios**, crea un producto.
2. En **Valores del IPV**, registra sus insumos y precios de prueba.
3. En **Fichas de costo**, crea una ficha con cantidades y componentes; queda como borrador.
4. Aprueba la ficha.
5. Pulsa **Control** para crear una instantánea del período.
6. En **Controles de IPV**, ejecuta **Validar** y revisa el resultado.

La ficha de demostración incluye ejemplos para Bebidas, Comidas y Servicios. No uses los importes de ejemplo para tomar decisiones comerciales o administrativas. El servidor local no incorpora todavía autenticación, roles ni sincronización offline.
