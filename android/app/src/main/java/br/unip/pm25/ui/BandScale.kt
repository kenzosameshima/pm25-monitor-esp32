package br.unip.pm25.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.dp
import br.unip.pm25.domain.AirQuality
import br.unip.pm25.domain.bandPosition
import br.unip.pm25.domain.rangeText
import br.unip.pm25.ui.theme.color

/**
 * As cinco faixas da CETESB numa barra, com um marcador onde o PM2,5 cai e o fim de cada faixa marcado (25, 50, 75
 * e 125). Mostra onde o valor está dentro da faixa, que o nome dela não diz: 41 e 26 são "Moderada", mas um está
 * perto de Ruim e o outro de Boa. Para o leitor de tela, a descrição diz de onde a onde vai a faixa.
 */
@Composable
fun BandScale(pm25: Double, quality: AirQuality, modifier: Modifier = Modifier) {
    val position = bandPosition(pm25) ?: return
    val measurer = rememberTextMeasurer()
    val labelStyle = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant)
    val marker = MaterialTheme.colorScheme.onSurface
    val ring = MaterialTheme.colorScheme.surface
    val limits = AirQuality.entries.dropLast(1).map { it.upperBound.toInt().toString() }
    // A altura segue a fonte do leitor: com o texto em 200% os números não podem ser cortados.
    val labelHeight = with(LocalDensity.current) { measurer.measure("0", labelStyle).size.height.toDp() }
    Canvas(
        modifier.fillMaxWidth().height(28.dp + labelHeight)
            .semantics { contentDescription = "Escala das faixas: ${quality.label}, ${quality.rangeText()}" },
    ) {
        val top = 6.dp.toPx()
        val barHeight = 8.dp.toPx()
        val gap = 2.dp.toPx()
        val segment = (size.width - gap * (AirQuality.entries.size - 1)) / AirQuality.entries.size
        AirQuality.entries.forEachIndexed { i, band ->
            drawRect(band.color(), Offset(i * (segment + gap), top), Size(segment, barHeight))
        }
        val x = (position * size.width).toFloat()
        // O anel na cor do fundo separa o marcador de qualquer faixa, clara ou escura.
        drawRoundRect(ring, Offset(x - 3.dp.toPx(), top - 5.dp.toPx()), Size(6.dp.toPx(), barHeight + 10.dp.toPx()),
            CornerRadius(3.dp.toPx()))
        drawRoundRect(marker, Offset(x - 1.5.dp.toPx(), top - 4.dp.toPx()), Size(3.dp.toPx(), barHeight + 8.dp.toPx()),
            CornerRadius(1.5.dp.toPx()))
        limits.forEachIndexed { i, text ->
            val label = measurer.measure(text, labelStyle)
            val center = (i + 1) * size.width / AirQuality.entries.size
            drawText(label, topLeft = Offset(center - label.size.width / 2f, top + barHeight + 10.dp.toPx()))
        }
    }
}
