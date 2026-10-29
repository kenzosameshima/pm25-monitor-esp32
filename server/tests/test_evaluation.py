"""Os textos da avaliação de previsões: quantas horas entraram nas contas e quando a amostra é pequena demais."""

from datetime import datetime

import pytest

from dashboard.evaluation import SMALL_SAMPLE_HOURS, evaluated_text, hours_text, small_sample_note

FIRST, LAST = datetime(2026, 10, 28, 20), datetime(2026, 10, 29, 6)


def test_horas_no_singular_e_no_plural():
    assert hours_text(1) == "1 hora" and hours_text(11) == "11 horas"


def test_varios_previsores_dizem_que_foram_avaliados_nas_mesmas_horas_e_quais():
    assert evaluated_text(11, 2, FIRST, LAST) == (
        "Todos os previsores foram avaliados nas mesmas 11 horas, de 28/10 20:00 a 29/10 06:00.")


def test_uma_hora_so_vira_a_mesma_hora_com_a_data_dela():
    assert evaluated_text(1, 3, FIRST, FIRST) == "Todos os previsores foram avaliados na mesma hora (28/10 20:00)."


def test_a_persistencia_sozinha_diz_so_as_horas_avaliadas():
    assert evaluated_text(48, 1, FIRST, LAST) == "Avaliada em 48 horas, de 28/10 20:00 a 29/10 06:00."
    assert evaluated_text(1, 1, FIRST, FIRST) == "Avaliada em 1 hora (28/10 20:00)."


@pytest.mark.parametrize("hours, note", [
    (1, "Amostra de apenas 1 hora"),
    (5, "Amostra de apenas 5 horas"),
    (SMALL_SAMPLE_HOURS - 1, f"Amostra de apenas {SMALL_SAMPLE_HOURS - 1} horas"),
])
def test_amostra_pequena_diz_quantas_horas_foram(hours, note):
    assert small_sample_note(hours) == note


@pytest.mark.parametrize("hours", [SMALL_SAMPLE_HOURS, 36, 48])
def test_um_dia_inteiro_ou_mais_nao_leva_aviso_de_amostra(hours):
    assert small_sample_note(hours) == ""
