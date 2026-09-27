package cu.ipvcostos.app

import android.app.Activity
import android.app.AlertDialog
import android.graphics.Typeface
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.ArrayAdapter
import android.widget.Button
import android.widget.EditText
import android.widget.HorizontalScrollView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Spinner
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

private val GREEN = 0xFF183B34.toInt()
private val GREEN_DARK = 0xFF122D28.toInt()
private val GREEN_PALE = 0xFFE8F2EC.toInt()
private val LIME = 0xFFD7E78D.toInt()
private val INK = 0xFF20352C.toInt()
private val MUTED = 0xFF7D8983.toInt()
private val LINE = 0xFFE6ECE7.toInt()
private val CANVAS = 0xFFF6F8F5.toInt()

private data class DraftLine(val materialId: Int, val quantity: String)

/** Small HTTP client. Both native and web clients read/write through the same SQLite API. */
private class IpvApi(private val activity: Activity) {
    private val preferences = activity.getSharedPreferences("ipv_settings", Activity.MODE_PRIVATE)
    var baseUrl: String
        get() = preferences.getString("base_url", "https://10.0.2.2:8443")!!.trimEnd('/')
        set(value) { preferences.edit().putString("base_url", value.trim().trimEnd('/')).apply() }

    fun request(method: String, path: String, body: JSONObject? = null): Any {
        val connection = (URL(baseUrl + path).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 8000
            readTimeout = 12000
            setRequestProperty("Accept", "application/json")
            if (body != null) {
                doOutput = true
                setRequestProperty("Content-Type", "application/json; charset=utf-8")
            }
        }
        try {
            if (body != null) connection.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            val code = connection.responseCode
            val stream = if (code in 200..299) connection.inputStream else connection.errorStream
            val text = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() } ?: "{}"
            if (code !in 200..299) {
                val message = try { JSONObject(text).optString("error", "Error HTTP $code") } catch (_: Exception) { "Error HTTP $code" }
                throw IOException(message)
            }
            return JSONTokener(text).nextValue()
        } finally {
            connection.disconnect()
        }
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

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        api = IpvApi(this)
        window.statusBarColor = GREEN_DARK
        window.navigationBarColor = GREEN_DARK
        buildShell()
        refresh()
    }

    override fun onDestroy() {
        executor.shutdown()
        super.onDestroy()
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
        val header = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(18), dp(12), dp(12), dp(12))
            setBackgroundColor(GREEN)
        }
        val brand = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val logo = label("iv   IPV", 19f, LIME, true)
        val subtitle = label("FICHAS Y COSTOS · SQLITE", 9f, 0xFFD1DFD5.toInt(), true)
        brand.addView(logo)
        brand.addView(subtitle)
        header.addView(brand, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        val settings = makeButton("⚙", false) { openSettings() }.apply {
            setTextColor(Color.WHITE)
            background = rounded(0x2AFFFFFF, 9)
            minWidth = dp(45)
        }
        header.addView(settings)
        root.addView(header)

        connectionLabel = label("Conectando…", 10f, 0xFF6F7E75.toInt()).apply {
            setPadding(dp(18), dp(8), dp(18), dp(8))
            setBackgroundColor(Color.WHITE)
        }
        root.addView(connectionLabel)

        val horizontal = HorizontalScrollView(this).apply { isHorizontalScrollBarEnabled = false; setBackgroundColor(Color.WHITE) }
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

        val scroll = ScrollView(this).apply { fillViewport = true; clipToPadding = false }
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
        val nav = (root.getChildAt(2) as HorizontalScrollView).getChildAt(0) as LinearLayout
        for (index in 0 until nav.childCount) {
            val item = nav.getChildAt(index) as TextView
            val selected = item.tag == currentTab
            item.setTextColor(if (selected) Color.WHITE else MUTED)
            item.background = rounded(if (selected) GREEN else Color.WHITE, 8)
        }
    }

    private fun refresh() {
        updateTabStyle()
        connectionLabel.text = "Conectando a ${api.baseUrl} …"
        connectionLabel.setTextColor(0xFF9A7C3A.toInt())
        content.removeAllViews()
        addText(content, "Cargando datos desde SQLite…", 13f, MUTED)
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
                    connectionLabel.text = "●  SQLite conectado · ${api.baseUrl}"
                    connectionLabel.setTextColor(0xFF43815C.toInt())
                    renderPage()
                }
            } catch (error: Exception) {
                runOnUiThread {
                    connectionLabel.text = "●  Sin conexión · ${error.message ?: "revisa la dirección del servidor"}"
                    connectionLabel.setTextColor(0xFFB8544B.toInt())
                    content.removeAllViews()
                    addHeading(content, "No se pudo conectar", "Inicia el servidor SQLite y comprueba la dirección configurada.")
                    addButton(content, "Configurar servidor", true) { openSettings() }
                    addButton(content, "Reintentar", false) { refresh() }
                }
            }
        }
    }

    private fun renderPage() {
        content.removeAllViews()
        updateTabStyle()
        when (currentTab) {
            "Resumen" -> renderDashboard()
            "Productos" -> renderProducts()
            "Valores IPV" -> renderMaterials()
            "Fichas" -> renderFichas()
            "Controles" -> renderControls()
        }
    }

    private fun addText(parent: LinearLayout, value: String, size: Float = 13f, color: Int = INK, bold: Boolean = false, top: Int = 0, bottom: Int = 0) {
        val view = label(value, size, color, bold)
        view.setPadding(0, dp(top), 0, dp(bottom))
        parent.addView(view)
    }

    private fun addHeading(parent: LinearLayout, title: String, subtitle: String) {
        addText(parent, currentTab.uppercase(), 9f, 0xFF718E7D.toInt(), true, bottom = 7)
        addText(parent, title, 25f, INK, true, bottom = 5)
        addText(parent, subtitle, 12f, MUTED, false, bottom = 16)
    }

    private fun addButton(parent: LinearLayout, text: String, primary: Boolean, action: () -> Unit) {
        val button = makeButton(text, primary, action)
        parent.addView(button, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply {
            topMargin = dp(5); bottomMargin = dp(5)
        })
    }

    private fun addCard(parent: LinearLayout, title: String, subtitle: String? = null, contentViews: (LinearLayout) -> Unit) {
        val card = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(14), dp(13), dp(14), dp(13))
            background = rounded(Color.WHITE, 13, LINE)
        }
        addText(card, title, 14f, INK, true, bottom = 3)
        if (!subtitle.isNullOrBlank()) addText(card, subtitle, 10f, MUTED, false, bottom = 8)
        contentViews(card)
        parent.addView(card, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(10) })
    }

    private fun addStatus(parent: LinearLayout, status: String) {
        val color = when {
            status.contains("Aprobada", true) || status.contains("Validado", true) || status.contains("Vigente", true) -> 0xFF43815C.toInt()
            status.contains("Difer", true) -> 0xFFB8544B.toInt()
            status.contains("Borrador", true) || status.contains("Pendiente", true) -> 0xFF9A7A31.toInt()
            else -> 0xFF617899.toInt()
        }
        val badge = TextView(this).apply {
            text = "●  $status"
            textSize = 10f
            setTextColor(color)
            setPadding(dp(9), dp(5), dp(9), dp(5))
            background = rounded(0xFFF3F6F2.toInt(), 20)
        }
        parent.addView(badge)
    }

    private fun renderDashboard() {
        addHeading(content, "Controla tus costos con claridad.", "Productos, valores del IPV y fichas conectados a SQLite.")
        val note = label("MODO DEMOSTRACIÓN · importes y datos de muestra ficticios", 10f, 0xFF756A49.toInt(), true).apply {
            setPadding(dp(12), dp(11), dp(12), dp(11)); background = rounded(0xFFF6F3E8.toInt(), 10)
        }
        content.addView(note, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(14) })
        val metrics = listOf(
            "Productos activos" to dashboard.optInt("products"),
            "Fichas de costo" to dashboard.optInt("fichas"),
            "Controles pendientes" to dashboard.optInt("pending_controls"),
            "Valores de referencia" to dashboard.optInt("materials")
        )
        metrics.chunked(2).forEach { pair ->
            val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
            pair.forEach { (title, value) ->
                val box = LinearLayout(this).apply {
                    orientation = LinearLayout.VERTICAL
                    setPadding(dp(13), dp(13), dp(10), dp(12))
                    background = rounded(Color.WHITE, 12, LINE)
                }
                addText(box, title, 10f, MUTED, false, bottom = 10)
                addText(box, value.toString(), 25f, INK, true, bottom = 3)
                addText(box, when (title) {
                    "Fichas de costo" -> "${dashboard.optInt("approved_fichas")} aprobadas"
                    "Controles pendientes" -> "por revisar"
                    "Valores de referencia" -> "insumos y servicios"
                    else -> "en el catálogo"
                }, 9f, MUTED)
                row.addView(box, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { rightMargin = dp(6); bottomMargin = dp(8) })
            }
            content.addView(row)
        }
        addButton(content, "＋  Crear Ficha de Costo", true) { openNewFichaDialog() }
        addCard(content, "Fichas recientes", "Últimas versiones modificadas") { card ->
            val recent = dashboard.optJSONArray("recent_fichas") ?: JSONArray()
            if (recent.length() == 0) addText(card, "Todavía no hay fichas.", 11f, MUTED)
            for (i in 0 until minOf(recent.length(), 4)) {
                val item = recent.getJSONObject(i)
                val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL; setPadding(0, dp(8), 0, dp(8)) }
                val info = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
                addText(info, item.optString("product_name"), 12f, INK, true, bottom = 3)
                addText(info, "${item.optString("category")} · ${item.optString("status")}", 9f, MUTED)
                row.addView(info, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
                addText(row, "${formatAmount(item.optString("total_cost"))} CUP", 11f, GREEN, true)
                card.addView(row)
                if (i < minOf(recent.length(), 4) - 1) addDivider(card)
            }
        }
        addCard(content, "Controles pendientes", "Revisa y valida los controles generados desde las fichas") { card ->
            val pending = controls.toObjectList().filter { it.optString("status") == "Pendiente" || it.optString("status") == "Con diferencias" }
            if (pending.isEmpty()) addText(card, "No hay controles pendientes.", 11f, MUTED)
            pending.take(3).forEach { c ->
                addText(card, "${c.optString("code")} · ${c.optString("product_name")}", 11f, INK, true, top = 6, bottom = 4)
                addText(card, "Período ${c.optString("period")} · ${formatAmount(c.optString("snapshot_total"))} CUP", 9f, MUTED, bottom = 6)
            }
            if (pending.isNotEmpty()) addButton(card, "Abrir controles", false) { currentTab = "Controles"; refresh() }
        }
    }

    private fun renderProducts() {
        addHeading(content, "Productos y servicios", "Catálogo común para las fichas de costo.")
        addButton(content, "＋  Nuevo producto o servicio", true) { openProductDialog() }
        val rows = products.toObjectList()
        if (rows.isEmpty()) emptyCard("Catálogo vacío", "Registra un producto o servicio para iniciar.")
        rows.forEach { p ->
            if (p.optInt("active", 1) == 0) return@forEach
            addCard(content, p.optString("name"), "${p.optString("code")} · ${p.optString("category")}") { card ->
                addText(card, "Unidad de salida: ${p.optString("unit")}", 10f, MUTED, bottom = 8)
                val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
                addText(row, "${p.optInt("ficha_count")} versiones de ficha", 10f, MUTED)
                card.addView(row)
            }
        }
    }

    private fun renderMaterials() {
        addHeading(content, "Valores del IPV", "Valores de referencia con unidad, vigencia y procedencia.")
        addButton(content, "＋  Registrar valor del IPV", true) { openNewMaterialDialog() }
        val rows = materials.toObjectList()
        if (rows.isEmpty()) emptyCard("Sin valores registrados", "Añade insumos para utilizarlos en las fichas.")
        rows.forEach { m ->
            addCard(content, m.optString("name"), "${m.optString("code")} · ${m.optString("unit")}") { card ->
                val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
                val price = label("${formatAmount(m.optString("unit_price"))} ${m.optString("currency", "CUP")}", 14f, GREEN, true)
                row.addView(price, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
                addStatus(row, m.optString("status", "Vigente"))
                card.addView(row)
                val source = m.optString("source").ifBlank { m.optString("supplier").ifBlank { "Fuente no indicada" } }
                addText(card, "${m.optString("effective_from", "Sin fecha")} · ${source}", 9f, MUTED, false, top = 7)
            }
        }
    }

    private fun renderFichas() {
        addHeading(content, "Fichas de costo", "Versiona componentes y cantidades; cada ficha alimenta un control.")
        addButton(content, "＋  Nueva Ficha de Costo", true) { openNewFichaDialog() }
        val rows = fichas.toObjectList()
        if (rows.isEmpty()) emptyCard("Todavía no hay fichas", "Selecciona un producto y añade los insumos de su costo.")
        rows.forEach { f ->
            addCard(content, f.optString("product_name"), "${f.optString("product_code")} · ${f.optString("category")} · versión ${f.optInt("version")}") { card ->
                val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
                addText(row, "${formatAmount(f.optString("total_cost"))} CUP", 16f, GREEN, true)
                row.addView(View(this), LinearLayout.LayoutParams(0, 1, 1f))
                addStatus(row, f.optString("status"))
                card.addView(row)
                addText(card, "${f.optInt("item_count")} componentes · vigente desde ${f.optString("valid_from")}", 9f, MUTED, false, top = 8, bottom = 8)
                val actions = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
                val view = makeButton("Ver detalle", false) { openFichaDetail(f.optInt("id")) }
                actions.addView(view, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { rightMargin = dp(4) })
                if (f.optString("status") == "Borrador") {
                    val approve = makeButton("Aprobar", false) { approveFicha(f.optInt("id")) }
                    actions.addView(approve, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { rightMargin = dp(4) })
                }
                val control = makeButton("＋ Control IPV", true) { openGenerateControl(f.optInt("id")) }
                actions.addView(control, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
                card.addView(actions)
            }
        }
    }

    private fun renderControls() {
        addHeading(content, "Controles de IPV", "Instantáneas vinculadas a una versión específica de ficha.")
        val rows = controls.toObjectList()
        if (rows.isEmpty()) emptyCard("Sin controles", "Abre una ficha de costo y genera el Control de IPV correspondiente.")
        rows.forEach { c ->
            addCard(content, c.optString("code"), "${c.optString("product_name")} · ficha v${c.optInt("ficha_version")} · ${c.optString("period")}") { card ->
                val row = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL; gravity = Gravity.CENTER_VERTICAL }
                addText(row, "${formatAmount(c.optString("snapshot_total"))} CUP", 16f, GREEN, true)
                row.addView(View(this), LinearLayout.LayoutParams(0, 1, 1f))
                addStatus(row, c.optString("status"))
                card.addView(row)
                val actions = LinearLayout(this).apply { orientation = LinearLayout.HORIZONTAL }
                actions.addView(makeButton("Ver detalle", false) { openControlDetail(c.optInt("id")) }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { rightMargin = dp(5) })
                if (c.optString("status") != "Validado") actions.addView(makeButton("Validar", true) { validateControl(c.optInt("id")) }, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
                card.addView(actions)
            }
        }
    }

    private fun emptyCard(title: String, description: String) {
        addCard(content, title, description) { addText(it, "Los registros creados aparecerán aquí.", 10f, MUTED) }
    }

    private fun addDivider(parent: LinearLayout) {
        parent.addView(View(this).apply { setBackgroundColor(LINE) }, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(1)).apply { topMargin = dp(2); bottomMargin = dp(2) })
    }

    private fun formatAmount(value: String): String = try {
        String.format(java.util.Locale("es", "ES"), "%,.2f", value.toDouble())
    } catch (_: Exception) { value }

    private fun showFormDialog(title: String, view: View, saveLabel: String, onSave: (AlertDialog) -> Unit) {
        val dialog = AlertDialog.Builder(this)
            .setTitle(title)
            .setView(view)
            .setNegativeButton("Cancelar", null)
            .setPositiveButton(saveLabel, null)
            .create()
        dialog.setOnShowListener { dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener { onSave(dialog) } }
        dialog.show()
    }

    private fun formContainer(): LinearLayout = LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(20), dp(8), dp(20), dp(4))
    }

    private fun field(parent: LinearLayout, hint: String, inputType: Int = InputType.TYPE_CLASS_TEXT, value: String = ""): EditText {
        val edit = EditText(this).apply {
            this.hint = hint
            this.inputType = inputType
            textSize = 13f
            setSingleLine(true)
            setText(value)
            setPadding(dp(11), dp(8), dp(11), dp(8))
            background = rounded(Color.WHITE, 8, LINE)
        }
        parent.addView(edit, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(48)).apply { bottomMargin = dp(9) })
        return edit
    }

    private fun spinner(parent: LinearLayout, values: List<String>): Spinner {
        val view = Spinner(this)
        val adapter = ArrayAdapter(this, android.R.layout.simple_spinner_item, values).apply { setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item) }
        view.adapter = adapter
        parent.addView(view, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(46)).apply { bottomMargin = dp(9) })
        return view
    }

    private fun scrollForm(form: LinearLayout): ScrollView = ScrollView(this).apply {
        addView(form)
        isFillViewport = true
        layoutParams = ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(420))
    }

    private fun openProductDialog() {
        val form = formContainer()
        val code = field(form, "Código (ej. BEB-003)")
        val name = field(form, "Nombre del producto o servicio")
        val category = spinner(form, listOf("Bebidas", "Comidas", "Servicios", "Otros"))
        val unit = field(form, "Unidad de salida (ración, vaso, hora…)")
        val description = field(form, "Descripción opcional")
        showFormDialog("Nuevo producto o servicio", scrollForm(form), "Guardar") { dialog ->
            if (code.text.isBlank() || name.text.isBlank() || unit.text.isBlank()) { toast("Completa código, nombre y unidad."); return@showFormDialog }
            val body = JSONObject().put("code", code.text.toString()).put("name", name.text.toString())
                .put("category", category.selectedItem.toString()).put("unit", unit.text.toString()).put("description", description.text.toString())
            runApi(dialog, "Producto guardado.") { api.request("POST", "/api/products", body) }
        }
    }

    private fun openNewMaterialDialog() {
        val form = formContainer()
        val code = field(form, "Código (ej. INS-013)")
        val name = field(form, "Nombre del insumo o valor")
        val unit = field(form, "Unidad (kg, L, hora…)")
        val price = field(form, "Precio unitario", InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL)
        val currency = field(form, "Moneda", value = "CUP")
        val source = field(form, "Documento o fuente de referencia")
        showFormDialog("Registrar valor del IPV", scrollForm(form), "Guardar") { dialog ->
            if (code.text.isBlank() || name.text.isBlank() || unit.text.isBlank() || price.text.isBlank()) { toast("Completa código, nombre, unidad y precio."); return@showFormDialog }
            val body = JSONObject().put("code", code.text.toString()).put("name", name.text.toString())
                .put("unit", unit.text.toString()).put("unit_price", price.text.toString())
                .put("currency", currency.text.toString().ifBlank { "CUP" }).put("source", source.text.toString())
                .put("effective_from", java.time.LocalDate.now().toString())
            runApi(dialog, "Valor registrado.") { api.request("POST", "/api/materials", body) }
        }
    }

    private fun openNewFichaDialog() {
        val activeProducts = products.toObjectList().filter { it.optInt("active", 1) == 1 }
        val availableMaterials = materials.toObjectList()
        if (activeProducts.isEmpty()) { toast("Primero registra un producto."); currentTab = "Productos"; renderPage(); return }
        if (availableMaterials.isEmpty()) { toast("Primero registra un valor del IPV."); currentTab = "Valores IPV"; renderPage(); return }
        val form = formContainer()
        val productSpinner = spinner(form, activeProducts.map { "${it.optString("code")} · ${it.optString("name")}" })
        val dateField = field(form, "Vigente desde (AAAA-MM-DD)", value = java.time.LocalDate.now().toString())
        val notes = field(form, "Observaciones opcionales")
        addText(form, "Componentes", 12f, GREEN, true, top = 4, bottom = 6)
        val materialSpinner = spinner(form, availableMaterials.map { "${it.optString("name")} · ${formatAmount(it.optString("unit_price"))}/${it.optString("unit")}" })
        val quantity = field(form, "Cantidad utilizada", InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL, "1")
        val lines = mutableListOf<DraftLine>()
        val lineList = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        val addLine = makeButton("＋  Añadir componente", false) {
            val material = availableMaterials.getOrNull(materialSpinner.selectedItemPosition)
            val q = quantity.text.toString().replace(',', '.')
            if (material == null || q.toDoubleOrNull() == null || q.toDouble() <= 0) { toast("Indica una cantidad mayor que cero."); return@makeButton }
            lines.add(DraftLine(material.optInt("id"), q))
            renderDraftLines(lineList, lines, availableMaterials)
            quantity.setText("")
        }
        form.addView(addLine, LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(6) })
        form.addView(lineList)
        showFormDialog("Nueva Ficha de Costo", scrollForm(form), "Crear borrador") { dialog ->
            if (lines.isEmpty()) { toast("Añade al menos un componente."); return@showFormDialog }
            val itemArray = JSONArray()
            lines.forEach { itemArray.put(JSONObject().put("material_id", it.materialId).put("quantity", it.quantity)) }
            val body = JSONObject().put("product_id", activeProducts[productSpinner.selectedItemPosition].optInt("id"))
                .put("valid_from", dateField.text.toString()).put("observations", notes.text.toString()).put("items", itemArray)
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
                setTextColor(0xFFB8544B.toInt())
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
                        .create().also { dialog ->
                            dialog.setOnShowListener {
                                if (ficha.optString("status") == "Borrador") dialog.getButton(AlertDialog.BUTTON_NEUTRAL).setOnClickListener { dialog.dismiss(); approveFicha(id) }
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
                runOnUiThread { toast("Ficha aprobada."); refresh() }
            } catch (error: Exception) { runOnUiThread { toast(error.message ?: "No se pudo aprobar.") } }
        }
    }

    private fun openGenerateControl(fichaId: Int) {
        val form = formContainer()
        val period = field(form, "Período (AAAA-MM)", value = java.time.YearMonth.now().toString())
        addText(form, "El control guardará una instantánea de la versión seleccionada.", 10f, MUTED, false, bottom = 7)
        showFormDialog("Generar Control de IPV", scrollForm(form), "Crear control") { dialog ->
            if (period.text.length < 7) { toast("Indica el período con formato AAAA-MM."); return@showFormDialog }
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
                    toast(if (result.optString("status") == "Validado") "Control validado." else "Se encontraron diferencias.")
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

    private fun openSettings() {
        val form = formContainer()
        addText(form, "La app Android y la web usan el servidor común. El archivo .db permanece en el servidor.", 11f, MUTED, false, bottom = 8)
        val urlField = field(form, "URL del backend", value = api.baseUrl)
        addText(form, "Emulador: https://10.0.2.2:8443\nMóvil/otra PC: https://IP_DE_LA_COMPUTADORA:8443\nInstala la CA local en el dispositivo para confiar en HTTPS.", 10f, MUTED)
        showFormDialog("Conexión con la base SQLite", scrollForm(form), "Guardar y probar") { dialog ->
            val newUrl = urlField.text.toString().trim()
            if (!newUrl.startsWith("https://")) { toast("La URL debe comenzar con https://."); return@showFormDialog }
            api.baseUrl = newUrl
            dialog.dismiss()
            refresh()
        }
    }

    private fun toast(message: String) = Toast.makeText(this, message, Toast.LENGTH_SHORT).show()

    private fun JSONArray.toObjectList(): List<JSONObject> = (0 until length()).mapNotNull { optJSONObject(it) }
}
