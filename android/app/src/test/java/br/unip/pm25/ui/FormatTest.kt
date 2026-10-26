package br.unip.pm25.ui

import org.junit.Assert.assertEquals
import org.junit.Test

class FormatTest {
    @Test
    fun `valor com unidade usa virgula e a unidade depois de um espaco`() {
        assertEquals("23,5 °C", 23.46.formatWith("°C"))
        assertEquals("40,2 µg/m³", 40.2.formatWith("µg/m³"))
    }

    @Test
    fun `percentual sem casas decimais cola o simbolo`() {
        assertEquals("64%", 64.0.formatWith("%", decimals = 0, gap = ""))
    }

    @Test
    fun `sem valor mostra so o traco, sem a unidade`() {
        val none: Double? = null
        assertEquals("—", none.formatWith("°C"))
        assertEquals("—", none.formatWith("%", decimals = 0, gap = ""))
        assertEquals(NO_VALUE, none.format())
    }
}
