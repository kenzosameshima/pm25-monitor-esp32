package br.unip.pm25.ui.home

import br.unip.pm25.data.LatestReading
import org.junit.Assert.assertEquals
import org.junit.Test
import java.time.Instant

class HistoricalReadingTest {
    private val ts = Instant.parse("2026-10-27T21:26:00Z")

    @Test
    fun `diz que e historico e traz cada valor com a unidade`() {
        val reading = LatestReading(ts, pm25 = 0.0, pm10 = 0.0, temperature = 22.2, humidity = 54.6, rssi = -53)
        assertEquals(
            "Leitura de 27/10 18:26, histórico (não é o valor atual): PM2,5 0,0 µg/m³ · PM10 0,0 µg/m³ · " +
                "22,2 °C · 55% · -53 dBm.",
            historicalReadingText(reading, "27/10 18:26"),
        )
    }

    @Test
    fun `so entram os valores que o no mandou`() {
        assertEquals(
            "Leitura de 27/10 18:26, histórico (não é o valor atual): PM2,5 12,0 µg/m³.",
            historicalReadingText(LatestReading(ts, pm25 = 12.0), "27/10 18:26"),
        )
    }

    @Test
    fun `leitura sem PM2,5 mostra o traco no lugar do valor`() {
        assertEquals(
            "Leitura de 27/10 18:26, histórico (não é o valor atual): PM2,5 — · 22,2 °C.",
            historicalReadingText(LatestReading(ts, temperature = 22.2), "27/10 18:26"),
        )
    }

    @Test
    fun `leitura marcada pelo servidor diz que e implausivel`() {
        val reading = LatestReading(ts, pm25 = 12.0, quality = "umid_fora_faixa")
        assertEquals(
            "Leitura de 27/10 18:26, histórico (não é o valor atual): PM2,5 12,0 µg/m³. " +
                "O servidor a marcou como implausível (umid_fora_faixa).",
            historicalReadingText(reading, "27/10 18:26"),
        )
    }
}
