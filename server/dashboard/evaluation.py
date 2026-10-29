"""Os textos da avaliação de previsões: quantas horas entraram nas contas e quando a amostra é pequena demais."""

from datetime import datetime

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


def small_sample_note(hours: int) -> str:
    """O aviso de uma linha avaliada em poucas horas; vazio quando a amostra tem um dia ou mais."""
    return f"Amostra de apenas {hours_text(hours)}" if hours < SMALL_SAMPLE_HOURS else ""
