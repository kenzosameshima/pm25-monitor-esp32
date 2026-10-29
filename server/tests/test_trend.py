"""A linha acima de um gráfico de linhas: o texto à esquerda, a legenda e os avisos à direita."""

from datetime import datetime

import pytest

from dashboard.trend import period_text, trend_head_html


@pytest.mark.parametrize("first, last, text", [
    (datetime(2026, 10, 29, 3), datetime(2026, 10, 29, 9), "29/10"),               # um dia só
    (datetime(2026, 10, 28, 20), datetime(2026, 10, 29, 2), "28–29/10"),           # vira o dia no mesmo mês
    (datetime(2026, 10, 31, 22), datetime(2026, 11, 1, 4), "31/10 a 01/11"),       # vira o mês: duas datas completas
    (datetime(2026, 12, 31, 22), datetime(2027, 1, 1, 4), "31/12 a 01/01"),        # e o ano
])
def test_o_periodo_diz_so_o_que_muda(first, last, text):
    assert period_text(first, last) == text


def test_o_texto_da_esquerda_vem_pronto_e_cada_sensor_leva_a_sua_cor():
    html = trend_head_html("28–29/10 · µg/m³", [("no-01", "#22b8cf"), ("no-02", "#e0529c")])
    assert '<span class="aq-label">28–29/10 · µg/m³</span>' in html
    assert 'style="background:#22b8cf"' in html and "no-01" in html
    assert 'style="background:#e0529c"' in html and "no-02" in html
    assert "sem leituras" not in html                   # sem nó calado, sem aviso


def test_no_sem_leituras_vem_explicado_ao_lado_da_legenda():
    html = trend_head_html("29/10 · µg/m³", [("no-01", "#22b8cf")], ["no-02"])
    assert "no-02 · sem leituras neste período" in html
    assert html.count("background:") == 1               # o nó calado não tem linha no gráfico, então não tem cor


def test_varios_nos_sem_leituras_dividem_o_mesmo_aviso():
    html = trend_head_html("29/10 · µg/m³", [], ["no-01", "no-02"])
    assert "no-01, no-02 · sem leituras neste período" in html


def test_os_nomes_nao_quebram_o_html():
    html = trend_head_html("x<y", [("a<b", "#22b8cf")], ["c&d"])
    assert "x&lt;y" in html and "a&lt;b" in html and "c&amp;d" in html
