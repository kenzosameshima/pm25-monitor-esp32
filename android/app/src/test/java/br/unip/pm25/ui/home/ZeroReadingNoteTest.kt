package br.unip.pm25.ui.home

import br.unip.pm25.data.LatestReading
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test
import java.time.Instant

class ZeroReadingNoteTest {
    private val ts = Instant.parse("2026-10-14T12:00:00Z")
    private val rest = "o sensor pode não estar vendo partículas. Por isso o cartão fica sem faixa de qualidade do ar."

    @Test
    fun `cita as tres particulas quando o no enviou as tres`() {
        assertEquals(
            "Leitura zerada (PM1, PM2,5 e PM10 em 0,0): $rest",
            zeroReadingNote(LatestReading(ts, pm1 = 0.0, pm25 = 0.0, pm10 = 0.0)),
        )
    }

    @Test
    fun `nao cita o PM1 que nao chegou`() {
        assertEquals(
            "Leitura zerada (PM2,5 e PM10 em 0,0): $rest",
            zeroReadingNote(LatestReading(ts, pm25 = 0.0, pm10 = 0.0)),
        )
    }

    @Test
    fun `nao cita o PM10 que nao chegou`() {
        assertEquals(
            "Leitura zerada (PM1 e PM2,5 em 0,0): $rest",
            zeroReadingNote(LatestReading(ts, pm1 = 0.0, pm25 = 0.0)),
        )
    }

    @Test
    fun `so o PM2,5 chegou`() {
        assertEquals("Leitura zerada (PM2,5 em 0,0): $rest", zeroReadingNote(LatestReading(ts, pm25 = 0.0)))
    }

    @Test
    fun `nao afirma que o ar esta limpo`() {
        val note = zeroReadingNote(LatestReading(ts, pm1 = 0.0, pm25 = 0.0, pm10 = 0.0))
        assertFalse(note.contains("Boa"))
        assertFalse(note.contains("limpo"))
    }
}
