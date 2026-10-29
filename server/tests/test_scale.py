"""A escala das faixas de qualidade do ar que o dashboard desenha sob o PM2,5 de cada nó."""

import re

import pytest

from app import analytics
from dashboard.scale import BAND_FILLS, band_scale_html


def test_a_escala_se_apresenta_como_uma_imagem_com_a_leitura_por_extenso():
    html = band_scale_html(0.3, "PM2,5 de 37,5 µg/m³, na faixa Moderada")
    assert 'role="img"' in html
    assert 'aria-label="PM2,5 de 37,5 µg/m³, na faixa Moderada"' in html


def test_o_texto_da_leitura_nao_quebra_o_html():
    html = band_scale_html(0.3, 'a<b "c"')
    assert 'aria-label="a&lt;b &quot;c&quot;"' in html


@pytest.mark.parametrize("position, left", [(0.0, "0.0%"), (0.3, "30.0%"), (1.0, "100.0%")])
def test_o_marcador_fica_na_posicao_da_leitura(position, left):
    assert f'class="aq-marker" style="left:{left}"' in band_scale_html(position, "x")


def test_as_cinco_faixas_aparecem_em_ordem_e_com_a_cor_de_cada_uma():
    html = band_scale_html(0.5, "x")
    fills = re.findall(r'<span style="background:(#[0-9a-f]{6})"></span>', html)
    assert fills == list(BAND_FILLS) and len(BAND_FILLS) == len(analytics.AIR_QUALITY_BANDS)


def test_os_limites_das_faixas_marcam_o_fim_de_cada_uma():
    html = band_scale_html(0.5, "x")
    ticks = re.findall(r'<span style="left:([\d.]+)%">(\d+)</span>', html)
    assert ticks == [("20.0", "25"), ("40.0", "50"), ("60.0", "75"), ("80.0", "125")]
