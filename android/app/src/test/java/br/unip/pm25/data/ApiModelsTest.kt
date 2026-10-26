package br.unip.pm25.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.time.Instant

/** As fixtures saíram da API de verdade (TestClient do FastAPI sobre um banco sintético). */
class ApiModelsTest {
    @Test
    fun `le a serie horaria com horas validas, incompletas e sem leitura`() {
        val series = ApiJson.decodeFromString<HourlySeries>(fixture("hourly.json"))
        assertEquals(45, series.minReadings)
        assertEquals(6, series.hours.size)
        assertEquals(listOf(60, 60, 30, 0, 60, 50), series.hours.map { it.readings })
        assertEquals(listOf(true, true, false, false, true, true), series.hours.map { it.valid })
        assertNull(series.hours[2].pm25)
        assertEquals(series.start, series.hours.first().hour)
    }

    @Test
    fun `le a hora suspeita, que nao vale e vem sem medias`() {
        val hours = ApiJson.decodeFromString<HourlySeries>(fixture("hourly_suspect.json")).hours
        assertEquals(listOf(false, true, false), hours.map { it.suspect })
        assertEquals(listOf(true, false, true), hours.map { it.valid })
        assertNull(hours[1].pm25)
    }

    @Test
    fun `resposta de servidor sem o campo suspect nao tem hora suspeita`() {
        val hours = ApiJson.decodeFromString<HourlySeries>(fixture("hourly.json")).hours
        assertEquals(List(6) { false }, hours.map { it.suspect })
    }

    @Test
    fun `le a saude da coleta`() {
        val health = ApiJson.decodeFromString<Health>(fixture("health.json"))
        assertEquals("no-01", health.deviceId)
        assertEquals(90, health.largestGapMin)
        assertEquals(0, health.lostMessages)
        assertEquals(0.6167, health.completeness, 0.001)
    }

    @Test
    fun `le a resposta de devices da API`() {
        val list = ApiJson.decodeFromString<DeviceList>(fixture("devices.json"))
        assertEquals(Instant.parse("2026-10-14T04:36:18Z"), list.generatedAt)
        assertEquals(15, list.silentAfterMin)

        val online = list.devices[0]
        assertEquals("no-01", online.deviceId)
        assertEquals("Teste local, bancada", online.location)
        assertEquals(DeviceStatus.ONLINE, online.status)
        val latest = requireNotNull(online.latest)
        assertEquals(14.5, latest.pm25!!, 0.0)
        assertEquals(-70, latest.rssi)
        assertEquals(Instant.parse("2026-10-14T04:35:00Z"), latest.ts)
    }

    @Test
    fun `estado novo do servidor nao derruba a lista inteira`() {
        val list = ApiJson.decodeFromString<DeviceList>(
            """{"generated_at": "2026-10-14T04:36:18Z", "late_after_min": 3, "silent_after_min": 15, "devices": [
                {"device_id": "no-01", "status": "paused"},
                {"device_id": "no-02", "status": "online"}]}"""
        )
        assertEquals(listOf("no-01", "no-02"), list.devices.map { it.deviceId })
        assertEquals(listOf(null, DeviceStatus.ONLINE), list.devices.map { it.status })
    }

    @Test
    fun `campos nulos e campos desconhecidos nao quebram a leitura`() {
        val silent = ApiJson.decodeFromString<DeviceList>(fixture("devices.json")).devices[1]
        assertEquals(DeviceStatus.SILENT, silent.status)
        assertNull(silent.location)
        assertNull(silent.lastReceived)
        assertNull(silent.latest)
    }
}
