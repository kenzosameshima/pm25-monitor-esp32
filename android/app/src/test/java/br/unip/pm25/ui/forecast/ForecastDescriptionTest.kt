package br.unip.pm25.ui.forecast

import br.unip.pm25.data.ApiJson
import br.unip.pm25.data.ForecastHour
import br.unip.pm25.data.ForecastResponse
import br.unip.pm25.data.fixture
import org.junit.Assert.assertEquals
import org.junit.Test
import java.time.Instant

/** O texto que o leitor de tela diz no lugar do gráfico de previsto × observado. */
class ForecastDescriptionTest {
    private val hour = Instant.parse("2026-10-14T01:00:00Z")

    private fun response(observed: List<Double?>) = ForecastResponse(
        generatedAt = hour, deviceId = "no-01", predictors = listOf("persistence"),
        hours = observed.mapIndexed { i, value -> ForecastHour(hour.plusSeconds(3600L * i), value) },
        scores = emptyList(),
    )

    @Test
    fun `diz horas, media e maxima do observado e de cada previsor`() {
        // observado 10, 16, 22, 18; persistência 10, 16, 22, 18; ridge 15, 21, 19, 17,5 (as demais horas são nulas)
        val forecast = ApiJson.decodeFromString<ForecastResponse>(fixture("forecast.json"))
        assertEquals(
            "PM2,5 por hora nas últimas 48 horas, em microgramas por metro cúbico. " +
                "Observado: 4 horas, média 16,5, máxima 22,0. " +
                "Persistência: 4 horas, média 16,5, máxima 22,0. " +
                "ridge v1: 4 horas, média 18,1, máxima 21,0.",
            forecastChartDescription(forecast),
        )
    }

    @Test
    fun `serie sem nenhum valor diz que esta sem valores`() {
        assertEquals(
            "PM2,5 por hora nas últimas 48 horas, em microgramas por metro cúbico. " +
                "Observado: sem valores. Persistência: sem valores.",
            forecastChartDescription(response(listOf(null, null))),
        )
    }

    @Test
    fun `uma unica hora fica no singular`() {
        assertEquals(
            "PM2,5 por hora nas últimas 48 horas, em microgramas por metro cúbico. " +
                "Observado: 1 hora, média 12,0, máxima 12,0. Persistência: sem valores.",
            forecastChartDescription(response(listOf(12.0, null))),
        )
    }
}
