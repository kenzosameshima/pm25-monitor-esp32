package br.unip.pm25.alerts

import br.unip.pm25.data.LoadError
import br.unip.pm25.domain.AirQuality
import br.unip.pm25.domain.Alert
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Instant
import java.util.TimeZone

class AlertNoticeTest {
    private val now = Instant.parse("2026-10-14T15:00:00Z")

    private fun <T> inSaoPaulo(block: () -> T): T {
        val original = TimeZone.getDefault()
        TimeZone.setDefault(TimeZone.getTimeZone("America/Sao_Paulo"))
        try {
            return block()
        } finally {
            TimeZone.setDefault(original)
        }
    }

    @Test
    fun `aviso de volta substitui o de falha do mesmo no, e o ar tem notificacao propria`() {
        val silent = Alert.NodeSilent("no-01", null, now).notice(now)
        val back = Alert.NodeBack("no-01", null).notice(now)
        val air = Alert.AirHigh("no-01", null, AirQuality.RUIM, 60.0, now).notice(now)
        val other = Alert.NodeSilent("no-02", null, now).notice(now)
        assertEquals(silent.id, back.id)
        assertNotEquals(silent.id, air.id)
        assertNotEquals(silent.id, other.id)
        assertEquals(Alert.ServerDown(LoadError.Network).notice(now).id, Alert.ServerBack.notice(now).id)
        assertEquals(AlertChannel.AIR, air.channel)
        assertEquals(AlertChannel.NODES, back.channel)
    }

    @Test
    fun `texto do ar mostra a hora local, o valor e a faixa`() = inSaoPaulo {
        val notice = Alert.AirHigh("no-01", "Escola", AirQuality.MUITO_RUIM, 101.4, Instant.parse("2026-10-14T14:00:00Z"))
            .notice(now)
        assertEquals("PM2,5 muito ruim em no-01", notice.title)
        assertEquals("Escola. Média das 11:00 às 12:00: 101 µg/m³, faixa Muito ruim da CETESB.", notice.text)
    }

    @Test
    fun `servidor fora do ar explica conforme o erro`() {
        assertTrue(Alert.ServerDown(LoadError.Network).notice(now).text.startsWith("Há pelo menos 15 minutos"))
        assertTrue(Alert.ServerDown(LoadError.Unauthorized).notice(now).text.contains("token de leitura"))
        assertTrue(Alert.ServerDown(LoadError.Tls).notice(now).text.contains("conexão segura"))
    }
}
