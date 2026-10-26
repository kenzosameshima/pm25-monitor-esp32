package br.unip.pm25.ui

import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.hasContentDescription
import androidx.compose.ui.test.hasScrollAction
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.performScrollToNode
import br.unip.pm25.data.Health
import br.unip.pm25.data.HourlyPoint
import br.unip.pm25.data.HourlySeries
import br.unip.pm25.ui.detail.DetailData
import br.unip.pm25.ui.detail.DetailScreen
import br.unip.pm25.ui.detail.DetailUiState
import br.unip.pm25.ui.theme.Pm25Theme
import org.junit.Rule
import org.junit.Test
import java.time.Instant

/** A tela de detalhe como um leitor de tela a encontra, e o aviso das horas suspeitas. */
class DetailScreenTest {
    @get:Rule
    val compose = createComposeRule()

    private val now = Instant.parse("2026-10-26T06:00:00Z")
    private val isHeading = SemanticsMatcher.keyIsDefined(SemanticsProperties.Heading)

    private fun hour(i: Int, pm25: Double?, suspect: Boolean = false) = HourlyPoint(
        hour = now.minusSeconds(3600L * (3 - i)), readings = 60, valid = pm25 != null && !suspect,
        pm25 = pm25, suspect = suspect,
    )

    private fun show(vararg hours: HourlyPoint) {
        val start = now.minusSeconds(3 * 3600)
        val series = HourlySeries(now, "no-01", start, now, 45, hours.toList())
        val health = Health(now, "no-01", start, now, 0.9, 5, 0, 0, 0, 0)
        compose.setContent {
            Pm25Theme {
                DetailScreen(DetailUiState(data = DetailData(series, health, now)), "no-01", "EE Exemplo",
                    onBack = {}, onRefresh = {}, onSelectRange = {}, onOpenForecast = {})
            }
        }
    }

    private fun scrollTo(matcher: SemanticsMatcher) {
        compose.onAllNodes(hasScrollAction()).onFirst().performScrollToNode(matcher)
    }

    @Test
    fun titulosDosCartoesSaoCabecalhos() {
        show(hour(0, 20.0), hour(1, 30.0))
        compose.onNode(hasText("PM2,5 por hora (µg/m³)") and isHeading).assertExists()
        scrollTo(hasText("Saúde da coleta", substring = true))
        compose.onNode(hasText("Saúde da coleta", substring = true) and isHeading).assertExists()
    }

    @Test
    fun graficoTemDescricaoComMediaEMaxima() {
        show(hour(0, 20.0), hour(1, 30.0))
        compose.onNode(hasContentDescription("média 25,0, máxima 30,0", substring = true)).assertExists()
    }

    @Test
    fun horaSuspeitaFicaForaEOAvisoDizQuantasForam() {
        show(hour(0, 20.0), hour(1, null, suspect = true), hour(2, 30.0))
        compose.onNode(hasText("Em 1 h o sensor quase não viu partículas", substring = true)).assertExists()
        // a hora suspeita não entra na média: só 20 e 30
        compose.onNode(hasContentDescription("média 25,0, máxima 30,0", substring = true)).assertExists()
    }

    @Test
    fun semHoraSuspeitaNaoHaAviso() {
        show(hour(0, 20.0), hour(1, 30.0))
        compose.onNode(hasText("quase não viu partículas", substring = true)).assertDoesNotExist()
    }
}
