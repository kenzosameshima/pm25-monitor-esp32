package br.unip.pm25.ui.detail

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.dp
import br.unip.pm25.domain.AirQuality
import br.unip.pm25.ui.format
import br.unip.pm25.ui.theme.color
import java.time.Instant
import java.time.format.DateTimeFormatter
import kotlin.math.ceil
import kotlin.math.max

/** Uma linha do gráfico: um valor por hora, nulo onde não há dado. */
data class ChartSeries(val label: String, val values: List<Double?>, val color: Color, val dashed: Boolean = false)

/** Teto do eixo: múltiplo de 10 acima do maior valor, com folga. */
private fun axisTop(value: Double): Double = max(10.0, ceil(value * 1.1 / 10) * 10)

private val DASH = PathEffect.dashPathEffect(floatArrayOf(10f, 8f))

/**
 * PM2,5 por hora, uma ou mais séries sobre as mesmas horas. Valores nulos interrompem a linha em vez
 * de ligar pontos distantes; um valor isolado aparece como ponto. O eixo começa em zero e a linha
 * tracejada laranja marca o limite da faixa Boa da CETESB.
 */
@Composable
fun HourlyChart(
    hours: List<Instant>,
    series: List<ChartSeries>,
    timeFormat: DateTimeFormatter,
    description: String,
    modifier: Modifier = Modifier,
) {
    val measurer = rememberTextMeasurer()
    val grid = MaterialTheme.colorScheme.outlineVariant
    val reference = AirQuality.MODERADA.color()
    val labelStyle = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant)
    val limit = AirQuality.BOA.upperBound
    val top = axisTop(max(series.flatMap { it.values }.filterNotNull().maxOrNull() ?: 0.0, limit))

    Canvas(modifier.fillMaxWidth().height(220.dp).semantics { contentDescription = description }) {
        val left = 36.dp.toPx()
        val bottom = size.height - 22.dp.toPx()
        val topY = 8.dp.toPx()
        val width = size.width - left
        fun x(i: Int) = left + if (hours.size > 1) width * i / (hours.size - 1) else width / 2
        fun y(v: Double) = bottom - (bottom - topY) * (v / top).toFloat()

        for (g in listOf(0.0, top / 2, top)) {
            drawLine(grid, Offset(left, y(g)), Offset(size.width, y(g)), strokeWidth = 1.dp.toPx())
            val text = measurer.measure(g.format(0), labelStyle)
            drawText(text, topLeft = Offset(left - text.size.width - 6.dp.toPx(), y(g) - text.size.height / 2))
        }
        drawLine(reference, Offset(left, y(limit)), Offset(size.width, y(limit)), strokeWidth = 1.5.dp.toPx(),
            pathEffect = DASH)

        for (s in series) {
            val path = Path()
            var drawing = false
            s.values.forEachIndexed { i, v ->
                if (v == null) {
                    drawing = false
                } else {
                    if (drawing) path.lineTo(x(i), y(v)) else path.moveTo(x(i), y(v))
                    drawing = true
                }
            }
            drawPath(path, s.color, style = Stroke(2.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round,
                pathEffect = if (s.dashed) DASH else null))
            s.values.forEachIndexed { i, v ->
                if (v != null && s.values.getOrNull(i - 1) == null && s.values.getOrNull(i + 1) == null) {
                    drawCircle(s.color, 3.dp.toPx(), Offset(x(i), y(v)))
                }
            }
        }

        if (hours.isNotEmpty()) {
            listOf(0, hours.size / 2, hours.size - 1).distinct().forEach { i ->
                val text = measurer.measure(timeFormat.format(hours[i]), labelStyle)
                val start = (x(i) - text.size.width / 2).coerceIn(left, size.width - text.size.width)
                drawText(text, topLeft = Offset(start, bottom + 4.dp.toPx()))
            }
        }
    }
}

/** Legenda das séries, com uma amostra do traço de cada uma. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun ChartLegend(series: List<ChartSeries>, modifier: Modifier = Modifier) {
    FlowRow(modifier, horizontalArrangement = Arrangement.spacedBy(16.dp)) {
        series.forEach { s ->
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Canvas(Modifier.width(24.dp).height(12.dp)) {
                    drawLine(s.color, Offset(0f, size.height / 2), Offset(size.width, size.height / 2),
                        strokeWidth = 2.dp.toPx(), pathEffect = if (s.dashed) PathEffect.dashPathEffect(floatArrayOf(6f, 4f)) else null)
                }
                Text(s.label, style = MaterialTheme.typography.labelMedium)
            }
        }
    }
}
