package br.unip.pm25.domain

import br.unip.pm25.data.ApiJson
import br.unip.pm25.data.ForecastResponse
import br.unip.pm25.data.fixture
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.time.Instant

class ForecastReadingTest {
    /** Gerada pela API às hh:47, com 4 horas observadas e um modelo ridge v1 gravado em forecasts. */
    private val forecast = ApiJson.decodeFromString<ForecastResponse>(fixture("forecast.json"))

    @Test
    fun `le a comparacao com persistencia e modelo`() {
        assertEquals(listOf(PERSISTENCE, "ridge v1"), forecast.predictors)
        assertEquals(6, forecast.hours.size)
        val third = forecast.hours[3]
        assertEquals(18.0, third.observed!!, 0.0)
        assertEquals(mapOf(PERSISTENCE to 22.0, "ridge v1" to 19.0), third.predictions)
        assertNull(forecast.hours[0].predictions[PERSISTENCE])
        assertEquals(0.8154, forecast.scores.single { it.predictor == "ridge v1" }.skill!!, 0.0001)
    }

    @Test
    fun `hora em andamento tem previsao e ainda nao tem observacao`() {
        val pending = pendingHour(forecast)!!
        assertEquals(Instant.parse("2026-10-14T05:00:00Z"), pending.hour)
        assertNull(pending.observed)
        assertEquals(18.0, pending.predictions[PERSISTENCE]!!, 0.0)
        assertEquals(17.5, pending.predictions["ridge v1"]!!, 0.0)
    }

    @Test
    fun `sem a hora atual na resposta nao ha hora em andamento`() {
        assertNull(pendingHour(forecast.copy(generatedAt = Instant.parse("2026-10-15T00:10:00Z"))))
    }

    @Test
    fun `nomes e leitura do skill score`() {
        assertEquals("Persistência", predictorLabel(PERSISTENCE))
        assertEquals("ridge v1", predictorLabel("ridge v1"))
        assertEquals(SkillVerdict.BETTER, skillVerdict(0.3))
        assertEquals(SkillVerdict.WORSE, skillVerdict(-0.1))
        assertEquals(SkillVerdict.SAME, skillVerdict(0.0))
        assertEquals(SkillVerdict.UNDEFINED, skillVerdict(null))
    }
}
