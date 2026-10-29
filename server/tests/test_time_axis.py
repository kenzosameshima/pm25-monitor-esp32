"""As marcas do eixo do tempo de um gráfico de vários dias: uma meia-noite por dia, com a data só."""

from datetime import datetime

import pytest

from dashboard.time_axis import day_ticks


def days(ticks):
    return [t.strftime("%d/%m") for t in ticks]


def test_sete_dias_levam_uma_marca_por_dia_na_meia_noite():
    ticks = day_ticks(datetime(2026, 10, 23), datetime(2026, 10, 29, 14, 5))
    assert days(ticks) == ["23/10", "24/10", "25/10", "26/10", "27/10", "28/10", "29/10"]
    assert all((t.hour, t.minute, t.second) == (0, 0, 0) for t in ticks)       # a marca é o começo do dia


def test_um_periodo_que_comeca_no_meio_do_dia_marca_a_primeira_meia_noite_depois_do_comeco():
    ticks = day_ticks(datetime(2026, 10, 26, 10, 30), datetime(2026, 10, 29, 9, 0))
    assert days(ticks) == ["27/10", "28/10", "29/10"]                          # nada antes do primeiro dado


def test_menos_de_dois_dias_ficam_sem_marcas_de_data_porque_as_horas_ainda_fazem_falta():
    assert day_ticks(datetime(2026, 10, 28), datetime(2026, 10, 29, 9, 0)) == []
    assert day_ticks(datetime(2026, 10, 29, 3), datetime(2026, 10, 29, 9)) == []


def test_dois_dias_cheios_ja_levam_a_marca_de_cada_dia():
    assert days(day_ticks(datetime(2026, 10, 27), datetime(2026, 10, 29))) == ["27/10", "28/10", "29/10"]


@pytest.mark.parametrize("first, last, step", [
    (datetime(2026, 10, 20), datetime(2026, 10, 29, 12), 1),     # 10 dias: todo dia
    (datetime(2026, 10, 16), datetime(2026, 10, 29, 12), 2),     # 14 dias: dia sim, dia não
    (datetime(2026, 9, 30), datetime(2026, 10, 29, 20), 7),      # 30 dias: uma por semana
    (datetime(2026, 7, 1), datetime(2026, 10, 29, 20), 14),      # 4 meses: de duas em duas semanas
])
def test_quanto_mais_dias_menos_marcas_para_os_rotulos_nao_se_atropelarem(first, last, step):
    ticks = day_ticks(first, last)
    assert ticks[0] == first and len(ticks) <= 10
    assert {(b - a).days for a, b in zip(ticks, ticks[1:])} == {step}


def test_nenhuma_marca_fica_depois_do_fim_do_periodo():
    ticks = day_ticks(datetime(2026, 9, 30), datetime(2026, 10, 29, 20))
    assert ticks[-1] <= datetime(2026, 10, 29, 20)
