package br.unip.pm25.ui

import org.junit.Assert.assertEquals
import org.junit.Test
import java.time.Instant
import java.time.LocalDateTime
import java.time.ZoneId
import java.util.TimeZone

class FormatMomentTest {
    /**
     * CLOCK guarda o fuso de quando a classe carregou, e outro teste muda o fuso padrão por um instante, então o
     * fuso de CLOCK pode não ser o do computador. Aqui os dois ficam iguais, qualquer que seja, para o resultado
     * não depender da ordem dos testes.
     */
    private fun inFormatterZone(block: (local: (day: Int, hour: Int, minute: Int) -> Instant) -> Unit) {
        val original = TimeZone.getDefault()
        val zone: ZoneId = CLOCK.zone
        TimeZone.setDefault(TimeZone.getTimeZone(zone))
        try {
            block { day, hour, minute -> LocalDateTime.of(2026, 10, day, hour, minute).atZone(zone).toInstant() }
        } finally {
            TimeZone.setDefault(original)
        }
    }

    @Test
    fun `no mesmo dia mostra so a hora`() = inFormatterZone { local ->
        assertEquals("09:30", formatMoment(local(14, 9, 30), now = local(14, 15, 0)))
    }

    @Test
    fun `em outro dia mostra a data e a hora`() = inFormatterZone { local ->
        assertEquals("13/10 18:45", formatMoment(local(13, 18, 45), now = local(14, 15, 0)))
    }

    @Test
    fun `a meia-noite separa os dias`() = inFormatterZone { local ->
        assertEquals("00:00", formatMoment(local(14, 0, 0), now = local(14, 23, 59)))
        assertEquals("13/10 23:59", formatMoment(local(13, 23, 59), now = local(14, 0, 0)))
    }
}
