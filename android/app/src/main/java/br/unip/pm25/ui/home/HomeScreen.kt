package br.unip.pm25.ui.home

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
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
import br.unip.pm25.domain.AirQuality
import br.unip.pm25.domain.formatAge
import br.unip.pm25.domain.readingAge
import br.unip.pm25.ui.theme.Pm25Theme
import br.unip.pm25.ui.theme.color
import br.unip.pm25.ui.theme.onColor
import kotlinx.coroutines.delay
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

/** Os nós fecham uma leitura por minuto; consultar mais vezes que isso não traz dado novo. */
private const val REFRESH_INTERVAL_MS = 60_000L
private val PT_BR: Locale = Locale.forLanguageTag("pt-BR")
private val CLOCK = DateTimeFormatter.ofPattern("HH:mm").withZone(ZoneId.systemDefault())

/** Tela inicial ligada ao ViewModel: atualiza ao abrir e a cada minuto enquanto estiver visível. */
@Composable
fun HomeRoute(viewModel: HomeViewModel) {
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
    HomeScreen(state, onRefresh = viewModel::refresh)
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(state: HomeUiState, onRefresh: () -> Unit, modifier: Modifier = Modifier) {
    Scaffold(modifier = modifier, topBar = { TopAppBar(title = { Text("Qualidade do ar") }) }) { padding ->
        PullToRefreshBox(
            isRefreshing = state.loading && state.data != null,
            onRefresh = onRefresh,
            modifier = Modifier.padding(padding).fillMaxSize(),
        ) {
            val data = state.data
            when {
                data != null -> DeviceListContent(data, state.error)
                state.error != null -> ErrorPanel(state.error, onRefresh)
                else -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { CircularProgressIndicator() }
            }
        }
    }
}

@Composable
private fun DeviceListContent(data: DeviceList, error: LoadError?) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        if (error != null) {
            item { StaleBanner(error, data.generatedAt) }
        } else {
            item {
                Text("Atualizado às ${CLOCK.format(data.generatedAt)}", style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        if (data.devices.isEmpty()) {
            item { Text("Nenhum sensor enviou leituras ainda.") }
        }
        items(data.devices, key = { it.deviceId }) { DeviceCard(it, data.generatedAt) }
        item {
            Text(
                "As cores seguem as faixas da CETESB para o PM2,5, definidas para a média de 24 horas; " +
                    "aqui servem de referência para a leitura de um minuto.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun DeviceCard(device: DeviceState, serverNow: Instant) {
    Card(Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                StatusDot(device.status)
                Spacer(Modifier.width(8.dp))
                Text(device.deviceId, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.weight(1f))
                Text(device.status.label(), style = MaterialTheme.typography.labelMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            device.location?.let {
                Text(it, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            val latest = device.latest
            if (latest == null) Text("Sem leituras.") else LatestReadingContent(latest, serverNow)
        }
    }
}

@Composable
private fun LatestReadingContent(latest: LatestReading, serverNow: Instant) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Column {
            Row(verticalAlignment = Alignment.Bottom) {
                Text(latest.pm25.format(), style = MaterialTheme.typography.displaySmall)
                Text(" µg/m³", style = MaterialTheme.typography.bodyMedium, modifier = Modifier.padding(bottom = 6.dp))
            }
            Text("PM2,5 · leitura ${formatAge(readingAge(latest.ts, serverNow))}",
                style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Spacer(Modifier.weight(1f))
        AirQuality.of(latest.pm25)?.let { QualityChip(it) }
    }
    Row(horizontalArrangement = Arrangement.spacedBy(24.dp)) {
        Metric("Temperatura", "${latest.temperature.format()} °C")
        Metric("Umidade", "${latest.humidity.format(0)}%")
        Metric("PM10", "${latest.pm10.format()} µg/m³")
    }
    if (latest.quality != "ok") {
        Text("O servidor marcou esta leitura como implausível (${latest.quality}).",
            style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.error)
    }
}

@Composable
private fun Metric(label: String, value: String) {
    Column {
        Text(label, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
private fun QualityChip(quality: AirQuality) {
    Text(
        quality.label,
        color = quality.onColor(),
        style = MaterialTheme.typography.labelLarge,
        modifier = Modifier
            .background(quality.color(), RoundedCornerShape(50))
            .padding(horizontal = 12.dp, vertical = 6.dp),
    )
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

@Composable
private fun StaleBanner(error: LoadError, lastUpdate: Instant) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer)) {
        Column(Modifier.padding(12.dp)) {
            Text(error.message(), color = MaterialTheme.colorScheme.onErrorContainer)
            Text("Mostrando os dados de ${CLOCK.format(lastUpdate)}.", style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onErrorContainer)
        }
    }
}

@Composable
private fun ErrorPanel(error: LoadError, onRetry: () -> Unit) {
    // Rolável para o gesto de puxar para atualizar também funcionar aqui.
    Column(
        Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp, Alignment.CenterVertically),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(error.message(), style = MaterialTheme.typography.bodyLarge)
        Button(onClick = onRetry) { Text("Tentar de novo") }
    }
}

private fun DeviceStatus.label() = when (this) {
    DeviceStatus.ONLINE -> "Em operação"
    DeviceStatus.LATE -> "Atrasado"
    DeviceStatus.SILENT -> "Sem dados"
}

fun LoadError.message(): String = when (this) {
    LoadError.Network -> "Sem conexão com o servidor. Confira a internet e se a API está no ar."
    LoadError.Unauthorized -> "O servidor recusou o token de leitura. Confira pm25.readToken no local.properties."
    LoadError.ReadDisabled -> "A consulta está desligada no servidor (PM25_READ_TOKEN vazio)."
    is LoadError.Blocked -> "Acesso bloqueado por tentativas inválidas. Tente de novo em " +
        (retryAfterSeconds?.let { "$it s" } ?: "alguns minutos") + "."
    is LoadError.Server -> "O servidor respondeu com erro $code."
    LoadError.BadResponse -> "A resposta do servidor veio fora do formato esperado."
}

private fun Double?.format(decimals: Int = 1): String =
    if (this == null) "—" else String.format(PT_BR, "%.${decimals}f", this)

@Preview(showBackground = true)
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
    Pm25Theme { HomeScreen(HomeUiState(data = data), onRefresh = {}) }
}
