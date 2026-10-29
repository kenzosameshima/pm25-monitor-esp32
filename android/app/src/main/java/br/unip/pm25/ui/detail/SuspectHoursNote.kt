package br.unip.pm25.ui.detail

/**
 * Aviso das horas em que o sensor quase não viu partículas e que por isso ficam em branco no histórico.
 * A causa (sensor ou ar muito limpo) ainda não foi confirmada contra a estação da CETESB, então o texto
 * descreve o que o sensor viu e não afirma o que o ar faz.
 */
internal fun suspectHoursNote(hours: Int): String =
    "Em $hours h o sensor quase não viu partículas, o que pode ser falha dele ou ar muito limpo; " +
        "por precaução, essas horas ficam em branco."
