package br.unip.pm25.data

import kotlinx.coroutines.test.runTest
import kotlinx.serialization.SerializationException
import okhttp3.Headers.Companion.headersOf
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import retrofit2.HttpException
import retrofit2.Response
import java.io.IOException
import java.time.Instant

class DeviceRepositoryTest {
    private fun failureOf(error: () -> Nothing): LoadError {
        var result: Outcome<DeviceList>? = null
        runTest { result = DeviceRepository(FakeApi(onDevices = error)).devices() }
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
    fun `resposta valida vira sucesso`() = runTest {
        val list = DeviceList(Instant.EPOCH, 3, 15, emptyList())
        val result = DeviceRepository(FakeApi(onDevices = { list })).devices()
        assertTrue(result is Outcome.Success && result.value == list)
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
}
