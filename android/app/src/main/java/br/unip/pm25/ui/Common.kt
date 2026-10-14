package br.unip.pm25.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import br.unip.pm25.data.LoadError
import br.unip.pm25.domain.AirQuality
import br.unip.pm25.ui.theme.color
import br.unip.pm25.ui.theme.onColor
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale

/** Peças compartilhadas pelas telas: textos de erro, avisos e formatação em português. */

val PT_BR: Locale = Locale.forLanguageTag("pt-BR")
val CLOCK: DateTimeFormatter = DateTimeFormatter.ofPattern("HH:mm").withZone(ZoneId.systemDefault())
val DAY_CLOCK: DateTimeFormatter = DateTimeFormatter.ofPattern("dd/MM HH:mm").withZone(ZoneId.systemDefault())

fun Double?.format(decimals: Int = 1): String =
    if (this == null) "—" else String.format(PT_BR, "%.${decimals}f", this)

fun LoadError.message(): String = when (this) {
    LoadError.Network -> "Sem conexão com o servidor. Confira a internet e se a API está no ar."
    LoadError.Unauthorized -> "O servidor recusou o token de leitura. Confira pm25.readToken no local.properties."
    LoadError.ReadDisabled -> "A consulta está desligada no servidor (PM25_READ_TOKEN vazio)."
    LoadError.NotFound -> "O servidor não tem leituras deste sensor."
    is LoadError.Blocked -> "Acesso bloqueado por tentativas inválidas. Tente de novo em " +
        (retryAfterSeconds?.let { "$it s" } ?: "alguns minutos") + "."
    is LoadError.Server -> "O servidor respondeu com erro $code."
    LoadError.BadResponse -> "A resposta do servidor veio fora do formato esperado."
}

/** Falha numa atualização com dados anteriores na tela: avisa o motivo e de quando são os dados. */
@Composable
fun StaleBanner(error: LoadError, lastUpdate: Instant) {
    Card(colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.errorContainer)) {
        Column(Modifier.padding(12.dp)) {
            Text(error.message(), color = MaterialTheme.colorScheme.onErrorContainer)
            Text("Mostrando os dados de ${CLOCK.format(lastUpdate)}.", style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onErrorContainer)
        }
    }
}

/** Falha sem nenhum dado para mostrar: o motivo e o botão de tentar de novo. Não rola; cabe numa lista. */
@Composable
fun ErrorMessage(error: LoadError, onRetry: () -> Unit, modifier: Modifier = Modifier) {
    Column(
        modifier.padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp, Alignment.CenterVertically),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(error.message(), style = MaterialTheme.typography.bodyLarge)
        Button(onClick = onRetry) { Text("Tentar de novo") }
    }
}

/** ErrorMessage em tela cheia, rolável para o gesto de puxar para atualizar também funcionar. */
@Composable
fun ErrorPanel(error: LoadError, onRetry: () -> Unit) {
    ErrorMessage(error, onRetry, Modifier.fillMaxSize().verticalScroll(rememberScrollState()))
}

@Composable
fun Metric(label: String, value: String, modifier: Modifier = Modifier) {
    Column(modifier) {
        Text(label, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, style = MaterialTheme.typography.bodyMedium)
    }
}

@Composable
fun QualityChip(quality: AirQuality) {
    Text(
        quality.label,
        color = quality.onColor(),
        style = MaterialTheme.typography.labelLarge,
        modifier = Modifier
            .background(quality.color(), RoundedCornerShape(50))
            .padding(horizontal = 12.dp, vertical = 6.dp),
    )
}
