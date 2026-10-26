package br.unip.pm25.data

import com.sun.net.httpserver.HttpServer
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Test
import java.net.InetAddress
import java.net.InetSocketAddress
import java.util.concurrent.CopyOnWriteArrayList

/**
 * Pm25Api de verdade (Retrofit, OkHttp e o conversor JSON) contra um servidor HTTP local. Os outros testes
 * usam FakeApi e não passam por aqui: o caminho de cada rota, o token e a leitura dos erros só aparecem nesta camada.
 */
class Pm25ApiTest {
    private val token = "token-de-teste"

    /** Servidor de teste: guarda o que recebeu e responde com o `status`, os `headers` e o `body` do momento. */
    private class StubServer : AutoCloseable {
        class Seen(val method: String, val target: String, val authorization: String?)

        val seen = CopyOnWriteArrayList<Seen>()
        @Volatile var status = 200
        @Volatile var body = "{}"
        @Volatile var headers: Map<String, String> = emptyMap()

        private val server = HttpServer.create(InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0).apply {
            createContext("/") { exchange ->
                seen += Seen(exchange.requestMethod, exchange.requestURI.toString(), exchange.requestHeaders.getFirst("Authorization"))
                val bytes = body.toByteArray()
                exchange.responseHeaders.add("Content-Type", "application/json")
                headers.forEach { (name, value) -> exchange.responseHeaders.add(name, value) }
                exchange.sendResponseHeaders(status, bytes.size.toLong())
                exchange.responseBody.use { it.write(bytes) }
            }
            start()
        }

        fun url(path: String = "") = "http://127.0.0.1:${server.address.port}/$path"

        override fun close() = server.stop(0)
    }

    @Test
    fun `cada rota pede o caminho certo com o token de leitura`() = runBlocking {
        StubServer().use { server ->
            val api = Pm25Api.create(server.url(), token)
            server.body = fixture("devices.json")
            api.devices()
            server.body = fixture("hourly.json")
            api.hourly("no-01", 24)
            server.body = fixture("health.json")
            api.health("no-01", 168)
            server.body = fixture("forecast.json")
            api.forecast("no-01", 48)

            assertEquals(
                listOf(
                    "GET /v1/devices",
                    "GET /v1/devices/no-01/hourly?hours=24",
                    "GET /v1/devices/no-01/health?hours=168",
                    "GET /v1/devices/no-01/forecast?hours=48",
                ),
                server.seen.map { "${it.method} ${it.target}" },
            )
            assertEquals(List(4) { "Bearer $token" }, server.seen.map { it.authorization })
        }
    }

    @Test
    fun `a resposta passa pelo conversor JSON`() = runBlocking {
        StubServer().use { server ->
            server.body = fixture("hourly.json")
            val series = Pm25Api.create(server.url(), token).hourly("no-01", 6)
            assertEquals("no-01", series.deviceId)
            assertEquals(listOf(true, true, false, false, true, true), series.hours.map { it.valid })
        }
    }

    @Test
    fun `url base com subcaminho mantem o prefixo`() = runBlocking {
        StubServer().use { server ->
            server.body = fixture("devices.json")
            Pm25Api.create(server.url("pm25/"), token).devices()
            assertEquals("/pm25/v1/devices", server.seen.single().target)
        }
    }

    @Test
    fun `401 e 429 com Retry-After chegam ao repositorio como erros explicaveis`() = runBlocking {
        StubServer().use { server ->
            val repository = repository(Pm25Api.create(server.url(), token))

            server.status = 401
            assertEquals(LoadError.Unauthorized, (repository.devices() as Outcome.Failure).error)

            server.status = 429
            server.headers = mapOf("Retry-After" to "120")
            assertEquals(LoadError.Blocked(120), (repository.devices() as Outcome.Failure).error)
        }
    }

    @Test
    fun `servidor fora do ar vira erro de rede`() = runBlocking {
        val url = StubServer().use { it.url() }  // fechado logo em seguida: nada escuta nessa porta
        val repository = repository(Pm25Api.create(url, token))
        assertEquals(LoadError.Network, (repository.devices() as Outcome.Failure).error)
    }
}
