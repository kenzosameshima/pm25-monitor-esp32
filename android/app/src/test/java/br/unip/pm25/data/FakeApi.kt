package br.unip.pm25.data

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

fun fixture(name: String): String =
    requireNotNull(FakeApi::class.java.classLoader?.getResource(name)) { "fixture $name ausente" }.readText()
