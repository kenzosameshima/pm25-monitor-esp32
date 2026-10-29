"""O tempo sem leitura escrito na unidade que se lê de relance."""


def duration_text(minutes: float) -> str:
    """Minutos até uma hora (59 min); de uma hora em diante, horas e os minutos que sobram (1 h, 1 h 30 min, 24 h)."""
    total = int(round(minutes))
    if total < 60:
        return f"{total} min"
    hours, rest = divmod(total, 60)
    return f"{hours} h" if rest == 0 else f"{hours} h {rest} min"
