"""As marcas do eixo do tempo dos gráficos de vários dias: uma por dia, só com a data."""

from datetime import datetime, time, timedelta

MIN_SPAN = timedelta(days=2)                             # abaixo disso, as horas ainda fazem falta nos rótulos
STEPS = ((10, 1), (20, 2), (70, 7))                      # até tantos dias, uma marca a cada tantos; depois, a cada 14


def day_ticks(first: datetime, last: datetime) -> list[datetime]:
    """As meias-noites entre `first` e `last` (horários locais, sem fuso) onde o eixo escreve a data. Até 10 dias é uma
    por dia; depois, de 2 em 2 (até 20), de 7 em 7 (até 70) e de 14 em 14, para os rótulos não se atropelarem. A
    contagem parte da primeira meia-noite depois de `first`. Vazio em menos de 2 dias: aí as horas ainda fazem falta."""
    if last - first < MIN_SPAN:
        return []
    days = (last.date() - first.date()).days + 1
    step = next((s for limit, s in STEPS if days <= limit), 14)
    tick = datetime.combine(first.date(), time())
    if tick < first:
        tick += timedelta(days=1)
    ticks = []
    while tick <= last:
        ticks.append(tick)
        tick += timedelta(days=step)
    return ticks
