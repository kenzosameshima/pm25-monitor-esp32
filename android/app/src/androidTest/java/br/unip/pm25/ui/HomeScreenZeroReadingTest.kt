package br.unip.pm25.ui

import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createComposeRule
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

/** O cartão de um nó em operação que envia tudo em zero: mostra o que chegou, mas sem a faixa "Boa". */
class HomeScreenZeroReadingTest {
    @get:Rule
    val compose = createComposeRule()

    private val now = Instant.now()

    @Before
    fun show() {
        val sentAt = now.minus(Duration.ofMinutes(2))
        val zeroed = LatestReading(ts = sentAt, pm1 = 0.0, pm25 = 0.0, pm10 = 0.0, temperature = 22.2, humidity = 54.6)
        val list = DeviceList(
            generatedAt = now, lateAfterMin = 3, silentAfterMin = 15,
            devices = listOf(DeviceState("no-02", null, DeviceStatus.ONLINE, 1.0, sentAt, zeroed)),
        )
        compose.setContent {
            Pm25Theme { HomeScreen(HomeUiState(data = Timed(list, now)), onRefresh = {}, onOpenDevice = {}) }
        }
    }

    @Test
    fun mostraOValorEOAvisoMasNaoAFaixa() {
        compose.onNode(hasText("0,0")).assertExists()
        compose.onNode(hasText("Leitura zerada", substring = true)).assertExists()
        compose.onNode(hasText("Boa")).assertDoesNotExist()
    }
}
