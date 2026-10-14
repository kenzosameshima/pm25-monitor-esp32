package br.unip.pm25.data

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class LocalNetworkTest {
    @Test
    fun `enderecos privados e o computador visto do emulador sao rede local`() {
        listOf("10.0.2.2", "192.168.0.10", "172.16.5.1", "172.31.255.255", "169.254.1.1", "servidor.local",
            "fd12:3456::1", "[fe80::1]").forEach { assertTrue(it, isLocalNetworkHost(it)) }
    }

    @Test
    fun `internet, loopback e enderecos invalidos nao sao`() {
        listOf("maquina.tailnet.ts.net", "8.8.8.8", "172.32.0.1", "127.0.0.1", "localhost", "::1",
            "10.0.2", "300.1.1.1", "").forEach { assertFalse(it, isLocalNetworkHost(it)) }
    }
}
