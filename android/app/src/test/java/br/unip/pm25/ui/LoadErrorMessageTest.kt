package br.unip.pm25.ui

import br.unip.pm25.data.LoadError
import org.junit.Assert.assertFalse
import org.junit.Test

/** Os textos de erro aparecem na tela e em notificações, que o celular mostra até com a tela bloqueada. */
class LoadErrorMessageTest {
    private val every = listOf(
        LoadError.Network, LoadError.Tls, LoadError.Unauthorized, LoadError.ReadDisabled, LoadError.NotFound,
        LoadError.Blocked(30), LoadError.Blocked(null), LoadError.Server(500), LoadError.BadResponse,
    )

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
