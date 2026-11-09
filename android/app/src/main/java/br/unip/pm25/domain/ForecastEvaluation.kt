package br.unip.pm25.domain

import br.unip.pm25.data.ForecastResponse
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/** Sufixo das versões recalculadas depois do fato (scripts.forecast_job): servem à avaliação, não à previsão. */
const val RETRO_SUFFIX = "-retro"

/** Menos que um dia de horas: o ciclo diário do PM2,5 nem fecha. É um aviso de tela, não um teste estatístico. */
const val SMALL_SAMPLE_HOURS = 24

fun isRetroactive(predictor: String): Boolean = predictor.endsWith(RETRO_SUFFIX)

const val DIFFERENT_PERIODS = "Períodos de avaliação diferentes: MAE e RMSE não são diretamente comparáveis entre linhas."
const val SKILL_NOTE = "O skill score de cada linha compara o previsor com a persistência nas mesmas horas dele."
const val RETRO_NOTE = "Previsão retroativa: recalculada depois do fato, só com as leituras anteriores à hora-alvo. " +
    "Fica numa versão à parte e não vale como validação prospectiva."

/** Em que horas as métricas foram calculadas, as mesmas regras do painel (dashboard/evaluation.py). */
sealed interface EvaluationWindow {
    /** Todas as linhas usam as mesmas horas; o texto diz quantas e de quando a quando. */
    data class Same(val text: String) : EvaluationWindow

    /** As linhas usam horas diferentes: MAE e RMSE não se comparam entre elas. */
    data object Different : EvaluationWindow
}

private fun hoursText(n: Int) = if (n == 1) "1 hora" else "$n horas"

fun evaluationWindow(forecast: ForecastResponse, zone: ZoneId = ZoneId.systemDefault()): EvaluationWindow? {
    val scores = forecast.scores
    if (scores.isEmpty()) return null
    val rated = forecast.hours.filter { h ->
        h.observed != null && scores.all { h.predictions[it.predictor] != null }
    }
    val counts = scores.map { it.hours }.distinct()
    if (counts.size > 1 || rated.size != counts.single() || rated.isEmpty()) return EvaluationWindow.Different
    val clock = DateTimeFormatter.ofPattern("dd/MM HH:mm").withZone(zone)
    val first = clock.format(rated.first().hour)
    val last = clock.format(rated.last().hour)
    val n = rated.size
    val span = if (n == 1) " ($first)" else ", de $first a $last"
    if (scores.size == 1) return EvaluationWindow.Same("Avaliada em ${hoursText(n)}$span.")
    val same = if (n == 1) "na mesma hora" else "nas mesmas $n horas"
    return EvaluationWindow.Same("Todos os previsores foram avaliados $same$span.")
}

/** O aviso de uma linha avaliada em poucas horas; nulo quando a amostra tem um dia ou mais. */
fun smallSampleNote(hours: Int): String? =
    if (hours < SMALL_SAMPLE_HOURS) "Amostra de apenas ${hoursText(hours)}" else null
