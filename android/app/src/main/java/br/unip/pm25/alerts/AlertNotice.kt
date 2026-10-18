package br.unip.pm25.alerts

import br.unip.pm25.data.LoadError
import br.unip.pm25.domain.Alert
import br.unip.pm25.ui.format
import br.unip.pm25.ui.formatMoment
import br.unip.pm25.ui.message
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/** Canais de notificação: o usuário pode silenciar cada tipo de alerta separadamente nas configurações. */
enum class AlertChannel(val id: String, val title: String, val description: String) {
    NODES("sensores", "Sensores", "Um sensor parou de enviar dados ou voltou a enviar."),
    AIR("qualidade-do-ar", "Qualidade do ar", "A média horária de PM2,5 de um sensor ficou na faixa Ruim ou pior."),
    SERVER("servidor", "Servidor", "O app não consegue consultar o servidor, ou voltou a conseguir."),
}

/**
 * O que mostrar para um alerta. `id` identifica a notificação: o aviso de volta substitui o de falha do
 * mesmo nó (ou do servidor), em vez de deixar os dois na bandeja.
 */
data class AlertNotice(val id: Int, val channel: AlertChannel, val title: String, val text: String)

fun Alert.notice(now: Instant = Instant.now()): AlertNotice = when (this) {
    is Alert.NodeSilent -> AlertNotice(nodeId(deviceId), AlertChannel.NODES, "$deviceId sem enviar dados",
        where(location) + "Último envio: ${formatMoment(lastReceived, now)}. Confira a energia e o Wi-Fi do sensor.")
    is Alert.NodeBack -> AlertNotice(nodeId(deviceId), AlertChannel.NODES, "$deviceId voltou a enviar dados",
        where(location) + "As leituras voltaram a chegar ao servidor.")
    is Alert.AirHigh -> AlertNotice(airId(deviceId), AlertChannel.AIR, "PM2,5 ${band.label.lowercase()} em $deviceId",
        where(location) + "Média das ${clock(hour)} às ${clock(hour.plusSeconds(3600))}: ${pm25.format(0)} µg/m³, " +
            "faixa ${band.label} da CETESB.")
    is Alert.ServerDown -> AlertNotice(SERVER_ID, AlertChannel.SERVER, "Servidor sem resposta",
        if (error == LoadError.Network) {
            "Há pelo menos 15 minutos o app não consegue falar com o servidor, com o celular na internet. " +
                "Os sensores guardam as leituras e reenviam quando ele voltar."
        } else {
            error.message()
        })
    Alert.ServerBack -> AlertNotice(SERVER_ID, AlertChannel.SERVER, "Servidor respondendo de novo",
        "O app voltou a consultar o servidor.")
}

private const val SERVER_ID = 1

private fun nodeId(deviceId: String) = "no:$deviceId".hashCode()

private fun airId(deviceId: String) = "ar:$deviceId".hashCode()

private fun where(location: String?) = if (location.isNullOrBlank()) "" else "$location. "

private val HOUR_FORMAT = DateTimeFormatter.ofPattern("HH:mm")

private fun clock(moment: Instant) = moment.atZone(ZoneId.systemDefault()).format(HOUR_FORMAT)
