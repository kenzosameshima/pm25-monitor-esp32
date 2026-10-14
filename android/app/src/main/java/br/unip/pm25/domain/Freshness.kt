package br.unip.pm25.domain

import br.unip.pm25.data.DeviceList
import br.unip.pm25.data.DeviceState
import br.unip.pm25.data.DeviceStatus
import java.time.Duration
import java.time.Instant

/**
 * Idade de uma leitura de um minuto que começou em `readingStart`, medida pelo relógio do servidor
 * (`serverNow`, o generated_at da resposta). Usar o relógio do servidor evita que um celular com a
 * hora errada mostre um dado antigo como atual. A leitura só fica completa no fim do minuto.
 */
fun readingAge(readingStart: Instant, serverNow: Instant): Duration {
    val age = Duration.between(readingStart.plusSeconds(60), serverNow)
    return if (age.isNegative) Duration.ZERO else age
}

/**
 * Hora estimada do servidor agora: o `generatedAt` da resposta mais o tempo que passou desde que ela
 * chegou, contado pelo relógio do celular. Do celular só entra a diferença entre dois instantes dele
 * mesmo, então a estimativa não depende de o relógio dele estar certo. Serve para um dado salvo não
 * parecer recente: uma resposta de ontem soma um dia à idade das leituras.
 */
fun estimatedServerNow(generatedAt: Instant, receivedAt: Instant, deviceNow: Instant): Instant {
    val elapsed = Duration.between(receivedAt, deviceNow)
    return if (elapsed.isNegative) generatedAt else generatedAt.plus(elapsed)
}

/**
 * Estado do nó na hora estimada do servidor, com os limites que o próprio servidor manda na resposta.
 * Com a resposta recém-chegada dá o mesmo que o servidor; com uma resposta salva, um nó que estava em
 * operação passa a atrasado e depois a sem dados, em vez de continuar verde para sempre.
 */
fun currentStatus(device: DeviceState, list: DeviceList, serverNow: Instant): DeviceStatus {
    val last = device.lastReceived ?: return DeviceStatus.SILENT
    val minutes = Duration.between(last, serverNow).toMillis() / 60_000.0
    return when {
        minutes < list.lateAfterMin -> DeviceStatus.ONLINE
        minutes < list.silentAfterMin -> DeviceStatus.LATE
        else -> DeviceStatus.SILENT
    }
}

/** "agora", "há 5 min", "há 2 h", "há 3 dias". */
fun formatAge(age: Duration): String {
    val minutes = age.toMinutes()
    return when {
        minutes < 1 -> "agora"
        minutes < 60 -> "há $minutes min"
        minutes < 48 * 60 -> "há ${minutes / 60} h"
        else -> "há ${minutes / (24 * 60)} dias"
    }
}
