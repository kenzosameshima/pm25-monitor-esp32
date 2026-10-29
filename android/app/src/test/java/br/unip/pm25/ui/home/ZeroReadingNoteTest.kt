package br.unip.pm25.ui.home

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class ZeroReadingNoteTest {
    @Test
    fun `diz o que chegou, que o sensor pode nao ver particulas e por que nao ha faixa`() {
        assertEquals(
            "Leitura zerada (PM1, PM2,5 e PM10 em 0,0): o sensor pode não estar vendo partículas. " +
                "Por isso o cartão fica sem faixa de qualidade do ar.",
            ZERO_READING_NOTE,
        )
    }

    @Test
    fun `nao afirma que o ar esta limpo`() {
        assertFalse(ZERO_READING_NOTE.contains("Boa"))
        assertFalse(ZERO_READING_NOTE.contains("limpo"))
    }
}
