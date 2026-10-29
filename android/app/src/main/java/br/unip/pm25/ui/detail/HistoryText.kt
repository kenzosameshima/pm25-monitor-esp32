package br.unip.pm25.ui.detail

import br.unip.pm25.domain.HourlySummary
import br.unip.pm25.ui.format

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
