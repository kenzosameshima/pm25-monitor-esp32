"""Escala das faixas de qualidade do ar que o cartão de um nó mostra sob o PM2,5."""

from html import escape

from app import analytics

# Uma cor por faixa, na ordem das faixas da CETESB (Boa a Péssima). Só a escala usa estas cores.
BAND_FILLS = ("#3fae6b", "#e6c445", "#ee8a3a", "#d9483b", "#8e4fb5")


def band_scale_html(position: float, label: str) -> str:
    """O HTML da escala: uma barra com as cinco faixas e um marcador na posição (0 a 1) da leitura.

    O marcador diz onde a leitura está dentro da faixa, que o nome da faixa sozinho não diz (41 e 26 são
    "Moderada", mas um está perto de Ruim e o outro de Boa). Os números marcam o fim de cada faixa. A escala
    se apresenta como imagem e `label` é o que o leitor de tela lê no lugar dela.
    """
    segments = "".join(f'<span style="background:{fill}"></span>' for fill in BAND_FILLS)
    limits = [bound for bound, _ in analytics.AIR_QUALITY_BANDS[:-1]]
    ticks = "".join(f'<span style="left:{(i + 1) * 100 / len(BAND_FILLS):.1f}%">{bound:g}</span>'
                    for i, bound in enumerate(limits))
    return (f'<div class="aq-scale" role="img" aria-label="{escape(label)}">'
            f'<div class="aq-track">{segments}</div>'
            f'<div class="aq-marker" style="left:{position * 100:.1f}%"></div>'
            f'<div class="aq-ticks">{ticks}</div>'
            "</div>")
