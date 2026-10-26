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
import javax.net.ssl.SSLException

/** Por que uma consulta falhou, em termos que a tela consegue explicar ao usuário. */
sealed interface LoadError {
    /** Sem rede, servidor desligado ou tempo esgotado: vale tentar de novo. */
    data object Network : LoadError

    /** A conexão segura falhou: certificado não aceito, data do celular errada ou rede que intercepta o tráfego. */
    data object Tls : LoadError

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
    suspend fun devices(): Outcome<Timed<DeviceList>> = fetch(devicesRoute())

    suspend fun cachedDevices(): Timed<DeviceList>? = cached(devicesRoute())

    suspend fun hourly(deviceId: String, hours: Int): Outcome<Timed<HourlySeries>> =
        fetch(hourlyRoute(deviceId, hours))

    suspend fun cachedHourly(deviceId: String, hours: Int): Timed<HourlySeries>? =
        cached(hourlyRoute(deviceId, hours))

    suspend fun health(deviceId: String, hours: Int): Outcome<Timed<Health>> =
        fetch(healthRoute(deviceId, hours))

    suspend fun cachedHealth(deviceId: String, hours: Int): Timed<Health>? =
        cached(healthRoute(deviceId, hours))

    suspend fun forecast(deviceId: String, hours: Int): Outcome<Timed<ForecastResponse>> =
        fetch(forecastRoute(deviceId, hours))

    suspend fun cachedForecast(deviceId: String, hours: Int): Timed<ForecastResponse>? =
        cached(forecastRoute(deviceId, hours))

    /** Uma consulta à API e a cópia salva dela: a chave e o formato do arquivo ficam juntos, numa definição só. */
    private class Route<T>(val key: String, val serializer: KSerializer<T>, val call: suspend () -> T)

    private fun devicesRoute() = Route(DEVICES, DeviceList.serializer()) { api.devices() }

    private fun hourlyRoute(deviceId: String, hours: Int) =
        Route(key("hourly", deviceId, hours), HourlySeries.serializer()) { api.hourly(deviceId, hours) }

    private fun healthRoute(deviceId: String, hours: Int) =
        Route(key("health", deviceId, hours), Health.serializer()) { api.health(deviceId, hours) }

    private fun forecastRoute(deviceId: String, hours: Int) =
        Route(key("forecast", deviceId, hours), ForecastResponse.serializer()) { api.forecast(deviceId, hours) }

    private fun key(route: String, deviceId: String, hours: Int) = "$route-$deviceId-$hours"

    private suspend fun <T> fetch(route: Route<T>): Outcome<Timed<T>> =
        when (val result = load(route.call)) {
            is Outcome.Success -> {
                val timed = Timed(result.value, clock())
                store.write(route.key, ApiJson.encodeToString(Timed.serializer(route.serializer), timed))
                Outcome.Success(timed)
            }
            is Outcome.Failure -> result
        }

    /** A versão salva, ou null se não houver ou se ela não seguir mais o contrato (app atualizado, arquivo estragado). */
    private suspend fun <T> cached(route: Route<T>): Timed<T>? {
        val text = store.read(route.key) ?: return null
        return try {
            ApiJson.decodeFromString(Timed.serializer(route.serializer), text)
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
        } catch (e: SSLException) {  // vem antes de IOException, de que é subclasse
            Outcome.Failure(LoadError.Tls)
        } catch (e: IOException) {
            Outcome.Failure(LoadError.Network)
        } catch (e: SerializationException) {
            Outcome.Failure(LoadError.BadResponse)
        } catch (e: DateTimeParseException) {
            Outcome.Failure(LoadError.BadResponse)
        }
}

private const val DEVICES = "devices"
