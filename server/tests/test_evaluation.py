"""Os textos da avaliação de previsões: quantas horas entraram nas contas e quando a amostra é pequena demais."""

from datetime import datetime

import pytest

from dashboard.evaluation import (SMALL_SAMPLE_HOURS, evaluated_text, evaluation_guide, hours_text, notice_html,
                                  pending_band, small_sample_note)

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


def test_a_faixa_sem_observacao_cobre_as_horas_depois_da_ultima_observada_de_ponta_a_ponta():
    # Cada hora é um ponto no começo dela: a faixa começa no ponto médio entre a última hora observada e a seguinte e
    # termina meia hora depois da última desenhada, e cada ponto pendente fica no meio de um pedaço dela.
    assert pending_band(datetime(2026, 10, 29, 10), datetime(2026, 10, 29, 12)) == (
        datetime(2026, 10, 29, 10, 30), datetime(2026, 10, 29, 12, 30))


def test_sem_nada_alem_da_ultima_observacao_nao_ha_faixa():
    assert pending_band(datetime(2026, 10, 29, 10), datetime(2026, 10, 29, 10)) is None


def test_o_aviso_leva_a_frase_principal_e_o_detalhe_no_mesmo_bloco():
    html = notice_html("Períodos de avaliação diferentes: MAE e RMSE não se comparam.", "O skill score vale por linha.")
    assert html.startswith('<div class="aq-note" role="note">') and html.endswith("</div>") and html.count("<div") == 1
    assert html.index("Períodos de avaliação diferentes") < html.index('<span class="aq-note-detail">O skill score')


def test_o_texto_do_aviso_nao_quebra_o_html():
    html = notice_html("a<b", "c & d")
    assert "a&lt;b" in html and "c &amp; d" in html


def test_o_guia_define_cada_coluna_da_tabela_no_vocabulario_do_glossario():
    guide = evaluation_guide(retroactive=False)
    for term in ("Horas avaliadas", "Persistência", "MAE", "RMSE", "Skill score"):
        assert f"**{term}:**" in guide
    assert "um menos a razão entre o RMSE do previsor e o da persistência" in guide
    assert "retroativa" not in guide                                   # sem previsor retroativo, o assunto nem aparece


def test_o_guia_explica_o_retro_sem_depender_do_nome_tecnico():
    guide = evaluation_guide(retroactive=True)
    assert "retroativa" in guide and "-retro" in guide                 # o nome técnico aparece só para ligar à tabela
    assert "depois do fato" in guide and "não vale como validação prospectiva" in guide


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
