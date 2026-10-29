package br.unip.pm25.domain

import br.unip.pm25.data.LatestReading

/**
 * Faixas de qualidade do ar da CETESB para o PM2,5, em µg/m³.
 *
 * A CETESB define as faixas para a média de 24 horas; aplicadas a uma leitura de um minuto, servem
 * só como referência visual, e a tela diz isso ao usuário.
 */
enum class AirQuality(val label: String, val upperBound: Double) {
    BOA("Boa", 25.0),
    MODERADA("Moderada", 50.0),
    RUIM("Ruim", 75.0),
    MUITO_RUIM("Muito ruim", 125.0),
    PESSIMA("Péssima", Double.POSITIVE_INFINITY);

    companion object {
        /** Faixa de um valor de PM2,5; cada limite pertence à faixa de baixo (25,0 é Boa). */
        fun of(pm25: Double?): AirQuality? {
            if (pm25 == null || pm25.isNaN() || pm25 < 0) return null
            return entries.first { pm25 <= it.upperBound }
        }
    }
}

/**
 * Se uma leitura chegou com todas as partículas que o nó enviou em zero (e ao menos o PM2,5). Sozinha ela não
 * diz se o sensor parou de ver partículas ou se o ar está muito limpo, então quem a mostra não lhe dá faixa.
 */
fun isZeroReading(reading: LatestReading): Boolean {
    val pm25 = reading.pm25
    if (pm25 == null || pm25.isNaN()) return false
    return listOfNotNull(reading.pm1, pm25, reading.pm10).all { it == 0.0 }
}

/**
 * Onde um PM2,5 cai numa escala de 0 a 1 que dá a cada faixa o mesmo comprimento. Dentro de cada faixa a posição é
 * proporcional ao valor; a última não tem teto, então a escala a mostra até o dobro do seu limite inferior (de 125
 * a 250) e o que passa disso fica no fim. É o mesmo cálculo do servidor (`analytics.band_position`), para o
 * dashboard e o app desenharem a mesma escala. Null sem valor válido.
 */
fun bandPosition(pm25: Double?): Double? {
    if (pm25 == null || pm25.isNaN() || pm25 < 0) return null
    val limits = AirQuality.entries.dropLast(1).map { it.upperBound }
    val starts = listOf(0.0) + limits
    val ends = limits + 2 * limits.last()
    for (i in ends.indices) {
        if (pm25 <= ends[i]) return (i + (pm25 - starts[i]) / (ends[i] - starts[i])) / ends.size
    }
    return 1.0
}

/** De onde a onde vai a faixa, para quem não vê a escala: "de 25 a 50 µg/m³"; a última não tem teto. */
fun AirQuality.rangeText(): String {
    val lower = if (ordinal == 0) 0 else AirQuality.entries[ordinal - 1].upperBound.toInt()
    return if (upperBound.isInfinite()) "acima de $lower µg/m³" else "de $lower a ${upperBound.toInt()} µg/m³"
}
