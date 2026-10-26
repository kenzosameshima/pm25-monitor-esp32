package br.unip.pm25.ui

import br.unip.pm25.data.LoadError
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** Os textos de erro aparecem na tela e em notificações, que o celular mostra até com a tela bloqueada. */
class LoadErrorMessageTest {
    private val every = listOf(
        LoadError.Network, LoadError.Tls, LoadError.Unauthorized, LoadError.ReadDisabled, LoadError.NotFound,
        LoadError.Blocked(30), LoadError.Blocked(null), LoadError.Server(500), LoadError.BadResponse,
    )

    @Test
    fun `cada erro tem um texto proprio`() {
        val texts = every.map { it.message() }
        assertTrue(texts.all { it.isNotBlank() })
        assertEquals(texts.size, texts.toSet().size)
    }

    @Test
    fun `bloqueio diz em quantos segundos tentar de novo, ou que leva alguns minutos`() {
        assertTrue(LoadError.Blocked(120).message().contains("120 s"))
        assertTrue(LoadError.Blocked(null).message().contains("alguns minutos"))
    }

    @Test
    fun `erro do servidor traz o codigo HTTP`() {
        assertTrue(LoadError.Server(502).message().contains("502"))
    }

    @Test
    fun `nenhum texto cita arquivo ou variavel de configuracao`() {
        for (error in every) {
            val text = error.message()
            for (internal in listOf("local.properties", "pm25.", "PM25_", ".env")) {
                assertFalse("$error cita $internal: $text", text.contains(internal))
            }
        }
    }
}
