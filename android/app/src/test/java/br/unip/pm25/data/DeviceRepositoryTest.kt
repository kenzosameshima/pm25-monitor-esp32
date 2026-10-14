package br.unip.pm25.data

import kotlinx.coroutines.test.runTest
import kotlinx.serialization.SerializationException
import okhttp3.Headers.Companion.headersOf
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import retrofit2.HttpException
import retrofit2.Response
import java.io.IOException
import java.time.Duration
import java.time.Instant

class DeviceRepositoryTest {
    private val list = DeviceList(Instant.parse("2026-10-14T11:59:00Z"), 3, 15, emptyList())

    private fun failureOf(error: () -> Nothing): LoadError {
        var result: Outcome<Timed<DeviceList>>? = null
        runTest { result = repository(FakeApi(onDevices = error)).devices() }
        return (result as Outcome.Failure).error
    }

    private fun http(code: Int, headers: Map<String, String> = emptyMap()): HttpException {
        val raw = okhttp3.Response.Builder()
            .request(okhttp3.Request.Builder().url("http://10.0.2.2:8000/v1/devices").build())
            .protocol(okhttp3.Protocol.HTTP_1_1)
            .code(code).message("erro")
            .headers(headersOf(*headers.flatMap { listOf(it.key, it.value) }.toTypedArray()))
            .build()
        return HttpException(Response.error<DeviceList>("{}".toResponseBody(), raw))
    }

    @Test
    fun `resposta valida vira sucesso com a hora de chegada`() = runTest {
        val clock = TestClock()
        val result = repository(FakeApi(onDevices = { list }), clock = clock).devices()
        assertTrue(result is Outcome.Success)
        assertEquals(Timed(list, clock.now), (result as Outcome.Success).value)
    }

    @Test
    fun `codigos http viram erros explicaveis`() {
        assertEquals(LoadError.Unauthorized, failureOf { throw http(401) })
        assertEquals(LoadError.NotFound, failureOf { throw http(404) })
        assertEquals(LoadError.ReadDisabled, failureOf { throw http(503) })
        assertEquals(LoadError.Blocked(120), failureOf { throw http(429, mapOf("Retry-After" to "120")) })
        assertEquals(LoadError.Blocked(null), failureOf { throw http(429) })
        assertEquals(LoadError.Server(500), failureOf { throw http(500) })
    }

    @Test
    fun `falha de rede e resposta fora do contrato`() {
        assertEquals(LoadError.Network, failureOf { throw IOException("sem rota") })
        assertEquals(LoadError.BadResponse, failureOf { throw SerializationException("campo faltando") })
    }

    @Test
    fun `resposta salva sobrevive ao app reaberto`() = runTest {
        val store = InMemorySnapshotStore()
        val clock = TestClock()
        repository(FakeApi(onDevices = { list }), store, clock).devices()
        val receivedAt = clock.now
        clock.advance(Duration.ofDays(1))

        val reopened = repository(FakeApi(onDevices = { throw IOException() }), store, clock)
        assertEquals(Timed(list, receivedAt), reopened.cachedDevices())
    }

    @Test
    fun `falha nao apaga a resposta salva`() = runTest {
        val store = InMemorySnapshotStore()
        val api = FakeApi(onDevices = { list })
        val repo = repository(api, store)
        repo.devices()
        api.onDevices = { throw IOException() }
        repo.devices()
        assertEquals(list, repo.cachedDevices()?.value)
    }

    @Test
    fun `cada rota e cada janela tem a sua copia`() = runTest {
        val series = ApiJson.decodeFromString<HourlySeries>(fixture("hourly.json"))
        val repo = repository(FakeApi(onHourly = { _, _ -> series }))
        repo.hourly("no-01", 24)
        assertEquals(series, repo.cachedHourly("no-01", 24)?.value)
        assertNull(repo.cachedHourly("no-01", 168))
        assertNull(repo.cachedHourly("no-02", 24))
    }

    @Test
    fun `copia estragada ou de outro formato e ignorada`() = runTest {
        val store = InMemorySnapshotStore()
        store.texts["devices"] = "{\"value\": {\"isto\": \"não é uma lista\"}, \"received_at\": \"2026-10-14T12:00:00Z\"}"
        assertNull(repository(FakeApi(), store).cachedDevices())
        store.texts["devices"] = "{ cortado no meio"
        assertNull(repository(FakeApi(), store).cachedDevices())
    }
}
