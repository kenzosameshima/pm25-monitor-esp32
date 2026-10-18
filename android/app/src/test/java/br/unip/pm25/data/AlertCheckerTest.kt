package br.unip.pm25.data

import br.unip.pm25.domain.Alert
import br.unip.pm25.domain.AirQuality
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException
import java.time.Instant

class AlertCheckerTest {
    private val now = Instant.parse("2026-10-14T12:00:00Z")
    private val lastHour = Instant.parse("2026-10-14T11:00:00Z")
    private val api = FakeApi()
    private val alertStore = InMemorySnapshotStore()

    private fun devices(vararg minutesAgo: Long?) = DeviceList(now, 3, 15, minutesAgo.mapIndexed { i, m ->
        DeviceState("no-0${i + 1}", null, DeviceStatus.ONLINE, m?.toDouble(), m?.let { now.minusSeconds(it * 60) })
    })

    private fun hourly(deviceId: String, pm25: Double?) =
        HourlySeries(now, deviceId, lastHour, now, 45, listOf(HourlyPoint(lastHour, 60, pm25 != null, pm25)))

    /** Um checador novo a cada chamada, sobre o mesmo armazenamento: como o worker em execuções separadas. */
    private suspend fun check(): List<Alert> = AlertChecker(repository(api), alertStore).check()

    @Test
    fun `o estado salvo evita repetir o aviso entre execucoes`() = runTest {
        api.onDevices = { devices(30) }
        api.onHourly = { id, _ -> hourly(id, 60.0) }
        val first = check()
        assertEquals(2, first.size)
        assertTrue(first.any { it is Alert.NodeSilent } && first.any { it is Alert.AirHigh })
        assertEquals(emptyList<Alert>(), check())
    }

    @Test
    fun `consulta a ultima hora completa so dos nos que ja enviaram dados`() = runTest {
        val asked = mutableListOf<Pair<String, Int>>()
        api.onDevices = { devices(1, null) }
        api.onHourly = { id, hours -> asked += id to hours; hourly(id, 10.0) }
        check()
        assertEquals(listOf("no-01" to 1), asked)
    }

    @Test
    fun `falha na hora de um no nao impede o resto da checagem`() = runTest {
        api.onDevices = { devices(1, 1) }
        api.onHourly = { id, _ -> if (id == "no-01") throw IOException("caiu") else hourly(id, 80.0) }
        val alerts = check()
        assertEquals(listOf(Alert.AirHigh("no-02", null, AirQuality.MUITO_RUIM, 80.0, lastHour)), alerts)
    }

    @Test
    fun `servidor fora do ar avisa na segunda checagem seguida`() = runTest {
        api.onDevices = { throw IOException("sem rota") }
        assertEquals(emptyList<Alert>(), check())
        assertEquals(listOf(Alert.ServerDown(LoadError.Network)), check())
        assertEquals(emptyList<Alert>(), check())
        api.onDevices = { devices(1) }
        api.onHourly = { id, _ -> hourly(id, 10.0) }
        assertEquals(listOf(Alert.ServerBack), check())
    }

    @Test
    fun `estado salvo estragado recomeca do zero`() = runTest {
        alertStore.texts["estado"] = "{isto não é json"
        api.onDevices = { devices(30) }
        api.onHourly = { id, _ -> hourly(id, null) }
        assertEquals(1, check().size)
    }
}
