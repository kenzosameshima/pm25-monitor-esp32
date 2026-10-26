package br.unip.pm25.domain

import br.unip.pm25.data.HourlyPoint

/** Acima disso, sensores ópticos como o PMS5003 tendem a superestimar o PM2,5 (mesmo limite do servidor). */
const val HIGH_HUMIDITY = 75.0

/**
 * Resumo do PM2,5 de uma janela de horas. Só entram as horas válidas (com leituras suficientes);
 * as demais contam apenas em `totalHours`.
 */
data class HourlySummary(
    val totalHours: Int,
    val validHours: Int,
    val mean: Double?,
    val max: HourlyPoint?,
    /** Horas válidas com média acima do limite da faixa Boa da CETESB. */
    val hoursAboveGood: Int,
    /** Horas válidas com umidade média acima de HIGH_HUMIDITY. */
    val humidHours: Int,
    /** Horas em que o sensor quase não viu partículas: ficam fora da média e já contam entre as não válidas. */
    val suspectHours: Int,
)

fun summarize(points: List<HourlyPoint>): HourlySummary {
    val valid = points.filter { it.valid && it.pm25 != null }
    return HourlySummary(
        totalHours = points.size,
        validHours = valid.size,
        mean = valid.map { it.pm25!! }.average().takeUnless { it.isNaN() },
        max = valid.maxByOrNull { it.pm25!! },
        hoursAboveGood = valid.count { it.pm25!! > AirQuality.BOA.upperBound },
        humidHours = valid.count { (it.humidity ?: 0.0) > HIGH_HUMIDITY },
        suspectHours = points.count { it.suspect },
    )
}
