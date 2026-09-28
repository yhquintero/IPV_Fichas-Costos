package cu.ipvcostos.app

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/* ==========================================================================
   IPV · Fichas y Costos — Seguridad Android (solo APIs de la plataforma)
   Autor: Ing. Yosvany Hernández Quintero

   · SecureStore: cifrado AES-256-GCM con clave no exportable en Android Keystore.
   · Session: tokens JWT (access/refresh) y usuario, siempre cifrados en reposo.
   · OfflineCache: últimas respuestas GET cifradas para trabajar sin conexión.
   · RealtimeClient: escucha /api/events (Server-Sent Events) en segundo plano.
   ========================================================================== */

/** Error que indica que el usuario debe iniciar sesión. */
class AuthRequiredException(message: String = "Inicie sesión para continuar.") : java.io.IOException(message)

class SecureStore(context: Context, name: String) {
    private val prefs = context.getSharedPreferences(name, Context.MODE_PRIVATE)

    private fun key(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getEntry(ALIAS, null) as? KeyStore.SecretKeyEntry)?.let { return it.secretKey }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build()
        )
        return generator.generateKey()
    }

    fun put(name: String, value: String?) {
        if (value == null) { prefs.edit().remove(name).apply(); return }
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, key())
        val payload = cipher.iv + cipher.doFinal(value.toByteArray(Charsets.UTF_8))
        prefs.edit().putString(name, Base64.encodeToString(payload, Base64.NO_WRAP)).apply()
    }

    fun get(name: String): String? {
        val stored = prefs.getString(name, null) ?: return null
        return try {
            val raw = Base64.decode(stored, Base64.NO_WRAP)
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, raw.copyOfRange(0, 12)))
            String(cipher.doFinal(raw.copyOfRange(12, raw.size)), Charsets.UTF_8)
        } catch (_: Exception) {
            prefs.edit().remove(name).apply() // dato manipulado o clave rotada: se descarta
            null
        }
    }

    fun clear() = prefs.edit().clear().apply()

    companion object {
        private const val ALIAS = "ipv_secure_key_v1"
        private const val TRANSFORMATION = "AES/GCM/NoPadding"
    }
}

class Session(context: Context) {
    private val store = SecureStore(context, "ipv_session")
    var accessToken: String?
        get() = store.get("access")
        set(v) = store.put("access", v)
    var refreshToken: String?
        get() = store.get("refresh")
        set(v) = store.put("refresh", v)
    var user: JSONObject?
        get() = store.get("user")?.let { runCatching { JSONObject(it) }.getOrNull() }
        set(v) = store.put("user", v?.toString())

    val isLoggedIn: Boolean get() = refreshToken != null
    val role: String get() = user?.optString("role", "viewer") ?: "viewer"

    fun save(response: JSONObject) {
        accessToken = response.getString("access_token")
        refreshToken = response.getString("refresh_token")
        user = response.getJSONObject("user")
    }

    fun clear() = store.clear()
}

class OfflineCache(context: Context) {
    private val store = SecureStore(context, "ipv_offline_cache")
    fun put(path: String, body: String) {
        if (body.length < 400_000) store.put(path, "${System.currentTimeMillis()}|$body")
    }
    /** Devuelve (cuerpo, antigüedad en minutos) o null. */
    fun get(path: String): Pair<String, Long>? {
        val raw = store.get(path) ?: return null
        val sep = raw.indexOf('|')
        if (sep < 0) return null
        val age = (System.currentTimeMillis() - raw.substring(0, sep).toLong()) / 60000
        return raw.substring(sep + 1) to age
    }
    fun clear() = store.clear()
}

/** Cliente SSE: invoca [onChange] cada vez que el servidor publica un cambio. */
class RealtimeClient(
    private val baseUrl: () -> String,
    private val token: () -> String?,
    private val configure: (HttpURLConnection) -> Unit,
    private val onChange: (JSONObject) -> Unit,
) {
    @Volatile private var running = false
    private var thread: Thread? = null

    fun start() {
        if (running) return
        running = true
        thread = Thread({
            while (running) {
                var connection: HttpURLConnection? = null
                try {
                    val t = token()
                    val suffix = if (t != null) "?access_token=" + java.net.URLEncoder.encode(t, "UTF-8") else ""
                    connection = (URL(baseUrl() + "/api/events" + suffix).openConnection() as HttpURLConnection).apply {
                        connectTimeout = 10000
                        readTimeout = 45000 // el servidor envía ping cada 15 s
                        setRequestProperty("Accept", "text/event-stream")
                        configure(this)
                    }
                    if (connection.responseCode != 200) throw java.io.IOException("SSE ${connection.responseCode}")
                    BufferedReader(InputStreamReader(connection.inputStream, Charsets.UTF_8)).use { reader ->
                        var event = ""
                        while (running) {
                            val line = reader.readLine() ?: break
                            when {
                                line.startsWith("event:") -> event = line.substring(6).trim()
                                line.startsWith("data:") && event == "change" ->
                                    runCatching { onChange(JSONObject(line.substring(5).trim())) }
                                line.isEmpty() -> event = ""
                            }
                        }
                    }
                } catch (_: Exception) {
                    // Reintento con espera
                } finally {
                    connection?.disconnect()
                }
                if (running) try { Thread.sleep(5000) } catch (_: InterruptedException) { running = false }
            }
        }, "ipv-realtime").apply { isDaemon = true; start() }
    }

    fun stop() {
        running = false
        thread?.interrupt()
        thread = null
    }
}

/** El servidor requiere el código de la aplicación autenticadora. */
class MfaRequiredException(message: String) : java.io.IOException(message)

/** La contraseña caducó o el administrador exige cambiarla: solo se permite cambiarla. */
class PasswordExpiredException(message: String) : java.io.IOException(message)

/** El certificado presentado no coincide con la huella fijada: posible interceptación. */
class PinMismatchException(message: String) : java.io.IOException(message)

/**
 * Fijación de certificado (certificate pinning) con SHA-256 del certificado DER.
 * · Se compara contra toda la cadena, por lo que basta con fijar la CA local.
 * · Si no hay huella configurada se aplica TOFU: se fija la CA en la primera conexión válida.
 * · La verificación ocurre en el handshake TLS, antes de enviar cabeceras o el token.
 */
class CertificatePinner(context: Context) {
    private val prefs = context.getSharedPreferences("ipv_pinning", Context.MODE_PRIVATE)
    @Volatile var lastMismatch: String? = null

    var pin: String?
        get() = prefs.getString("pin", null)
        set(v) { prefs.edit().apply { if (v == null) remove("pin") else putString("pin", normalize(v)) }.apply() }

    fun normalize(raw: String) = raw.uppercase().filter { it in "0123456789ABCDEF" }

    fun pretty(hex: String?) = hex?.chunked(2)?.joinToString(":") ?: "—"

    private fun sha256(bytes: ByteArray): String =
        java.security.MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02X".format(it) }

    fun verifier(): javax.net.ssl.HostnameVerifier {
        val default = javax.net.ssl.HttpsURLConnection.getDefaultHostnameVerifier()
        return javax.net.ssl.HostnameVerifier { host, session ->
            if (!default.verify(host, session)) return@HostnameVerifier false
            val chain = try { session.peerCertificates } catch (_: Exception) { return@HostnameVerifier false }
            val hashes = chain.map { sha256(it.encoded) }
            val expected = pin
            when {
                expected == null -> { pin = hashes.last(); lastMismatch = null; true } // TOFU sobre la CA
                expected in hashes -> { lastMismatch = null; true }
                else -> { lastMismatch = hashes.last(); false }
            }
        }
    }

    fun apply(connection: java.net.HttpURLConnection) {
        if (connection is javax.net.ssl.HttpsURLConnection) connection.hostnameVerifier = verifier()
    }
}
