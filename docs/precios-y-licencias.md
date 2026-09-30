# Precios de desarrollo en Cuba y licencias por período — IPV Fichas de Costo

**Autor:** Ing. Yosvany Hernández Quintero · **Fecha del estudio:** 27 de septiembre de 2026

> **Aviso de método.** En Cuba no existe ninguna estadística pública de tarifas de software. Los datos directos del mercado cubano son **anuncios de Revolico** y ofertas de empleo. Cada cifra se marca como:
> - 📌 **Fuente directa**: aparece tal cual en una fuente citada.
> - 🧮 **Estimación propia**: inferida a partir de fuentes, con el razonamiento explicado.

---

## 1. Tipo de cambio utilizado

Se usan las tasas indicadas por el cliente, tomadas como vigentes:

| Divisa | USD | EUR | MLC | CAD | MXN | ZELLE | CLA |
|---|---|---|---|---|---|---|---|
| CUP por unidad | 740,00 | 840,00 | 467,12 | 477,29 | 52,34 | 718,22 | 675,64 |

📌 **Contraste con fuentes publicadas:**
- elTOQUE, sábado **26/09/2026** por la mañana: 1 USD = **730 CUP**, 1 EUR = **840 CUP**, 1 CLA = **667,59 CUP**. Lo recoge [Directorio Cubano](https://www.directoriocubano.info/cuba/nuevo-record-dolar-euro-cuba-tasas-cambio-26-septiembre-2026/).
- CiberCuba: 1 USD = 699 CUP y 1 MLC ≈ 450 CUP el 16/09/2026 ([fuente](https://www.cibercuba.com/noticias/2026-09-17-u1-e199894-s27061-nid340536-asi-cierra-mercado-informal-cuba-dolar-sube-euro)). El 06/09/2026 eran 683 CUP ([fuente](https://www.cibercuba.com/noticias/2026-09-07-u1-e209395-s27061-nid339755-asi-cierra-mercado-informal-cuba-dolar-congela-euro)).

**No encontré una tasa publicada más reciente que la suya.** Sus 740 CUP/USD están 10 pesos por encima de la última publicada (730, del 26/09). Eso encaja con la subida sostenida del dólar (+57 CUP en 20 días), así que **se toma su tabla como la vigente**.

⚠️ El dólar informal sube ~2–3 CUP por día. **Por eso todos los precios se fijan en USD** y el importe en CUP se recalcula el día del cobro. El Keygen lee las tasas de `keygen/tasas.json`, que usted puede actualizar.

**Cálculo de las otras columnas:** el precio en CUP se divide entre la tasa de cada divisa. Ejemplo: 400 USD × 740 = 296 000 CUP, y 296 000 ÷ 840 = 352 EUR.

---

## 2. Datos del mercado encontrados

| Dato | Valor | Fuente y fecha |
|---|---|---|
| 📌 Sitios web / tiendas online / catálogos (La Habana) | anuncios de **100 USD, 200 USD, 299 USD y 300 USD** | [Revolico – Informática/Programación](https://www.revolico.com/search?category=servicios&subcategory=informatica-programacion) y [anuncio de 300 USD](https://www.revolico.com/item/desarrollo-de-sitios-web-programador-tiendas-online-47414836). Consultado el 27/09/2026; los anuncios no muestran la fecha absoluta («hace 4 días») |
| 📌 «Desarrollo web 360» de una empresa habanera | desde **45 USD** | [Revolico – Informática y marketing](https://revolico.com/search?category=servicios_&cu=0&subcategory=servicios-informatica-creatividad-y-marketing), consultado el 27/09/2026 |
| 📌 Oferta de empleo «desarrollador Android (Kotlin/Java)» | **200 USD** (probablemente salario mensual) | [Revolico – Empleos](https://www.revolico.com/search?category=empleos_&order=price&page=10), consultado el 27/09/2026 |
| 📌 Tarifa de referencia en desarrollo web para freelancers cubanos que trabajan en el exterior | **20–100 USD/hora** | [RankubaSEO, guía 2026](https://rankubaseo.com/en/online-jobs-from-cuba), 07/05/2026 |
| 📌 Pujas medias en Freelancer.com («freelance en Cuba») | app Android/Kotlin con pasarela de pago: **2 075 USD**; front-end Next.js: **280 USD** | [Freelancer.com](https://www.freelancer.com/job-search/freelance-en-cuba/), sin fecha visible, consultado el 27/09/2026 |
| 📌 Freelancer Android en España | **27,50 €/hora** | [Yeeply](https://yeeply.com/blog/desarrollo-de-apps/cuanto-cuesta-crear-una-app/), agosto de 2026 |
| 📌 App móvil básica hecha por agencia (Latinoamérica) | **5 000–15 000 USD** | [ColombiaGames](https://colombiagames.com/cuanto-cuesta-desarrollar-una-aplicacion-movil/), marzo de 2026 |
| 📌 Salario medio estatal en Cuba | **7 074 CUP/mes** (abril de 2026) ≈ 9,6 USD | ONEI, citada por [Directorio Cubano](https://www.directoriocubano.info/actualidad/onei-revela-los-salarios-por-sectores-en-cuba-estos-son-los-mejor-y-peor-pagados-en-2026/), 25/06/2026 |
| 📌 Salario mínimo | **3 210 CUP/mes** desde julio de 2026 ≈ 4,3 USD | [CubaFull](https://www.cubafull.com/noticia/nuevo-salario-minimo-cuba), 04/07/2026 |

🧮 **Tarifa horaria implícita en Cuba (estimación propia):**
- Un sitio WordPress de 100–300 USD en Revolico supone unas 20–40 horas de trabajo, es decir, **~5–10 USD/hora**.
- Para trabajo nativo en Kotlin, a medida y con backend, un profesional cualificado puede pedir **~8–15 USD/hora** a clientes locales que pagan en divisas.
- Esto es **3–10 veces menos** que el freelance internacional (20–100 USD/h) y **15–40 veces menos** que una agencia latinoamericana.

**No encontré precios publicados de apps Android a medida para clientes cubanos.** Los rangos de Android son una 🧮 **estimación**: horas típicas por complejidad × 8–15 USD/h, contrastadas con la puja de 2 075 USD de Freelancer.com para una app Kotlin con pagos.

---

## 3. Aplicación web — rangos estimados

| Complejidad | Qué incluye | Horas 🧮 |
|---|---|---|
| **Baja** | Landing, catálogo, sitio institucional o tienda WordPress/WooCommerce | 20–50 h |
| **Media** | Backend propio, base de datos, usuarios con roles, panel de administración, reportes | 60–150 h |
| **Alta** | Autenticación avanzada (2FA), pagos (Transfermóvil/EnZona/Tropipay/Stripe), APIs externas, tiempo real, auditoría y copias de seguridad (nivel **IPV Fichas de Costo**) | 200–450 h |

| Rango USD | CUP (cálculo) | EUR | MLC | CAD | MXN | Zelle | CLA |
|---|---|---|---|---|---|---|---|
| **Baja** · 150–400 USD | 150 × 740 = **111 000** · 400 × 740 = **296 000** | 132–352 | 238–634 | 233–620 | 2,121–5,655 | 155–412 | 164–438 |
| **Media** · 500–1,500 USD | 500 × 740 = **370 000** · 1,500 × 740 = **1 110 000** | 440–1,321 | 792–2,376 | 775–2,326 | 7,069–21,207 | 515–1,545 | 548–1,643 |
| **Alta** · 2,000–5,000 USD | 2,000 × 740 = **1 480 000** · 5,000 × 740 = **3 700 000** | 1,762–4,405 | 3,168–7,921 | 3,101–7,752 | 28,277–70,692 | 2,061–5,152 | 2,191–5,476 |

**Por qué tiene sentido:**
- **Baja (150–400 USD):** coincide con los anuncios reales de Revolico (📌 100–300 USD). Está pensada para mipymes y trabajadores por cuenta propia que ya facturan en divisas.
- **Media y alta:** multiplican las horas por 8–15 USD/h (🧮). Aun así quedan muy por debajo de una agencia extranjera, que es la competencia real cuando el cliente paga desde el exterior con remesas o Zelle.
- **Poder adquisitivo:** una web «media» de 500 USD (370 000 CUP) equivale a **52 salarios medios estatales**. Por eso el cliente natural es:
  - una **mipyme**, porque cobra en USD o en precios dolarizados;
  - un **cliente con remesas**;
  - una **entidad estatal** que paga en CUP por transferencia según su presupuesto.
  
  A una persona que vive de un salario en CUP este servicio le resulta inalcanzable.

## 4. Aplicación Android nativa (Android Studio + Kotlin) — rangos estimados

| Complejidad | Qué incluye | Horas 🧮 |
|---|---|---|
| **Baja** | App de catálogo o informativa, pocas pantallas, datos locales | 30–60 h |
| **Media** | Consumo de API, inicio de sesión, modo sin conexión, notificaciones | 100–200 h |
| **Alta** | Cifrado en Keystore, biometría, fijación de certificados, pagos, tiempo real, sincronización (nivel **IPV Android**) | 250–500 h |

| Rango USD | CUP (cálculo) | EUR | MLC | CAD | MXN | Zelle | CLA |
|---|---|---|---|---|---|---|---|
| **Baja** · 300–800 USD | 300 × 740 = **222 000** · 800 × 740 = **592 000** | 264–705 | 475–1,267 | 465–1,240 | 4,241–11,311 | 309–824 | 329–876 |
| **Media** · 1,000–2,500 USD | 1,000 × 740 = **740 000** · 2,500 × 740 = **1 850 000** | 881–2,202 | 1,584–3,960 | 1,550–3,876 | 14,138–35,346 | 1,030–2,576 | 1,095–2,738 |
| **Alta** · 3,000–7,000 USD | 3,000 × 740 = **2 220 000** · 7,000 × 740 = **5 180 000** | 2,643–6,167 | 4,753–11,089 | 4,651–10,853 | 42,415–98,968 | 3,091–7,212 | 3,286–7,667 |

**Por qué Android cuesta más que la web:**
- Kotlin nativo exige más horas por pantalla y pruebas en varios dispositivos y versiones de Android.
- Hay que firmar y distribuir el APK. En Cuba no se accede de forma normal a Google Play, así que se distribuye por Apklis o de forma directa.
- Hay menos desarrolladores Kotlin nativos que de WordPress.
- En 🧮 la complejidad **baja** se ha bajado frente a la media internacional, porque competiría con apps «envoltorio» de la web, que cuestan menos.

---

## 5. Venta por licencia de uso por período

**Alternativa a la venta única:** el cliente no compra el código. Paga el derecho de uso durante un período, y cada licencia queda atada a **un dispositivo**:
- la **PC donde corre el servidor** (la web la usan todos los equipos de la red local);
- **cada teléfono** con la app Android.

### Criterios de precio 🧮
- **Referencia mensual:**
  - **Web: 18 USD al mes** (13 320 CUP). Es ≈ 1,9 salarios medios estatales y menos del 2 % de la facturación típica de una mipyme pequeña.
  - **Android: 8 USD al mes por teléfono.** Es un precio más bajo porque es un complemento del servidor.
- **La semana es una «prueba pagada»:** es más cara en proporción, para que nadie viva de semanas sueltas.
- **Descuento por pagar por adelantado:** 11–12 % en 3 meses, 17–19 % en 6 meses, 27–28 % en 1 año y 36–38 % en 2 años.
- **Recuperación de la inversión:** con 1 año de licencia Web + 3 teléfonos (160 + 3 × 70 = **370 USD**), un solo cliente paga lo que costaría una web «media» a medida. Además el código sigue siendo suyo y la renta es recurrente.

### IPV Web (servidor/PC) — por equipo servidor

| Plan | Días | USD | Descuento vs. mensual | CUP (USD × 740) | EUR | MLC | Zelle | CLA | USD/mes equivalente |
|---|---|---|---|---|---|---|---|---|---|
| 1 Semana | 7 | **6** | +43% (prueba) | 6 × 740 = **4 440** | 5.29 | 9.51 | 6.18 | 6.57 | 25.71 |
| 1 Mes | 30 | **18** | — | 18 × 740 = **13 320** | 15.86 | 28.52 | 18.55 | 19.71 | 18.00 |
| 3 Meses | 90 | **48** | −11 % | 48 × 740 = **35 520** | 42.29 | 76.04 | 49.46 | 52.57 | 16.00 |
| 6 Meses | 180 | **90** | −17 % | 90 × 740 = **66 600** | 79.29 | 142.58 | 92.73 | 98.57 | 15.00 |
| 1 Año | 365 | **160** | −27 % | 160 × 740 = **118 400** | 140.95 | 253.47 | 164.85 | 175.24 | 13.15 |
| 2 Años | 730 | **280** | −36 % | 280 × 740 = **207 200** | 246.67 | 443.57 | 288.49 | 306.67 | 11.51 |

### IPV Android — por teléfono

| Plan | Días | USD | Descuento vs. mensual | CUP (USD × 740) | EUR | MLC | Zelle | CLA | USD/mes equivalente |
|---|---|---|---|---|---|---|---|---|---|
| 1 Semana | 7 | **3** | +61% (prueba) | 3 × 740 = **2 220** | 2.64 | 4.75 | 3.09 | 3.29 | 12.86 |
| 1 Mes | 30 | **8** | — | 8 × 740 = **5 920** | 7.05 | 12.67 | 8.24 | 8.76 | 8.00 |
| 3 Meses | 90 | **21** | −12 % | 21 × 740 = **15 540** | 18.50 | 33.27 | 21.64 | 23.00 | 7.00 |
| 6 Meses | 180 | **39** | −19 % | 39 × 740 = **28 860** | 34.36 | 61.78 | 40.18 | 42.72 | 6.50 |
| 1 Año | 365 | **70** | −28 % | 70 × 740 = **51 800** | 61.67 | 110.89 | 72.12 | 76.67 | 5.75 |
| 2 Años | 730 | **120** | −38 % | 120 × 740 = **88 800** | 105.71 | 190.10 | 123.64 | 131.43 | 4.93 |

**Sugerencias de política comercial:**
- **Paquete Web + Android:** se puede aplicar un 10 % de descuento sobre la suma.
- **Entidades estatales:** que paguen en CUP por transferencia, recalculando al tipo del día y con factura.
- **Renovación anticipada:** los días que le quedaban a la licencia no se suman automáticamente. Si quiere respetarlos, emita la nueva licencia con el plan inmediatamente superior.
- **Contrato:** incluya soporte y actualizaciones durante la vigencia. Si no hay renovación, el sistema se bloquea pero **los datos siguen siendo del cliente**. Entregue sus copias de seguridad si las pide.

---

## 6. Cómo funciona el sistema de licencias

```
 Cliente (PC o móvil)                       Usted (proveedor)
 ────────────────────                       ─────────────────
 1. La app entra en la vista de Licencia
    (sin licencia activada o vencida):
    Usuario · Plan · ID Dispositivo
    (IPVW-… en PC / IPVA-… en móvil)
 2. Botón «Generar solicitud y enviarla     ► 3. Pega Usuario, ID Dispositivo y Plan
    por WhatsApp»                              en el Keygen → «Generar licencia»
                                               (queda registrada en el CSV)
 5. Pega la licencia en la vista de       ◄──── 4. Botón «Enviar licencia por WhatsApp»
    Licencia y pulsa «Activar»                 (IPV1.…)
```

**ID del dispositivo, cifrado:** el identificador de hardware nunca sale del equipo. Lo que se envía es un **resumen SHA-256 con sal**, irreversible, más dos dígitos de control que detectan errores al copiarlo.

| Equipo | Identificador usado |
|---|---|
| PC / portátil Windows | `MachineGuid` del registro (no cambia al reinstalar la aplicación) |
| Linux | `/etc/machine-id` |
| Android | `Settings.Secure.ANDROID_ID`. **No el IMEI:** desde Android 10 ninguna app normal puede leerlo (es un permiso reservado al sistema). `ANDROID_ID` es único por teléfono y sobrevive a la reinstalación de la app. Cambia solo si se restablece el teléfono de fábrica, y entonces se emite una licencia nueva |

**Seguridad de la licencia:**
- Va **firmada con ECDSA P-256**. La clave privada está solo en su Keygen, cifrada con su contraseña (PBKDF2, 600 000 iteraciones).
- Las apps solo tienen la clave pública. Con ella pueden comprobar una licencia, pero no fabricarla.
- **Se rechaza** si:
  - cambia una sola letra (plan, fecha, usuario);
  - es de otro equipo;
  - es de la otra app (Web o Android);
  - está vencida;
  - se atrasa el reloj más de 1 día respecto a la última fecha vista.
- **Verificado:**
  - la firma Python es 100 % compatible con OpenSSL y con `SHA256withECDSA` de Java/Android;
  - Kotlin y Python calculan el mismo código de dispositivo;
  - 5 pruebas automáticas cubren la firma, el servidor y el Keygen.

**Límites honestos:**
- Ninguna licencia instalada en el equipo del cliente es imposible de romper.
- **Servidor:** es código Python legible. Alguien con conocimientos podría borrar la comprobación. Para dificultarlo, distribuya el servidor compilado (**PyInstaller** o **Nuitka**), sin los `.py`.
- **Android:** active R8/ofuscación en la versión *release*, que ya está configurada en `proguard-rules.pro`.
- La licencia protege contra la copia casual y el uso sin pagar, que es el riesgo real en este mercado. No resiste un ataque experto.

### Puesta en marcha (una sola vez)

```powershell
python keygen\keygen.py init --whatsapp 53XXXXXXXX   # crea la clave (le pedirá una contraseña)
# → escribe la clave pública y su WhatsApp en licencia.py y en License.kt
# Vuelva a compilar el APK y a distribuir el servidor.
```

Guarde **`keygen\clave_privada.json` y su contraseña** en dos lugares seguros (por ejemplo, un USB guardado y un gestor de contraseñas). No se suben al repositorio (`.gitignore`). Si los pierde, no podrá renovar licencias. Si se los roban, cualquiera podrá emitirlas: en ese caso ejecute `init --force` y vuelva a distribuir.

### Uso diario

Lo habitual ya no requiere consola: en la aplicación web abra **Creador de Licencias** (menú lateral, solo administradores) para crear la clave, emitir, verificar y consultar el historial sin salir del sistema. El Keygen de escritorio sigue disponible y comparte clave y registro:

```powershell
python keygen\keygen.py                         # interfaz gráfica: Usuario · ID Dispositivo · Plan → Generar
python keygen\keygen.py emitir --usuario "Mipyme X" --codigo IPVW-XXXXX-XXXXX-XXXXX-XXXXX-XX --plan 1A
python keygen\keygen.py verificar --licencia IPV1....
python keygen\keygen.py precios                 # tabla de precios USD/CUP/EUR/MLC/Zelle/CLA
```

- Planes: `1S` (1 semana), `1M` (1 mes), `3M` (3 meses), `6M` (6 meses), `1A` (1 año), `2A` (2 años).
- Todas las licencias quedan en `keygen\registro_licencias.csv` (fecha, serie, usuario, plan, vencimiento, precio en USD y CUP).
- Para actualizar el tipo de cambio, cree `keygen\tasas.json`, por ejemplo: `{"USD": 745, "EUR": 845}`.
