package br.unip.pm25.data

import br.unip.pm25.domain.Alert
import br.unip.pm25.domain.AlertState
import br.unip.pm25.domain.Check
import br.unip.pm25.domain.evaluate
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/**
 * Uma checagem dos alertas: consulta a lista de nós e a última hora completa de cada um, compara com o
 * que já foi avisado (salvo em `store`, que precisa sobreviver entre execuções) e devolve só os alertas
 * novos. O estado novo fica salvo antes de a função retornar. Checagens simultâneas (a periódica e uma
 * pedida na hora) rodam uma de cada vez, para o mesmo fato não ser avisado duas vezes.
 */
class AlertChecker(private val repository: DeviceRepository, private val store: SnapshotStore) {
    private val mutex = Mutex()

    suspend fun check(): List<Alert> = mutex.withLock {
        val state = load()
        val check = when (val result = repository.devices()) {
            is Outcome.Failure -> Check.Failed(result.error)
            is Outcome.Success -> Check.Answered(result.value.value, lastHours(result.value.value))
        }
        val (next, alerts) = evaluate(state, check)
        store.write(STATE_KEY, ApiJson.encodeToString(AlertState.serializer(), next))
        alerts
    }

    /** A última hora completa de cada nó que já enviou dados. Um nó cuja consulta falhar fica de fora. */
    private suspend fun lastHours(list: DeviceList): Map<String, HourlyPoint> =
        list.devices.filter { it.lastReceived != null }.mapNotNull { device ->
            (repository.hourly(device.deviceId, 1) as? Outcome.Success)?.value?.value?.hours?.lastOrNull()
                ?.let { device.deviceId to it }
        }.toMap()

    /** O estado salvo, ou o inicial se não houver ou se ele não seguir mais o formato atual. */
    private suspend fun load(): AlertState {
        val text = store.read(STATE_KEY) ?: return AlertState()
        return try {
            ApiJson.decodeFromString(AlertState.serializer(), text)
        } catch (e: IllegalArgumentException) {  // inclui SerializationException
            AlertState()
        }
    }
}

private const val STATE_KEY = "estado"
