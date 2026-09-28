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

// Design tokens — Paleta vibrante profesional
private val GREEN = 0xFF183B34.toInt()
private val GREEN_DARK = 0xFF122D28.toInt()
private val GREEN_LIGHT = 0xFF2A7057.toInt()
private val GREEN_PALE = 0xFFE8F2EC.toInt()
private val LIME = 0xFFD7E78D.toInt()
private val LIME_VIVID = 0xFFA8D850.toInt()
private val INK = 0xFF20352C.toInt()
private val MUTED = 0xFF7D8983.toInt()
private val LINE = 0xFFE6ECE7.toInt()
private val CANVAS = 0xFFF6F8F5.toInt()
private val SURFACE = 0xFFFFFFFF.toInt()
private val SUCCESS = 0xFF10B981.toInt()
private val ERROR = 0xFFEF4444.toInt()
private val WARNING = 0xFFF59E0B.toInt()
private val BLUE = 0xFF3B82F6.toInt()
private val PURPLE = 0xFF8B5CF6.toInt()

private const val APP_VERSION = "1.0.0"

private data class DraftLine(val materialId: Int, val quantity: String)

/**
 * Cliente HTTP de la API IPV.
 * · Envía el JWT en cada solicitud y lo renueva automáticamente (rotación de refresh token).
 * · Si no hay red, las consultas GET se sirven desde la caché offline cifrada.
 */
private class IpvApi(private val activity: Activity) {
    private val preferences = activity.getSharedPreferences("ipv_settings", Activity.MODE_PRIVATE)
    val session = Session(activity)
    val cache = OfflineCache(activity)
    val pinner = CertificatePinner(activity)
    @Volatile var lastFromCacheMinutes: Long = -1

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
        if (code != 200) { session.clear(); return false }
        session.save(JSONObject(text))
        return true
    }

    fun login(email: String, password: String, otp: String = ""): JSONObject {
        val (code, text) = raw("POST", "/api/auth/login",
            JSONObject().put("email", email).put("password", password).put("otp", otp), false)
        if (code == 401 && runCatching { JSONObject(text).optBoolean("mfa_required") }.getOrDefault(false)) {
            throw MfaRequiredException(errorOf(code, text))
        }
        if (code != 200) throw IOException(errorOf(code, text))
        val data = JSONObject(text)
        session.save(data)
        return data
    }

    /** Cambia la contraseña; el servidor devuelve tokens nuevos para ESTE dispositivo. */
    fun changePassword(current: String, new: String): JSONObject {
        val data = request("POST", "/api/auth/password", JSONObject().put("current", current).put("new", new)) as JSONObject
        session.save(data)
        return data
    }

    fun sessions(): JSONArray = request("GET", "/api/auth/sessions", cacheable = false) as JSONArray

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

    fun request(method: String, path: String, body: JSONObject? = null, cacheable: Boolean = true): Any {
        val result = try {
            var (code, text) = raw(method, path, body, true)
            if (code == 401 && renew()) {
                val retry = raw(method, path, body, true)
                code = retry.first; text = retry.second
            }
            if (code == 401) throw AuthRequiredException(errorOf(code, text))
            if (code == 403 && runCatching { JSONObject(text).optBoolean("password_expired") }.getOrDefault(false)) {
                throw PasswordExpiredException(errorOf(code, text))
            }
            if (code !in 200..299) throw IOException(errorOf(code, text))
            if (method == "GET" && cacheable) { cache.put(path, text); lastFromCacheMinutes = -1 }
            text
        } catch (error: IOException) {
            if (error is AuthRequiredException || error is PinMismatchException || error is PasswordExpiredException ||
                method != "GET" || !cacheable || error.message?.startsWith("Error HTTP") == true) throw error
            val cached = cache.get(path) ?: throw error
            lastFromCacheMinutes = cached.second
            cached.first
        }
        return JSONTokener(result).nextValue()
    }
}

class MainActivity : Activity() {
    private lateinit var api: IpvApi
    private lateinit var root: LinearLayout
    private lateinit var content: LinearLayout
    private lateinit var connectionLabel: TextView
    private val executor: ExecutorService = Executors.newSingleThreadExecutor()
    private var currentTab = "Resumen"
    private var dashboard = JSONObject()
    private var products = JSONArray()
    private var materials = JSONArray()
    private var fichas = JSONArray()
    private var controls = JSONArray()
    private val tabs = listOf("Resumen", "Productos", "Valores IPV", "Fichas", "Controles")

    private var realtime: RealtimeClient? = null
    private var unlocked = false
    private lateinit var license: LicenseManager
    private var licenseDialog: AlertDialog? = null

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
        addText(form, "🔒 Acceso seguro · ${api.baseUrl}", 11f, MUTED, false, bottom = 8)
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
            background = rounded(Color.WHITE, 8, PURPLE)
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

    private fun rounded(color: Int, radius: Int = 12, stroke: Int? = null): GradientDrawable = GradientDrawable().apply {
        setColor(color)
        cornerRadius = dp(radius).toFloat()
        if (stroke != null) setStroke(dp(1), stroke)
    }

    private fun label(value: String, size: Float = 14f, color: Int = INK, bold: Boolean = false): TextView = TextView(this).apply {
        text = value
        textSize = size
        setTextColor(color)
        if (bold) setTypeface(typeface, Typeface.BOLD)
        includeFontPadding = true
    }

    private fun makeButton(value: String, primary: Boolean = false, click: () -> Unit): Button = Button(this).apply {
        text = value
        textSize = 12f
        isAllCaps = false
        setTextColor(if (primary) Color.WHITE else GREEN)
        background = rounded(if (primary) GREEN else 0xFFFFFFFF.toInt(), 9, if (primary) null else LINE)
        minHeight = dp(42)
        setPadding(dp(14), dp(3), dp(14), dp(3))
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
            background = GradientDrawable(GradientDrawable.Orientation.LEFT_RIGHT, intArrayOf(LIME_VIVID.toInt(), LIME.toInt(), GREEN_LIGHT))
        }
        root.addView(accentStripe, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(4)))

        val header = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(18), dp(14), dp(12), dp(14))
            setBackgroundColor(GREEN)
        }
        val brand = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val logo = label("iv   IPV", 19f, LIME, true)
        val subtitle = label("FICHAS Y COSTOS · GESTIÓN INTEGRAL", 9f, 0xFFD1DFD5.toInt(), true)
        brand.addView(logo)
        brand.addView(subtitle)
        header.addView(brand, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))

        val statsBtn = makeButton("📊", false) { openStatistics() }.apply {
            setTextColor(Color.WHITE)
            background = rounded(0x2AFFFFFF, 9)
            minWidth = dp(45)
        }
        header.addView(statsBtn)

        val aboutBtn = makeButton("ℹ", false) { openAbout() }.apply {
            setTextColor(Color.WHITE)
            background = rounded(0x2AFFFFFF, 9)
            minWidth = dp(45)
        }
        header.addView(aboutBtn)

        val settings = makeButton("⚙", false) { openSettings() }.apply {
            setTextColor(Color.WHITE)
            background = rounded(0x2AFFFFFF, 9)
            minWidth = dp(45)
        }
        header.addView(settings)
        root.addView(header)

        // Connection indicator
        connectionLabel = label("Conectando…", 10f, MUTED).apply {
            setPadding(dp(18), dp(8), dp(18), dp(8))
            setBackgroundColor(SURFACE)
        }
        root.addView(connectionLabel)

        // Tab navigation
        val horizontal = HorizontalScrollView(this).apply { isHorizontalScrollBarEnabled = false; setBackgroundColor(SURFACE) }
        val nav = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            setPadding(dp(10), dp(5), dp(10), dp(7))
            setBackgroundColor(Color.WHITE)
        }
        tabs.forEach { tab ->
            val navButton = TextView(this).apply {
                text = tab
                textSize = 11f
                gravity = Gravity.CENTER
                setPadding(dp(12), dp(9), dp(12), dp(9))
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
        val nav = (root.getChildAt(3) as HorizontalScrollView).getChildAt(0) as LinearLayout
        for (index in 0 until nav.childCount) {
            val item = nav.getChildAt(index) as TextView
            val selected = item.tag == currentTab
            item.setTextColor(if (selected) Color.WHITE else MUTED)
            item.background = rounded(if (selected) GREEN else Color.WHITE, 8)
        }
    }

    private fun refresh(silent: Boolean = false) {
        updateTabStyle()
        if (!silent) {
            connectionLabel.text = "Conectando a ${api.baseUrl} …"
            connectionLabel.setTextColor(WARNING)
            content.removeAllViews()
            addText(content, "Cargando datos desde la base de datos…", 13f, MUTED)
        }
        executor.execute {
            try {
                val freshDashboard = api.request("GET", "/api/dashboard") as JSONObject
                val freshProducts = api.request("GET", "/api/products") as JSONArray
                val freshMaterials = api.request("GET", "/api/materials") as JSONArray
                val freshFichas = api.request("GET", "/api/fichas") as JSONArray
                val freshControls = api.request("GET", "/api/controls") as JSONArray
                runOnUiThread {
                    dashboard = freshDashboard
                    products = freshProducts
                    materials = freshMaterials
                    fichas = freshFichas
                    controls = freshControls
                    val offline = api.lastFromCacheMinutes
                    if (offline >= 0) {
                        connectionLabel.text = "●  Sin conexión · datos guardados hace $offline min"
                        connectionLabel.setTextColor(WARNING)
                    } else {
                        val who = api.session.user?.optString("name")?.let { " · $it" } ?: ""
                        connectionLabel.text = "●  Conectado en tiempo real$who"
                        connectionLabel.setTextColor(SUCCESS)
                    }
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
            "Fichas" -> renderFichas()
            "Controles" -> renderControls()
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
        statRow(grid, "Valores de referencia", dashboard.optString("materials", "0"), "Insumos registrados")
        content.addView(grid)

        addSpacer(content, 12)
        addText(content, "FICHAS RECIENTES", 9f, MUTED, true, bottom = 6)
        val recentFichas = dashboard.optJSONArray("recent_fichas") ?: JSONArray()
        if (recentFichas.length() == 0) {
            addText(content, "Aún no hay fichas registradas.", 11f, MUTED, bottom = 8)
        } else {
            for (i in 0 until recentFichas.length()) {
                val f = recentFichas.getJSONObject(i)
                val card = card(f.optString("product_name", ""), "${f.optString("status", "")} · ${formatAmount(f.optString("total_cost", "0"))} CUP")
                card.setOnClickListener { openFichaDetail(f.optInt("id")) }
                content.addView(card)
            }
        }
    }

    // ==================== Products ====================

    private fun renderProducts() {
        addHeading(content, "Productos y servicios", "Catálogo de elementos con ficha de costo.")
        addButton(content, "＋  Nuevo producto", true) { openProductForm() }
        addSpacer(content, 6)
        val active = products.toObjectList().filter { it.optInt("active", 1) == 1 }
        if (active.isEmpty()) {
            addText(content, "No hay productos activos en el catálogo.", 11f, MUTED)
        } else {
            active.forEach { p ->
                val card = card(p.optString("name", ""), "${p.optString("category", "")} · ${p.optString("code", "")}")
                content.addView(card)
            }
        }
    }

    // ==================== Materials ====================

    private fun renderMaterials() {
        addHeading(content, "Valores del IPV", "Insumos, materias primas y servicios con precios unitarios.")
        addButton(content, "＋  Nuevo valor", true) { openMaterialForm() }
        addSpacer(content, 6)
        val list = materials.toObjectList()
        if (list.isEmpty()) {
            addText(content, "No hay valores de referencia registrados.", 11f, MUTED)
        } else {
            list.forEach { m ->
                val card = card(m.optString("name", ""), "${formatAmount(m.optString("unit_price", "0"))} CUP / ${m.optString("unit", "")} · ${m.optString("status", "")}")
                content.addView(card)
            }
        }
    }

    // ==================== Fichas ====================

    private fun renderFichas() {
        addHeading(content, "Fichas de costo", "Documentos versionados con los componentes y el costo total.")
        addButton(content, "＋  Nueva ficha", true) { openFichaForm() }
        addSpacer(content, 6)
        val list = fichas.toObjectList()
        if (list.isEmpty()) {
            addText(content, "No hay fichas de costo registradas.", 11f, MUTED)
        } else {
            list.forEach { f ->
                val card = card("${f.optString("product_name", "")} · v${f.optInt("version", 0)}", "${f.optString("status", "")} · ${formatAmount(f.optString("total_cost", "0"))} CUP")
                card.setOnClickListener { openFichaDetail(f.optInt("id")) }
                content.addView(card)
            }
        }
    }

    // ==================== Controls ====================

    private fun renderControls() {
        addHeading(content, "Controles de IPV", "Instantáneas de verificación vinculadas a fichas aprobadas.")
        val list = controls.toObjectList()
        if (list.isEmpty()) {
            addText(content, "No hay controles registrados. Genera uno desde una ficha aprobada.", 11f, MUTED)
        } else {
            list.forEach { c ->
                val card = card(c.optString("code", ""), "${c.optString("product_name", "")} · ${c.optString("period", "")} · ${c.optString("status", "")}")
                card.setOnClickListener { openControlDetail(c.optInt("id")) }
                content.addView(card)
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
        addText(parent, title, 20f, INK, true, bottom = 2)
        addText(parent, subtitle, 11f, MUTED, false, bottom = 12)
    }

    private fun addSpacer(parent: LinearLayout, height: Int) {
        parent.addView(View(this).apply { minimumHeight = dp(height) }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(height)))
    }

    private fun addButton(parent: LinearLayout, value: String, primary: Boolean, click: () -> Unit) {
        val btn = makeButton(value, primary, click)
        parent.addView(btn, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(8) })
    }

    private fun card(title: String, subtitle: String): LinearLayout {
        val row = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(16), dp(14), dp(16), dp(14))
            background = rounded(SURFACE, 12, LINE)
            isClickable = true
            isFocusable = true
            elevation = dp(2).toFloat()
        }
        // Accent stripe at top
        val stripe = View(this).apply {
            minimumHeight = dp(3)
            background = GradientDrawable(GradientDrawable.Orientation.LEFT_RIGHT, intArrayOf(LIME_VIVID.toInt(), GREEN_LIGHT))
        }
        row.addView(stripe, LinearLayout.LayoutParams(dp(40), dp(3)).apply { bottomMargin = dp(8) })
        row.addView(label(title, 14f, INK, true))
        row.addView(label(subtitle, 10f, MUTED).apply { setPadding(0, dp(4), 0, 0) })
        content.addView(row, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(8) })
        return row
    }

    private var statIndex = 0
    private fun statRow(parent: LinearLayout, title: String, value: String, note: String) {
        val accentColors = intArrayOf(SUCCESS, BLUE, WARNING.toInt(), PURPLE)
        val accent = accentColors[statIndex % accentColors.size]
        statIndex++

        val row = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(14), dp(12), dp(14), dp(12))
            background = rounded(SURFACE, 12, LINE)
            elevation = dp(1).toFloat()
        }
        // Colored indicator
        val indicator = View(this).apply {
            background = rounded(accent, 6)
        }
        row.addView(indicator, LinearLayout.LayoutParams(dp(4), dp(36)).apply { rightMargin = dp(12) })
        val left = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        left.addView(label(title, 11f, MUTED, true))
        left.addView(label(note, 9f, 0xFF9AA49E.toInt()).apply { setPadding(0, dp(3), 0, 0) })
        row.addView(left, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        row.addView(label(value, 24f, INK, true))
        parent.addView(row, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(6) })
    }

    private fun formatAmount(value: String): String {
        val n = value.toDoubleOrNull() ?: 0.0
        return String.format("%.2f", n)
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
            textSize = 13f
            setPadding(dp(12), dp(10), dp(12), dp(10))
            background = rounded(Color.WHITE, 8, LINE)
            setTextColor(INK)
            setHintTextColor(0xFFBCC5BF.toInt())
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

    private fun openProductForm() {
        val form = formContainer()
        val code = field(form, "Código *")
        val name = field(form, "Nombre *")
        val category = field(form, "Categoría *", value = "Bebidas")
        val unit = field(form, "Unidad", value = "unidad")
        showFormDialog("Nuevo producto o servicio", scrollForm(form), "Registrar") { dialog ->
            val c = code.text.toString().trim()
            val n = name.text.toString().trim()
            val cat = category.text.toString().trim()
            if (c.isEmpty() || n.isEmpty() || cat.isEmpty()) { toast("Código, nombre y categoría son obligatorios."); return@showFormDialog }
            val body = JSONObject().put("code", c).put("name", n).put("category", cat).put("unit", unit.text.toString().ifBlank { "unidad" })
            runApi(dialog, "Producto registrado correctamente.") { api.request("POST", "/api/products", body) }
        }
    }

    private fun openMaterialForm() {
        val form = formContainer()
        val code = field(form, "Código *")
        val name = field(form, "Nombre *")
        val unit = field(form, "Unidad *", value = "kg")
        val price = field(form, "Precio unitario *", InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL)
        val supplier = field(form, "Proveedor")
        val source = field(form, "Fuente / documento")
        showFormDialog("Nuevo valor de referencia", scrollForm(form), "Registrar") { dialog ->
            val c = code.text.toString().trim()
            val n = name.text.toString().trim()
            val u = unit.text.toString().trim()
            if (c.isEmpty() || n.isEmpty() || u.isEmpty()) { toast("Código, nombre y unidad son obligatorios."); return@showFormDialog }
            val body = JSONObject().put("code", c).put("name", n).put("unit", u)
                .put("unit_price", price.text.toString().ifBlank { "0" })
                .put("supplier", supplier.text.toString())
                .put("source", source.text.toString())
            runApi(dialog, "Valor de referencia registrado.") { api.request("POST", "/api/materials", body) }
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

        val quantity = field(form, "Cantidad", InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL, "1")
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
                .put("items", itemArray)
            runApi(dialog, "Ficha creada como borrador.") { api.request("POST", "/api/fichas", body) }
        }
    }

    private fun renderDraftLines(target: LinearLayout, lines: MutableList<DraftLine>, materialsList: List<JSONObject>) {
        target.removeAllViews()
        lines.forEachIndexed { index, line ->
            val material = materialsList.find { it.optInt("id") == line.materialId }
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(0, dp(3), 0, dp(3)) }
            val info = label("${material?.optString("name") ?: "Insumo"} · ${line.quantity} ${material?.optString("unit") ?: ""}", 10f, MUTED)
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
                        append("Costo total: ${formatAmount(ficha.optString("total_cost"))} CUP\n\n")
                        val lines = ficha.optJSONArray("items") ?: JSONArray()
                        for (i in 0 until lines.length()) {
                            val line = lines.getJSONObject(i)
                            append("• ${line.optString("description")} — ${line.optString("quantity")} ${line.optString("unit")} = ${formatAmount(line.optString("subtotal"))} CUP\n")
                        }
                        if (ficha.optString("observations").isNotBlank()) append("\n${ficha.optString("observations")}")
                    }
                    AlertDialog.Builder(this).setTitle("Ficha de Costo").setMessage(message)
                        .setPositiveButton("Cerrar", null)
                        .apply { if (ficha.optString("status") == "Borrador") setNeutralButton("Aprobar", null) }
                        .apply { if (ficha.optString("status") == "Aprobada") setNeutralButton("Generar Control", null) }
                        .create().also { dialog ->
                            dialog.setOnShowListener {
                                if (ficha.optString("status") == "Borrador") dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener { dialog.dismiss(); approveFicha(id) }
                                if (ficha.optString("status") == "Aprobada") dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener { dialog.dismiss(); openGenerateControl(id) }
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
                    val verifiedTotal = if (control.optString("checked_at").isBlank()) "Sin validar" else formatAmount(control.optString("checked_total")) + " CUP"
                    val message = buildString {
                        append("${control.optString("product_name")} · ficha v${control.optInt("ficha_version")}\n")
                        append("Período: ${control.optString("period")}\nEstado: ${control.optString("status")}\n")
                        append("Total registrado: ${formatAmount(control.optString("snapshot_total"))} CUP\n")
                        append("Total verificado: $verifiedTotal\n\nLíneas: ${lines.length()}\n")
                        for (i in 0 until messages.length()) append("\n${messages.getJSONObject(i).optString("text")}")
                    }
                    val dialog = AlertDialog.Builder(this).setTitle("Control IPV · ${control.optString("code")}")
                        .setMessage(message).setPositiveButton("Cerrar", null)
                        .apply { if (control.optString("status") != "Validado") setNeutralButton("Validar", null) }
                        .create()
                    dialog.setOnShowListener {
                        if (control.optString("status") != "Validado") dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener { dialog.dismiss(); validateControl(id) }
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
        addText(form, "Huella del certificado fijado (SHA-256):", 10f, MUTED, true)
        addText(form, api.pinner.pretty(api.pinner.pin), 9f, INK)
        val pinField = field(form, "Nueva huella (de: iniciar-https.ps1 -ShowPin) — vacío = no cambiar")
        val resetPin = android.widget.CheckBox(this).apply {
            text = "Olvidar la huella y confiar en la próxima conexión"
            setTextColor(WARNING)
        }
        form.addView(resetPin)
        if (user != null) addButton(form, "🛡  Seguridad de la cuenta (dispositivos y contraseña)", true) { openAccountSecurity() }
        if (LicenseCore.enforced) addButton(form, "🔑  Licencia: estado y renovación", false) { openLicense(forced = false) {} }
        if (user != null) addButton(form, "Cerrar sesión y borrar datos locales", false) {
            executor.execute {
                api.logout()
                runOnUiThread { toast("Sesión cerrada."); refresh() }
            }
        }
        showFormDialog("Configuración de conexión", scrollForm(form), "Guardar y probar") { dialog ->
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

    /** Ejecuta [action] solo si hay licencia vigente; si no, muestra la activación (no se puede omitir). */
    private fun licenseGate(action: () -> Unit) {
        if (!LicenseCore.enforced) { action(); return }
        try {
            val info = license.current()
            val left = info.daysLeft(System.currentTimeMillis() / 1000)
            if (left <= 7) toast("⏳ Su licencia (${info.planName}) vence en $left día(s): ${info.expiryText()}")
            action()
        } catch (e: LicenseCore.LicenseException) {
            openLicense(forced = true, reason = e.message ?: "", onActivated = action)
        }
    }

    private fun openLicense(forced: Boolean, reason: String = "", onActivated: () -> Unit) {
        if (licenseDialog?.isShowing == true) return
        val form = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(20), dp(8), dp(20), dp(4)) }
        val current = runCatching { license.current() }.getOrNull()
        val status = when {
            current != null -> "✅ Licencia vigente: ${current.planName} a nombre de ${current.user}. Vence el ${current.expiryText()} " +
                "(${current.daysLeft(System.currentTimeMillis() / 1000)} días). Serie ${current.serial}."
            reason.isNotBlank() -> "🔒 $reason"
            else -> "🔒 Este teléfono necesita una licencia."
        }
        form.addView(label(status, 13f, if (current != null) SUCCESS else ERROR, true).apply { setPadding(0, 0, 0, dp(10)) })
        form.addView(label("1. Escriba su nombre y elija el plan.\n2. Envíe la solicitud por WhatsApp.\n3. Pegue la licencia recibida y pulse Activar.", 12f, MUTED))
        val user = EditText(this).apply { hint = "Usuario (nombre o empresa)"; setSingleLine() }
        form.addView(user)
        val planKeys = LicenseCore.PLANS.keys.toList()
        val plan = Spinner(this).apply {
            adapter = ArrayAdapter(this@MainActivity, android.R.layout.simple_spinner_dropdown_item,
                LicenseCore.PLANS.values.map { "${it.first} — ${it.third} USD" })
            setSelection(1)
        }
        form.addView(plan)
        form.addView(label("ID Dispositivo (cifrado)", 11f, MUTED, true).apply { setPadding(0, dp(10), 0, dp(2)) })
        form.addView(TextView(this).apply {
            text = license.requestCode
            typeface = Typeface.MONOSPACE
            textSize = 14f
            setTextColor(LIME_VIVID)
            setTextIsSelectable(true)
            background = rounded(GREEN_DARK, 10)
            setPadding(dp(12), dp(10), dp(12), dp(10))
        })
        val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; setPadding(0, dp(8), 0, dp(8)) }
        row.addView(makeButton("📋 Copiar", false) {
            val cm = getSystemService(CLIPBOARD_SERVICE) as android.content.ClipboardManager
            cm.setPrimaryClip(android.content.ClipData.newPlainText("ID Dispositivo IPV", license.requestCode))
            toast("Código copiado")
        }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { rightMargin = dp(6) })
        row.addView(makeButton("💬 WhatsApp", true) {
            val planName = "${LicenseCore.PLANS.getValue(planKeys[plan.selectedItemPosition]).first} (${planKeys[plan.selectedItemPosition]})"
            val text = license.whatsappMessage(user.text.toString().trim(), planName)
            val uri = android.net.Uri.parse("https://wa.me/${LicenseCore.WHATSAPP_NUMBER}?text=${android.net.Uri.encode(text)}")
            try {
                startActivity(android.content.Intent(android.content.Intent.ACTION_VIEW, uri))
            } catch (e: android.content.ActivityNotFoundException) {
                toast("No se encontró WhatsApp. Copie el código y envíelo manualmente.")
            }
        }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        form.addView(row)
        val token = EditText(this).apply {
            hint = "Pegue aquí la licencia (IPV1.…)"
            minLines = 3
            typeface = Typeface.MONOSPACE
            textSize = 12f
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
        }
        form.addView(token)
        form.addView(label("La licencia está firmada digitalmente y solo funciona en este teléfono.", 11f, MUTED).apply { setPadding(0, dp(6), 0, 0) })
        val dialog = AlertDialog.Builder(this)
            .setTitle(if (current != null) "🔑 Renovar licencia" else "🔑 Activar licencia")
            .setView(ScrollView(this).apply { addView(form) })
            .setPositiveButton("Activar", null)
            .setNegativeButton(if (forced) "Salir" else "Cerrar", null)
            .setCancelable(!forced)
            .create()
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                try {
                    val info = license.activate(token.text.toString())
                    toast("✅ Licencia activada: ${info.planName}, vence el ${info.expiryText()}")
                    dialog.dismiss()
                    onActivated()
                } catch (e: LicenseCore.LicenseException) {
                    token.error = e.message
                } catch (e: org.json.JSONException) {
                    token.error = "La licencia está dañada."
                }
            }
            dialog.getButton(AlertDialog.BUTTON_NEGATIVE).setOnClickListener {
                dialog.dismiss()
                if (forced) finish()
            }
        }
        licenseDialog = dialog
        dialog.show()
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
                    if (topExpensive.length() > 0) {
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
        val actions = arrayOf(
            "▦  Nuevo Producto",
            "◈  Nuevo Valor IPV",
            "▤  Nueva Ficha de Costo",
            "📊  Ver Estadísticas",
            "⚙  Configuración"
        )
        AlertDialog.Builder(this)
            .setTitle("Acciones Rápidas")
            .setItems(actions) { _, which ->
                triggerHapticFeedback()
                when (which) {
                    0 -> openProductForm()
                    1 -> openMaterialForm()
                    2 -> openFichaForm()
                    3 -> openStatistics()
                    4 -> openSettings()
                }
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
