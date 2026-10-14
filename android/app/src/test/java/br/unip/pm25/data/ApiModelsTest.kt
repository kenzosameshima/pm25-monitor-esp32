package br.unip.pm25.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test
import java.time.Instant

class ApiModelsTest {
    private fun fixture(name: String): String =
        requireNotNull(javaClass.classLoader?.getResource(name)) { "fixture $name ausente" }.readText()

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
    fun `campos nulos e campos desconhecidos nao quebram a leitura`() {
        val silent = ApiJson.decodeFromString<DeviceList>(fixture("devices.json")).devices[1]
        assertEquals(DeviceStatus.SILENT, silent.status)
        assertNull(silent.location)
        assertNull(silent.lastReceived)
        assertNull(silent.latest)
    }
}
