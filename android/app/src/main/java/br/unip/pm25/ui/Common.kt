package br.unip.pm25.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.FlowRowScope
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
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
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

/** "14:30" se `moment` é de hoje (no fuso do celular); "13/10 14:30" se não é. */
fun formatMoment(moment: Instant, now: Instant = Instant.now()): String {
    val zone = ZoneId.systemDefault()
    val sameDay = moment.atZone(zone).toLocalDate() == now.atZone(zone).toLocalDate()
    return (if (sameDay) CLOCK else DAY_CLOCK).format(moment)
}

/** O que aparece no lugar de um valor que o servidor não mandou. */
const val NO_VALUE = "—"

fun Double?.format(decimals: Int = 1): String =
    if (this == null) NO_VALUE else String.format(PT_BR, "%.${decimals}f", this)

/** O valor com a unidade, ou só `NO_VALUE` se não há valor: "— °C" parece um dado e é lido como se fosse. */
fun Double?.formatWith(unit: String, decimals: Int = 1, gap: String = " "): String =
    if (this == null) NO_VALUE else format(decimals) + gap + unit

fun LoadError.message(): String = when (this) {
    LoadError.Network -> "Sem conexão com o servidor. Confira a internet e se a API está no ar."
    LoadError.Tls -> "Não foi possível abrir a conexão segura com o servidor. Confira a data e a hora do " +
        "celular e se a rede não intercepta a conexão."
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
            Text("Mostrando os dados de ${formatMoment(lastUpdate)}.", style = MaterialTheme.typography.bodySmall,
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

/** Métricas lado a lado; com fonte grande, as que não cabem passam para a linha de baixo em vez de sair da tela. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun MetricRow(content: @Composable FlowRowScope.() -> Unit) {
    FlowRow(
        horizontalArrangement = Arrangement.spacedBy(24.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
        content = content,
    )
}

/** Marca um título como cabeçalho, para o leitor de tela poder pular de um para o outro. */
fun Modifier.asHeading(): Modifier = semantics { heading() }

/** Rótulo e valor são lidos juntos pelo leitor de tela; um valor ausente é lido como "sem dado", não como um traço. */
@Composable
fun Metric(label: String, value: String, modifier: Modifier = Modifier) {
    val reading = if (value == NO_VALUE) {
        Modifier.clearAndSetSemantics { contentDescription = "$label: sem dado" }
    } else {
        Modifier.semantics(mergeDescendants = true) {}
    }
    Column(modifier.then(reading)) {
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
