package br.unip.pm25.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.time.Duration
import java.time.Instant

class AirQualityTest {
    @Test
    fun `cada limite pertence a faixa de baixo`() {
        assertEquals(AirQuality.BOA, AirQuality.of(0.0))
        assertEquals(AirQuality.BOA, AirQuality.of(25.0))
        assertEquals(AirQuality.MODERADA, AirQuality.of(25.1))
        assertEquals(AirQuality.RUIM, AirQuality.of(75.0))
        assertEquals(AirQuality.MUITO_RUIM, AirQuality.of(125.0))
        assertEquals(AirQuality.PESSIMA, AirQuality.of(125.1))
    }

    @Test
    fun `sem valor valido nao ha faixa`() {
        assertNull(AirQuality.of(null))
        assertNull(AirQuality.of(Double.NaN))
        assertNull(AirQuality.of(-1.0))
    }
}

class FreshnessTest {
    private val start = Instant.parse("2026-10-14T12:00:00Z")

    @Test
    fun `idade conta a partir do fim do minuto e pelo relogio do servidor`() {
        assertEquals(Duration.ofMinutes(4), readingAge(start, start.plusSeconds(5 * 60)))
        assertEquals(Duration.ZERO, readingAge(start, start.plusSeconds(30)))   // minuto ainda aberto
        assertEquals(Duration.ZERO, readingAge(start, start.minusSeconds(600))) // servidor "atrás" da leitura
    }

    @Test
    fun `texto da idade`() {
        assertEquals("agora", formatAge(Duration.ofSeconds(59)))
        assertEquals("há 5 min", formatAge(Duration.ofMinutes(5)))
        assertEquals("há 2 h", formatAge(Duration.ofMinutes(150)))
        assertEquals("há 3 dias", formatAge(Duration.ofDays(3)))
    }
}
