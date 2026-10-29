"""A linha acima de um gráfico de linhas do dashboard: um texto de um lado, a legenda do outro."""

from datetime import datetime
from html import escape


def period_text(first: datetime, last: datetime) -> str:
    """Os dias que o gráfico cobre, do jeito mais curto: 29/10, 28–29/10 (mesmo mês) ou 31/10 a 01/11."""
    if first.date() == last.date():
        return f"{first:%d/%m}"
    if (first.year, first.month) == (last.year, last.month):
        return f"{first:%d}–{last:%d/%m}"
    return f"{first:%d/%m} a {last:%d/%m}"


def trend_head_html(label: str, series: list[tuple[str, str]], silent: list[str] = (), *, title: bool = False,
                    blank: str | None = None, subtitle: str | None = None) -> str:
    """O HTML da linha: `label` à esquerda (o período e a unidade, ou o nome da variável); à direita, cada série com a
    cor da sua linha e, por fim, o aviso dos nós que não enviaram nada (sem linha no gráfico, então sem cor). Com
    `title`, o texto da esquerda é o título do gráfico e ganha destaque; sem ele, é uma nota de apoio, discreta.
    `blank` diz o que o espaço sem cor do gráfico quer dizer, numa bolinha vazada ao lado das séries. `subtitle` é
    uma segunda linha, abaixo do título e da legenda (o período e o fuso, por exemplo)."""
    keys = "".join(f'<span class="aq-key"><i style="background:{color}" aria-hidden="true"></i>{escape(name)}</span>'
                   for name, color in series)
    if blank:
        keys += f'<span class="aq-key"><i class="aq-blank" aria-hidden="true"></i>{escape(blank)}</span>'
    if silent:
        keys += f'<span class="aq-key-off">{escape(", ".join(silent))} · sem leituras neste período</span>'
    label_class = "aq-label aq-title" if title else "aq-label"
    second = f'<span class="aq-sub">{escape(subtitle)}</span>' if subtitle else ""
    return (f'<div class="aq-trend-head"><span class="{label_class}">{escape(label)}</span>'
            f'<span class="aq-keys">{keys}</span>{second}</div>')
