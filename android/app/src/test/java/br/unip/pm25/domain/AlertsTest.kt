package br.unip.pm25.domain

import br.unip.pm25.data.DeviceList
import br.unip.pm25.data.DeviceState
import br.unip.pm25.data.DeviceStatus
import br.unip.pm25.data.HourlyPoint
import br.unip.pm25.data.LoadError
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Instant

class AlertsTest {
    private val now = Instant.parse("2026-10-14T12:00:00Z")
    private val lastHour = Instant.parse("2026-10-14T11:00:00Z")

    /** Nó que enviou dados há `minutesAgo` minutos (null: nunca enviou). */
    private fun device(id: String, minutesAgo: Long?, location: String? = null) = DeviceState(
        id, location, DeviceStatus.ONLINE, minutesAgo?.toDouble(), minutesAgo?.let { now.minusSeconds(it * 60) }, null,
    )

    private fun answered(vararg devices: DeviceState, hours: Map<String, Double?> = emptyMap()) = Check.Answered(
        DeviceList(now, lateAfterMin = 3, silentAfterMin = 15, devices = devices.toList()),
        hours.mapValues { (_, pm25) -> HourlyPoint(lastHour, if (pm25 == null) 0 else 60, pm25 != null, pm25) },
    )

    /** Aplica as checagens em sequência a partir do estado inicial; devolve o estado final e os alertas de cada uma. */
    private fun run(vararg checks: Check): Pair<AlertState, List<List<Alert>>> {
        var state = AlertState()
        val alerts = checks.map { check -> evaluate(state, check).also { state = it.first }.second }
        return state to alerts
    }

    @Test
    fun `no sem dados avisa uma vez e a volta avisa de novo`() {
        val (state, alerts) = run(
            answered(device("no-01", 1)),
            answered(device("no-01", 20, "Escola")),
            answered(device("no-01", 25, "Escola")),
            answered(device("no-01", 0, "Escola")),
        )
        assertEquals(emptyList<Alert>(), alerts[0])
        assertEquals(listOf(Alert.NodeSilent("no-01", "Escola", now.minusSeconds(20 * 60))), alerts[1])
        assertEquals(emptyList<Alert>(), alerts[2])                       // continua sem dados: não repete
        assertEquals(listOf(Alert.NodeBack("no-01", "Escola")), alerts[3])
        assertEquals(emptySet<String>(), state.silent)
    }

    @Test
    fun `atrasado nao e sem dados, e no que nunca enviou nao gera alerta`() {
        val (_, alerts) = run(answered(device("no-01", 10), device("no-02", null)))
        assertEquals(emptyList<Alert>(), alerts.single())
    }

    @Test
    fun `no ja sem dados na primeira checagem avisa`() {
        val (state, alerts) = run(answered(device("no-01", 60)))
        assertTrue(alerts.single().single() is Alert.NodeSilent)
        assertEquals(setOf("no-01"), state.silent)
    }

    @Test
    fun `no que sai da lista deixa de ser acompanhado`() {
        val (state, alerts) = run(answered(device("no-01", 60)), answered())
        assertEquals(emptyList<Alert>(), alerts[1])
        assertEquals(AlertState(), state)
    }

    @Test
    fun `servidor so vira alerta depois de falhas seguidas, e a volta avisa`() {
        val (state, alerts) = run(
            Check.Failed(LoadError.Network),
            Check.Failed(LoadError.Network),
            Check.Failed(LoadError.Network),
            answered(device("no-01", 1)),
        )
        assertEquals(emptyList<Alert>(), alerts[0])                       // uma falha isolada não avisa
        assertEquals(listOf(Alert.ServerDown(LoadError.Network)), alerts[1])
        assertEquals(emptyList<Alert>(), alerts[2])
        assertEquals(listOf(Alert.ServerBack), alerts[3])
        assertEquals(AlertState(), state)
    }

    @Test
    fun `uma resposta entre falhas zera a contagem`() {
        val (_, alerts) = run(Check.Failed(LoadError.Network), answered(), Check.Failed(LoadError.Network))
        assertEquals(listOf(emptyList<Alert>(), emptyList(), emptyList()), alerts)
    }

    @Test
    fun `falha do servidor nao apaga o que ja foi avisado sobre os nos`() {
        val (state, alerts) = run(
            answered(device("no-01", 60), hours = mapOf("no-01" to 60.0)),
            Check.Failed(LoadError.Network),
            answered(device("no-01", 61), hours = mapOf("no-01" to 60.0)),
        )
        assertEquals(2, alerts[0].size)
        assertEquals(emptyList<Alert>(), alerts[2])                       // nada repetido depois da falha
        assertEquals(setOf("no-01"), state.silent)
    }

    @Test
    fun `ar avisa ao entrar em Ruim e ao piorar, nao ao melhorar dentro do episodio`() {
        val (state, alerts) = run(
            answered(device("no-01", 1), hours = mapOf("no-01" to 40.0)),   // Moderada
            answered(device("no-01", 1), hours = mapOf("no-01" to 60.0)),   // Ruim
            answered(device("no-01", 1), hours = mapOf("no-01" to 70.0)),   // ainda Ruim
            answered(device("no-01", 1), hours = mapOf("no-01" to 100.0)),  // Muito ruim
            answered(device("no-01", 1), hours = mapOf("no-01" to 60.0)),   // melhora para Ruim
            answered(device("no-01", 1), hours = mapOf("no-01" to 80.0)),   // piora de novo
        )
        assertEquals(emptyList<Alert>(), alerts[0])
        assertEquals(listOf(Alert.AirHigh("no-01", null, AirQuality.RUIM, 60.0, lastHour)), alerts[1])
        assertEquals(emptyList<Alert>(), alerts[2])
        assertEquals(AirQuality.MUITO_RUIM, (alerts[3].single() as Alert.AirHigh).band)
        assertEquals(emptyList<Alert>(), alerts[4])
        assertEquals(AirQuality.MUITO_RUIM, (alerts[5].single() as Alert.AirHigh).band)
        assertEquals(mapOf("no-01" to AirQuality.MUITO_RUIM), state.airBands)
    }

    @Test
    fun `ar abaixo de Ruim encerra o episodio, e a proxima subida avisa`() {
        val (_, alerts) = run(
            answered(device("no-01", 1), hours = mapOf("no-01" to 60.0)),
            answered(device("no-01", 1), hours = mapOf("no-01" to 30.0)),
            answered(device("no-01", 1), hours = mapOf("no-01" to 55.0)),
        )
        assertEquals(listOf(1, 0, 1), alerts.map { it.size })
    }

    @Test
    fun `hora sem media valida nao muda o que ja foi avisado sobre o ar`() {
        val (state, alerts) = run(
            answered(device("no-01", 1), hours = mapOf("no-01" to 60.0)),
            answered(device("no-01", 1), hours = mapOf("no-01" to null)),   // hora incompleta
            answered(device("no-01", 1)),                                   // consulta da hora falhou
            answered(device("no-01", 1), hours = mapOf("no-01" to 60.0)),
        )
        assertEquals(listOf(1, 0, 0, 0), alerts.map { it.size })
        assertEquals(mapOf("no-01" to AirQuality.RUIM), state.airBands)
    }

    @Test
    fun `ar no limite de 50 ainda e Moderada`() {
        val (_, alerts) = run(answered(device("no-01", 1), hours = mapOf("no-01" to 50.0)))
        assertEquals(emptyList<Alert>(), alerts.single())
    }
}
