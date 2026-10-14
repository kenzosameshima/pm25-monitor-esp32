package br.unip.pm25.data

import kotlinx.coroutines.CancellationException
import kotlinx.serialization.KSerializer
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.SerializationException
import retrofit2.HttpException
import java.io.IOException
import java.time.Instant
import java.time.format.DateTimeParseException

/** Por que uma consulta falhou, em termos que a tela consegue explicar ao usuário. */
sealed interface LoadError {
    /** Sem rede, servidor desligado ou tempo esgotado: vale tentar de novo. */
    data object Network : LoadError

    /** 401: token de leitura ausente ou errado no app. */
    data object Unauthorized : LoadError

    /** 503: o servidor está sem PM25_READ_TOKEN configurado. */
    data object ReadDisabled : LoadError

    /** 404: o servidor não tem leituras desse nó. */
    data object NotFound : LoadError

    /** 429: IP bloqueado por falhas de autenticação seguidas. */
    data class Blocked(val retryAfterSeconds: Int?) : LoadError

    /** Outro código HTTP. */
    data class Server(val code: Int) : LoadError

    /** Resposta fora do contrato esperado. */
    data object BadResponse : LoadError
}

sealed interface Outcome<out T> {
    data class Success<T>(val value: T) : Outcome<T>
    data class Failure(val error: LoadError) : Outcome<Nothing>
}

/** Uma resposta da API e o instante em que chegou ao celular, pelo relógio dele. Também é o formato salvo. */
@Serializable
data class Timed<T>(
    val value: T,
    @SerialName("received_at") @Serializable(InstantSerializer::class) val receivedAt: Instant,
)

/**
 * Acesso às rotas de leitura. Cada resposta que dá certo é salva em `store`, e a versão salva de cada
 * rota pode ser lida sem rede (`cached*`). `clock` marca quando cada resposta chegou.
 */
class DeviceRepository(
    private val api: Pm25Api,
    private val store: SnapshotStore,
    private val clock: () -> Instant = Instant::now,
) {
    suspend fun devices(): Outcome<Timed<DeviceList>> = fetch(DEVICES, DeviceList.serializer()) { api.devices() }

    suspend fun cachedDevices(): Timed<DeviceList>? = cached(DEVICES, DeviceList.serializer())

    suspend fun hourly(deviceId: String, hours: Int): Outcome<Timed<HourlySeries>> =
        fetch(key("hourly", deviceId, hours), HourlySeries.serializer()) { api.hourly(deviceId, hours) }

    suspend fun cachedHourly(deviceId: String, hours: Int): Timed<HourlySeries>? =
        cached(key("hourly", deviceId, hours), HourlySeries.serializer())

    suspend fun health(deviceId: String, hours: Int): Outcome<Timed<Health>> =
        fetch(key("health", deviceId, hours), Health.serializer()) { api.health(deviceId, hours) }

    suspend fun cachedHealth(deviceId: String, hours: Int): Timed<Health>? =
        cached(key("health", deviceId, hours), Health.serializer())

    suspend fun forecast(deviceId: String, hours: Int): Outcome<Timed<ForecastResponse>> =
        fetch(key("forecast", deviceId, hours), ForecastResponse.serializer()) { api.forecast(deviceId, hours) }

    suspend fun cachedForecast(deviceId: String, hours: Int): Timed<ForecastResponse>? =
        cached(key("forecast", deviceId, hours), ForecastResponse.serializer())

    private fun key(route: String, deviceId: String, hours: Int) = "$route-$deviceId-$hours"

    private suspend fun <T> fetch(key: String, serializer: KSerializer<T>, call: suspend () -> T): Outcome<Timed<T>> =
        when (val result = load(call)) {
            is Outcome.Success -> {
                val timed = Timed(result.value, clock())
                store.write(key, ApiJson.encodeToString(Timed.serializer(serializer), timed))
                Outcome.Success(timed)
            }
            is Outcome.Failure -> result
        }

    /** A versão salva, ou null se não houver ou se ela não seguir mais o contrato (app atualizado, arquivo estragado). */
    private suspend fun <T> cached(key: String, serializer: KSerializer<T>): Timed<T>? {
        val text = store.read(key) ?: return null
        return try {
            ApiJson.decodeFromString(Timed.serializer(serializer), text)
        } catch (e: IllegalArgumentException) {  // inclui SerializationException
            null
        } catch (e: DateTimeParseException) {
            null
        }
    }

    private suspend fun <T> load(call: suspend () -> T): Outcome<T> =
        try {
            Outcome.Success(call())
        } catch (e: CancellationException) {
            throw e
        } catch (e: HttpException) {
            Outcome.Failure(
                when (e.code()) {
                    401 -> LoadError.Unauthorized
                    404 -> LoadError.NotFound
                    503 -> LoadError.ReadDisabled
                    429 -> LoadError.Blocked(e.response()?.headers()?.get("Retry-After")?.toIntOrNull())
                    else -> LoadError.Server(e.code())
                }
            )
        } catch (e: IOException) {
            Outcome.Failure(LoadError.Network)
        } catch (e: SerializationException) {
            Outcome.Failure(LoadError.BadResponse)
        } catch (e: DateTimeParseException) {
            Outcome.Failure(LoadError.BadResponse)
        }
}

private const val DEVICES = "devices"
