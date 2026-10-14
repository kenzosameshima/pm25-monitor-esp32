package br.unip.pm25.domain

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
