package br.unip.pm25.domain

import br.unip.pm25.data.DeviceList
import br.unip.pm25.data.DeviceStatus
import br.unip.pm25.data.HourlyPoint
import br.unip.pm25.data.LoadError
import kotlinx.serialization.Serializable
import java.time.Instant

/**
 * Regras dos alertas em segundo plano. Cada checagem (a cada 15 minutos ou mais, quando o Android
 * deixa) compara o que a API respondeu com o que já foi avisado, e só um fato novo vira notificação:
 * um nó que ficou sem dados ou voltou, a média horária de PM2,5 que entrou numa faixa pior, o servidor
 * que parou de responder ou voltou.
 */

/** Checagens seguidas sem resposta antes de avisar: uma falha isolada da rede não vira alerta. */
const val SERVER_FAILURES_TO_ALERT = 2

/** A partir desta faixa da CETESB, a média da última hora completa vira alerta. */
val HIGH_AIR = AirQuality.RUIM

/** O que já foi avisado. Salvo entre checagens; começa vazio na primeira. */
@Serializable
data class AlertState(
    val serverFailures: Int = 0,
    val serverDown: Boolean = false,
    /** Nós já avisados como sem dados. */
    val silent: Set<String> = emptySet(),
    /** Faixa de PM2,5 já avisada por nó, só para HIGH_AIR ou pior. */
    val airBands: Map<String, AirQuality> = emptyMap(),
)

sealed interface Alert {
    data class NodeSilent(val deviceId: String, val location: String?, val lastReceived: Instant) : Alert
    data class NodeBack(val deviceId: String, val location: String?) : Alert

    /** A média de PM2,5 da hora que começou em `hour` ficou na faixa `band`. */
    data class AirHigh(val deviceId: String, val location: String?, val band: AirQuality, val pm25: Double,
                       val hour: Instant) : Alert

    data class ServerDown(val error: LoadError) : Alert
    data object ServerBack : Alert
}

/** O resultado de uma checagem. */
sealed interface Check {
    /** A lista de nós e a última hora completa de cada nó, quando ela veio. */
    data class Answered(val devices: DeviceList, val lastHours: Map<String, HourlyPoint>) : Check
    data class Failed(val error: LoadError) : Check
}

/**
 * O estado depois de `check` e os alertas que ele gera. Um nó que nunca enviou dados não gera alerta
 * (o servidor nem o lista); um nó que some da lista deixa de ser acompanhado. Uma hora sem média válida
 * não muda o que já foi avisado sobre o ar.
 */
fun evaluate(state: AlertState, check: Check): Pair<AlertState, List<Alert>> = when (check) {
    is Check.Failed -> {
        val failures = state.serverFailures + 1
        if (!state.serverDown && failures >= SERVER_FAILURES_TO_ALERT) {
            state.copy(serverFailures = failures, serverDown = true) to listOf(Alert.ServerDown(check.error))
        } else {
            state.copy(serverFailures = failures) to emptyList()
        }
    }
    is Check.Answered -> answered(state, check)
}

private fun answered(state: AlertState, check: Check.Answered): Pair<AlertState, List<Alert>> {
    val alerts = mutableListOf<Alert>()
    if (state.serverDown) alerts += Alert.ServerBack
    val list = check.devices
    val silent = mutableSetOf<String>()
    val airBands = mutableMapOf<String, AirQuality>()
    for (device in list.devices) {
        val id = device.deviceId
        val last = device.lastReceived ?: continue
        // A resposta acabou de chegar: o relógio dela é o "agora" do servidor.
        if (currentStatus(device, list, list.generatedAt) == DeviceStatus.SILENT) {
            silent += id
            if (id !in state.silent) alerts += Alert.NodeSilent(id, device.location, last)
        } else if (id in state.silent) {
            alerts += Alert.NodeBack(id, device.location)
        }

        val hour = check.lastHours[id]?.takeIf { it.valid }
        val pm25 = hour?.pm25
        val band = AirQuality.of(pm25)
        val previous = state.airBands[id]
        when {
            hour == null || pm25 == null || band == null -> previous?.let { airBands[id] = it }
            band >= HIGH_AIR -> {
                airBands[id] = band
                if (previous == null || band > previous) alerts += Alert.AirHigh(id, device.location, band, pm25, hour.hour)
            }
            // Abaixo de HIGH_AIR, o episódio acabou: uma nova subida volta a avisar.
        }
    }
    return AlertState(serverFailures = 0, serverDown = false, silent = silent, airBands = airBands) to alerts
}
