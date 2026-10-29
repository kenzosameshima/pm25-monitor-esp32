package br.unip.pm25.domain

import br.unip.pm25.data.DeviceList
import br.unip.pm25.data.DeviceState
import br.unip.pm25.data.DeviceStatus
import br.unip.pm25.data.LatestReading
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.double
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
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

    @Test
    fun `as faixas sao as mesmas do servidor`() {
        // shared/air-quality-bands.json, o mesmo arquivo que o teste do servidor confere.
        val text = requireNotNull(AirQualityTest::class.java.classLoader?.getResource("air-quality-bands.json")) {
            "air-quality-bands.json ausente dos recursos de teste"
        }.readText()
        val shared = Json.parseToJsonElement(text).jsonArray.map {
            val bound = it.jsonObject.getValue("upper_bound").jsonPrimitive
            it.jsonObject.getValue("label").jsonPrimitive.content to
                if (bound is JsonNull) Double.POSITIVE_INFINITY else bound.double
        }
        assertEquals(shared, AirQuality.entries.map { it.label to it.upperBound })
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
    fun `so o no sem dados deixa de ter valor atual`() {
        assertTrue(hasCurrentValue(DeviceStatus.ONLINE))
        assertTrue(hasCurrentValue(DeviceStatus.LATE))     // atrasado ainda mostra o valor, com a idade ao lado
        assertFalse(hasCurrentValue(DeviceStatus.SILENT))
    }

    @Test
    fun `texto da idade`() {
        assertEquals("agora", formatAge(Duration.ofSeconds(59)))
        assertEquals("há 5 min", formatAge(Duration.ofMinutes(5)))
        assertEquals("há 2 h", formatAge(Duration.ofMinutes(150)))
        assertEquals("há 3 dias", formatAge(Duration.ofDays(3)))
    }
}

class ZeroReadingTest {
    private val ts = Instant.parse("2026-10-14T12:00:00Z")

    @Test
    fun `leitura com todas as particulas em zero e zerada`() {
        assertTrue(isZeroReading(LatestReading(ts, pm1 = 0.0, pm25 = 0.0, pm10 = 0.0)))
        assertTrue(isZeroReading(LatestReading(ts, pm25 = 0.0, pm10 = 0.0)))  // PM1 que o nó não mandou não conta
    }

    @Test
    fun `qualquer particula vista desfaz o zero`() {
        assertFalse(isZeroReading(LatestReading(ts, pm1 = 0.0, pm25 = 0.0, pm10 = 0.1)))
        assertFalse(isZeroReading(LatestReading(ts, pm1 = 0.0, pm25 = 0.2, pm10 = 0.0)))
        assertFalse(isZeroReading(LatestReading(ts, pm1 = 0.3, pm25 = 0.0, pm10 = 0.0)))
    }

    @Test
    fun `sem pm25 nao ha leitura para dizer que e zero`() {
        assertFalse(isZeroReading(LatestReading(ts, pm1 = 0.0, pm25 = null, pm10 = 0.0)))
        assertFalse(isZeroReading(LatestReading(ts)))
        assertFalse(isZeroReading(LatestReading(ts, pm25 = Double.NaN, pm10 = 0.0)))
    }
}
