"""A última leitura de um nó sem dados, aberta no cartão: os valores em grade, com o aviso de que são históricos."""

from datetime import datetime
from html import escape


def last_reading_html(when: datetime, values: list[tuple[str, str]], rssi: str | None) -> str:
    """O HTML do bloco: o dia e a hora da leitura, o aviso de que ela é história, os valores (rótulo e valor, na
    ordem dada) e, se o nó informou, o sinal Wi-Fi da própria leitura. O nome do expansor que guarda o bloco já diz
    que é a última leitura. Sem a faixa de qualidade do ar: o registro antigo não diz como o ar está agora."""
    cells = "".join(f'<div><span class="aq-last-label">{escape(label)}</span>'
                    f'<span class="aq-last-value">{escape(value)}</span></div>' for label, value in values)
    foot = f'<div class="aq-last-foot">Sinal Wi-Fi na leitura: {escape(rssi)}</div>' if rssi else ""
    return (f'<div class="aq-last"><div class="aq-last-title">{when:%d/%m} às {when:%H:%M}</div>'
            '<div class="aq-last-note">Leitura histórica; não representa a condição atual.</div>'
            f'<div class="aq-last-grid">{cells}</div>{foot}</div>')
