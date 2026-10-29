package br.unip.pm25.ui.home

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.onClick as semanticsOnClick
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.repeatOnLifecycle
import br.unip.pm25.data.DeviceList
import br.unip.pm25.data.DeviceState
import br.unip.pm25.data.DeviceStatus
import br.unip.pm25.data.LatestReading
import br.unip.pm25.data.LoadError
import br.unip.pm25.data.Timed
import br.unip.pm25.domain.AirQuality
import br.unip.pm25.domain.currentStatus
import br.unip.pm25.domain.estimatedServerNow
import br.unip.pm25.domain.formatAge
import br.unip.pm25.domain.hasCurrentValue
import br.unip.pm25.domain.readingAge
import br.unip.pm25.ui.AlertsCard
import br.unip.pm25.ui.ErrorPanel
import br.unip.pm25.ui.Metric
import br.unip.pm25.ui.MetricRow
import br.unip.pm25.ui.NO_VALUE
import br.unip.pm25.ui.QualityChip
import br.unip.pm25.ui.StaleBanner
import br.unip.pm25.ui.rememberAlertsPrompt
import br.unip.pm25.ui.format
import br.unip.pm25.ui.formatMoment
import br.unip.pm25.ui.formatWith
import br.unip.pm25.ui.theme.Pm25Theme
import kotlinx.coroutines.delay
import java.time.Instant

/** Os nós fecham uma leitura por minuto; consultar mais vezes que isso não traz dado novo. */
private const val REFRESH_INTERVAL_MS = 60_000L

/** Tela inicial ligada ao ViewModel: atualiza ao abrir e a cada minuto enquanto estiver visível. */
@Composable
fun HomeRoute(viewModel: HomeViewModel, onOpenDevice: (DeviceState) -> Unit) {
    val state by viewModel.state.collectAsStateWithLifecycle()
    val lifecycleOwner = LocalLifecycleOwner.current
    LaunchedEffect(lifecycleOwner) {
        lifecycleOwner.repeatOnLifecycle(Lifecycle.State.STARTED) {
            while (true) {
                viewModel.refresh()
                delay(REFRESH_INTERVAL_MS)
            }
        }
    }
    val alerts = rememberAlertsPrompt()
    HomeScreen(state, onRefresh = viewModel::refresh, onOpenDevice = onOpenDevice,
        header = if (alerts.visible) ({ AlertsCard(alerts) }) else null)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(
    state: HomeUiState,
    onRefresh: () -> Unit,
    onOpenDevice: (DeviceState) -> Unit,
    modifier: Modifier = Modifier,
    /** Primeiro item da lista, acima dos sensores (o cartão dos alertas, quando eles estão desligados). */
    header: (@Composable () -> Unit)? = null,
) {
    Scaffold(modifier = modifier, topBar = { TopAppBar(title = { Text("Qualidade do ar") }) }) { padding ->
        PullToRefreshBox(
            isRefreshing = state.loading && state.data != null,
            onRefresh = onRefresh,
            modifier = Modifier.padding(padding).fillMaxSize(),
        ) {
            val data = state.data
            when {
                data != null -> DeviceListContent(data, state.error, onOpenDevice, header)
                state.error != null -> ErrorPanel(state.error, onRefresh)
                else -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
            }
        }
    }
}

@Composable
private fun DeviceListContent(
    timed: Timed<DeviceList>,
    error: LoadError?,
    onOpenDevice: (DeviceState) -> Unit,
    header: (@Composable () -> Unit)?,
) {
    val data = timed.value
    // Idades medidas pela hora estimada do servidor agora: um dado salvo ontem não parece recente.
    val serverNow = estimatedServerNow(data.generatedAt, timed.receivedAt, Instant.now())
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        if (header != null) item { header() }
        if (error != null) {
            item { StaleBanner(error, data.generatedAt) }
        } else {
            item {
                Text("Atualizado: ${formatMoment(data.generatedAt)}", style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        if (data.devices.isEmpty()) {
            item { Text("Nenhum sensor enviou leituras ainda.") }
        }
        items(data.devices, key = { it.deviceId }) { device ->
            DeviceCard(device, currentStatus(device, data, serverNow), serverNow, onClick = { onOpenDevice(device) })
        }
        item {
            Text(
                "As cores seguem as faixas da CETESB para o PM2,5, definidas para a média de 24 horas; " +
                    "aqui servem de referência para a leitura de um minuto. Toque num sensor para ver o histórico.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun DeviceCard(device: DeviceState, status: DeviceStatus, serverNow: Instant, onClick: () -> Unit) {
    // O rótulo diz ao leitor de tela o que o toque faz; a ação continua sendo a do próprio cartão.
    val opens = Modifier.semantics { semanticsOnClick(label = "Ver o histórico de ${device.deviceId}", action = null) }
    Card(onClick = onClick, modifier = Modifier.fillMaxWidth().then(opens)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                StatusDot(status)
                Spacer(Modifier.width(8.dp))
                Text(device.deviceId, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.weight(1f))
                Text(status.label(), style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            device.location?.let {
                Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            val latest = device.latest
            when {
                latest == null -> Text("Sem leituras.")
                hasCurrentValue(status) -> LatestReadingContent(latest, serverNow)
                else -> NoRecentDataContent(latest, serverNow)
            }
        }
    }
}

/**
 * Nó sem dados recentes: o valor fica vazio e sem faixa, para a última leitura (um sensor parado em zero
 * aparece como "Boa") não parecer o ar de agora. Ela continua a um toque, dita como histórico.
 */
@Composable
private fun NoRecentDataContent(latest: LatestReading, serverNow: Instant) {
    var showLast by rememberSaveable { mutableStateOf(false) }
    Text(NO_VALUE, style = MaterialTheme.typography.displaySmall,
        modifier = Modifier.clearAndSetSemantics { contentDescription = "PM2,5: sem dados recentes" })
    Text("PM2,5 · última leitura ${formatAge(readingAge(latest.ts, serverNow))}",
        style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    TextButton(onClick = { showLast = !showLast }) {
        Text(if (showLast) "Ocultar a última leitura" else "Ver a última leitura")
    }
    if (showLast) {
        Text(historicalReadingText(latest, formatMoment(latest.ts)),
            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

/** A faixa vai para a linha de baixo quando a fonte grande não deixa o valor e ela lado a lado, em vez de ser espremida. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun LatestReadingContent(latest: LatestReading, serverNow: Instant) {
    FlowRow(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalArrangement = Arrangement.spacedBy(8.dp),
        itemVerticalAlignment = Alignment.CenterVertically,
    ) {
        Column {
            Row(verticalAlignment = Alignment.Bottom) {
                Text(latest.pm25.format(), style = MaterialTheme.typography.displaySmall)
                if (latest.pm25 != null) {
                    Text(" µg/m³", style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(bottom = 6.dp))
                }
            }
            Text("PM2,5 · leitura ${formatAge(readingAge(latest.ts, serverNow))}",
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        AirQuality.of(latest.pm25)?.let { QualityChip(it) }
    }
    MetricRow {
        Metric("Temperatura", latest.temperature.formatWith("°C"))
        Metric("Umidade", latest.humidity.formatWith("%", decimals = 0, gap = ""))
        Metric("PM10", latest.pm10.formatWith("µg/m³"))
    }
    if (latest.quality != "ok") {
        Text("O servidor marcou esta leitura como implausível (${latest.quality}).",
            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
    }
}

@Composable
private fun StatusDot(status: DeviceStatus) {
    val color = when (status) {
        DeviceStatus.ONLINE -> Color(0xFF2E7D32)
        DeviceStatus.LATE -> Color(0xFFF9A825)
        DeviceStatus.SILENT -> MaterialTheme.colorScheme.error
    }
    Box(Modifier.size(10.dp).background(color, CircleShape))
}

private fun DeviceStatus.label() = when (this) {
    DeviceStatus.ONLINE -> "Em operação"
    DeviceStatus.LATE -> "Atrasado"
    DeviceStatus.SILENT -> "Sem dados"
}

@Preview(showBackground = true)
@Preview(showBackground = true, fontScale = 2f, name = "Fonte 200%")
@Composable
private fun HomeScreenPreview() {
    val now = Instant.parse("2026-10-14T12:00:00Z")
    val reading = LatestReading(ts = now.minusSeconds(120), pm25 = 31.4, pm10 = 40.2, temperature = 23.5, humidity = 64.0)
    val data = DeviceList(
        generatedAt = now, lateAfterMin = 3, silentAfterMin = 15,
        devices = listOf(
            DeviceState("no-01", "EE Exemplo, Vila Mariana", DeviceStatus.ONLINE, 1.0, now.minusSeconds(60), reading),
            DeviceState("no-02", null, DeviceStatus.SILENT, 42.0, now.minusSeconds(2520), reading.copy(pm25 = 12.0)),
        ),
    )
    Pm25Theme { HomeScreen(HomeUiState(data = Timed(data, now)), onRefresh = {}, onOpenDevice = {}) }
}
