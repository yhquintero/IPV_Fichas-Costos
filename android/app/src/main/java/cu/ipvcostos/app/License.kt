package cu.ipvcostos.app

import android.annotation.SuppressLint
import android.content.Context
import android.provider.Settings
import org.json.JSONObject
import java.security.KeyFactory
import java.security.MessageDigest
import java.security.Signature
import java.security.spec.X509EncodedKeySpec
import java.text.SimpleDateFormat
import java.time.LocalDate
import java.time.ZoneOffset
import java.util.Base64
import java.util.Date
import java.util.Locale

/**
 * Licencias por período (1 semana … 2 años) firmadas con ECDSA P-256 por el Keygen del proveedor.
 *
 * Identificador del dispositivo: desde Android 10 las apps normales NO pueden leer el IMEI
 * (READ_PRIVILEGED_PHONE_STATE está reservado al sistema). Se usa Settings.Secure.ANDROID_ID,
 * que es único por dispositivo + clave de firma de la app y sobrevive a reinstalaciones.
 * Nunca se envía en claro: se transforma con SHA-256 + sal en el código de solicitud IPVA-….
 */
object LicenseCore {
    // Los escribe `python keygen/keygen.py init`. Vacío = licencias desactivadas (compilación de desarrollo).
    const val PUBLIC_KEY_B64 = ""
    const val WHATSAPP_NUMBER = ""

    const val APP = "A"
    private const val DAY = 86_400L
    private const val B32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"

    /** Plan -> (nombre, días, precio USD). Igual que licencia.PLANS (columna Android). */
    val PLANS = linkedMapOf(
        "1S" to Triple("1 Semana", 7, 3), "1M" to Triple("1 Mes", 30, 8), "3M" to Triple("3 Meses", 90, 21),
        "6M" to Triple("6 Meses", 180, 39), "1A" to Triple("1 Año", 365, 70), "2A" to Triple("2 Años", 730, 120),
        "PX" to Triple("Personalizado (desde–hasta)", 0, 0),
    )

    data class Info(
        val user: String, val plan: String, val serial: String, val issuedAt: Long, val expiresAt: Long,
        val validFrom: Long, val validFromDate: String? = null, val validUntilDate: String? = null
    ) {
        val planName: String get() = PLANS[plan]?.first ?: plan
        fun daysLeft(nowSec: Long): Long = maxOf(0L, (expiresAt - nowSec) / DAY)
        fun expiryText(): String = validUntilDate ?: SimpleDateFormat("dd/MM/yyyy", Locale("es")).format(Date(expiresAt * 1000))
    }

    class LicenseException(message: String) : Exception(message)

    val enforced: Boolean get() = PUBLIC_KEY_B64.isNotEmpty()

    private fun sha256(text: String): ByteArray = MessageDigest.getInstance("SHA-256").digest(text.toByteArray(Charsets.UTF_8))

    fun base32(data: ByteArray): String {
        val out = StringBuilder()
        var buffer = 0
        var bits = 0
        for (b in data) {
            buffer = (buffer shl 8) or (b.toInt() and 0xFF)
            bits += 8
            while (bits >= 5) {
                out.append(B32[(buffer shr (bits - 5)) and 31])
                bits -= 5
            }
        }
        if (bits > 0) out.append(B32[(buffer shl (5 - bits)) and 31])
        return out.toString()
    }

    private fun check(body: String) = base32(sha256("IPV-CHK|$body")).substring(0, 2)

    fun deviceBody(rawId: String): String = base32(sha256("IPV-LIC-v1|$APP|${rawId.trim().lowercase()}")).substring(0, 20)

    fun requestCode(rawId: String): String {
        val body = deviceBody(rawId)
        return "IPV$APP-" + body.chunked(5).joinToString("-") + "-" + check(body)
    }

    /** Verifica firma, app, dispositivo, fechas y retroceso del reloj. */
    fun verify(token: String, pubB64: String, body: String, nowSec: Long, lastSeen: Long,
               allowNotYetValid: Boolean = false): Info {
        val parts = token.filterNot { it.isWhitespace() }.split(".")
        if (parts.size != 3 || parts[0] != "IPV1") throw LicenseException("La licencia no tiene un formato válido.")
        val raw: ByteArray
        val sig: ByteArray
        try {
            raw = Base64.getUrlDecoder().decode(parts[1])
            sig = Base64.getUrlDecoder().decode(parts[2])
        } catch (e: IllegalArgumentException) {
            throw LicenseException("La licencia está incompleta o dañada.")
        }
        val key = KeyFactory.getInstance("EC").generatePublic(X509EncodedKeySpec(Base64.getDecoder().decode(pubB64)))
        val ok = try {
            Signature.getInstance("SHA256withECDSA").run { initVerify(key); update(raw); verify(sig) }
        } catch (e: java.security.SignatureException) {
            false
        }
        if (!ok) throw LicenseException("Firma no válida: la licencia fue alterada o no la emitió el proveedor.")
        val json = JSONObject(String(raw, Charsets.UTF_8))
        val plan = json.optString("plan")
        if (json.optInt("v") != 1 || plan !in PLANS) throw LicenseException("Versión de licencia no admitida.")
        if (json.optString("app") != APP) throw LicenseException("Esta licencia es para IPV Web (PC), no para el móvil.")
        if (json.optString("dev") != body) throw LicenseException("Esta licencia pertenece a otro dispositivo.")
        val issuedAt = json.getLong("iat")
        val expiresAt = json.getLong("exp")
        var validFrom = issuedAt
        var validFromDate: String? = null
        var validUntilDate: String? = null
        if (plan == "PX") {
            try {
                validFromDate = json.getString("start_date")
                validUntilDate = json.getString("end_date")
                val start = LocalDate.parse(validFromDate)
                val end = LocalDate.parse(validUntilDate)
                val startEpoch = start.atStartOfDay().toEpochSecond(ZoneOffset.UTC)
                val endExclusiveEpoch = end.plusDays(1).atStartOfDay().toEpochSecond(ZoneOffset.UTC)
                val issuedDate = java.time.Instant.ofEpochSecond(issuedAt).atZone(ZoneOffset.UTC).toLocalDate()
                if (end.isBefore(start) || end.isBefore(issuedDate) || json.getLong("nbf") != startEpoch || expiresAt != endExclusiveEpoch) {
                    throw LicenseException("El período personalizado firmado no es válido.")
                }
                validFrom = startEpoch
            } catch (e: LicenseException) {
                throw e
            } catch (_: Exception) {
                throw LicenseException("El período personalizado firmado no es válido.")
            }
        } else if (json.has("start_date") || json.has("end_date") || json.has("nbf")) {
            throw LicenseException("Una licencia de plan fijo no puede incluir fechas personalizadas.")
        }
        val info = Info(json.optString("usr"), plan, json.optString("sn"), issuedAt, expiresAt,
            validFrom, validFromDate, validUntilDate)
        if (nowSec + DAY < maxOf(info.issuedAt, lastSeen)) {
            throw LicenseException("La fecha del teléfono es anterior a la última registrada. Corrija la fecha y la hora.")
        }
        if (nowSec >= info.expiresAt) throw LicenseException("La licencia venció el ${info.expiryText()}.")
        if (nowSec < info.validFrom && !allowNotYetValid) {
            val startText = info.validFromDate ?: SimpleDateFormat("dd/MM/yyyy", Locale("es")).format(Date(info.validFrom * 1000))
            throw LicenseException("La licencia todavía no está vigente; comienza el $startText.")
        }
        return info
    }
}

/** Estado de la licencia en este teléfono (SharedPreferences privadas de la app). */
class LicenseManager(context: Context) {
    private val prefs = context.getSharedPreferences("ipv_license", Context.MODE_PRIVATE)

    @SuppressLint("HardwareIds") // ANDROID_ID: identificador permitido por la política de Google Play para licencias
    private val rawId: String = Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID) ?: "desconocido"

    val requestCode: String = LicenseCore.requestCode(rawId)
    private val body = LicenseCore.deviceBody(rawId)

    private fun now() = System.currentTimeMillis() / 1000

    /** Devuelve la licencia vigente o lanza LicenseException con el motivo. */
    fun current(): LicenseCore.Info {
        val token = prefs.getString("token", null) ?: throw LicenseCore.LicenseException("Este teléfono no tiene licencia activada.")
        val info = LicenseCore.verify(token, LicenseCore.PUBLIC_KEY_B64, body, now(), prefs.getLong("last_seen", 0))
        if (now() > prefs.getLong("last_seen", 0) + 600) prefs.edit().putLong("last_seen", now()).apply()
        return info
    }

    fun isValid(): Boolean = !LicenseCore.enforced || runCatching { current() }.isSuccess

    /** Acepta firmas válidas programadas para una fecha futura, sin conceder acceso antes de su inicio. */
    fun pending(): LicenseCore.Info? {
        val token = prefs.getString("token", null) ?: return null
        val info = runCatching {
            LicenseCore.verify(token, LicenseCore.PUBLIC_KEY_B64, body, now(), prefs.getLong("last_seen", 0), allowNotYetValid = true)
        }.getOrNull() ?: return null
        return info.takeIf { now() < it.validFrom }
    }

    fun activate(token: String): LicenseCore.Info {
        val clean = token.filterNot { it.isWhitespace() }
        val info = LicenseCore.verify(clean, LicenseCore.PUBLIC_KEY_B64, body, now(), prefs.getLong("last_seen", 0), allowNotYetValid = true)
        prefs.edit().putString("token", clean).putLong("last_seen", maxOf(now(), prefs.getLong("last_seen", 0))).apply()
        return info
    }

    fun whatsappMessage(user: String, planName: String): String = listOf(
        "🔑 *Solicitud de licencia — IPV Fichas de Costo*",
        "Usuario: ${user.ifBlank { "(escriba su nombre)" }}",
        "ID Dispositivo: $requestCode",
        "Plan: $planName",
        "Aplicación: IPV Android (móvil)",
    ).joinToString("\n")
}
