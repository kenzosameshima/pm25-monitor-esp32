package br.unip.pm25.ui.detail

import br.unip.pm25.domain.HourlySummary
import br.unip.pm25.ui.PT_BR
import br.unip.pm25.ui.format
import kotlin.math.floor

/**
 * Quantas horas ficaram sem média em cada causa, com as mesmas palavras do dashboard; null se nenhuma ficou. Uma hora
 * em branco no gráfico não diz sozinha se foi o sensor que parou, se faltaram leituras ou se ele quase não viu
 * partículas.
 */
internal fun blankHoursNote(summary: HourlySummary): String? {
    val parts = listOfNotNull(
        summary.noReadingHours.takeIf { it > 0 }?.let { "$it sem leituras" },
        summary.fewReadingsHours.takeIf { it > 0 }?.let { "$it com poucas leituras" },
        summary.suspectHours.takeIf { it > 0 }?.let { "$it ${if (it == 1) "suspeita" else "suspeitas"}" },
    )
    if (parts.isEmpty()) return null
    val text = if (parts.size == 1) parts.single() else "${parts.dropLast(1).joinToString(", ")} e ${parts.last()}"
    return "Horas sem média: $text."
}

/** O que o leitor de tela lê no lugar do gráfico: o resumo do período e, havendo, a causa das horas em branco. */
internal fun historyDescription(rangeLabel: String, summary: HourlySummary): String {
    val base = "PM2,5 por hora nas últimas $rangeLabel: média ${summary.mean.format()}, " +
        "máxima ${summary.max?.pm25.format()} microgramas por metro cúbico, " +
        "${summary.validHours} de ${summary.totalHours} horas válidas."
    return blankHoursNote(summary)?.let { "$base $it" } ?: base
}

/**
 * A completude da coleta em porcentagem, com uma casa decimal cortada, não arredondada: arredondar mostraria 100%
 * para 99,96%, e uma coleta que perdeu leituras não está completa. Pelo mesmo motivo, só a coleta sem nenhuma
 * leitura mostra 0%.
 */
internal fun completenessText(completeness: Double): String {
    if (completeness >= 1.0) return "100%"
    if (completeness <= 0.0) return "0%"
    val tenths = floor(completeness * 1000 + 1e-9).toInt().coerceIn(1, 999)
    return String.format(PT_BR, "%.1f%%", tenths / 10.0)
}
