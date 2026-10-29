package br.unip.pm25.ui.detail

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
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import br.unip.pm25.R
import br.unip.pm25.data.Health
import br.unip.pm25.data.HourlyPoint
import br.unip.pm25.data.HourlySeries
import br.unip.pm25.domain.HIGH_HUMIDITY
import br.unip.pm25.domain.summarize
import br.unip.pm25.ui.CLOCK
import br.unip.pm25.ui.DAY_CLOCK
import br.unip.pm25.ui.ErrorMessage
import br.unip.pm25.ui.Metric
import br.unip.pm25.ui.MetricRow
import br.unip.pm25.ui.NO_VALUE
import br.unip.pm25.ui.StaleBanner
import br.unip.pm25.ui.asHeading
import br.unip.pm25.ui.format
import br.unip.pm25.ui.theme.Pm25Theme
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private val DATE = DateTimeFormatter.ofPattern("dd/MM").withZone(ZoneId.systemDefault())

@Composable
fun DetailRoute(
    viewModel: DetailViewModel,
    deviceId: String,
    location: String?,
    onBack: () -> Unit,
    onOpenForecast: () -> Unit,
) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    DetailScreen(state, deviceId, location, onBack = onBack, onRefresh = viewModel::refresh,
        onSelectRange = viewModel::select, onOpenForecast = onOpenForecast)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DetailScreen(
    state: DetailUiState,
    deviceId: String,
    location: String?,
    onBack: () -> Unit,
    onRefresh: () -> Unit,
    onSelectRange: (HistoryRange) -> Unit,
    onOpenForecast: () -> Unit,
) {
    Scaffold(topBar = {
        TopAppBar(
            title = { Text(deviceId) },
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
                location?.let {
                    item { Text(it, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant) }
                }
                item { RangeSelector(state.range, onSelectRange) }
                val data = state.data
                when {
                    data != null -> {
                        state.error?.let { error -> item { StaleBanner(error, data.series.generatedAt) } }
                        item { HistoryCard(data.series, state.range) }
                        item {
                            FilledTonalButton(onClick = onOpenForecast, modifier = Modifier.fillMaxWidth()) {
                                Text("Previsão: previsto × observado")
                            }
                        }
                        item { HealthCard(data.health, state.range) }
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

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun RangeSelector(selected: HistoryRange, onSelect: (HistoryRange) -> Unit) {
    SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
        HistoryRange.entries.forEachIndexed { i, range ->
            SegmentedButton(
                selected = range == selected,
                onClick = { onSelect(range) },
                shape = SegmentedButtonDefaults.itemShape(i, HistoryRange.entries.size),
            ) { Text(range.label) }
        }
    }
}

@Composable
private fun HistoryCard(series: HourlySeries, range: HistoryRange) {
    val summary = summarize(series.hours)
    val timeFormat = if (range == HistoryRange.DAY) CLOCK else DATE
    val description = historyDescription(range.label, summary)
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("PM2,5 por hora (µg/m³)", style = MaterialTheme.typography.titleMedium, modifier = Modifier.asHeading())
            HourlyChart(series.hours.map { it.hour },
                listOf(ChartSeries("PM2,5", series.hours.map { if (it.valid) it.pm25 else null },
                    MaterialTheme.colorScheme.primary)),
                timeFormat, description)
            MetricRow {
                Metric("Média", summary.mean.format())
                Metric("Máxima", summary.max?.let { "${it.pm25.format()} às ${DAY_CLOCK.format(it.hour)}" } ?: NO_VALUE)
            }
            MetricRow {
                Metric("Horas válidas", "${summary.validHours} de ${summary.totalHours}")
                Metric("Acima de 25 µg/m³", "${summary.hoursAboveGood} h")
            }
            Text(
                "Horas com menos de ${series.minReadings} leituras de um minuto ficam em branco. A linha " +
                    "tracejada é o limite da faixa Boa da CETESB (25 µg/m³, para a média de 24 horas).",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            blankHoursNote(summary)?.let {
                Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            if (summary.suspectHours > 0) {
                Text(
                    suspectHoursNote(summary.suspectHours),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.tertiary,
                )
            }
            if (summary.humidHours > 0) {
                Text(
                    "Em ${summary.humidHours} h a umidade média passou de ${HIGH_HUMIDITY.format(0)}%: " +
                        "nessas horas o sensor tende a superestimar o PM2,5.",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.tertiary,
                )
            }
        }
    }
}

@Composable
private fun HealthCard(health: Health, range: HistoryRange) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("Saúde da coleta (${range.label})", style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.asHeading())
            Row(horizontalArrangement = Arrangement.spacedBy(24.dp)) {
                Metric("Completude", "${(health.completeness * 100).format(0)}%", Modifier.weight(1f))
                Metric("Maior lacuna", "${health.largestGapMin} min", Modifier.weight(1f))
                Metric("Reinícios", "${health.restarts}", Modifier.weight(1f))
            }
            Row(horizontalArrangement = Arrangement.spacedBy(24.dp)) {
                Metric("Mensagens perdidas", "${health.lostMessages}", Modifier.weight(1f))
                Metric("Duplicatas descartadas", "${health.duplicatesDiscarded}", Modifier.weight(1f))
                Metric("Leituras marcadas", "${health.flaggedReadings}", Modifier.weight(1f))
            }
            Text(
                "Mensagens perdidas são saltos na sequência de uma mesma inicialização do sensor. Duplicatas " +
                    "são reenvios que o servidor reconheceu e descartou: o sensor reenvia o que não teve " +
                    "confirmação, e nada é gravado duas vezes.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Preview(showBackground = true)
@Preview(showBackground = true, fontScale = 2f, name = "Fonte 200%")
@Composable
private fun DetailScreenPreview() {
    val end = Instant.parse("2026-10-14T12:00:00Z")
    val hours = (0 until 24).map { i ->
        val suspect = i == 14
        val valid = i !in 9..11 && !suspect
        HourlyPoint(end.minusSeconds(3600L * (24 - i)), if (i in 9..11) 20 else 60, valid,
            pm25 = if (valid) 12.0 + (i % 8) * 3 else null, humidity = if (valid) 60.0 + i else null,
            suspect = suspect)
    }
    val series = HourlySeries(end, "no-01", end.minusSeconds(86_400), end, 45, hours)
    val health = Health(end, "no-01", end.minusSeconds(86_400), end, 0.87, 182, 3, 1, 12, 0)
    Pm25Theme {
        DetailScreen(DetailUiState(data = DetailData(series, health, end)), "no-01", "EE Exemplo, Vila Mariana",
            onBack = {}, onRefresh = {}, onSelectRange = {}, onOpenForecast = {})
    }
}
