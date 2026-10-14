package br.unip.pm25.domain

import br.unip.pm25.data.ForecastHour
import br.unip.pm25.data.ForecastResponse
import java.time.Instant
import java.time.temporal.ChronoUnit

const val PERSISTENCE = "persistence"

/** Nome do previsor para a tela: a persistência em português; os modelos como o servidor os grava. */
fun predictorLabel(predictor: String): String = if (predictor == PERSISTENCE) "Persistência" else predictor

/**
 * A hora em andamento, pelo relógio do servidor: já tem previsões, mas ainda não tem observação
 * (a média só fecha no fim da hora). Nula se a resposta não trouxer essa hora, o que acontece com uma
 * resposta salva há mais de uma hora quando `serverNow` é a hora estimada do servidor agora.
 */
fun pendingHour(forecast: ForecastResponse, serverNow: Instant = forecast.generatedAt): ForecastHour? {
    val current = serverNow.truncatedTo(ChronoUnit.HOURS)
    return forecast.hours.firstOrNull { it.hour == current }
}

enum class SkillVerdict(val text: String) {
    BETTER("melhor que a persistência"),
    SAME("igual à persistência"),
    WORSE("pior que a persistência"),
    UNDEFINED("sem comparação possível"),
}

/** Leitura do skill score. A persistência é a referência: o skill dela é zero por definição. */
fun skillVerdict(skill: Double?): SkillVerdict = when {
    skill == null || skill.isNaN() -> SkillVerdict.UNDEFINED
    skill > 0.0 -> SkillVerdict.BETTER
    skill < 0.0 -> SkillVerdict.WORSE
    else -> SkillVerdict.SAME
}
