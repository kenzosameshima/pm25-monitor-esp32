"""A última leitura de um nó sem dados, aberta no cartão: os valores em grade, com o aviso de que são históricos."""

import re
from datetime import datetime

from dashboard.last_reading import last_reading_html

WHEN = datetime(2026, 10, 27, 18, 26)
VALUES = [("PM2,5 (µg/m³)", "0,0"), ("PM10 (µg/m³)", "0,0"), ("Temperatura", "22,2 °C"), ("Umidade", "54,6%")]


def test_o_titulo_diz_so_o_dia_e_a_hora_da_leitura():
    html = last_reading_html(WHEN, VALUES, "-53 dBm")
    assert '<div class="aq-last-title">27/10 às 18:26</div>' in html
    assert "Última leitura" not in html                  # quem diz isso é o nome do expansor que guarda o bloco


def test_o_aviso_de_que_e_historica_vem_antes_dos_numeros():
    html = last_reading_html(WHEN, VALUES, "-53 dBm")
    assert "Leitura histórica; não representa a condição atual." in html
    assert html.index("não representa a condição atual") < html.index("PM2,5")


def test_cada_valor_vem_com_o_seu_rotulo_na_ordem_dada():
    html = last_reading_html(WHEN, VALUES, None)
    pairs = re.findall(r'aq-last-label">([^<]*)</span><span class="aq-last-value">([^<]*)<', html)
    assert pairs == VALUES


def test_o_sinal_wifi_fecha_o_bloco_e_diz_que_e_o_da_leitura():
    html = last_reading_html(WHEN, VALUES, "-53 dBm")
    assert "Sinal Wi-Fi na leitura: -53 dBm" in html
    assert html.index("Sinal Wi-Fi") > html.index("54,6%")


def test_sem_sinal_o_bloco_nao_tem_rodape():
    assert "Wi-Fi" not in last_reading_html(WHEN, VALUES, None)


def test_os_textos_nao_quebram_o_html():
    html = last_reading_html(WHEN, [("a<b", "c&d")], "<x>")
    assert "a&lt;b" in html and "c&amp;d" in html and "&lt;x&gt;" in html
