package br.unip.pm25.ui.detail

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class SuspectHoursNoteTest {
    @Test
    fun `diz o que o sensor viu e que a causa nao esta decidida`() {
        assertEquals(
            "Em 3 h o sensor quase não viu partículas, o que pode ser falha dele ou ar muito limpo; " +
                "por precaução, essas horas ficam em branco.",
            suspectHoursNote(3),
        )
    }

    @Test
    fun `nao afirma o que o ar faz`() {
        assertFalse(suspectHoursNote(1).contains("o que o ar não faz"))
    }
}
