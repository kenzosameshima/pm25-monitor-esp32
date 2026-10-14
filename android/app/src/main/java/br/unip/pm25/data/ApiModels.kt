package br.unip.pm25.data

import kotlinx.serialization.KSerializer
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.descriptors.PrimitiveKind
import kotlinx.serialization.descriptors.PrimitiveSerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder
import kotlinx.serialization.json.Json
import java.time.Instant

/** Contrato das rotas de leitura da API (server/app/read_api.py). Horários sempre em UTC. */

/** Campos novos da API são ignorados: o app continua funcionando quando o servidor evolui primeiro. */
val ApiJson = Json { ignoreUnknownKeys = true }

object InstantSerializer : KSerializer<Instant> {
    override val descriptor = PrimitiveSerialDescriptor("Instant", PrimitiveKind.STRING)
    override fun deserialize(decoder: Decoder): Instant = Instant.parse(decoder.decodeString())
    override fun serialize(encoder: Encoder, value: Instant) = encoder.encodeString(value.toString())
}

@Serializable
data class DeviceList(
    /** Relógio do servidor no momento da resposta; base para calcular a idade das leituras. */
    @SerialName("generated_at") @Serializable(InstantSerializer::class) val generatedAt: Instant,
    @SerialName("late_after_min") val lateAfterMin: Int,
    @SerialName("silent_after_min") val silentAfterMin: Int,
    val devices: List<DeviceState>,
)

@Serializable
enum class DeviceStatus {
    @SerialName("online") ONLINE,
    @SerialName("late") LATE,
    @SerialName("silent") SILENT,
}

@Serializable
data class DeviceState(
    @SerialName("device_id") val deviceId: String,
    val location: String? = null,
    val status: DeviceStatus,
    @SerialName("minutes_since_last") val minutesSinceLast: Double? = null,
    @SerialName("last_received") @Serializable(InstantSerializer::class) val lastReceived: Instant? = null,
    val latest: LatestReading? = null,
)

@Serializable
data class LatestReading(
    /** Início da janela de um minuto medida pelo nó. */
    @Serializable(InstantSerializer::class) val ts: Instant,
    val pm25: Double? = null,
    val pm10: Double? = null,
    val pm1: Double? = null,
    val temperature: Double? = null,
    val humidity: Double? = null,
    val rssi: Int? = null,
    val quality: String = "ok",
)
