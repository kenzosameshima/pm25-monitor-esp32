package br.unip.pm25.ui.forecast

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import br.unip.pm25.R
import br.unip.pm25.data.ForecastHour
import br.unip.pm25.data.ForecastResponse
import br.unip.pm25.data.PredictorScore
import br.unip.pm25.domain.AirQuality
import br.unip.pm25.domain.PERSISTENCE
import br.unip.pm25.domain.pendingHour
import br.unip.pm25.domain.predictorLabel
import br.unip.pm25.domain.skillVerdict
import br.unip.pm25.ui.CLOCK
import br.unip.pm25.ui.DAY_CLOCK
import br.unip.pm25.ui.ErrorMessage
import br.unip.pm25.ui.Metric
import br.unip.pm25.ui.QualityChip
import br.unip.pm25.ui.StaleBanner
import br.unip.pm25.ui.detail.ChartLegend
import br.unip.pm25.ui.detail.ChartSeries
import br.unip.pm25.ui.detail.HourlyChart
import br.unip.pm25.ui.format
import br.unip.pm25.ui.theme.Pm25Theme
import java.time.Instant

@Composable
fun ForecastRoute(viewModel: ForecastViewModel, deviceId: String, onBack: () -> Unit) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    ForecastScreen(state, deviceId, onBack = onBack, onRefresh = viewModel::refresh)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ForecastScreen(state: ForecastUiState, deviceId: String, onBack: () -> Unit, onRefresh: () -> Unit) {
    Scaffold(topBar = {
        TopAppBar(
            title = { Text("Previsão · $deviceId") },
            navigationIcon = {
                IconButton(onClick = onBack) { Icon(painterResource(R.drawable.ic_arrow_back), contentDescription = "Voltar") }
            },
        )
    }) { padding ->
        PullToRefreshBox(
            isRefreshing = state.loading && state.data != null,
            onRefresh = onRefresh,
            modifier = Modifier.padding(padding).fillMaxSize(),
        ) {
            LazyColumn(
                modifier = Modifier.fillMaxSize(),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                val data = state.data
                when {
                    data != null -> {
                        state.error?.let { error -> item { StaleBanner(error, data.generatedAt) } }
                        item { PendingHourCard(data) }
                        item { ComparisonCard(data) }
                        item { ScoresCard(data.scores) }
                    }
                    state.error != null -> item { ErrorMessage(state.error, onRefresh, Modifier.fillMaxWidth()) }
                    else -> item {
                        Box(Modifier.fillMaxWidth().padding(48.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
                    }
                }
            }
        }
    }
}

/** Cores dos previsores: a persistência em cinza; os modelos em cores fortes, na ordem da resposta. */
@Composable
private fun predictorColors(predictors: List<String>): Map<String, Color> {
    val palette = listOf(MaterialTheme.colorScheme.tertiary, Color(0xFF8E24AA), Color(0xFF00897B), Color(0xFFD81B60))
    var next = 0
    return predictors.associateWith {
        if (it == PERSISTENCE) MaterialTheme.colorScheme.outline else palette[next++ % palette.size]
    }
}

@Composable
private fun PendingHourCard(data: ForecastResponse) {
    val pending = pendingHour(data)
    val models = data.predictors.filter { it != PERSISTENCE }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("Hora em andamento", style = MaterialTheme.typography.titleMedium)
            if (pending == null) {
                Text("A resposta não trouxe a hora atual.", style = MaterialTheme.typography.bodyMedium)
            } else {
                val end = pending.hour.plusSeconds(3600)
                Text("Média prevista de ${CLOCK.format(pending.hour)} às ${CLOCK.format(end)}; a observada só fecha às ${CLOCK.format(end)}.",
                    style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                data.predictors.forEach { p -> PredictionRow(predictorLabel(p), pending.predictions[p]) }
            }
            if (models.isEmpty()) {
                Text(
                    "Nenhum modelo publicou previsões ainda; até o job horário gravar na tabela forecasts, " +
                        "só aparece a persistência, que repete a média da hora anterior.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun PredictionRow(label: String, value: Double?) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        Text(label, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.weight(1f))
        Text("${value.format()} µg/m³", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
        AirQuality.of(value)?.let {
            Box(Modifier.padding(start = 12.dp)) { QualityChip(it) }
        }
    }
}

@Composable
private fun ComparisonCard(data: ForecastResponse) {
    val colors = predictorColors(data.predictors)
    val series = listOf(ChartSeries("Observado", data.hours.map { it.observed }, MaterialTheme.colorScheme.primary)) +
        data.predictors.map { p ->
            ChartSeries(predictorLabel(p), data.hours.map { it.predictions[p] }, colors.getValue(p), dashed = true)
        }
    val observedHours = data.hours.count { it.observed != null }
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("Previsto × observado (µg/m³)", style = MaterialTheme.typography.titleMedium)
            HourlyChart(
                hours = data.hours.map { it.hour },
                series = series,
                timeFormat = DAY_CLOCK,  // 48 h cruzam a meia-noite: só a hora seria ambígua
                description = "PM2,5 observado e previsto por hora nas últimas $FORECAST_HOURS horas, " +
                    "com $observedHours horas observadas e ${data.predictors.size} previsores.",
            )
            ChartLegend(series)
            Text(
                "Cada ponto previsto é a previsão feita antes daquela hora começar. Horas sem média válida " +
                    "ficam em branco.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun ScoresCard(scores: List<PredictorScore>) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("Desempenho nas últimas $FORECAST_HOURS horas", style = MaterialTheme.typography.titleMedium)
            if (scores.isEmpty()) {
                Text("Ainda não há horas com observação e previsão para comparar.",
                    style = MaterialTheme.typography.bodyMedium)
            }
            scores.forEachIndexed { i, s ->
                if (i > 0) HorizontalDivider()
                Text(predictorLabel(s.predictor), style = MaterialTheme.typography.titleSmall)
                Row(horizontalArrangement = Arrangement.spacedBy(24.dp)) {
                    Metric("Horas", "${s.hours}", Modifier.weight(1f))
                    Metric("MAE", "${s.mae.format(2)} µg/m³", Modifier.weight(1f))
                    Metric("RMSE", "${s.rmse.format(2)} µg/m³", Modifier.weight(1f))
                }
                val verdict = if (s.predictor == PERSISTENCE) "referência" else skillVerdict(s.skill).text
                Metric("Skill score", "${s.skill.format(2)} · $verdict")
            }
            Text(
                "MAE é o erro médio e RMSE pesa mais os erros grandes. O skill score compara o RMSE de cada " +
                    "previsor com o da persistência nas mesmas horas: acima de zero, o modelo acerta mais que " +
                    "simplesmente repetir a hora anterior.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun ForecastScreenPreview() {
    val now = Instant.parse("2026-10-14T12:40:00Z")
    val hour = Instant.parse("2026-10-14T12:00:00Z")
    val hours = (0..48).map { i ->
        val h = hour.minusSeconds(3600L * (47 - i))
        val observed = if (i < 47) 14.0 + (i % 9) * 2 else null
        ForecastHour(h, observed, mapOf(PERSISTENCE to 13.0 + ((i + 8) % 9) * 2, "ridge v1" to 14.5 + (i % 9) * 1.8))
    }
    val data = ForecastResponse(now, "no-01", listOf(PERSISTENCE, "ridge v1"), hours,
        listOf(PredictorScore(PERSISTENCE, 46, 5.3, 6.1, 0.0), PredictorScore("ridge v1", 46, 1.2, 1.6, 0.74)))
    Pm25Theme { ForecastScreen(ForecastUiState(data = data), "no-01", onBack = {}, onRefresh = {}) }
}
