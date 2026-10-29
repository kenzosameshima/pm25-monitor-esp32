package br.unip.pm25.ui.home

import br.unip.pm25.data.LatestReading

/**
 * Aviso do cartão de um nó em operação cuja leitura chegou toda em zero, citando só as partículas que o nó enviou.
 * O texto é o mesmo do dashboard e não afirma que o ar está limpo: o ADR 0004 diz que a causa não se decide só
 * com os dados do nó.
 */
internal fun zeroReadingNote(reading: LatestReading): String {
    val names = listOfNotNull("PM1".takeIf { reading.pm1 != null }, "PM2,5", "PM10".takeIf { reading.pm10 != null })
    val listed = if (names.size == 1) names.single() else "${names.dropLast(1).joinToString(", ")} e ${names.last()}"
    return "Leitura zerada ($listed em 0,0): o sensor pode não estar vendo partículas. " +
        "Por isso o cartão fica sem faixa de qualidade do ar."
}
