package br.unip.pm25.ui.home

import br.unip.pm25.data.LatestReading
import br.unip.pm25.ui.formatWith

/**
 * A última leitura de um nó sem dados recentes, dita como histórico para não passar por valor atual.
 * `moment` é o horário da leitura já formatado; só entram os valores que o nó mandou.
 */
fun historicalReadingText(latest: LatestReading, moment: String): String {
    val values = listOfNotNull(
        "PM2,5 ${latest.pm25.formatWith("µg/m³")}",
        latest.pm10?.let { "PM10 ${it.formatWith("µg/m³")}" },
        latest.temperature?.formatWith("°C"),
        latest.humidity?.formatWith("%", decimals = 0, gap = ""),
        latest.rssi?.toDouble()?.formatWith("dBm", decimals = 0),
    )
    val note = if (latest.quality == "ok") "" else " O servidor a marcou como implausível (${latest.quality})."
    return "Leitura de $moment, histórico (não é o valor atual): ${values.joinToString(" · ")}.$note"
}
