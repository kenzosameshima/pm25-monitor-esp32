"""Os textos da avaliação de previsões: quantas horas entraram nas contas e quando a amostra é pequena demais."""

from datetime import datetime, timedelta
from html import escape

# Menos que um dia de horas: o ciclo diário do PM2,5 nem fecha. É um aviso de tela, não um teste estatístico.
SMALL_SAMPLE_HOURS = 24


def hours_text(n: int) -> str:
    return "1 hora" if n == 1 else f"{n} horas"


def evaluated_text(hours: int, previsors: int, first: datetime, last: datetime) -> str:
    """Em que horas a tabela foi calculada: as mesmas para todos os previsores, ou as da persistência quando ela está só.
    `first` e `last` são a primeira e a última dessas horas, no horário local."""
    span = f" ({first:%d/%m %H:%M})" if hours == 1 else f", de {first:%d/%m %H:%M} a {last:%d/%m %H:%M}"
    if previsors == 1:
        return f"Avaliada em {hours_text(hours)}{span}."
    same = "na mesma hora" if hours == 1 else f"nas mesmas {hours} horas"
    return f"Todos os previsores foram avaliados {same}{span}."


def notice_html(headline: str, detail: str) -> str:
    """Um aviso que fica acima de uma tabela sem competir com ela: a frase principal e, embaixo, um detalhe, num bloco só
    (o estilo é `.aq-note`: fundo quase transparente, filete e texto pequeno)."""
    return (f'<div class="aq-note" role="note"><span>{escape(headline)}</span>'
            f'<span class="aq-note-detail">{escape(detail)}</span></div>')


def pending_band(last_observed: datetime, last_plotted: datetime) -> tuple[datetime, datetime] | None:
    """O trecho do gráfico que tem previsão e ainda não tem observação, como (início, fim). Cada hora é um ponto no
    começo dela: a faixa vai do ponto médio entre a última hora observada e a seguinte até meia hora depois da última
    desenhada, e cada ponto pendente fica no meio de um pedaço dela. None se tudo o que está desenhado já foi observado."""
    if last_plotted <= last_observed:
        return None
    half = timedelta(minutes=30)
    return last_observed + half, last_plotted + half


def small_sample_note(hours: int) -> str:
    """O aviso de uma linha avaliada em poucas horas; vazio quando a amostra tem um dia ou mais."""
    return f"Amostra de apenas {hours_text(hours)}" if hours < SMALL_SAMPLE_HOURS else ""


def evaluation_guide(retroactive: bool) -> str:
    """Uma definição por coluna da tabela de avaliação, no vocabulário do glossário. A da previsão retroativa só entra
    quando a tabela tem uma, e diz o que o "-retro" do nome quer dizer para quem não conhece o nome técnico."""
    lines = [
        "- **Horas avaliadas:** quantas horas entraram nas contas da linha.",
        "- **Persistência:** repete a média da hora anterior; é a referência que qualquer modelo precisa superar.",
        "- **MAE:** o erro médio da previsão, em µg/m³.",
        "- **RMSE:** também em µg/m³, mas pesa mais os erros grandes.",
        "- **Skill score:** um menos a razão entre o RMSE do previsor e o da persistência, nas mesmas horas. Acima de "
        "zero, o previsor acerta mais que repetir a hora anterior.",
    ]
    if retroactive:
        lines.append("- **Previsão retroativa (“-retro” no nome):** recalculada depois do fato, só com as leituras "
                     "anteriores à hora-alvo. Fica numa versão à parte e não vale como validação prospectiva.")
    return "\n".join(lines)
