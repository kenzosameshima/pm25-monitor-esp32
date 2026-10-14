package br.unip.pm25.data

import java.time.Duration
import java.time.Instant

/** Pm25Api de teste: cada rota responde com a função dada; uma rota não configurada falha o teste. */
class FakeApi(
    var onDevices: () -> DeviceList = { error("devices não configurado") },
    var onHourly: (deviceId: String, hours: Int) -> HourlySeries = { _, _ -> error("hourly não configurado") },
    var onHealth: (deviceId: String, hours: Int) -> Health = { _, _ -> error("health não configurado") },
    var onForecast: (deviceId: String, hours: Int) -> ForecastResponse = { _, _ -> error("forecast não configurado") },
) : Pm25Api {
    override suspend fun devices(): DeviceList = onDevices()
    override suspend fun hourly(deviceId: String, hours: Int): HourlySeries = onHourly(deviceId, hours)
    override suspend fun health(deviceId: String, hours: Int): Health = onHealth(deviceId, hours)
    override suspend fun forecast(deviceId: String, hours: Int): ForecastResponse = onForecast(deviceId, hours)
}

/** SnapshotStore em memória, compartilhável entre repositórios para simular o app reaberto. */
class InMemorySnapshotStore : SnapshotStore {
    val texts = mutableMapOf<String, String>()
    override suspend fun read(key: String): String? = texts[key]
    override suspend fun write(key: String, text: String) {
        texts[key] = text
    }
}

/** Relógio do celular nos testes: começa num instante fixo e só anda quando o teste manda. */
class TestClock(var now: Instant = Instant.parse("2026-10-14T12:00:00Z")) {
    fun advance(duration: Duration) {
        now = now.plus(duration)
    }
}

fun repository(
    api: Pm25Api,
    store: SnapshotStore = InMemorySnapshotStore(),
    clock: TestClock = TestClock(),
) = DeviceRepository(api, store) { clock.now }

fun fixture(name: String): String =
    requireNotNull(FakeApi::class.java.classLoader?.getResource(name)) { "fixture $name ausente" }.readText()
