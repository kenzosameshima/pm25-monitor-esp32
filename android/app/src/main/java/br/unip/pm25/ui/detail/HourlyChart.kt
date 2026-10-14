package br.unip.pm25.ui.detail

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
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
import br.unip.pm25.data.HourlyPoint
import br.unip.pm25.domain.AirQuality
import br.unip.pm25.ui.format
import br.unip.pm25.ui.theme.color
import java.time.format.DateTimeFormatter
import kotlin.math.ceil
import kotlin.math.max

/** Teto do eixo: múltiplo de 10 acima do maior valor, com folga. */
private fun axisTop(value: Double): Double = max(10.0, ceil(value * 1.1 / 10) * 10)

/**
 * PM2,5 médio por hora. Horas inválidas (poucas leituras) interrompem a linha em vez de ligar pontos
 * distantes; uma hora válida isolada aparece como ponto. O eixo começa em zero e a linha tracejada
 * marca o limite da faixa Boa da CETESB.
 */
@Composable
fun HourlyChart(
    points: List<HourlyPoint>,
    timeFormat: DateTimeFormatter,
    description: String,
    modifier: Modifier = Modifier,
) {
    val measurer = rememberTextMeasurer()
    val line = MaterialTheme.colorScheme.primary
    val grid = MaterialTheme.colorScheme.outlineVariant
    val reference = AirQuality.MODERADA.color()
    val labelStyle = MaterialTheme.typography.labelSmall.copy(color = MaterialTheme.colorScheme.onSurfaceVariant)
    val values = points.map { if (it.valid) it.pm25 else null }
    val limit = AirQuality.BOA.upperBound
    val top = axisTop(max(values.filterNotNull().maxOrNull() ?: 0.0, limit))

    Canvas(modifier.fillMaxWidth().height(220.dp).semantics { contentDescription = description }) {
        val left = 36.dp.toPx()
        val bottom = size.height - 22.dp.toPx()
        val topY = 8.dp.toPx()
        val width = size.width - left
        fun x(i: Int) = left + if (points.size > 1) width * i / (points.size - 1) else width / 2
        fun y(v: Double) = bottom - (bottom - topY) * (v / top).toFloat()

        for (g in listOf(0.0, top / 2, top)) {
            drawLine(grid, Offset(left, y(g)), Offset(size.width, y(g)), strokeWidth = 1.dp.toPx())
            val text = measurer.measure(g.format(0), labelStyle)
            drawText(text, topLeft = Offset(left - text.size.width - 6.dp.toPx(), y(g) - text.size.height / 2))
        }
        drawLine(reference, Offset(left, y(limit)), Offset(size.width, y(limit)), strokeWidth = 1.5.dp.toPx(),
            pathEffect = PathEffect.dashPathEffect(floatArrayOf(10f, 8f)))

        val path = Path()
        var drawing = false
        values.forEachIndexed { i, v ->
            if (v == null) {
                drawing = false
            } else {
                if (drawing) path.lineTo(x(i), y(v)) else path.moveTo(x(i), y(v))
                drawing = true
            }
        }
        drawPath(path, line, style = Stroke(2.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
        values.forEachIndexed { i, v ->
            if (v != null && values.getOrNull(i - 1) == null && values.getOrNull(i + 1) == null) {
                drawCircle(line, 3.dp.toPx(), Offset(x(i), y(v)))
            }
        }

        if (points.isNotEmpty()) {
            val labels = listOf(0, points.size / 2, points.size - 1).distinct()
            labels.forEach { i ->
                val text = measurer.measure(timeFormat.format(points[i].hour), labelStyle)
                val start = (x(i) - text.size.width / 2).coerceIn(left, size.width - text.size.width)
                drawText(text, topLeft = Offset(start, bottom + 4.dp.toPx()))
            }
        }
    }
}
