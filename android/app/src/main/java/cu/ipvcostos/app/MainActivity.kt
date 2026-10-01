package cu.ipvcostos.app

import android.app.Activity
import android.app.AlertDialog
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.hardware.biometrics.BiometricPrompt
import android.os.Build
import android.os.Bundle
import android.os.CancellationSignal
import android.view.WindowManager
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
import android.widget.ArrayAdapter
import android.widget.TextView
import android.widget.Toast
import org.json.JSONArray
import org.json.JSONObject
import org.json.JSONTokener
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

/* ==========================================================================
   IPV · Fichas y Costos — Aplicación Android profesional
   Autor: Ing. Yosvany Hernández Quintero
   ========================================================================== */

// ===== Design tokens =====
// Misma identidad visual que la aplicación web (web/styles.css): escala de marca
// verde bosque → esmeralda, acento lima y neutros cálidos. Si cambia la web,
// cambie aquí los mismos valores para que las dos caras se vean iguales.
private val GREEN = 0xFF13382F.toInt()        // --primary      (marca 800)
private val GREEN_DARK = 0xFF0D2A23.toInt()   // --primary-dark (marca 900)
private val GREEN_MID = 0xFF22614E.toInt()    // marca 600
private val GREEN_LIGHT = 0xFF2D7D63.toInt()  // --primary-light(marca 500)
private val GREEN_PALE = 0xFFE7F1EB.toInt()
private val LIME = 0xFFD9EF8F.toInt()         // --accent
private val LIME_VIVID = 0xFFAADB4E.toInt()   // --accent-vivid
private val INK = 0xFF121D1A.toInt()          // --text
private val INK_SOFT = 0xFF3E4F48.toInt()     // --text-2
private val MUTED = 0xFF5C6A63.toInt()        // --text-3 (contraste >= 4.5:1)
private val LINE = 0xFFE3EAE2.toInt()         // --border
private val LINE_STRONG = 0xFFCDD8CB.toInt()  // --border-strong
private val CANVAS = 0xFFF3F7F3.toInt()       // --surface-2
private val SURFACE = 0xFFFFFFFF.toInt()      // --surface
private val SURFACE_SUNKEN = 0xFFEEF3ED.toInt()
private val SUCCESS = 0xFF0F9F74.toInt()      // --green
private val ERROR = 0xFFE0453F.toInt()        // --red
private val WARNING = 0xFFE08B05.toInt()      // --orange
private val BLUE = 0xFF2F6FED.toInt()         // --blue
private val PURPLE = 0xFF7C5CF0.toInt()       // --purple

/** Mismo color con alfa: para fondos tenues de iconos y etiquetas (como los *-glow de la web). */
private fun tint(color: Int, alpha: Int = 26): Int = (alpha shl 24) or (color and 0x00FFFFFF)

private const val APP_VERSION = "1.1.0"

private data class DraftLine(val materialId: Int, val quantity: String)

/**
 * Cliente HTTP de la API IPV.
 * · Envía el JWT en cada solicitud y lo renueva automáticamente (rotación de refresh token).
 * · Si no hay red, no se sirven datos antiguos: permisos y licencia exigen servidor.
 */
private class IpvApi(private val activity: Activity) {
    private val preferences = activity.getSharedPreferences("ipv_settings", Activity.MODE_PRIVATE)
    val session = Session(activity)
    // Eliminar la caché de versiones anteriores: ya no se usan datos sin
    // comprobar licencia y permisos con el servidor.
    val cache = OfflineCache(activity).apply { clear() }
    val pinner = CertificatePinner(activity)
    private val license = LicenseManager(activity)

    var baseUrl: String
        get() = preferences.getString("base_url", "https://10.0.2.2:8443")!!.trimEnd('/')
        set(value) { preferences.edit().putString("base_url", value.trim().trimEnd('/')).apply() }

    var biometricLock: Boolean
        get() = preferences.getBoolean("biometric_lock", false)
        set(value) { preferences.edit().putBoolean("biometric_lock", value).apply() }

    private fun raw(method: String, path: String, body: JSONObject?, auth: Boolean): Pair<Int, String> {
        val connection = (URL(baseUrl + path).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 10000
            readTimeout = 15000
            useCaches = false
            pinner.apply(this)
            setRequestProperty("Accept", "application/json")
            setRequestProperty("User-Agent", "IPV-FichasCostos/$APP_VERSION (Android)")
            if (auth) session.accessToken?.let { setRequestProperty("Authorization", "Bearer $it") }
            if (body != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/json; charset=utf-8")
            }
        }
        try {
            val code = try {
                if (body != null) connection.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
                connection.responseCode
            } catch (error: javax.net.ssl.SSLException) {
                val seen = pinner.lastMismatch ?: throw error
                throw PinMismatchException("⚠ El certificado del servidor no coincide con el fijado (${pinner.pretty(seen).take(23)}…). Posible interceptación: conexión bloqueada.")
            }
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            return code to (stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() } ?: "{}")
        } finally {
            connection.disconnect()
        }
    }

    private fun errorOf(code: Int, text: String): String =
        try { JSONObject(text).optString("error", "Error HTTP $code") } catch (_: Exception) { "Error HTTP $code" }

    @Synchronized
    private fun renew(): Boolean {
        val refresh = session.refreshToken ?: return false
        val (code, text) = raw("POST", "/api/auth/refresh", JSONObject().put("refresh_token", refresh), false)
        if (code != 200) { session.clear(); cache.clear(); return false }
        session.save(JSONObject(text))
        return true
    }

    fun login(email: String, password: String, otp: String = ""): JSONObject {
        if (LicenseCore.enforced && !license.isValid()) throw IOException("La licencia del móvil no está vigente.")
        val (code, text) = raw("POST", "/api/auth/login",
            JSONObject().put("email", email).put("password", password).put("otp", otp), false)
        if (code == 401 && runCatching { JSONObject(text).optBoolean("mfa_required") }.getOrDefault(false)) {
            throw MfaRequiredException(errorOf(code, text))
        }
        if (code != 200) throw IOException(errorOf(code, text))
        val data = JSONObject(text)
        cache.clear() // Nunca reutilizar datos cifrados de otro usuario/rol.
        session.save(data)
        return data
    }

    /** Cambia la contraseña; el servidor devuelve tokens nuevos para ESTE dispositivo. */
    fun changePassword(current: String, new: String): JSONObject {
        val data = request("POST", "/api/auth/password", JSONObject().put("current", current).put("new", new)) as JSONObject
        session.save(data)
        return data
    }

    fun sessions(): JSONArray = request("GET", "/api/auth/sessions") as JSONArray

    fun closeSession(id: String) {
        request("DELETE", "/api/auth/sessions/" + java.net.URLEncoder.encode(id, "UTF-8"))
    }

    fun closeOtherSessions(): Int =
        (request("POST", "/api/auth/sessions/revoke-others", JSONObject()) as JSONObject).optInt("closed")

    fun logout() {
        val refresh = session.refreshToken
        if (refresh != null) runCatching { raw("POST", "/api/auth/logout", JSONObject().put("refresh_token", refresh), true) }
        session.clear()
        cache.clear()
    }

    fun request(method: String, path: String, body: JSONObject? = null): Any {
        // Cada respuesta se obtiene del servidor: no se leen datos de la antigua
        // caché cuando puedan haber cambiado el rol o la licencia.
        if (LicenseCore.enforced && !license.isValid()) throw IOException("La licencia del móvil no está vigente.")
        var (code, text) = raw(method, path, body, true)
        if (code == 401 && renew()) {
            val retry = raw(method, path, body, true)
            code = retry.first; text = retry.second
        }
        if (code == 401) { cache.clear(); throw AuthRequiredException(errorOf(code, text)) }
        if (code == 403 && runCatching { JSONObject(text).optBoolean("password_expired") }.getOrDefault(false)) {
            throw PasswordExpiredException(errorOf(code, text))
        }
        if (code !in 200..299) {
            if (code == 402 || code == 403) cache.clear()
            throw if (code == 402) LicenseServerException(errorOf(code, text))
                  else if (code == 403) PermissionDeniedException(errorOf(code, text))
                  else IOException(errorOf(code, text))
        }
        return JSONTokener(text).nextValue()
    }
}

class MainActivity : Activity() {
    private lateinit var api: IpvApi
    private lateinit var root: LinearLayout
    private lateinit var content: LinearLayout
    private lateinit var connectionLabel: TextView
    private lateinit var statsButton: View
    private val executor: ExecutorService = Executors.newSingleThreadExecutor()
    private var currentTab = "Resumen"
    private var dashboard = JSONObject()
    private var products = JSONArray()
    private var materials = JSONArray()
    private var fichas = JSONArray()
    private var controls = JSONArray()
    private var inventory = JSONObject()
    private var trash = JSONArray()
    private val tabs = listOf("Resumen", "Productos", "Valores IPV", "Inventario", "Fichas", "Controles", "Papelera", "Licencia")

    private var realtime: RealtimeClient? = null
    private var unlocked = false
    private lateinit var license: LicenseManager
    private var licenseDialog: AlertDialog? = null
    private var licenseNoticeShown = false
    private var licenseAction: (() -> Unit)? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        api = IpvApi(this)
        // Datos financieros: se impide capturar la pantalla y mostrarla en "recientes"
        window.setFlags(WindowManager.LayoutParams.FLAG_SECURE, WindowManager.LayoutParams.FLAG_SECURE)
        window.statusBarColor = GREEN_DARK
        window.navigationBarColor = GREEN_DARK
        buildShell()
        realtime = RealtimeClient({ api.baseUrl }, { api.session.accessToken }, { api.pinner.apply(it) }) { event ->
            runOnUiThread {
                toast("🔔 ${event.optString("action").replace('_', ' ').lowercase()}")
                refresh(silent = true)
            }
        }
        license = LicenseManager(this)
        licenseGate { unlockThen { refresh() } }
    }

    override fun onResume() {
        super.onResume()
        // La licencia puede vencer con la app abierta o en segundo plano
        if (unlocked && !license.isValid()) {
            realtime?.stop(); unlocked = false
            licenseGate { unlockThen { refresh() } }
            return
        }
        if (unlocked) realtime?.start()
    }

    override fun onPause() {
        realtime?.stop()
        super.onPause()
    }

    override fun onDestroy() {
        realtime?.stop()
        executor.shutdown()
        super.onDestroy()
    }

    // ==================== Seguridad: biometría y sesión ====================

    private fun unlockThen(action: () -> Unit) {
        if (!api.biometricLock || !api.session.isLoggedIn || Build.VERSION.SDK_INT < Build.VERSION_CODES.P) {
            unlocked = true; realtime?.start(); action(); return
        }
        showBiometricPrompt(action)
    }

    @android.annotation.TargetApi(Build.VERSION_CODES.P)
    private fun showBiometricPrompt(action: () -> Unit) {
        val cancel = CancellationSignal()
        BiometricPrompt.Builder(this)
            .setTitle("IPV · Fichas y Costos")
            .setSubtitle("Confirme su identidad para acceder")
            .setNegativeButton("Salir", mainExecutor) { _, _ -> finish() }
            .build()
            .authenticate(cancel, mainExecutor, object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult?) {
                    unlocked = true; realtime?.start(); action()
                }
                override fun onAuthenticationError(errorCode: Int, errString: CharSequence?) {
                    toast(errString?.toString() ?: "Autenticación cancelada.")
                    finish()
                }
            })
    }

    private var loginOpen = false

    private fun openLogin(message: String? = null) {
        if (loginOpen) return
        loginOpen = true
        val form = formContainer()
        val pinEstado = if (api.pinner.pin != null) "certificado fijado" else "primera conexión: se fijará el certificado"
        addText(form, "🔒 Acceso seguro · ${api.baseUrl}\n$pinEstado", 11f, MUTED, false, bottom = 8)
        if (message != null) addText(form, message, 11f, ERROR, true, bottom = 8)
        val email = field(form, "Correo electrónico", InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_EMAIL_ADDRESS)
        val password = field(form, "Contraseña", InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD)
        val otpLabel = label("Código de verificación (app autenticadora o de recuperación)", 10f, PURPLE, true)
        val otp = EditText(this).apply {
            hint = "123456"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
            textSize = 18f
            gravity = Gravity.CENTER
            letterSpacing = 0.25f
            setPadding(dp(12), dp(10), dp(12), dp(10))
            background = rounded(SURFACE, 12, PURPLE)
            setTextColor(INK)
        }
        otpLabel.visibility = View.GONE
        otp.visibility = View.GONE
        form.addView(otpLabel)
        form.addView(otp, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(10) })
        addText(form, "La sesión se guarda cifrada con Android Keystore. Tras 5 intentos fallidos la cuenta se bloquea 15 minutos.", 10f, MUTED)
        val dialog = showFormDialog("Iniciar sesión", scrollForm(form), "Entrar") { dialog ->
            val button = dialog.getButton(AlertDialog.BUTTON_POSITIVE)
            button.isEnabled = false
            val e = email.text.toString().trim()
            val pw = password.text.toString()
            val code = otp.text.toString().trim()
            executor.execute {
                try {
                    val data = api.login(e, pw, code)
                    runOnUiThread {
                        loginOpen = false
                        dialog.dismiss()
                        triggerHapticFeedback()
                        toast("Bienvenido, ${data.getJSONObject("user").optString("name")}")
                        realtime?.stop(); realtime?.start()
                        showLoginNotices(data)
                        if (data.optBoolean("password_expired")) openPasswordChange(forced = true) else refresh()
                    }
                } catch (error: MfaRequiredException) {
                    runOnUiThread {
                        button.isEnabled = true
                        if (otp.visibility == View.VISIBLE) otp.setText("")
                        otpLabel.visibility = View.VISIBLE
                        otp.visibility = View.VISIBLE
                        otp.requestFocus()
                        toast(error.message ?: "Introduzca el código de verificación.")
                    }
                } catch (error: Exception) {
                    runOnUiThread {
                        button.isEnabled = true
                        if (otp.visibility == View.VISIBLE) otp.setText("") else password.setText("")
                        toast(error.message ?: "No se pudo iniciar sesión.")
                    }
                }
            }
        }
        dialog.setCancelable(false)
        dialog.getButton(AlertDialog.BUTTON_NEGATIVE).setOnClickListener {
            loginOpen = false
            dialog.dismiss()
            openSettings()
        }
        dialog.getButton(AlertDialog.BUTTON_NEGATIVE).text = "Servidor"
    }

    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    private fun rounded(color: Int, radius: Int = 14, stroke: Int? = null): GradientDrawable = GradientDrawable().apply {
        setColor(color)
        cornerRadius = dp(radius).toFloat()
        if (stroke != null) setStroke(dp(1), stroke)
    }

    /** Degradado redondeado (equivalente a los --gradient-* de la web). */
    private fun gradient(
        colors: IntArray,
        radius: Int = 14,
        orientation: GradientDrawable.Orientation = GradientDrawable.Orientation.TL_BR
    ): GradientDrawable = GradientDrawable(orientation, colors).apply {
        cornerRadius = dp(radius).toFloat()
    }

    /** Pastilla circular (bordes totalmente redondeados) para etiquetas y pestañas. */
    private fun pill(color: Int, stroke: Int? = null): GradientDrawable = rounded(color, 20, stroke)

    private fun label(value: String, size: Float = 14f, color: Int = INK, bold: Boolean = false): TextView = TextView(this).apply {
        text = value
        textSize = size
        setTextColor(color)
        if (bold) setTypeface(typeface, Typeface.BOLD)
        includeFontPadding = true
    }

    private fun makeButton(value: String, primary: Boolean = false, click: () -> Unit): Button = Button(this).apply {
        text = value
        textSize = 12.5f
        isAllCaps = false
        setTextColor(if (primary) Color.WHITE else GREEN_LIGHT)
        // Primario: mismo degradado que el .primary-btn de la web; secundario: superficie con borde.
        background = if (primary) gradient(intArrayOf(GREEN, GREEN_MID, GREEN_LIGHT), 12)
                     else rounded(SURFACE, 12, LINE_STRONG)
        elevation = if (primary) dp(3).toFloat() else dp(1).toFloat()
        stateListAnimator = null
        minHeight = dp(46)
        setPadding(dp(16), dp(3), dp(16), dp(3))
        setOnClickListener { click() }
    }

    private fun buildShell() {
        root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(CANVAS)
        }

        // Header with accent stripe
        val accentStripe = View(this).apply {
            minimumHeight = dp(4)
            background = GradientDrawable(GradientDrawable.Orientation.LEFT_RIGHT, intArrayOf(LIME_VIVID, LIME, GREEN_LIGHT))
        }
        root.addView(accentStripe, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(4)))

        val header = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(18), dp(16), dp(12), dp(16))
            // Degradado de marca igual al de la barra lateral de la web.
            background = GradientDrawable(
                GradientDrawable.Orientation.TL_BR,
                intArrayOf(GREEN_DARK, GREEN, GREEN_LIGHT)
            )
            elevation = dp(6).toFloat()
        }
        val brand = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val logo = label("iv   IPV", 20f, LIME, true).apply { letterSpacing = 0.01f }
        val subtitle = label("FICHAS Y COSTOS · GESTIÓN INTEGRAL", 9f, 0xFFC6D8CD.toInt(), true).apply { letterSpacing = 0.12f }
        brand.addView(logo)
        brand.addView(subtitle)
        header.addView(brand, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))

        val statsBtn = makeButton("📊", false) { openStatistics() }.apply {
            setTextColor(Color.WHITE)
            background = rounded(0x26FFFFFF, 12, 0x33FFFFFF)
            elevation = 0f
            minWidth = dp(46)
            contentDescription = "Estadísticas"
        }
        statsButton = statsBtn
        header.addView(statsBtn)

        val aboutBtn = makeButton("ℹ", false) { openAbout() }.apply {
            setTextColor(Color.WHITE)
            background = rounded(0x26FFFFFF, 12, 0x33FFFFFF)
            elevation = 0f
            minWidth = dp(46)
            contentDescription = "Acerca de IPV"
        }
        header.addView(aboutBtn)

        val settings = makeButton("⚙", false) { openSettings() }.apply {
            setTextColor(Color.WHITE)
            background = rounded(0x26FFFFFF, 12, 0x33FFFFFF)
            elevation = 0f
            minWidth = dp(46)
            contentDescription = "Configuración"
        }
        header.addView(settings)
        root.addView(header)

        // Connection indicator
        connectionLabel = label("Conectando…", 10.5f, MUTED, true).apply {
            setPadding(dp(18), dp(9), dp(18), dp(9))
            setBackgroundColor(SURFACE_SUNKEN)
        }
        root.addView(connectionLabel)

        // Tab navigation
        val horizontal = HorizontalScrollView(this).apply { isHorizontalScrollBarEnabled = false; setBackgroundColor(SURFACE) }
        val nav = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(dp(10), dp(8), dp(10), dp(10))
            setBackgroundColor(SURFACE)
        }
        tabs.forEach { tab ->
            val navButton = TextView(this).apply {
                text = tab
                textSize = 11.5f
                gravity = Gravity.CENTER
                setPadding(dp(14), dp(9), dp(14), dp(9))
                setOnClickListener { currentTab = tab; refresh() }
            }
            navButton.tag = tab
            nav.addView(navButton, LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { rightMargin = dp(3) })
        }
        horizontal.addView(nav)
        root.addView(horizontal)

        // Content area
        val scroll = ScrollView(this).apply { isFillViewport = true; clipToPadding = false }
        content = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(18), dp(16), dp(28))
        }
        scroll.addView(content)
        root.addView(scroll, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        setContentView(root)
        updateTabStyle()
    }

    private fun updateTabStyle() {
        if (::statsButton.isInitialized) statsButton.visibility = if (can("fichas")) View.VISIBLE else View.GONE
        val nav = (root.getChildAt(3) as HorizontalScrollView).getChildAt(0) as LinearLayout
        val tabModule = mapOf("Productos" to "products", "Valores IPV" to "materials",
            "Inventario" to "materials", "Fichas" to "fichas", "Controles" to "controls",
            "Papelera" to "trash")
        if (tabModule[currentTab]?.let { !can(it) } == true) currentTab = "Resumen"
        for (index in 0 until nav.childCount) {
            val item = nav.getChildAt(index) as TextView
            item.visibility = if (tabModule[item.tag as String]?.let { can(it) } == false) View.GONE else View.VISIBLE
            val selected = item.tag == currentTab
            item.setTextColor(if (selected) Color.WHITE else MUTED)
            item.setTypeface(item.typeface, if (selected) Typeface.BOLD else Typeface.NORMAL)
            // Pestaña activa: pastilla con el degradado de marca (como .nav-item.active en la web).
            item.background = if (selected) gradient(intArrayOf(GREEN, GREEN_LIGHT), 20)
                              else pill(SURFACE_SUNKEN, LINE)
        }
    }

    private fun can(module: String, permission: String = "view") = api.session.can(module, permission)

    private fun refresh(silent: Boolean = false) {
        updateTabStyle()
        // La vista de Licencia se dibuja con los datos locales del teléfono, sin API
        if (currentTab == "Licencia") { renderPage(); return }
        // Sin licencia activada o vencida, la app entra primero en la vista de Licencia
        if (LicenseCore.enforced && !license.isValid()) {
            if (!silent) toast("🔒 Sin licencia vigente: genere la solicitud y envíela por WhatsApp.")
            openLicenseView()
            return
        }
        if (!silent) {
            connectionLabel.text = "Conectando a ${api.baseUrl} …"
            connectionLabel.setTextColor(WARNING)
            content.removeAllViews()
            addText(content, "Cargando datos desde la base de datos…", 13f, MUTED)
        }
        executor.execute {
            try {
                val freshDashboard = api.request("GET", "/api/dashboard") as JSONObject
                // Permisos consultados del servidor al iniciar/renovar sesión. No pedir
                // módulos bloqueados ni sustituir un 403 por datos de caché.
                val freshProducts = if (can("products")) api.request("GET", "/api/products") as JSONArray else JSONArray()
                val freshMaterials = if (can("materials")) api.request("GET", "/api/materials") as JSONArray else JSONArray()
                val freshFichas = if (can("fichas")) api.request("GET", "/api/fichas") as JSONArray else JSONArray()
                val freshControls = if (can("controls")) api.request("GET", "/api/controls") as JSONArray else JSONArray()
                val freshInventory = if (can("materials")) api.request("GET", "/api/inventory") as JSONObject else JSONObject()
                val freshTrash = if (can("trash")) api.request("GET", "/api/trash") as JSONObject else JSONObject().put("items", JSONArray())
                runOnUiThread {
                    dashboard = freshDashboard
                    products = freshProducts
                    materials = freshMaterials
                    fichas = freshFichas
                    controls = freshControls
                    inventory = freshInventory
                    trash = freshTrash.optJSONArray("items") ?: JSONArray()
                    val who = api.session.user?.optString("name")?.let { " · $it" } ?: ""
                    connectionLabel.text = "●  Conectado en tiempo real$who"
                    connectionLabel.setTextColor(SUCCESS)
                    renderPage()
                }
            } catch (error: PinMismatchException) {
                runOnUiThread {
                    connectionLabel.text = "●  Conexión bloqueada por seguridad"
                    connectionLabel.setTextColor(ERROR)
                    content.removeAllViews()
                    addHeading(content, "Certificado no reconocido", error.message ?: "")
                    addText(content, "Si el administrador regeneró la autoridad certificadora, actualice la huella en Configuración → Seguridad. En caso contrario, NO continúe: alguien podría estar interceptando la red.", 12f, MUTED)
                    addButton(content, "Abrir configuración", true) { openSettings() }
                }
            } catch (error: PasswordExpiredException) {
                runOnUiThread {
                    connectionLabel.text = "●  Cambio de contraseña requerido"
                    connectionLabel.setTextColor(WARNING)
                    content.removeAllViews()
                    addHeading(content, "Cambie su contraseña", error.message ?: "Su contraseña ha caducado.")
                    addButton(content, "Cambiar contraseña", true) { openPasswordChange(forced = true) }
                    openPasswordChange(forced = true)
                }
            } catch (error: LicenseServerException) {
                runOnUiThread {
                    content.removeAllViews()
                    connectionLabel.text = "●  Licencia del servidor requerida"
                    addHeading(content, "Acceso bloqueado", error.message ?: "Active la licencia del servidor.")
                }
            } catch (error: PermissionDeniedException) {
                runOnUiThread {
                    content.removeAllViews()
                    connectionLabel.text = "●  Permiso denegado"
                    addHeading(content, "Acceso restringido", error.message ?: "Consulte con el administrador.")
                    addButton(content, "Reintentar", false) { refresh() }
                }
            } catch (error: AuthRequiredException) {
                runOnUiThread {
                    connectionLabel.text = "●  Sesión requerida"
                    connectionLabel.setTextColor(WARNING)
                    content.removeAllViews()
                    addHeading(content, "Inicie sesión", "El servidor requiere autenticación para mostrar los datos.")
                    addButton(content, "Iniciar sesión", true) { openLogin() }
                    openLogin(if (api.session.isLoggedIn) error.message else null)
                }
            } catch (error: Exception) {
                runOnUiThread {
                    connectionLabel.text = "●  Sin conexión · ${error.message ?: "verifique la dirección del servidor"}"
                    connectionLabel.setTextColor(ERROR)
                    content.removeAllViews()
                    addHeading(content, "No se pudo conectar", "Verifique que el servidor esté activo y la dirección configurada sea correcta.")
                    addButton(content, "Configurar servidor", true) { openSettings() }
                    addButton(content, "Reintentar", false) { refresh() }
                }
            }
        }
    }

    private fun renderPage() {
        content.removeAllViews()
        when (currentTab) {
            "Resumen" -> renderDashboard()
            "Productos" -> renderProducts()
            "Valores IPV" -> renderMaterials()
            "Inventario" -> renderInventory()
            "Fichas" -> renderFichas()
            "Controles" -> renderControls()
            "Papelera" -> renderTrash()
            "Licencia" -> renderLicensePage()
        }
    }

    // ==================== Dashboard ====================

    private fun renderDashboard() {
        statIndex = 0
        addHeading(content, "Visión general", "Gestión centralizada de costos del IPV.")
        val grid = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        statRow(grid, "Productos activos", dashboard.optString("products", "0"), "Catálogo vigente")
        statRow(grid, "Fichas de costo", dashboard.optString("fichas", "0"), "${dashboard.optString("approved_fichas", "0")} aprobadas")
        statRow(grid, "Controles pendientes", dashboard.optString("pending_controls", "0"), if (dashboard.optInt("pending_controls", 0) > 0) "Requieren revisión" else "Todos al día")
        statRow(grid, "Valores del IPV", dashboard.optString("materials", "0"),
            if (dashboard.optInt("low_stock", 0) > 0) "${dashboard.optInt("low_stock")} bajo mínimo"
            else if (can("materials", "costs")) "Inventario ${formatAmount(dashboard.optString("stock_value", "0"))} CUP" else "Inventario")
        content.addView(grid)

        addSpacer(content, 12)
        addText(content, "FICHAS RECIENTES", 9f, MUTED, true, bottom = 6)
        val recentFichas = dashboard.optJSONArray("recent_fichas") ?: JSONArray()
        val totalFichas = dashboard.optInt("fichas", fichas.length())
        if (recentFichas.length() == 0 && totalFichas == 0) {
            val productCount = dashboard.optInt("products", products.length())
            val materialCount = dashboard.optInt("materials", materials.length())
            addText(content, "Aún no hay fichas registradas.", 11f, MUTED, bottom = 4)
            addText(content, "Primeros pasos", 14f, INK, true, bottom = 4)
            addText(content, "${if (productCount > 0) "✓" else "1."} Registre un producto o servicio desde Productos${if (productCount > 0) " · Completado" else " · Pendiente"}.", 11f, MUTED, bottom = 3)
            addText(content, "${if (materialCount > 0) "✓" else "2."} Añada valores e insumos del IPV${if (materialCount > 0) " · Completado" else " · Pendiente"}.", 11f, MUTED, bottom = 3)
            addText(content, "3. Cree y revise una ficha de costo.", 11f, MUTED, bottom = 8)
            when {
                productCount == 0 && can("products") -> addButton(content, "Ir a Productos", true) { currentTab = "Productos"; refresh() }
                materialCount == 0 && can("materials") -> addButton(content, "Ir a Valores IPV", true) { currentTab = "Valores IPV"; refresh() }
                can("fichas") -> addButton(content, "Ir a Fichas", true) { currentTab = "Fichas"; refresh() }
            }
        } else if (recentFichas.length() == 0) {
            val fichaLabel = if (totalFichas == 1) "ficha" else "fichas"
            addText(content, "Hay $totalFichas $fichaLabel, pero no hay cambios recientes para mostrar.", 11f, MUTED, bottom = 4)
            if (can("fichas")) addButton(content, "Ver fichas", false) { currentTab = "Fichas"; refresh() }
        } else {
            addCount(content, recentFichas.length(), "fichas")
            for (i in 0 until recentFichas.length()) {
                val f = recentFichas.getJSONObject(i)
                val row = card(f.optString("product_name", ""), "${f.optString("status", "")}${if (can("fichas", "costs")) " · ${formatAmount(f.optString("total_cost", "0"))} CUP" else ""}", i + 1)
                row.setOnClickListener { openFichaDetail(f.optInt("id")) }
            }
        }
    }

    // ==================== Products ====================

    private fun renderProducts() {
        addHeading(content, "Productos y servicios", "Catálogo con ficha de costo y rendimiento (comensales / copas).")
        if (can("products", "edit")) addButton(content, "＋  Nuevo producto", true) { openProductForm() }
        addSpacer(content, 6)
        val active = products.toObjectList().filter { it.optInt("active", 1) == 1 }
        if (active.isEmpty()) {
            addText(content, "No hay productos activos en el catálogo.", 11f, MUTED)
        } else {
            addCount(content, active.size, "productos")
            active.forEachIndexed { i, p ->
                val yq = p.optString("last_yield_qty", p.optString("yield_qty", "1"))
                val yu = p.optString("last_yield_unit", p.optString("yield_unit", "unidad"))
                val row = card(p.optString("name", ""), "${p.optString("category", "")} · ${p.optString("code", "")} · rinde $yq $yu", i + 1)
                row.setOnClickListener { openProductDetail(p.optInt("id")) }
            }
        }
    }

    // ==================== Materials ====================

    private fun renderMaterials() {
        addHeading(content, "Valores del IPV", "Insumos, licores, bebidas y servicios. Pulse para editar, ajustar existencias o enviar a la papelera.")
        if (can("materials", "edit")) addButton(content, "＋  Nuevo valor", true) { openMaterialForm() }
        addSpacer(content, 6)
        val list = materials.toObjectList()
        if (list.isEmpty()) {
            addText(content, "No hay valores de referencia registrados.", 11f, MUTED)
        } else {
            addCount(content, list.size, "valores")
            list.forEachIndexed { i, m ->
                val low = m.optString("min_stock", "0").toDoubleOrNull() ?: 0.0
                val stock = m.optString("stock", "0").toDoubleOrNull() ?: 0.0
                val stockNote = if (low > 0 && stock <= low) "⚠ ${m.optString("stock")} ${m.optString("unit")} (mín. ${m.optString("min_stock")})"
                else "${m.optString("stock", "0")} ${m.optString("unit")} en almacén"
                val row = card(m.optString("name", ""),
                    "${if (can("materials", "costs")) formatAmount(m.optString("unit_price", "0")) + " CUP / " else ""}${m.optString("unit", "")} · ${m.optString("category", "Insumos")} · $stockNote", i + 1)
                row.setOnClickListener { openMaterialDetail(m.optInt("id")) }
            }
        }
    }

    // ==================== Fichas ====================

    private fun renderFichas() {
        addHeading(content, "Fichas de costo", "Cada ficha rinde un número de comensales o copas. El inventario indica cuántas se pueden preparar.")
        if (can("fichas", "edit")) addButton(content, "＋  Nueva ficha", true) { openFichaForm() }
        addSpacer(content, 6)
        val list = fichas.toObjectList()
        if (list.isEmpty()) {
            addText(content, "No hay fichas de costo registradas.", 11f, MUTED)
        } else {
            addCount(content, list.size, "fichas")
            list.forEachIndexed { i, f ->
                val yq = f.optString("yield_qty", "1")
                val yu = f.optString("yield_unit", "unidad")
                val fromStock = f.opt("servings_from_stock")
                val stockNote = if (fromStock == null || fromStock.toString() == "null") ""
                else " · inventario ≈ ${f.opt("servings_from_stock")} $yu"
                val row = card("${f.optString("product_name", "")} · v${f.optInt("version", 0)}",
                    "${f.optString("status", "")} · rinde $yq $yu${if (can("fichas", "costs")) " · ${formatAmount(f.optString("total_cost", "0"))} CUP" else ""}$stockNote", i + 1)
                row.setOnClickListener { openFichaDetail(f.optInt("id")) }
            }
        }
    }

    // ==================== Controls ====================

    private fun renderInventory() {
        val totals = inventory.optJSONObject("totals") ?: JSONObject()
        addHeading(content, "Inventario", "Existencias de cada valor del IPV y cuántas raciones o copas se pueden preparar.")
        if (can("materials", "edit")) addButton(content, "＋  Nuevo valor", true) { openMaterialForm() }
        statIndex = 0
        val grid = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        statRow(grid, "Valores", totals.optString("materials", "0"), "${totals.optString("categories", "0")} categorías")
        if (can("materials", "costs")) statRow(grid, "Valor del almacén", formatAmount(totals.optString("stock_value", "0")) + " CUP", "existencias × precio")
        statRow(grid, "Bajo mínimo", totals.optString("low_stock", "0"), if (totals.optInt("low_stock", 0) > 0) "Requieren reposición" else "Todo en orden")
        content.addView(grid)
        addSpacer(content, 10)
        val items = inventory.optJSONArray("items") ?: JSONArray()
        if (items.length() == 0) {
            addText(content, "Inventario vacío. Cargue datos de prueba desde la web o registre valores.", 11f, MUTED)
        } else {
            addCount(content, items.length(), "ítems")
            items.toObjectList().forEachIndexed { i, m ->
                val used = m.optJSONArray("used_by") ?: JSONArray()
                val first = if (used.length() > 0) {
                    val u = used.getJSONObject(0)
                    " · ${u.optString("product_name")} ≈ ${u.opt("servings")} ${u.optString("yield_unit")}"
                } else ""
                val row = card(m.optString("name", ""),
                    "${m.optString("stock")} ${m.optString("unit")} · mín. ${m.optString("min_stock")}${if (can("materials", "costs")) " · ${formatAmount(m.optString("stock_value", "0"))} CUP" else ""}$first", i + 1)
                row.setOnClickListener { openMaterialDetail(m.optInt("id")) }
            }
        }
    }

    private fun renderTrash() {
        addHeading(content, "Papelera de reciclaje", "Restaure lo eliminado o bórrelo definitivamente. Nada se pierde por accidente.")
        val list = trash.toObjectList()
        if (list.isEmpty()) {
            addText(content, "La papelera está vacía.", 11f, MUTED)
        } else {
            if (can("trash", "edit")) addButton(content, "Vaciar papelera", false) { emptyTrash() }
            addCount(content, list.size, "elementos")
            list.forEachIndexed { i, t ->
                val row = card("${t.optString("kind_label")}: ${t.optString("name")}",
                    listOf(t.optString("code"), t.optString("detail"), t.optString("deleted_at")).filter { it.isNotBlank() }.joinToString(" · "), i + 1)
                if (can("trash", "edit") && can(t.optString("kind"), "edit")) row.setOnClickListener {
                    AlertDialog.Builder(this)
                        .setTitle(t.optString("name"))
                        .setMessage("¿Restaurar este elemento o eliminarlo para siempre?")
                        .setPositiveButton("Restaurar") { _, _ -> restoreTrash(t.optString("kind"), t.optInt("id")) }
                        .setNeutralButton("Eliminar") { _, _ -> purgeTrash(t.optString("kind"), t.optInt("id")) }
                        .setNegativeButton("Cancelar", null)
                        .show()
                }
            }
        }
    }

    private fun renderControls() {
        addHeading(content, "Controles de IPV", "Instantáneas de verificación vinculadas a fichas aprobadas.")
        val list = controls.toObjectList()
        if (list.isEmpty()) {
            addText(content, "No hay controles registrados. Genera uno desde una ficha aprobada.", 11f, MUTED)
        } else {
            addCount(content, list.size, "controles")
            list.forEachIndexed { i, c ->
                val row = card(c.optString("code", ""), "${c.optString("product_name", "")} · ${c.optString("period", "")} · ${c.optString("status", "")}", i + 1)
                row.setOnClickListener { openControlDetail(c.optInt("id")) }
            }
        }
    }

    // ==================== UI Helpers ====================

    private fun addText(parent: LinearLayout, value: String, size: Float = 12f, color: Int = INK, bold: Boolean = false, bottom: Int = 4) {
        val tv = label(value, size, color, bold)
        tv.setPadding(0, 0, 0, dp(bottom))
        parent.addView(tv)
    }

    private fun addHeading(parent: LinearLayout, title: String, subtitle: String) {
        addText(parent, title, 21f, INK, true, bottom = 3)
        addText(parent, subtitle, 11.5f, MUTED, false, bottom = 14)
    }

    /** Contador de la lista: «▤ 33 ítems». Así se sabe cuántos hay sin contar a mano. */
    private fun addCount(parent: LinearLayout, total: Int, label: String) {
        addText(parent, "▤  $total $label", 10f, MUTED, true, bottom = 8)
    }

    private fun addSpacer(parent: LinearLayout, height: Int) {
        parent.addView(View(this).apply { minimumHeight = dp(height) }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(height)))
    }

    private fun addButton(parent: LinearLayout, value: String, primary: Boolean, click: () -> Unit) {
        val btn = makeButton(value, primary, click)
        parent.addView(btn, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(8) })
    }

    /** Tarjeta de un listado. [index] > 0 pinta el Id de orden delante del título (1, 2, 3…). */
    private fun card(title: String, subtitle: String, index: Int = 0): LinearLayout {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(15), dp(16), dp(15))
            background = rounded(SURFACE, 16, LINE)
            isClickable = true
            isFocusable = true
            elevation = dp(2).toFloat()
        }
        // Franja de acento: misma pista visual que el borde superior de las tarjetas web.
        val stripe = View(this).apply {
            background = GradientDrawable(
                GradientDrawable.Orientation.LEFT_RIGHT,
                intArrayOf(LIME_VIVID, GREEN_LIGHT)
            ).apply { cornerRadius = dp(2).toFloat() }
        }
        row.addView(stripe, LinearLayout.LayoutParams(dp(36), dp(3)).apply { bottomMargin = dp(10) })
        row.addView(label(if (index > 0) "$index.  $title" else title, 14.5f, INK, true))
        row.addView(label(subtitle, 10.5f, MUTED).apply { setPadding(0, dp(5), 0, 0) })
        content.addView(row, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(10) })
        return row
    }

    private var statIndex = 0
    private fun statRow(parent: LinearLayout, title: String, value: String, note: String) {
        val accentColors = intArrayOf(SUCCESS, BLUE, WARNING, PURPLE)
        val accent = accentColors[statIndex % accentColors.size]
        statIndex++

        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(14), dp(14), dp(16), dp(14))
            background = rounded(SURFACE, 16, LINE)
            elevation = dp(2).toFloat()
        }
        // Indicador de color + halo tenue: réplica del .stat-icon de la web.
        val indicator = View(this).apply { background = rounded(accent, 3) }
        val indicatorBox = LinearLayout(this).apply {
            gravity = Gravity.CENTER
            background = rounded(tint(accent, 28), 12)
            addView(indicator, LinearLayout.LayoutParams(dp(4), dp(22)))
        }
        row.addView(indicatorBox, LinearLayout.LayoutParams(dp(34), dp(38)).apply { rightMargin = dp(12) })
        val left = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        left.addView(label(title, 11.5f, INK_SOFT, true))
        left.addView(label(note, 9.5f, MUTED).apply { setPadding(0, dp(3), 0, 0) })
        row.addView(left, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        row.addView(label(value, 25f, INK, true))
        parent.addView(row, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(8) })
    }

    /** Importes en formato $ 3,163,138.00 CUP: $ delante, miles con coma y decimales con punto. */
    private fun formatAmount(value: String): String {
        val n = value.toDoubleOrNull() ?: 0.0
        val fmt = java.text.NumberFormat.getNumberInstance(java.util.Locale.US)
        fmt.minimumFractionDigits = 2
        fmt.maximumFractionDigits = 2
        return "$ " + fmt.format(n)
    }

    private fun formContainer(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(4), dp(4), dp(4), dp(4))
    }

    private fun field(parent: LinearLayout, hint: String, inputType: Int = InputType.TYPE_CLASS_TEXT, value: String = ""): EditText {
        addText(parent, hint, 10f, MUTED, true, bottom = 2)
        val editText = EditText(this).apply {
            this.hint = hint
            this.inputType = inputType
            setText(value)
            textSize = 13.5f
            setPadding(dp(13), dp(12), dp(13), dp(12))
            background = rounded(SURFACE, 12, LINE_STRONG)
            setTextColor(INK)
            setHintTextColor(0xFFA9B5AE.toInt())
        }
        parent.addView(editText, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(10) })
        return editText
    }

    private fun scrollForm(form: LinearLayout): ScrollView = ScrollView(this).apply {
        addView(form)
        clipToPadding = false
    }

    private fun showFormDialog(title: String, view: View, positive: String, onSubmit: (AlertDialog) -> Unit): AlertDialog {
        val dialog = AlertDialog.Builder(this)
            .setTitle(title)
            .setView(view)
            .setPositiveButton(positive, null)
            .setNegativeButton("Cancelar", null)
            .create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener { onSubmit(dialog) }
        }
        dialog.show()
        return dialog
    }

    // ==================== Forms ====================

    private fun openProductForm(existing: JSONObject? = null) {
        val form = formContainer()
        val code = field(form, "Código *", value = existing?.optString("code") ?: "")
        val name = field(form, "Nombre *", value = existing?.optString("name") ?: "")
        val category = field(form, "Categoría *", value = existing?.optString("category") ?: "Comidas")
        val unit = field(form, "Unidad de venta", value = existing?.optString("unit") ?: "unidad")
        val yieldQty = field(form, "Rendimiento del lote *", InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL,
            existing?.optString("yield_qty") ?: "1")
        val yieldUnit = field(form, "Unidad del rendimiento (comensales, copas, vasos…)",
            value = existing?.optString("yield_unit") ?: "comensales")
        val desc = field(form, "Descripción", value = existing?.optString("description") ?: "")
        val isEdit = existing != null
        showFormDialog(if (isEdit) "Editar producto" else "Nuevo producto o servicio", scrollForm(form), if (isEdit) "Guardar" else "Registrar") { dialog ->
            val c = code.text.toString().trim()
            val n = name.text.toString().trim()
            val cat = category.text.toString().trim()
            if (c.isEmpty() || n.isEmpty() || cat.isEmpty()) { toast("Código, nombre y categoría son obligatorios."); return@showFormDialog }
            val body = JSONObject().put("code", c).put("name", n).put("category", cat)
                .put("unit", unit.text.toString().ifBlank { "unidad" })
                .put("yield_qty", yieldQty.text.toString().ifBlank { "1" })
                .put("yield_unit", yieldUnit.text.toString().ifBlank { "unidad" })
                .put("description", desc.text.toString())
            if (isEdit) runApi(dialog, "Producto actualizado.") { api.request("PUT", "/api/products/${existing!!.optInt("id")}", body) }
            else runApi(dialog, "Producto registrado correctamente.") { api.request("POST", "/api/products", body) }
        }
    }

    private fun openMaterialForm(existing: JSONObject? = null) {
        val form = formContainer()
        val code = field(form, "Código *", value = existing?.optString("code") ?: "")
        val name = field(form, "Nombre *", value = existing?.optString("name") ?: "")
        val category = field(form, "Categoría *", value = existing?.optString("category") ?: "Licores")
        val unit = field(form, "Unidad *", value = existing?.optString("unit") ?: "L")
        val price = if (can("materials", "costs")) field(form, "Precio unitario *",
            InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL,
            existing?.optString("unit_price") ?: "") else null
        val stock = field(form, "Existencias en almacén", InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL,
            existing?.optString("stock") ?: "0")
        val minStock = field(form, "Existencia mínima", InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL,
            existing?.optString("min_stock") ?: "0")
        val supplier = field(form, "Proveedor", value = existing?.optString("supplier") ?: "")
        val source = field(form, "Fuente / documento", value = existing?.optString("source") ?: "")
        val isEdit = existing != null
        showFormDialog(if (isEdit) "Editar valor del IPV" else "Nuevo valor del IPV", scrollForm(form), if (isEdit) "Guardar" else "Registrar") { dialog ->
            val c = code.text.toString().trim()
            val n = name.text.toString().trim()
            val u = unit.text.toString().trim()
            if (c.isEmpty() || n.isEmpty() || u.isEmpty()) { toast("Código, nombre y unidad son obligatorios."); return@showFormDialog }
            val body = JSONObject().put("code", c).put("name", n).put("unit", u)
                .put("category", category.text.toString().ifBlank { "Insumos" })
                .put("stock", stock.text.toString().ifBlank { "0" })
                .put("min_stock", minStock.text.toString().ifBlank { "0" })
                .put("supplier", supplier.text.toString())
                .put("source", source.text.toString())
            if (price != null) body.put("unit_price", price.text.toString().ifBlank { "0" })
            if (isEdit) runApi(dialog, "Valor del IPV actualizado.") { api.request("PUT", "/api/materials/${existing!!.optInt("id")}", body) }
            else runApi(dialog, "Valor del IPV registrado.") { api.request("POST", "/api/materials", body) }
        }
    }

    private fun openFichaForm() {
        val activeProducts = products.toObjectList().filter { it.optInt("active", 1) == 1 }
        if (activeProducts.isEmpty()) { toast("Registre al menos un producto activo."); return }
        val materialsList = materials.toObjectList()
        if (materialsList.isEmpty()) { toast("Registre al menos un valor de referencia."); return }

        val form = formContainer()
        addText(form, "Producto o servicio *", 10f, MUTED, true, bottom = 2)
        val productSpinner = Spinner(this).apply {
            adapter = ArrayAdapter(this@MainActivity, android.R.layout.simple_spinner_dropdown_item, activeProducts.map { "${it.optString("name")} (${it.optString("code")})" })
            background = rounded(Color.WHITE, 8, LINE)
            setPadding(dp(10), dp(8), dp(10), dp(8))
        }
        form.addView(productSpinner, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(10) })

        addText(form, "Insumo", 10f, MUTED, true, bottom = 2)
        val materialSpinner = Spinner(this).apply {
            adapter = ArrayAdapter(this@MainActivity, android.R.layout.simple_spinner_dropdown_item, materialsList.map { "${it.optString("name")} (${it.optString("code")})" })
            background = rounded(Color.WHITE, 8, LINE)
            setPadding(dp(10), dp(8), dp(10), dp(8))
        }
        form.addView(materialSpinner, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(10) })

        val first = activeProducts.first()
        val yieldQty = field(form, "Rinde (comensales, copas o vasos del lote)", InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL,
            first.optString("yield_qty", "1"))
        val yieldUnit = field(form, "Unidad del rendimiento", value = first.optString("yield_unit", "comensales"))
        val quantity = field(form, "Cantidad del lote", InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL, "1")
        val lines = mutableListOf<DraftLine>()
        val lineList = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val addLine = makeButton("＋  Añadir componente", false) {
            val material = materialsList.getOrNull(materialSpinner.selectedItemPosition)
            val q = quantity.text.toString().replace(',', '.')
            if (material == null || q.toDoubleOrNull() == null || q.toDouble() <= 0) { toast("Indique una cantidad mayor que cero."); return@makeButton }
            lines.add(DraftLine(material.optInt("id"), q))
            renderDraftLines(lineList, lines, materialsList)
            quantity.setText("")
        }
        form.addView(addLine, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(6) })
        form.addView(lineList)

        showFormDialog("Nueva Ficha de Costo", scrollForm(form), "Crear borrador") { dialog ->
            if (lines.isEmpty()) { toast("Añada al menos un componente."); return@showFormDialog }
            val itemArray = JSONArray()
            lines.forEach { itemArray.put(JSONObject().put("material_id", it.materialId).put("quantity", it.quantity)) }
            val body = JSONObject().put("product_id", activeProducts[productSpinner.selectedItemPosition].optInt("id"))
                .put("yield_qty", yieldQty.text.toString().ifBlank { "1" })
                .put("yield_unit", yieldUnit.text.toString().ifBlank { "unidad" })
                .put("items", itemArray)
            runApi(dialog, "Ficha creada como borrador.") { api.request("POST", "/api/fichas", body) }
        }
    }

    private fun renderDraftLines(target: LinearLayout, lines: MutableList<DraftLine>, materialsList: List<JSONObject>) {
        target.removeAllViews()
        lines.forEachIndexed { index, line ->
            val material = materialsList.find { it.optInt("id") == line.materialId }
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(0, dp(3), 0, dp(3)) }
            val info = label("${index + 1}.  ${material?.optString("name") ?: "Insumo"} · ${line.quantity} ${material?.optString("unit") ?: ""}", 10f, MUTED)
            row.addView(info, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            val remove = TextView(this).apply {
                text = "Quitar"
                textSize = 10f
                setTextColor(ERROR)
                setPadding(dp(8), dp(5), dp(5), dp(5))
                setOnClickListener { lines.removeAt(index); renderDraftLines(target, lines, materialsList) }
            }
            row.addView(remove)
            target.addView(row)
        }
    }

    private fun openFichaDetail(id: Int) {
        executor.execute {
            try {
                val ficha = api.request("GET", "/api/fichas/$id") as JSONObject
                runOnUiThread {
                    val message = buildString {
                        append("${ficha.optString("product_name")} · versión ${ficha.optInt("version")}\n")
                        append("Estado: ${ficha.optString("status")}\nVigente desde: ${ficha.optString("valid_from")}\n")
                        append("Rinde: ${ficha.optString("yield_qty")} ${ficha.optString("yield_unit")}\n")
                        if (can("fichas", "costs")) {
                            append("Costo del lote: ${formatAmount(ficha.optString("total_cost"))} CUP\n")
                            append("Costo por ${ficha.optString("yield_unit")}: ${formatAmount(ficha.optString("cost_per_serving"))} CUP\n")
                        }
                        val srv = ficha.opt("servings_from_stock")
                        if (srv != null && srv.toString() != "null") append("Con el inventario: ≈ $srv ${ficha.optString("yield_unit")}\n")
                        append("\n")
                        val lines = ficha.optJSONArray("items") ?: JSONArray()
                        append("Componentes: ${lines.length()}\n")
                        for (i in 0 until lines.length()) {
                            val line = lines.getJSONObject(i)
                            append("${i + 1}. ${line.optString("description")} — ${line.optString("quantity")} ${line.optString("unit")}")
                            if (can("fichas", "costs")) append(" = ${formatAmount(line.optString("subtotal"))} CUP")
                            append("\n")
                        }
                        if (ficha.optString("observations").isNotBlank()) append("\n${ficha.optString("observations")}")
                    }
                    AlertDialog.Builder(this).setTitle("Ficha de Costo").setMessage(message)
                        .setPositiveButton("Cerrar", null)
                        .apply { if (can("fichas", "edit")) setNegativeButton("Papelera") { _, _ -> trashItem("fichas", id, ficha.optString("product_name")) } }
                        .apply { if (can("fichas", "edit") && ficha.optString("status") == "Borrador") setNeutralButton("Aprobar", null) }
                        .apply { if (can("controls", "edit") && ficha.optString("status") == "Aprobada") setNeutralButton("Generar Control", null) }
                        .create().also { dialog ->
                            dialog.setOnShowListener {
                                if (can("fichas", "edit") && ficha.optString("status") == "Borrador") dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener { dialog.dismiss(); approveFicha(id) }
                                if (can("controls", "edit") && ficha.optString("status") == "Aprobada") dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener { dialog.dismiss(); openGenerateControl(id) }
                            }
                            dialog.show()
                        }
                }
            } catch (error: Exception) { runOnUiThread { toast(error.message ?: "No se pudo abrir la ficha.") } }
        }
    }

    private fun approveFicha(id: Int) {
        executor.execute {
            try {
                api.request("POST", "/api/fichas/$id/approve", JSONObject())
                runOnUiThread { toast("Ficha aprobada correctamente."); refresh() }
            } catch (error: Exception) { runOnUiThread { toast(error.message ?: "No se pudo aprobar.") } }
        }
    }

    private fun openGenerateControl(fichaId: Int) {
        val form = formContainer()
        val period = field(form, "Período (AAAA-MM)", value = java.time.YearMonth.now().toString())
        addText(form, "El control guardará una instantánea de la versión aprobada seleccionada.", 10f, MUTED, false, bottom = 7)
        showFormDialog("Generar Control de IPV", scrollForm(form), "Crear control") { dialog ->
            if (period.text.length < 7) { toast("Indique el período con formato AAAA-MM."); return@showFormDialog }
            val body = JSONObject().put("ficha_id", fichaId).put("period", period.text.toString())
            runApi(dialog, "Control IPV creado como pendiente.") { api.request("POST", "/api/controls", body) }
        }
    }

    private fun openControlDetail(id: Int) {
        executor.execute {
            try {
                val control = api.request("GET", "/api/controls/$id") as JSONObject
                runOnUiThread {
                    val messages = control.optJSONArray("validation_messages") ?: JSONArray()
                    val lines = control.optJSONArray("items") ?: JSONArray()
                    val verifiedTotal = if (!can("controls", "costs")) "Oculto" else if (control.optString("checked_at").isBlank()) "Sin validar" else formatAmount(control.optString("checked_total")) + " CUP"
                    val message = buildString {
                        append("${control.optString("product_name")} · ficha v${control.optInt("ficha_version")}\n")
                        append("Período: ${control.optString("period")}\nEstado: ${control.optString("status")}\n")
                        if (can("controls", "costs")) append("Total registrado: ${formatAmount(control.optString("snapshot_total"))} CUP\n")
                        append("Total verificado: $verifiedTotal\n\nLíneas: ${lines.length()}\n")
                        for (i in 0 until messages.length()) append("\n${messages.getJSONObject(i).optString("text")}")
                    }
                    val dialog = AlertDialog.Builder(this).setTitle("Control IPV · ${control.optString("code")}")
                        .setMessage(message).setPositiveButton("Cerrar", null)
                        .apply { if (can("controls", "edit") && control.optString("status") != "Validado") setNeutralButton("Validar", null) }
                        .create()
                    dialog.setOnShowListener {
                        if (can("controls", "edit") && control.optString("status") != "Validado") dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener { dialog.dismiss(); validateControl(id) }
                    }
                    dialog.show()
                }
            } catch (error: Exception) { runOnUiThread { toast(error.message ?: "No se pudo abrir el control.") } }
        }
    }

    private fun validateControl(id: Int) {
        executor.execute {
            try {
                val result = api.request("POST", "/api/controls/$id/validate", JSONObject()) as JSONObject
                runOnUiThread {
                    toast(if (result.optString("status") == "Validado") "Control validado sin diferencias." else "Se encontraron observaciones.")
                    refresh()
                    openControlDetail(id)
                }
            } catch (error: Exception) { runOnUiThread { toast(error.message ?: "No se pudo validar.") } }
        }
    }

    private fun runApi(dialog: AlertDialog, successMessage: String, action: () -> Any) {
        dialog.getButton(AlertDialog.BUTTON_POSITIVE).isEnabled = false
        executor.execute {
            try {
                action()
                runOnUiThread { dialog.dismiss(); toast(successMessage); refresh() }
            } catch (error: Exception) {
                runOnUiThread { dialog.getButton(AlertDialog.BUTTON_POSITIVE).isEnabled = true; toast(error.message ?: "Error al guardar.") }
            }
        }
    }

    private fun openMaterialDetail(id: Int) {
        executor.execute {
            try {
                val m = api.request("GET", "/api/materials/$id") as JSONObject
                runOnUiThread {
                    val used = m.optJSONArray("used_by") ?: JSONArray()
                    val usage = if (used.length() == 0) "Sin recetas que lo usen."
                    else "Se usa en ${used.length()} ficha(s):\n" + (0 until used.length()).joinToString("\n") {
                        val u = used.getJSONObject(it)
                        "${it + 1}. ${u.optString("product_name")}: ${u.optString("per_serving")} ${m.optString("unit")} por ${u.optString("yield_unit")} · inventario ≈ ${u.opt("servings")} ${u.optString("yield_unit")}"
                    }
                    val msg = buildString {
                        append("${m.optString("code")} · ${m.optString("category")}\n")
                        if (can("materials", "costs")) append("Precio: ${formatAmount(m.optString("unit_price"))} ${m.optString("currency")} / ${m.optString("unit")}\n")
                        append("Existencias: ${m.optString("stock")} ${m.optString("unit")} (mín. ${m.optString("min_stock")})\n")
                        if (can("materials", "costs")) append("Valor en almacén: ${formatAmount(m.optString("stock_value"))} CUP\n\n")
                        append(usage)
                    }
                    AlertDialog.Builder(this).setTitle(m.optString("name")).setMessage(msg)
                        .apply { if (can("materials", "edit")) {
                            setPositiveButton("Editar") { _, _ -> openMaterialForm(m) }
                            setNeutralButton("Papelera") { _, _ -> trashItem("materials", id, m.optString("name")) }
                        } }
                        .setNegativeButton("Cerrar", null)
                        .show()
                }
            } catch (error: Exception) { runOnUiThread { toast(error.message ?: "No se pudo abrir el valor.") } }
        }
    }

    private fun openProductDetail(id: Int) {
        executor.execute {
            try {
                val p = api.request("GET", "/api/products/$id") as JSONObject
                runOnUiThread {
                    val fichasOf = p.optJSONArray("fichas") ?: JSONArray()
                    val msg = buildString {
                        append("${p.optString("code")} · ${p.optString("category")}\n")
                        append("Rinde ${p.optString("yield_qty")} ${p.optString("yield_unit")} por lote\n")
                        append("Fichas: ${fichasOf.length()}\n")
                        if (p.optString("description").isNotBlank()) append("\n${p.optString("description")}")
                    }
                    AlertDialog.Builder(this).setTitle(p.optString("name")).setMessage(msg)
                        .apply { if (can("products", "edit")) {
                            setPositiveButton("Editar") { _, _ -> openProductForm(p) }
                            setNeutralButton("Papelera") { _, _ -> trashItem("products", id, p.optString("name")) }
                        } }
                        .setNegativeButton("Cerrar", null)
                        .show()
                }
            } catch (error: Exception) { runOnUiThread { toast(error.message ?: "No se pudo abrir el producto.") } }
        }
    }

    private fun trashItem(kind: String, id: Int, name: String) {
        AlertDialog.Builder(this)
            .setTitle("Mover a la papelera")
            .setMessage("«$name» dejará de aparecer en las listas. Podrá restaurarlo desde Papelera.")
            .setPositiveButton("Mover") { _, _ ->
                executor.execute {
                    try {
                        api.request("DELETE", "/api/$kind/$id")
                        runOnUiThread { toast("Movido a la papelera."); refresh() }
                    } catch (error: Exception) { runOnUiThread { toast(error.message ?: "No se pudo eliminar.") } }
                }
            }
            .setNegativeButton("Cancelar", null)
            .show()
    }

    private fun restoreTrash(kind: String, id: Int) {
        executor.execute {
            try {
                api.request("POST", "/api/trash/$kind/$id/restore", JSONObject())
                runOnUiThread { toast("Elemento restaurado."); refresh() }
            } catch (error: Exception) { runOnUiThread { toast(error.message ?: "No se pudo restaurar.") } }
        }
    }

    private fun purgeTrash(kind: String, id: Int) {
        AlertDialog.Builder(this)
            .setTitle("Borrado definitivo")
            .setMessage("Se eliminará para siempre, junto con sus documentos derivados.")
            .setPositiveButton("Eliminar") { _, _ ->
                executor.execute {
                    try {
                        api.request("DELETE", "/api/trash/$kind/$id")
                        runOnUiThread { toast("Eliminado definitivamente."); refresh() }
                    } catch (error: Exception) { runOnUiThread { toast(error.message ?: "No se pudo eliminar.") } }
                }
            }
            .setNegativeButton("Cancelar", null)
            .show()
    }

    private fun emptyTrash() {
        AlertDialog.Builder(this)
            .setTitle("Vaciar la papelera")
            .setMessage("Se borrarán definitivamente todos los elementos de la papelera.")
            .setPositiveButton("Vaciar") { _, _ ->
                executor.execute {
                    try {
                        api.request("POST", "/api/trash/empty", JSONObject())
                        runOnUiThread { toast("Papelera vaciada."); refresh() }
                    } catch (error: Exception) { runOnUiThread { toast(error.message ?: "No se pudo vaciar.") } }
                }
            }
            .setNegativeButton("Cancelar", null)
            .show()
    }

    // ==================== Settings ====================

    private fun openSettings() {
        val form = formContainer()
        addText(form, "La aplicación Android y la interfaz web comparten la misma base de datos SQLite centralizada en el servidor.", 11f, MUTED, false, bottom = 8)
        val urlField = field(form, "URL del servidor", value = api.baseUrl)
        addText(form, "Emulador: https://10.0.2.2:8443\nMóvil u otra PC: https://IP_DEL_SERVIDOR:8443\n\nInstale la CA local en el dispositivo para confiar en HTTPS.", 10f, MUTED)
        addText(form, "Seguridad", 12f, INK, true, bottom = 4)
        val user = api.session.user
        addText(form, if (user != null) "Sesión: ${user.optString("name")} (${user.optString("role")})" else "Sin sesión iniciada", 11f, MUTED)
        val bio = android.widget.CheckBox(this).apply {
            text = "Proteger la app con huella / rostro"
            isChecked = api.biometricLock
            isEnabled = Build.VERSION.SDK_INT >= Build.VERSION_CODES.P
            setTextColor(INK)
        }
        form.addView(bio)
        val fijada = api.pinner.pin != null
        addText(form, if (fijada) "✅ Huella del certificado fijada (SHA-256):" else "⚠ Sin huella fijada: se aceptará la del próximo servidor al que se conecte.", 10f, if (fijada) MUTED else WARNING, true)
        addText(form, api.pinner.pretty(api.pinner.pin), 9f, INK)
        val pinField = field(form, "Nueva huella (de: iniciar-https.ps1 -ShowPin) — vacío = no cambiar")
        val resetPin = android.widget.CheckBox(this).apply {
            text = "Olvidar la huella y confiar en la próxima conexión"
            setTextColor(WARNING)
        }
        form.addView(resetPin)
        if (user != null) addButton(form, "🛡  Seguridad de la cuenta (dispositivos y contraseña)", true) { openAccountSecurity() }
        var settingsDialog: AlertDialog? = null
        addButton(form, "🔑  Licencia: estado y renovación", false) {
            settingsDialog?.dismiss()
            openLicenseView()
        }
        if (user != null) addButton(form, "Cerrar sesión y borrar datos locales", false) {
            executor.execute {
                api.logout()
                runOnUiThread { toast("Sesión cerrada."); refresh() }
            }
        }
        settingsDialog = showFormDialog("Configuración de conexión", scrollForm(form), "Guardar y probar") { dialog ->
            val newUrl = urlField.text.toString().trim()
            if (!newUrl.startsWith("https://")) { toast("La URL debe comenzar con https://."); return@showFormDialog }
            if (newUrl != api.baseUrl) { api.session.clear(); api.cache.clear(); api.pinner.pin = null }
            api.baseUrl = newUrl
            api.biometricLock = bio.isChecked
            val newPin = api.pinner.normalize(pinField.text.toString())
            if (newPin.isNotEmpty()) {
                if (newPin.length != 64) { toast("La huella debe tener 64 caracteres hexadecimales."); return@showFormDialog }
                api.pinner.pin = newPin
            } else if (resetPin.isChecked) api.pinner.pin = null
            dialog.dismiss()
            refresh()
        }
    }

    // ==================== Licencia por período ====================

    /** Ejecuta [action] solo si hay licencia vigente; si no, la app entra en la vista de
     *  Licencia (no se puede omitir): allí se genera la solicitud y se envía por WhatsApp.
     *  Igual que la web: al arrancar, lo primero es la licencia. Con licencias desactivadas
     *  (sin clave pública) avisa una vez y continúa, como el aviso de la página Licencia web. */
    private fun licenseGate(action: () -> Unit) {
        if (!LicenseCore.enforced) {
            if (!licenseNoticeShown) {
                licenseNoticeShown = true
                toast("🛡 Licencias desactivadas: cree la clave en el Creador de Licencias (web, menú Licencia).")
            }
            action(); return
        }
        license.pending()?.let { pending ->
            if (licenseDialog?.isShowing != true) {
                licenseDialog = AlertDialog.Builder(this)
                    .setTitle("Licencia programada")
                    .setMessage("La licencia comenzará el ${pending.validFromDate} (UTC) y vencerá el ${pending.expiryText()}. El acceso se habilitará desde su fecha de inicio.")
                    .setPositiveButton("Cerrar aplicación") { _, _ -> finish() }
                    .setCancelable(false)
                    .show()
            }
            return
        }
        try {
            val info = license.current()
            val left = info.daysLeft(System.currentTimeMillis() / 1000)
            if (left <= 7) toast("⏳ Su licencia (${info.planName}) vence en $left día(s): ${info.expiryText()}")
            action()
        } catch (e: LicenseCore.LicenseException) {
            licenseAction = action
            openLicenseView()
        }
    }

    /** La app entra en la vista de Licencia (pantalla completa): desde aquí se genera la
     *  solicitud de licencia, se envía por WhatsApp y se pega la licencia recibida. */
    private fun openLicenseView() {
        currentTab = "Licencia"
        updateTabStyle()
        renderPage()
    }

    /** Bloque «ID Dispositivo (cifrado)»: el código de solicitud de este teléfono. */
    private fun licenseIdBlock() {
        addText(content, "ID Dispositivo (cifrado)", 11f, MUTED, true, bottom = 2)
        content.addView(TextView(this).apply {
            text = license.requestCode
            typeface = Typeface.MONOSPACE
            textSize = 14f
            setTextColor(LIME_VIVID)
            setTextIsSelectable(true)
            background = rounded(GREEN_DARK, 10)
            setPadding(dp(12), dp(10), dp(12), dp(10))
        }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(8) })
        addText(content, "Envíe este código al proveedor para recibir la licencia. No contiene datos del equipo: es un resumen SHA-256 irreversible.", 11f, MUTED, bottom = 8)
    }

    /** Vista de Licencia: estado, solicitud por WhatsApp y activación de la licencia. */
    private fun renderLicensePage() {
        addHeading(content, "Licencia de uso", "La licencia se firma digitalmente y queda atada a este teléfono.")
        if (!LicenseCore.enforced) {
            addText(content, "🛡 Licencias desactivadas (sin clave pública configurada).", 13f, WARNING, true, bottom = 8)
            addText(
                content,
                "El proveedor aún no creó la clave de firma. Desde la aplicación web abra el «Creador de Licencias» " +
                    "(menú Licencia → Abrir Creador de Licencias): la clave se crea una sola vez y el sistema se activa al " +
                    "instante. Después recompile este APK con la nueva clave pública.",
                12f, MUTED, bottom = 12
            )
            licenseIdBlock()
            return
        }
        val result = runCatching { license.current() }
        val current = result.getOrNull()
        val now = System.currentTimeMillis() / 1000
        if (current != null) {
            addText(content, "✅ Licencia vigente: ${current.planName} a nombre de ${current.user}.", 13f, SUCCESS, true)
            addText(content, "Vence el ${current.expiryText()} (${current.daysLeft(now)} días). Serie ${current.serial}.", 12f, MUTED, bottom = 12)
        } else {
            connectionLabel.text = "●  Sin licencia vigente · genere la solicitud y envíela por WhatsApp"
            connectionLabel.setTextColor(WARNING)
            addText(content, "🔒 ${result.exceptionOrNull()?.message ?: "Este teléfono necesita una licencia."}", 13f, ERROR, true)
            addText(content, "1. Escriba su nombre y elija el plan.\n2. Envíe la solicitud por WhatsApp.\n3. Pegue la licencia recibida y pulse Activar.", 12f, MUTED, bottom = 12)
        }
        val user = field(content, "Usuario (nombre o empresa)")
        val planKeys = LicenseCore.PLANS.keys.filter { it != "PX" }
        val plan = Spinner(this).apply {
            adapter = ArrayAdapter(
                this@MainActivity, android.R.layout.simple_spinner_dropdown_item,
                planKeys.map { key -> "${LicenseCore.PLANS.getValue(key).first} — ${LicenseCore.PLANS.getValue(key).third} USD" })
            setSelection(1)
        }
        content.addView(plan, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(10) })
        licenseIdBlock()
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, dp(8), 0, dp(8)) }
        row.addView(makeButton("📋 Copiar", false) {
            val cm = getSystemService(CLIPBOARD_SERVICE) as android.content.ClipboardManager
            cm.setPrimaryClip(android.content.ClipData.newPlainText("ID Dispositivo IPV", license.requestCode))
            toast("Código copiado")
        }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { rightMargin = dp(6) })
        row.addView(makeButton("💬 Generar solicitud y enviarla por WhatsApp", true) {
            val planName = "${LicenseCore.PLANS.getValue(planKeys[plan.selectedItemPosition]).first} (${planKeys[plan.selectedItemPosition]})"
            val text = license.whatsappMessage(user.text.toString().trim(), planName)
            val uri = android.net.Uri.parse("https://wa.me/${LicenseCore.WHATSAPP_NUMBER}?text=${android.net.Uri.encode(text)}")
            try {
                startActivity(android.content.Intent(android.content.Intent.ACTION_VIEW, uri))
            } catch (e: android.content.ActivityNotFoundException) {
                toast("No se encontró WhatsApp. Copie el código y envíelo manualmente.")
            }
        }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        content.addView(row)
        addText(content, "ACTIVAR LICENCIA", 9f, MUTED, true, bottom = 4)
        val token = EditText(this).apply {
            hint = "Pegue aquí la licencia recibida (IPV1.…)"
            minLines = 3
            typeface = Typeface.MONOSPACE
            textSize = 12f
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
        }
        content.addView(token, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(8) })
        addText(content, "La licencia está firmada digitalmente y solo funciona en este teléfono.", 11f, MUTED, bottom = 8)
        addButton(content, if (current != null) "🔓 Renovar / cambiar licencia" else "🔓 Activar licencia", true) {
            try {
                val info = license.activate(token.text.toString())
                val nowSec = System.currentTimeMillis() / 1000
                if (info.validFrom > nowSec) {
                    AlertDialog.Builder(this)
                        .setTitle("Licencia programada")
                        .setMessage("Quedó guardada. Comenzará el ${info.validFromDate} (UTC) y vencerá el ${info.expiryText()}; la aplicación se habilitará desde esa fecha.")
                        .setPositiveButton("Cerrar aplicación") { _, _ -> finish() }
                        .setCancelable(false)
                        .show()
                    return@addButton
                }
                toast("✅ Licencia activada: ${info.planName}, vence el ${info.expiryText()}")
                currentTab = "Resumen"
                updateTabStyle()
                val next = licenseAction ?: { unlockThen { refresh() } }
                licenseAction = null
                next()
            } catch (e: LicenseCore.LicenseException) {
                token.error = e.message
                toast(e.message ?: "La licencia no es válida.")
            } catch (e: org.json.JSONException) {
                token.error = "La licencia está dañada."
                toast("La licencia está dañada.")
            }
        }
    }

    // ==================== Seguridad de la cuenta ====================

    /** Avisos tras iniciar sesión: intentos fallidos, red nueva y caducidad próxima. */
    private fun showLoginNotices(data: JSONObject) {
        val notes = mutableListOf<String>()
        val fails = data.optInt("failed_attempts_since_last_login", 0)
        if (fails > 0) {
            val ip = data.optString("last_failed_ip").takeIf { it.isNotBlank() }?.let { " (IP $it)" } ?: ""
            notes += "⚠ Hubo $fails intento(s) fallido(s) de entrar en su cuenta desde su último acceso$ip."
        }
        if (data.optBoolean("new_ip")) notes += "🔐 Este inicio de sesión se hizo desde una red nueva y quedó registrado."
        if (!data.isNull("password_expires_in_days") && data.has("password_expires_in_days")) {
            val left = data.optInt("password_expires_in_days", 99)
            if (left <= 7 && !data.optBoolean("password_expired")) notes += "⏳ Su contraseña caduca en $left día(s)."
        }
        if (notes.isEmpty()) return
        AlertDialog.Builder(this)
            .setTitle("Aviso de seguridad")
            .setMessage(notes.joinToString("\n\n") + if (fails > 0) "\n\nSi no fue usted, cambie su contraseña y cierre las demás sesiones." else "")
            .setPositiveButton("Entendido", null)
            .show()
    }

    private var passwordDialogOpen = false

    /** Cambio de contraseña. Con [forced] no se puede cancelar (solo cerrar sesión). */
    private fun openPasswordChange(forced: Boolean) {
        if (passwordDialogOpen) return
        passwordDialogOpen = true
        val form = formContainer()
        if (forced) addText(form, "Su contraseña ha caducado o el administrador exige cambiarla. Debe hacerlo para continuar.", 11f, WARNING, true, bottom = 8)
        val pwType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
        val current = field(form, "Contraseña actual", pwType)
        val fresh = field(form, "Nueva contraseña", pwType)
        val repeat = field(form, "Repetir nueva contraseña", pwType)
        addText(form, "Mínimo 10 caracteres combinando mayúsculas, minúsculas, números y símbolos. No puede repetir contraseñas anteriores. Se cerrarán las sesiones de sus otros dispositivos.", 10f, MUTED)
        val dialog = showFormDialog(if (forced) "Cambio de contraseña obligatorio" else "Cambiar contraseña", scrollForm(form), "Guardar") { dialog ->
            if (fresh.text.toString() != repeat.text.toString()) { toast("Las contraseñas nuevas no coinciden."); return@showFormDialog }
            val button = dialog.getButton(AlertDialog.BUTTON_POSITIVE)
            button.isEnabled = false
            val cur = current.text.toString()
            val nw = fresh.text.toString()
            executor.execute {
                try {
                    api.changePassword(cur, nw)
                    runOnUiThread {
                        passwordDialogOpen = false
                        dialog.dismiss()
                        triggerHapticFeedback()
                        toast("Contraseña actualizada. Se cerraron sus otras sesiones.")
                        refresh()
                    }
                } catch (error: Exception) {
                    runOnUiThread { button.isEnabled = true; toast(error.message ?: "No se pudo cambiar la contraseña.") }
                }
            }
        }
        dialog.setOnDismissListener { passwordDialogOpen = false }
        if (forced) {
            dialog.setCancelable(false)
            dialog.getButton(AlertDialog.BUTTON_NEGATIVE).text = "Cerrar sesión"
            dialog.getButton(AlertDialog.BUTTON_NEGATIVE).setOnClickListener {
                dialog.dismiss()
                executor.execute { api.logout(); runOnUiThread { refresh() } }
            }
        }
    }

    /** Dispositivos con sesión abierta + cambio de contraseña. */
    private fun openAccountSecurity() {
        val form = formContainer()
        val user = api.session.user
        addText(form, user?.let { "${it.optString("name")} · ${it.optString("email")}" } ?: "", 12f, INK, true)
        addText(form, if (user?.optBoolean("mfa") == true) "🛡 Verificación en dos pasos activa" else "⚠ Verificación en dos pasos desactivada (actívela desde la web)", 11f,
            if (user?.optBoolean("mfa") == true) SUCCESS else WARNING, bottom = 10)
        addButton(form, "🔑  Cambiar contraseña", false) { openPasswordChange(forced = false) }
        addText(form, "Dispositivos con sesión abierta", 13f, INK, true, bottom = 6)
        val list = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        form.addView(list)
        addText(list, "Cargando…", 11f, MUTED)
        val dialog = AlertDialog.Builder(this)
            .setTitle("Seguridad de la cuenta")
            .setView(scrollForm(form))
            .setPositiveButton("Cerrar", null)
            .show()
        loadDevices(list, dialog)
    }

    private fun loadDevices(list: LinearLayout, dialog: AlertDialog) {
        executor.execute {
            try {
                val sessions = api.sessions().toObjectList()
                runOnUiThread { renderDevices(list, dialog, sessions) }
            } catch (error: Exception) {
                runOnUiThread { list.removeAllViews(); addText(list, error.message ?: "No se pudo cargar la lista.", 11f, ERROR) }
            }
        }
    }

    private fun renderDevices(list: LinearLayout, dialog: AlertDialog, sessions: List<JSONObject>) {
        list.removeAllViews()
        for (item in sessions) {
            val current = item.optBoolean("current")
            val device = item.optString("device")
            val icon = if (Regex("Android|iPhone|iPad").containsMatchIn(device)) "📱" else "💻"
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                setPadding(dp(12), dp(10), dp(12), dp(10))
                background = rounded(if (current) 0xFFE8F8EF.toInt() else SURFACE, 12, if (current) SUCCESS else LINE)
            }
            val info = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
            info.addView(label("$icon  $device" + if (current) "  · este dispositivo" else "", 12f, INK, true))
            info.addView(label("IP ${item.optString("ip", "—")} · última actividad ${item.optString("last_seen").replace('T', ' ').removeSuffix("Z")} UTC", 9f, MUTED))
            row.addView(info, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            if (!current) {
                row.addView(makeButton("Cerrar", false) {
                    executor.execute {
                        try {
                            api.closeSession(item.optString("id"))
                            runOnUiThread { toast("Sesión cerrada en $device."); loadDevices(list, dialog) }
                        } catch (error: Exception) { runOnUiThread { toast(error.message ?: "Error") } }
                    }
                })
            }
            list.addView(row, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(6) })
        }
        val others = sessions.count { !it.optBoolean("current") }
        if (others > 0) {
            addButton(list, "Cerrar las $others sesiones de otros dispositivos", false) {
                AlertDialog.Builder(this)
                    .setMessage("¿Cerrar la sesión en todos sus otros dispositivos?")
                    .setPositiveButton("Cerrar sesiones") { _, _ ->
                        executor.execute {
                            try {
                                val closed = api.closeOtherSessions()
                                runOnUiThread { toast("$closed sesión(es) cerrada(s)."); loadDevices(list, dialog) }
                            } catch (error: Exception) { runOnUiThread { toast(error.message ?: "Error") } }
                        }
                    }
                    .setNegativeButton("Cancelar", null)
                    .show()
            }
        } else {
            addText(list, "No hay sesiones abiertas en otros dispositivos.", 11f, MUTED)
        }
    }

    // ==================== About ====================

    private fun openAbout() {
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(20), dp(16), dp(20), dp(8))
        }

        // Brand
        val brandRow = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
        val brandBox = TextView(this).apply {
            text = "iv"
            textSize = 26f
            setTypeface(typeface, Typeface.BOLD)
            setTextColor(GREEN)
            background = rounded(LIME.toInt(), 12)
            setPadding(dp(12), dp(8), dp(12), dp(8))
            gravity = Gravity.CENTER
        }
        brandRow.addView(brandBox)
        val brandText = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(12), 0, 0, 0) }
        brandText.addView(label("IPV · Fichas y Costos", 17f, INK, true))
        brandText.addView(label("Sistema de gestión de costos", 10f, MUTED))
        brandRow.addView(brandText)
        layout.addView(brandRow, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(14) })

        // Version badge
        val versionBadge = TextView(this).apply {
            text = "v$APP_VERSION · Edición profesional"
            textSize = 10f
            setTextColor(GREEN)
            background = rounded(GREEN_PALE.toInt(), 20)
            setPadding(dp(12), dp(5), dp(12), dp(5))
            gravity = Gravity.CENTER
        }
        layout.addView(versionBadge, LinearLayout.LayoutParams(ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(16) })

        // Description
        layout.addView(label("Plataforma integral para la gestión de Fichas de Costo, valores de referencia del IPV y Controles de verificación. Permite el registro centralizado de productos y servicios, el cálculo versionado de costos y la validación periódica mediante controles vinculados a cada versión aprobada.", 11f, MUTED).apply {
            setPadding(0, 0, 0, dp(16))
        })

        // Author card
        val authorCard = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(14), dp(12), dp(14), dp(12))
            background = rounded(GREEN, 12)
        }
        val authorAvatar = TextView(this).apply {
            text = "YH"
            textSize = 16f
            setTypeface(typeface, Typeface.BOLD)
            setTextColor(LIME.toInt())
            background = rounded(0x33D7E78D.toInt(), 50)
            gravity = Gravity.CENTER
            setPadding(dp(6), dp(6), dp(6), dp(6))
        }
        authorCard.addView(authorAvatar, LinearLayout.LayoutParams(dp(42), dp(42)).apply { rightMargin = dp(12) })
        val authorInfo = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        authorInfo.addView(label("Ing. Yosvany Hernández Quintero", 13f, Color.WHITE, true))
        authorInfo.addView(label("Diseño y desarrollo del sistema", 10f, 0xFFB0C6B9.toInt()))
        authorCard.addView(authorInfo)
        layout.addView(authorCard, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(16) })

        // Features
        layout.addView(label("FUNCIONALIDADES", 9f, MUTED, true).apply { setPadding(0, 0, 0, dp(6)) })
        val features = listOf(
            "Catálogo de productos y servicios",
            "Valores de referencia con vigencia",
            "Fichas de costo versionadas",
            "Controles de IPV verificables",
            "Validación automática de totales",
            "Exportación CSV"
        )
        features.forEach { f ->
            layout.addView(label("  •  $f", 11f, 0xFF607067.toInt()).apply { setPadding(0, 0, 0, dp(3)) })
        }

        addSpacer(layout, 12)

        // Tech stack
        layout.addView(label("ARQUITECTURA", 9f, MUTED, true).apply { setPadding(0, 0, 0, dp(6)) })
        layout.addView(label("API REST en Python · SQLite con WAL · HTTPS/TLS 1.2+ · Kotlin · Android SDK", 10f, 0xFF607067.toInt()).apply { setPadding(0, 0, 0, dp(8)) })

        val scroll = ScrollView(this).apply { addView(layout) }
        AlertDialog.Builder(this)
            .setTitle("Acerca de IPV")
            .setView(scroll)
            .setPositiveButton("Entendido", null)
            .show()
    }

    private fun toast(message: String) = Toast.makeText(this, message, Toast.LENGTH_SHORT).show()

    private fun JSONArray.toObjectList(): List<JSONObject> = (0 until length()).mapNotNull { optJSONObject(it) }


    // ==========================================================================
    //  ADVANCED FEATURES — Statistics, Charts, Enhanced UX
    // ==========================================================================

    private fun openStatistics() {
        executor.execute {
            try {
                val stats = api.request("GET", "/api/statistics") as JSONObject
                runOnUiThread {
                    val layout = LinearLayout(this).apply {
                        orientation = LinearLayout.VERTICAL
                        setPadding(dp(20), dp(16), dp(20), dp(8))
                    }

                    // Title
                    layout.addView(label("📊 Estadísticas Avanzadas", 18f, INK, true).apply {
                        setPadding(0, 0, 0, dp(16))
                    })

                    // Monthly trend
                    val trend = stats.optJSONArray("monthly_trend") ?: JSONArray()
                    if (trend.length() > 0) {
                        layout.addView(label("TENDENCIA MENSUAL", 10f, MUTED, true).apply {
                            setPadding(0, 0, 0, dp(8))
                        })
                        val trendCard = LinearLayout(this).apply {
                            orientation = LinearLayout.VERTICAL
                            setPadding(dp(14), dp(12), dp(14), dp(12))
                            background = rounded(SURFACE, 12, LINE)
                            elevation = dp(2).toFloat()
                        }
                        for (i in 0 until minOf(6, trend.length())) {
                            val month = trend.getJSONObject(i)
                            val monthName = month.optString("month").takeLast(2)
                            val count = month.optInt("count")
                            val barWidth = (count * 20).coerceAtMost(200)
                            
                            val row = LinearLayout(this).apply {
                                orientation = LinearLayout.HORIZONTAL
                                gravity = Gravity.CENTER_VERTICAL
                                setPadding(0, dp(4), 0, dp(4))
                            }
                            row.addView(label(monthName, 11f, MUTED).apply {
                                minWidth = dp(40)
                            })
                            val bar = View(this).apply {
                                background = rounded(LIME_VIVID.toInt(), 4)
                                minimumWidth = dp(barWidth)
                            }
                            row.addView(bar, LinearLayout.LayoutParams(dp(barWidth), dp(20)))
                            row.addView(label(count.toString(), 12f, INK, true).apply {
                                setPadding(dp(8), 0, 0, 0)
                            })
                            trendCard.addView(row)
                        }
                        layout.addView(trendCard, LinearLayout.LayoutParams(
                            ViewGroup.LayoutParams.MATCH_PARENT,
                            ViewGroup.LayoutParams.WRAP_CONTENT
                        ).apply { bottomMargin = dp(16) })
                    }

                    // Top expensive products
                    val topExpensive = stats.optJSONArray("top_expensive") ?: JSONArray()
                    if (can("fichas", "costs") && topExpensive.length() > 0) {
                        layout.addView(label("PRODUCTOS MÁS COSTOSOS", 10f, MUTED, true).apply {
                            setPadding(0, 0, 0, dp(8))
                        })
                        for (i in 0 until minOf(5, topExpensive.length())) {
                            val product = topExpensive.getJSONObject(i)
                            val card = LinearLayout(this).apply {
                                orientation = LinearLayout.HORIZONTAL
                                gravity = Gravity.CENTER_VERTICAL
                                setPadding(dp(14), dp(12), dp(14), dp(12))
                                background = rounded(SURFACE, 10, LINE)
                                elevation = dp(1).toFloat()
                            }
                            val info = LinearLayout(this).apply {
                                orientation = LinearLayout.VERTICAL
                            }
                            info.addView(label(product.optString("name"), 13f, INK, true))
                            info.addView(label("${product.optString("code")} · v${product.optInt("version")}", 10f, MUTED).apply {
                                setPadding(0, dp(2), 0, 0)
                            })
                            card.addView(info, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
                            val price = formatAmount(product.optString("total_cost"))
                            card.addView(label("$price CUP", 14f, SUCCESS, true))
                            layout.addView(card, LinearLayout.LayoutParams(
                                ViewGroup.LayoutParams.MATCH_PARENT,
                                ViewGroup.LayoutParams.WRAP_CONTENT
                            ).apply { bottomMargin = dp(6) })
                        }
                    }

                    val scroll = ScrollView(this).apply { addView(layout) }
                    AlertDialog.Builder(this)
                        .setView(scroll)
                        .setPositiveButton("Cerrar", null)
                        .show()
                }
            } catch (error: Exception) {
                runOnUiThread { toast("Error al cargar estadísticas: ${error.message}") }
            }
        }
    }

    private fun triggerHapticFeedback() {
        // Respuesta háptica del sistema: no requiere el permiso VIBRATE y respeta los ajustes del usuario
        val effect = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) android.view.HapticFeedbackConstants.CONFIRM
                     else android.view.HapticFeedbackConstants.VIRTUAL_KEY
        window?.decorView?.performHapticFeedback(effect)
    }

    private fun showQuickActions() {
        val actions = mutableListOf<Pair<String, () -> Unit>>()
        if (can("products", "edit")) actions.add("▦  Nuevo Producto" to { openProductForm() })
        if (can("materials", "edit")) actions.add("◈  Nuevo Valor IPV" to { openMaterialForm() })
        if (can("fichas", "edit")) actions.add("▤  Nueva Ficha de Costo" to { openFichaForm() })
        if (can("fichas")) actions.add("📊  Ver Estadísticas" to { openStatistics() })
        actions.add("⚙  Configuración" to { openSettings() })
        AlertDialog.Builder(this)
            .setTitle("Acciones Rápidas")
            .setItems(actions.map { it.first }.toTypedArray()) { _, which ->
                triggerHapticFeedback()
                actions[which].second()
            }
            .show()
    }

    private fun exportData(type: String) {
        executor.execute {
            try {
                val report = api.request("GET", "/api/report/$type") as JSONObject
                val data = report.optJSONArray("data") ?: JSONArray()
                if (data.length() == 0) {
                    runOnUiThread { toast("No hay datos para exportar") }
                    return@execute
                }
                
                val csv = StringBuilder()
                // Headers
                val first = data.getJSONObject(0)
                val keys = mutableListOf<String>()
                first.keys().forEach { keys.add(it) }
                csv.appendLine(keys.joinToString(";"))
                
                // Data rows
                for (i in 0 until data.length()) {
                    val row = data.getJSONObject(i)
                    val values = keys.map { key ->
                        "\"${row.optString(key).replace("\"", "\"\"")}\""
                    }
                    csv.appendLine(values.joinToString(";"))
                }
                
                runOnUiThread {
                    AlertDialog.Builder(this)
                        .setTitle("Exportar Datos")
                        .setMessage("Se han generado ${data.length()} registros.\n\n¿Deseas copiar al portapapeles?")
                        .setPositiveButton("Copiar") { _, _ ->
                            val clipboard = getSystemService(CLIPBOARD_SERVICE) as android.content.ClipboardManager
                            val clip = android.content.ClipData.newPlainText("IPV Export", csv.toString())
                            clipboard.setPrimaryClip(clip)
                            toast("Datos copiados al portapapeles")
                        }
                        .setNegativeButton("Cancelar", null)
                        .show()
                }
            } catch (error: Exception) {
                runOnUiThread { toast("Error al exportar: ${error.message}") }
            }
        }
    }
}
