package br.unip.pm25.ui

import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.performSemanticsAction
import br.unip.pm25.data.DeviceList
import br.unip.pm25.data.DeviceState
import br.unip.pm25.data.DeviceStatus
import br.unip.pm25.data.LatestReading
import br.unip.pm25.data.Timed
import br.unip.pm25.ui.home.HomeScreen
import br.unip.pm25.ui.home.HomeUiState
import br.unip.pm25.ui.theme.Pm25Theme
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import java.time.Instant

/** O que um leitor de tela encontra na tela inicial: as árvores de semântica que o TalkBack percorre. */
class HomeScreenTest {
    @get:Rule
    val compose = createComposeRule()

    private val now = Instant.now()
    private val opened = mutableListOf<String>()

    @Before
    fun show() {
        val full = LatestReading(ts = now.minusSeconds(120), pm25 = 31.4, pm10 = 40.2, temperature = 23.5, humidity = 64.0)
        val sparse = LatestReading(ts = now.minusSeconds(120), pm25 = 12.0)  // sem temperatura, umidade nem PM10
        val list = DeviceList(
            generatedAt = now, lateAfterMin = 3, silentAfterMin = 15,
            devices = listOf(
                DeviceState("no-01", "EE Exemplo", DeviceStatus.ONLINE, 1.0, now.minusSeconds(60), full),
                DeviceState("no-02", null, DeviceStatus.ONLINE, 1.0, now.minusSeconds(60), sparse),
            ),
        )
        compose.setContent {
            Pm25Theme {
                HomeScreen(HomeUiState(data = Timed(list, now)), onRefresh = {}, onOpenDevice = { opened += it.deviceId })
            }
        }
    }

    private fun hasTapLabel(label: String) = SemanticsMatcher("rótulo do toque \"$label\"") {
        it.config.getOrNull(SemanticsActions.OnClick)?.label == label
    }

    @Test
    fun valorAusenteELidoComoSemDado() {
        compose.onNodeWithContentDescription("Temperatura: sem dado").assertExists()
        compose.onNodeWithContentDescription("Umidade: sem dado").assertExists()
        compose.onNodeWithContentDescription("PM10: sem dado").assertExists()
    }

    @Test
    fun rotuloEValorSaoLidosJuntos() {
        compose.onNode(hasText("Temperatura") and hasText("23,5 °C")).assertExists()
        compose.onNode(hasText("PM10") and hasText("40,2 µg/m³")).assertExists()
    }

    @Test
    fun cartaoDizOQueOToqueFazEAAcaoContinuaAbrindoONo() {
        // performSemanticsAction é o que o TalkBack aciona; falharia se o rótulo tivesse apagado a ação do cartão
        compose.onNode(hasTapLabel("Ver o histórico de no-01")).assertExists()
            .performSemanticsAction(SemanticsActions.OnClick)
        assertEquals(listOf("no-01"), opened)
    }
}
