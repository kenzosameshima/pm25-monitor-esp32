package br.unip.pm25.ui.home

/**
 * Aviso do cartão de um nó em operação cuja leitura chegou toda em zero. O texto é o mesmo do dashboard e não
 * afirma que o ar está limpo: o ADR 0004 diz que a causa não se decide só com os dados do nó.
 */
internal const val ZERO_READING_NOTE =
    "Leitura zerada (PM1, PM2,5 e PM10 em 0,0): o sensor pode não estar vendo partículas. " +
        "Por isso o cartão fica sem faixa de qualidade do ar."
