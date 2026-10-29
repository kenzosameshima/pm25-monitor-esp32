"""O tempo sem leitura escrito na unidade que se lê de relance."""

import pytest

from dashboard.duration import duration_text


@pytest.mark.parametrize("minutes, text", [
    (0, "0 min"),
    (1, "1 min"),
    (59, "59 min"),
    (60, "1 h"),                  # hora cheia: sem "0 min"
    (61, "1 h 1 min"),
    (90, "1 h 30 min"),
    (1439, "23 h 59 min"),
    (1440, "24 h"),               # o nó que não mandou nada na janela de 24 h
    (59.6, "1 h"),                # os minutos chegam arredondados do servidor, mas o texto não sai com fração
])
def test_o_tempo_vai_em_minutos_ate_uma_hora_e_depois_em_horas(minutes, text):
    assert duration_text(minutes) == text
