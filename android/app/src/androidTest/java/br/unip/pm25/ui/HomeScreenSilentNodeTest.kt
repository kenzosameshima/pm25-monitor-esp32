package br.unip.pm25.ui

import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.performClick
import br.unip.pm25.data.DeviceList
import br.unip.pm25.data.DeviceState
import br.unip.pm25.data.DeviceStatus
import br.unip.pm25.data.LatestReading
import br.unip.pm25.data.Timed
import br.unip.pm25.ui.home.HomeScreen
import br.unip.pm25.ui.home.HomeUiState
import br.unip.pm25.ui.theme.Pm25Theme
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import java.time.Duration
import java.time.Instant

/** O cartão de um nó sem dados: a última leitura (um sensor parado em zero) não pode parecer o ar de agora. */
class HomeScreenSilentNodeTest {
    @get:Rule
    val compose = createComposeRule()

    private val now = Instant.now()

    @Before
    fun show() {
        val stoppedAt = now.minus(Duration.ofHours(27))
        val stopped = LatestReading(ts = stoppedAt, pm25 = 0.0, pm10 = 0.0, temperature = 22.2, humidity = 54.6, rssi = -53)
        val list = DeviceList(
            generatedAt = now, lateAfterMin = 3, silentAfterMin = 15,
            devices = listOf(DeviceState("no-02", null, DeviceStatus.SILENT, 0.0, stoppedAt, stopped)),
        )
        compose.setContent {
            Pm25Theme { HomeScreen(HomeUiState(data = Timed(list, now)), onRefresh = {}, onOpenDevice = {}) }
        }
    }

    @Test
    fun semDadosNaoMostraValorNemFaixa() {
        compose.onNodeWithContentDescription("PM2,5: sem dados recentes").assertExists()
        compose.onNode(hasText("0,0", substring = true)).assertDoesNotExist()
        compose.onNode(hasText("Boa")).assertDoesNotExist()
    }

    @Test
    fun ultimaLeituraFicaAUmToqueDitaComoHistorico() {
        compose.onNode(hasText("Ver a última leitura")).performClick()
        compose.onNode(hasText("histórico (não é o valor atual)", substring = true)).assertExists()
        compose.onNode(hasText("Ocultar a última leitura")).assertExists()
    }
}
