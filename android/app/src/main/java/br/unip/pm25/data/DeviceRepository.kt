package br.unip.pm25.data

import kotlinx.coroutines.CancellationException
import kotlinx.serialization.SerializationException
import retrofit2.HttpException
import java.io.IOException
import java.time.format.DateTimeParseException

/** Por que uma consulta falhou, em termos que a tela consegue explicar ao usuário. */
sealed interface LoadError {
    /** Sem rede, servidor desligado ou tempo esgotado: vale tentar de novo. */
    data object Network : LoadError

    /** 401: token de leitura ausente ou errado no app. */
    data object Unauthorized : LoadError

    /** 503: o servidor está sem PM25_READ_TOKEN configurado. */
    data object ReadDisabled : LoadError

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

class DeviceRepository(private val api: Pm25Api) {
    suspend fun devices(): Outcome<DeviceList> = load { api.devices() }

    private suspend fun <T> load(call: suspend () -> T): Outcome<T> =
        try {
            Outcome.Success(call())
        } catch (e: CancellationException) {
            throw e
        } catch (e: HttpException) {
            Outcome.Failure(
                when (e.code()) {
                    401 -> LoadError.Unauthorized
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
