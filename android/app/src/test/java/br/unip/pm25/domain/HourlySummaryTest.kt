package br.unip.pm25.domain

import br.unip.pm25.data.ApiJson
import br.unip.pm25.data.HourlyPoint
import br.unip.pm25.data.HourlySeries
import br.unip.pm25.data.fixture
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.time.Instant

class HourlySummaryTest {
    @Test
    fun `resume so as horas validas da serie da api`() {
        // PM2,5 das horas: 10, 14, (30 leituras), (sem leitura), 26 com umidade de 85%, 30
        val series = ApiJson.decodeFromString<HourlySeries>(fixture("hourly.json"))
        val s = summarize(series.hours)
        assertEquals(6, s.totalHours)
        assertEquals(4, s.validHours)
        assertEquals(20.0, s.mean!!, 1e-9)
        val max = requireNotNull(s.max)
        assertEquals(30.0, max.pm25!!, 0.0)
        assertEquals(series.hours[5].hour, max.hour)
        assertEquals(2, s.hoursAboveGood)
        assertEquals(1, s.humidHours)
    }

    @Test
    fun `conta as horas suspeitas e as deixa fora da media`() {
        // PM2,5 das horas: 20, (suspeita), 30
        val s = summarize(ApiJson.decodeFromString<HourlySeries>(fixture("hourly_suspect.json")).hours)
        assertEquals(3, s.totalHours)
        assertEquals(2, s.validHours)
        assertEquals(1, s.suspectHours)
        assertEquals(25.0, s.mean!!, 1e-9)
    }

    @Test
    fun `hora sem leituras ou com poucas leituras nao e suspeita`() {
        val series = ApiJson.decodeFromString<HourlySeries>(fixture("hourly.json"))
        assertEquals(0, summarize(series.hours).suspectHours)
    }

    @Test
    fun `separa as horas sem media pela causa`() {
        // hourly.json: a terceira hora tem 30 leituras (poucas) e a quarta, nenhuma
        val s = summarize(ApiJson.decodeFromString<HourlySeries>(fixture("hourly.json")).hours)
        assertEquals(1, s.noReadingHours)
        assertEquals(1, s.fewReadingsHours)
        assertEquals(0, s.suspectHours)
    }

    @Test
    fun `a hora suspeita tem leituras de sobra e nao conta como poucas leituras`() {
        val s = summarize(ApiJson.decodeFromString<HourlySeries>(fixture("hourly_suspect.json")).hours)
        assertEquals(1, s.suspectHours)
        assertEquals(0, s.noReadingHours)
        assertEquals(0, s.fewReadingsHours)
    }

    @Test
    fun `sem horas validas nao ha media nem maxima`() {
        val invalid = HourlyPoint(Instant.EPOCH, readings = 10, valid = false)
        val s = summarize(listOf(invalid, invalid))
        assertEquals(2, s.totalHours)
        assertEquals(0, s.validHours)
        assertNull(s.mean)
        assertNull(s.max)
    }
}
