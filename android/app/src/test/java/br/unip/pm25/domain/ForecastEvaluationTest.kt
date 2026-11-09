package br.unip.pm25.domain

import br.unip.pm25.data.ForecastHour
import br.unip.pm25.data.ForecastResponse
import br.unip.pm25.data.PredictorScore
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Instant
import java.time.ZoneId

class ForecastEvaluationTest {
    private val zone = ZoneId.of("America/Sao_Paulo")
    private val start = Instant.parse("2026-10-14T13:00:00Z")  // 10:00 em Brasília

    private fun hour(i: Int, observed: Double?, vararg predictions: Pair<String, Double?>) =
        ForecastHour(start.plusSeconds(3600L * i), observed, mapOf(*predictions))

    private fun forecast(hours: List<ForecastHour>, scores: List<PredictorScore>) =
        ForecastResponse(start, "no-01", scores.map { it.predictor }, hours, scores)

    @Test
    fun `previsao retroativa se reconhece pelo sufixo`() {
        assertTrue(isRetroactive("ridge v1-retro"))
        assertFalse(isRetroactive("ridge v1"))
        assertFalse(isRetroactive(PERSISTENCE))
    }

    @Test
    fun `rotulo da retroativa diz que ela e retroativa`() {
        assertEquals("ridge v1 (retroativa)", predictorLabel("ridge v1-retro"))
        assertEquals("ridge v1", predictorLabel("ridge v1"))
    }

    @Test
    fun `mesmas horas para todos dizem o periodo avaliado`() {
        val hours = listOf(
            hour(0, 10.0, PERSISTENCE to 9.0, "ridge v1" to 10.5),
            hour(1, 12.0, PERSISTENCE to 10.0, "ridge v1" to 11.0),
            hour(2, null, PERSISTENCE to 12.0, "ridge v1" to 12.5),
        )
        val scores = listOf(PredictorScore(PERSISTENCE, 2, 1.5, 1.6, 0.0), PredictorScore("ridge v1", 2, 0.75, 0.8, 0.5))
        assertEquals(
            EvaluationWindow.Same("Todos os previsores foram avaliados nas mesmas 2 horas, de 14/10 10:00 a 14/10 11:00."),
            evaluationWindow(forecast(hours, scores), zone),
        )
    }

    @Test
    fun `so a persistencia diz em quantas horas foi avaliada`() {
        val hours = listOf(hour(0, 10.0, PERSISTENCE to 9.0))
        val scores = listOf(PredictorScore(PERSISTENCE, 1, 1.0, 1.0, 0.0))
        assertEquals(EvaluationWindow.Same("Avaliada em 1 hora (14/10 10:00)."), evaluationWindow(forecast(hours, scores), zone))
    }

    @Test
    fun `horas diferentes entre previsores avisam que as linhas nao se comparam`() {
        val hours = listOf(
            hour(0, 10.0, PERSISTENCE to 9.0, "ridge v1" to null),
            hour(1, 12.0, PERSISTENCE to 10.0, "ridge v1" to 11.0),
        )
        val scores = listOf(PredictorScore(PERSISTENCE, 2, 1.5, 1.6, 0.0), PredictorScore("ridge v1", 1, 1.0, 1.0, 0.4))
        assertEquals(EvaluationWindow.Different, evaluationWindow(forecast(hours, scores), zone))
    }

    @Test
    fun `sem metricas nao ha periodo avaliado`() {
        assertNull(evaluationWindow(forecast(listOf(hour(0, null, PERSISTENCE to 9.0)), emptyList()), zone))
    }

    @Test
    fun `amostra de menos de um dia ganha aviso`() {
        assertEquals("Amostra de apenas 23 horas", smallSampleNote(23))
        assertEquals("Amostra de apenas 1 hora", smallSampleNote(1))
        assertNull(smallSampleNote(24))
    }
}
