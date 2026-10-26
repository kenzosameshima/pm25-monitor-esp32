package br.unip.pm25.alerts

import org.junit.Assert.assertEquals
import org.junit.Test

/** Quando uma consulta que falhou pode virar o alerta de servidor fora do ar. */
class ServerFailureGateTest {
    /** O resultado e quantas vezes a rede do celular foi consultada. */
    private fun gate(apiUrl: String, validated: Boolean): Pair<Boolean, Int> {
        var asked = 0
        val result = failuresTellAboutServer(apiUrl) { asked++; validated }
        return result to asked
    }

    @Test
    fun `servidor na rede local basta a conexao do WorkManager e nao consulta a rede do celular`() {
        assertEquals(true to 0, gate("http://10.0.2.2:8000/", validated = false))
        assertEquals(true to 0, gate("https://servidor.local/", validated = false))
    }

    @Test
    fun `servidor pela internet so conta com a rede do celular validada`() {
        assertEquals(true to 1, gate("https://pm25.exemplo.ts.net/", validated = true))
        assertEquals(false to 1, gate("https://pm25.exemplo.ts.net/", validated = false))
    }

    @Test
    fun `endereco ilegivel e tratado como internet`() {
        assertEquals(false to 1, gate("isto nao e uma url", validated = false))
    }
}
