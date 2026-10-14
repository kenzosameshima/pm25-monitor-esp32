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
data class HourlySeries(
    @SerialName("generated_at") @Serializable(InstantSerializer::class) val generatedAt: Instant,
    @SerialName("device_id") val deviceId: String,
    @Serializable(InstantSerializer::class) val start: Instant,
    @Serializable(InstantSerializer::class) val end: Instant,
    /** Leituras de um minuto que uma hora precisa ter para valer (45, ou 75% da hora). */
    @SerialName("min_readings") val minReadings: Int,
    val hours: List<HourlyPoint>,
)

/** Uma hora, mesmo sem leitura. Quando `valid` é falso, as médias vêm nulas. */
@Serializable
data class HourlyPoint(
    @Serializable(InstantSerializer::class) val hour: Instant,
    val readings: Int,
    val valid: Boolean,
    val pm25: Double? = null,
    val pm10: Double? = null,
    val pm1: Double? = null,
    val temperature: Double? = null,
    val humidity: Double? = null,
)

@Serializable
data class Health(
    @SerialName("generated_at") @Serializable(InstantSerializer::class) val generatedAt: Instant,
    @SerialName("device_id") val deviceId: String,
    @Serializable(InstantSerializer::class) val start: Instant,
    @Serializable(InstantSerializer::class) val end: Instant,
    val completeness: Double,
    @SerialName("largest_gap_min") val largestGapMin: Int,
    @SerialName("lost_messages") val lostMessages: Int,
    val restarts: Int,
    @SerialName("duplicates_discarded") val duplicatesDiscarded: Int,
    @SerialName("flagged_readings") val flaggedReadings: Int,
)

@Serializable
data class ForecastResponse(
    @SerialName("generated_at") @Serializable(InstantSerializer::class) val generatedAt: Instant,
    @SerialName("device_id") val deviceId: String,
    /** "persistence" primeiro, depois um por modelo gravado no servidor ("<nome> <versão>"). */
    val predictors: List<String>,
    val hours: List<ForecastHour>,
    val scores: List<PredictorScore>,
)

@Serializable
data class ForecastHour(
    @Serializable(InstantSerializer::class) val hour: Instant,
    /** Média horária observada; nula se a hora não vale ou ainda não terminou. */
    val observed: Double? = null,
    val predictions: Map<String, Double?> = emptyMap(),
)

/** Métricas de um previsor nas horas com observação, persistência e previsão dele. */
@Serializable
data class PredictorScore(
    val predictor: String,
    val hours: Int,
    val mae: Double,
    val rmse: Double,
    /** 1 − RMSE do previsor ÷ RMSE da persistência; acima de zero, o previsor supera a persistência. */
    val skill: Double? = null,
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
