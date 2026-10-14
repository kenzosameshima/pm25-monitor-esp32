package br.unip.pm25.domain

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
