package br.unip.pm25.ui.forecast

import br.unip.pm25.data.ForecastResponse
import br.unip.pm25.domain.predictorLabel
import br.unip.pm25.ui.format

/**
 * O que o leitor de tela diz do gráfico de previsto × observado: por série, em quantas horas há valor, a
 * média e a máxima. O gráfico é um desenho, então sem isto só os números dos cartões chegariam a quem não o vê.
 */
internal fun forecastChartDescription(data: ForecastResponse): String {
    val observed = "Observado" to data.hours.map { it.observed }
    val predicted = data.predictors.map { p -> predictorLabel(p) to data.hours.map { it.predictions[p] } }
    val series = (listOf(observed) + predicted).joinToString(" ") { (label, values) -> "$label: ${summary(values)}." }
    return "PM2,5 por hora nas últimas $FORECAST_HOURS horas, em microgramas por metro cúbico. $series"
}

private fun summary(values: List<Double?>): String {
    val present = values.filterNotNull()
    if (present.isEmpty()) return "sem valores"
    val hours = if (present.size == 1) "1 hora" else "${present.size} horas"
    return "$hours, média ${present.average().format()}, máxima ${present.max().format()}"
}
