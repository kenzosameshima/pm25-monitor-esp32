package br.unip.pm25.ui

import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.hasContentDescription
import androidx.compose.ui.test.hasScrollAction
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.performScrollToNode
import br.unip.pm25.data.ForecastHour
import br.unip.pm25.data.ForecastResponse
import br.unip.pm25.data.PredictorScore
import br.unip.pm25.data.Timed
import br.unip.pm25.domain.PERSISTENCE
import br.unip.pm25.ui.forecast.ForecastScreen
import br.unip.pm25.ui.forecast.ForecastUiState
import br.unip.pm25.ui.theme.Pm25Theme
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import java.time.Instant

/** A tela de previsão como um leitor de tela a encontra. */
class ForecastScreenTest {
    @get:Rule
    val compose = createComposeRule()

    private val isHeading = SemanticsMatcher.keyIsDefined(SemanticsProperties.Heading)

    @Before
    fun show() {
        val now = Instant.parse("2026-10-14T12:40:00Z")
        val hour = Instant.parse("2026-10-14T10:00:00Z")
        val hours = listOf(
            ForecastHour(hour, 10.0, mapOf(PERSISTENCE to null, "ridge v1" to null)),
            ForecastHour(hour.plusSeconds(3600), 20.0, mapOf(PERSISTENCE to 10.0, "ridge v1" to 18.0)),
            ForecastHour(hour.plusSeconds(7200), null, mapOf(PERSISTENCE to 20.0, "ridge v1" to 19.0)),
        )
        val forecast = ForecastResponse(
            now, "no-01", listOf(PERSISTENCE, "ridge v1"), hours,
            listOf(PredictorScore(PERSISTENCE, 1, 10.0, 10.0, 0.0), PredictorScore("ridge v1", 1, 2.0, 2.0, 0.8)),
        )
        compose.setContent {
            Pm25Theme { ForecastScreen(ForecastUiState(data = Timed(forecast, now)), "no-01", onBack = {}, onRefresh = {}) }
        }
    }

    @Test
    fun titulosDosCartoesSaoCabecalhos() {
        compose.onNode(hasText("Hora em andamento") and isHeading).assertExists()
        compose.onNode(hasText("Previsto × observado", substring = true) and isHeading).assertExists()
        compose.onAllNodes(hasScrollAction()).onFirst().performScrollToNode(hasText("Desempenho nas últimas", substring = true))
        compose.onNode(hasText("Desempenho nas últimas", substring = true) and isHeading).assertExists()
    }

    @Test
    fun graficoDizOsValoresDeCadaSerie() {
        // observado 10 e 20; persistência 10 e 20; ridge 18 e 19
        compose.onNode(hasContentDescription("Observado: 2 horas, média 15,0, máxima 20,0.", substring = true)).assertExists()
        compose.onNode(hasContentDescription("ridge v1: 2 horas, média 18,5, máxima 19,0.", substring = true)).assertExists()
    }
}
