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


def test_o_titulo_de_um_grafico_leva_a_marca_de_destaque_e_a_nota_de_apoio_nao():
    note = trend_head_html("29/10 · µg/m³", [])
    title = trend_head_html("PM2,5 (µg/m³)", [], title=True)
    assert '<span class="aq-label">' in note and "aq-title" not in note
    assert '<span class="aq-label aq-title">PM2,5 (µg/m³)</span>' in title


def test_o_espaco_em_branco_vem_explicado_ao_lado_das_cores():
    html = trend_head_html("Qualidade da coleta por hora", [("sem leituras", "#8b93a1")], title=True,
                           blank="em branco: hora válida")
    assert "em branco: hora válida</span>" in html
    assert '<i class="aq-blank" aria-hidden="true"></i>' in html      # a marca do branco é uma bolinha vazada
    assert html.count("background:") == 1                             # e só a causa tem cor: o branco é o que sobra


def test_sem_explicacao_do_branco_a_legenda_nao_traz_a_marca():
    assert "aq-blank" not in trend_head_html("PM2,5", [("no-01", "#22b8cf")])


def test_a_segunda_linha_do_cabecalho_vem_depois_do_titulo_e_da_legenda():
    html = trend_head_html("PM2,5 (µg/m³) · previsão para a hora seguinte", [("Observado", "#3b82f6")], title=True,
                           subtitle="27/10 15:00 a 29/10 16:00 · horário de Brasília")
    assert html.endswith('<span class="aq-sub">27/10 15:00 a 29/10 16:00 · horário de Brasília</span></div>')
    assert html.index("aq-keys") < html.index("aq-sub")               # a legenda fica na linha do título


def test_sem_segunda_linha_o_cabecalho_nao_traz_a_marca():
    assert "aq-sub" not in trend_head_html("PM2,5", [("no-01", "#22b8cf")])


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
