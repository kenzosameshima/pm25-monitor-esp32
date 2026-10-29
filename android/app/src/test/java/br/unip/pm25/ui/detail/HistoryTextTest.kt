package br.unip.pm25.ui.detail

import br.unip.pm25.data.HourlyPoint
import br.unip.pm25.domain.HourlySummary
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.time.Instant

class HistoryTextTest {
    private fun summary(none: Int = 0, few: Int = 0, suspect: Int = 0) = HourlySummary(
        totalHours = 24, validHours = 24 - none - few - suspect, mean = 12.0,
        max = HourlyPoint(Instant.EPOCH, readings = 60, valid = true, pm25 = 30.0), hoursAboveGood = 0, humidHours = 0,
        suspectHours = suspect, noReadingHours = none, fewReadingsHours = few,
    )

    @Test
    fun `diz quantas horas ficaram sem media em cada causa`() {
        assertEquals("Horas sem média: 2 sem leituras, 1 com poucas leituras e 1 suspeita.",
            blankHoursNote(summary(none = 2, few = 1, suspect = 1)))
    }

    @Test
    fun `so cita as causas que existem e flexiona suspeita`() {
        assertEquals("Horas sem média: 3 suspeitas.", blankHoursNote(summary(suspect = 3)))
        assertEquals("Horas sem média: 1 sem leituras e 4 com poucas leituras.", blankHoursNote(summary(none = 1, few = 4)))
    }

    @Test
    fun `sem horas em branco nao ha frase`() {
        assertNull(blankHoursNote(summary()))
    }

    @Test
    fun `a descricao do grafico traz o resumo e a causa das horas sem media`() {
        assertEquals(
            "PM2,5 por hora nas últimas 24 h: média 12,0, máxima 30,0 microgramas por metro cúbico, " +
                "21 de 24 horas válidas. Horas sem média: 2 sem leituras e 1 suspeita.",
            historyDescription("24 h", summary(none = 2, suspect = 1)),
        )
    }

    @Test
    fun `a descricao nao cita horas sem media quando nao ha`() {
        assertEquals(
            "PM2,5 por hora nas últimas 24 h: média 12,0, máxima 30,0 microgramas por metro cúbico, " +
                "24 de 24 horas válidas.",
            historyDescription("24 h", summary()),
        )
    }
}
