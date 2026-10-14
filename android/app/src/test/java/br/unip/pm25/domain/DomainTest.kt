package br.unip.pm25.domain

import br.unip.pm25.data.DeviceList
import br.unip.pm25.data.DeviceState
import br.unip.pm25.data.DeviceStatus
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
    fun `hora do servidor soma o tempo desde a chegada, sem depender da hora do celular`() {
        val generatedAt = Instant.parse("2026-10-14T12:00:00Z")
        val phoneWrong = Instant.parse("2026-10-14T09:13:00Z")   // celular 3 h atrasado
        val later = phoneWrong.plus(Duration.ofHours(20))
        assertEquals(generatedAt.plus(Duration.ofHours(20)), estimatedServerNow(generatedAt, phoneWrong, later))
        // leitura salva com 1 min de idade fica com 20 h e 1 min
        assertEquals("há 20 h", formatAge(readingAge(generatedAt.minusSeconds(120), estimatedServerNow(generatedAt, phoneWrong, later))))
        // relógio do celular voltou para trás: não inventa tempo negativo
        assertEquals(generatedAt, estimatedServerNow(generatedAt, later, phoneWrong))
    }

    @Test
    fun `estado do no envelhece com a resposta salva, pelos limites do servidor`() {
        val received = Instant.parse("2026-10-14T12:00:00Z")
        val device = DeviceState("no-01", null, DeviceStatus.ONLINE, 0.5, received.minusSeconds(30), null)
        val list = DeviceList(received, lateAfterMin = 3, silentAfterMin = 15, devices = listOf(device))
        assertEquals(DeviceStatus.ONLINE, currentStatus(device, list, received))                 // igual ao servidor
        assertEquals(DeviceStatus.LATE, currentStatus(device, list, received.plusSeconds(4 * 60)))
        assertEquals(DeviceStatus.SILENT, currentStatus(device, list, received.plusSeconds(20 * 60)))
        assertEquals(DeviceStatus.SILENT, currentStatus(device.copy(lastReceived = null), list, received))
    }

    @Test
    fun `texto da idade`() {
        assertEquals("agora", formatAge(Duration.ofSeconds(59)))
        assertEquals("há 5 min", formatAge(Duration.ofMinutes(5)))
        assertEquals("há 2 h", formatAge(Duration.ofMinutes(150)))
        assertEquals("há 3 dias", formatAge(Duration.ofDays(3)))
    }
}
