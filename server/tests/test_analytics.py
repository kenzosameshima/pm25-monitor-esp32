"""Testes das regras de análise compartilhadas pelo dashboard, pelos scripts e pela API de leitura."""

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from app import analytics, db

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def reading(device: str, minute: int, pm25: float = 10.0, boot: int = 1, seq: int | None = None,
            quality: str = "ok", humidity: float | None = 60.0, received_delay_s: int = 30) -> dict:
    """Leitura do minuto `minute` contado a partir de NOW (negativo: no passado)."""
    ts = NOW + timedelta(minutes=minute)
    return {"device_id": device, "boot_id": boot, "seq": minute if seq is None else seq,
            "ts_sensor": db.iso(ts), "ts_received": db.iso(ts + timedelta(seconds=received_delay_s)),
            "pm1": None, "pm25": pm25, "pm10": None, "pm25_cf1": None, "temperature": 20.0,
            "humidity": humidity, "rssi": -60, "uptime_s": 0, "samples": 58, "schema_version": "1",
            "quality": quality}


def insert(conn, rows: list[dict]) -> None:
    for device in sorted({r["device_id"] for r in rows}):
        db.insert_batch(conn, device, [r for r in rows if r["device_id"] == device], NOW)


@pytest.fixture
def conn(tmp_path):
    c = db.connect(str(tmp_path / "pm25.db"))
    db.init_db(c)
    yield c
    c.close()


# ---------------------------------------------------------------- médias horárias

def test_hora_so_vale_com_45_leituras(conn):
    two_hours_ago = -120
    insert(conn, [reading("no-01", two_hours_ago + m, pm25=10.0) for m in range(45)]
           + [reading("no-01", two_hours_ago + 60 + m, pm25=20.0) for m in range(44)])
    h = analytics.hourly_means(conn, NOW - timedelta(hours=3), NOW, ["no-01"])
    assert list(h["n"]) == [45, 44]
    assert h["pm25"].iloc[0] == 10.0
    assert pd.isna(h["pm25"].iloc[1])                       # 44 leituras: a hora não vale


def test_horas_sem_leitura_aparecem_vazias_entre_horas_validas(conn):
    insert(conn, [reading("no-01", -180 + m) for m in range(60)] + [reading("no-01", -60 + m) for m in range(60)])
    h = analytics.hourly_means(conn, NOW - timedelta(hours=3), NOW, ["no-01"])
    assert list(h["n"]) == [60, 0, 60]
    assert h["hora"].diff().dropna().eq(pd.Timedelta(hours=1)).all()


def test_leituras_marcadas_so_entram_se_pedido(conn):
    insert(conn, [reading("no-01", -60 + m, quality="ok" if m < 40 else "suspect") for m in range(60)])
    start = NOW - timedelta(hours=1)
    assert pd.isna(analytics.hourly_means(conn, start, NOW, ["no-01"])["pm25"].iloc[0])
    assert analytics.hourly_means(conn, start, NOW, ["no-01"], only_ok=False)["n"].iloc[0] == 60


def test_coluna_toda_nula_vira_nan(conn):
    insert(conn, [reading("no-01", -60 + m, humidity=None) for m in range(60)])
    h = analytics.hourly_means(conn, NOW - timedelta(hours=1), NOW, ["no-01"])
    assert h["pm25"].iloc[0] == 10.0 and pd.isna(h["humidity"].iloc[0])


def test_sem_leituras_devolve_colunas_esperadas(conn):
    h = analytics.hourly_means(conn, NOW - timedelta(hours=1), NOW)
    assert h.empty and list(h.columns) == analytics.HOURLY_COLUMNS


# ---------------------------------------------------------------- horas suspeitas (sensor sem partículas)

def hour_with(values: list[float], start: int = -120, **extra) -> list[dict]:
    """Uma leitura por minuto, a partir do minuto `start`, com o PM2,5 de cada posição de `values`."""
    return [reading("no-01", start + m, pm25=v, **extra) for m, v in enumerate(values)]


@pytest.mark.parametrize("lows, suspect", [(14, False), (15, True), (60, True)])
def test_hora_com_um_quarto_das_leituras_abaixo_de_meio_e_suspeita(conn, lows, suspect):
    insert(conn, hour_with([0.0] * lows + [40.0] * (60 - lows)))
    h = analytics.hourly_means(conn, NOW - timedelta(hours=3), NOW, ["no-01"])
    assert h["n"].iloc[0] == 60                              # as leituras continuam contadas
    assert bool(h["suspeita"].iloc[0]) is suspect
    assert bool(pd.isna(h["pm25"].iloc[0])) is suspect       # hora suspeita não tem média
    if not suspect:
        assert h["pm25"].iloc[0] == pytest.approx(40.0 * (60 - lows) / 60)   # as zeradas entram na média


@pytest.mark.parametrize("value, suspect", [(0.9, True), (1.0, False)])
def test_hora_com_media_abaixo_de_um_e_suspeita(conn, value, suspect):
    insert(conn, hour_with([value] * 60))                    # nenhuma leitura abaixo de 0,5: vale só a média
    h = analytics.hourly_means(conn, NOW - timedelta(hours=3), NOW, ["no-01"])
    assert bool(h["suspeita"].iloc[0]) is suspect


def test_hora_suspeita_perde_todas_as_medias(conn):
    insert(conn, hour_with([0.0] * 60))
    h = analytics.hourly_means(conn, NOW - timedelta(hours=3), NOW, ["no-01"])
    assert h[list(analytics.VARIABLES)].iloc[0].isna().all()


def test_hora_suspeita_nao_atrapalha_as_vizinhas(conn):
    insert(conn, hour_with([10.0] * 60, start=-180) + hour_with([0.0] * 60, start=-120) + hour_with([10.0] * 60, start=-60))
    h = analytics.hourly_means(conn, NOW - timedelta(hours=3), NOW, ["no-01"])
    assert list(h["n"]) == [60, 60, 60]
    assert list(h["suspeita"]) == [False, True, False]
    assert h["pm25"].iloc[0] == 10.0 and pd.isna(h["pm25"].iloc[1]) and h["pm25"].iloc[2] == 10.0


def test_hora_comum_nao_e_suspeita(conn):
    insert(conn, hour_with([12.0] * 60))
    h = analytics.hourly_means(conn, NOW - timedelta(hours=3), NOW, ["no-01"])
    assert not h["suspeita"].iloc[0] and h["pm25"].iloc[0] == 12.0


def test_so_leituras_ok_contam_para_a_regra(conn):
    """50 leituras ok com 40 µg/m³ e 10 marcadas em zero: as marcadas não entram na conta nem derrubam a hora."""
    insert(conn, hour_with([40.0] * 50) + hour_with([0.0] * 10, start=-70, quality="umid_fora_faixa"))
    h = analytics.hourly_means(conn, NOW - timedelta(hours=3), NOW, ["no-01"])
    assert h["n"].iloc[0] == 50 and not h["suspeita"].iloc[0] and h["pm25"].iloc[0] == 40.0


def test_sem_o_filtro_de_qualidade_nenhuma_hora_e_suspeita(conn):
    insert(conn, hour_with([0.0] * 60))
    h = analytics.hourly_means(conn, NOW - timedelta(hours=3), NOW, ["no-01"], only_ok=False)
    assert not h["suspeita"].iloc[0] and h["pm25"].iloc[0] == 0.0


def test_sem_descartar_a_hora_suspeita_ela_so_continua_marcada(conn):
    insert(conn, hour_with([0.0] * 60))
    h = analytics.hourly_means(conn, NOW - timedelta(hours=3), NOW, ["no-01"], drop_suspect=False)
    assert h["suspeita"].iloc[0] and h["pm25"].iloc[0] == 0.0 and h["n"].iloc[0] == 60


def test_comparacao_nao_traz_o_observado_de_hora_suspeita(conn):
    insert(conn, hour_with([10.0] * 60, start=-180) + hour_with([0.0] * 60, start=-120) + hour_with([20.0] * 60, start=-60))
    comp = analytics.forecast_comparison(conn, "no-01", NOW + timedelta(minutes=30))
    observed = comp.series[analytics.OBSERVED]
    assert observed[pd.Timestamp(NOW - timedelta(hours=3))] == 10.0
    assert pd.isna(observed[pd.Timestamp(NOW - timedelta(hours=2))])
    assert observed[pd.Timestamp(NOW - timedelta(hours=1))] == 20.0


# ---------------------------------------------------------------- estado dos nós

@pytest.mark.parametrize("minutes_after, expected", [(2, "em_operacao"), (10, "atrasado"), (20, "sem_dados")])
def test_estado_pelo_ultimo_envio(conn, minutes_after, expected):
    insert(conn, [reading("no-01", -1, received_delay_s=0)])
    status = analytics.device_status(conn, NOW - timedelta(minutes=1) + timedelta(minutes=minutes_after))
    assert status["status"].iloc[0] == expected
    assert status["minutes_since"].iloc[0] == pytest.approx(minutes_after)


def test_estado_traz_a_leitura_mais_recente(conn):
    insert(conn, [reading("no-01", -2, pm25=5.0), reading("no-01", -1, pm25=7.0), reading("no-02", -1, pm25=9.0)])
    status = analytics.device_status(conn, NOW).set_index("device_id")
    assert status.loc["no-01", "pm25"] == 7.0 and status.loc["no-02", "pm25"] == 9.0
    assert status.loc["no-01", "ts_sensor"] == pd.Timestamp(NOW - timedelta(minutes=1))


def test_estado_traz_a_ultima_versao_do_firmware(conn):
    db.insert_batch(conn, "no-01", [reading("no-01", -2)], NOW, firmware="v1")
    db.insert_batch(conn, "no-01", [reading("no-01", -1)], NOW + timedelta(minutes=1), firmware="v2")
    db.insert_batch(conn, "no-02", [reading("no-02", -1)], NOW)
    status = analytics.device_status(conn, NOW).set_index("device_id")
    assert status.loc["no-01", "firmware"] == "v2" and pd.isna(status.loc["no-02", "firmware"])


def test_estado_deixa_de_fora_nos_de_teste(conn):
    insert(conn, [reading("no-01", -1), reading("teste-https", -1)])
    assert list(analytics.device_status(conn, NOW)["device_id"]) == ["no-01"]


def test_estado_sem_nos(conn):
    status = analytics.device_status(conn, NOW)
    assert status.empty and list(status.columns) == analytics.STATUS_COLUMNS


# ---------------------------------------------------------------- saúde da coleta

def test_saude_separa_perda_reinicio_e_duplicata(conn):
    rows = [reading("no-01", -60 + m, seq=m) for m in range(30)]                      # boot 1
    rows += [reading("no-01", -60 + m, boot=2, seq=m - 30) for m in range(30, 60) if m != 40]  # boot 2, perde seq 10
    insert(conn, rows)
    db.insert_batch(conn, "no-01", rows[:3], NOW)                                     # reenvio: 3 duplicatas
    health = analytics.collection_health(conn, NOW - timedelta(hours=1), NOW).iloc[0]
    assert health["mensagens_perdidas"] == 1
    assert health["reinicios"] == 1
    assert health["duplicatas_descartadas"] == 3
    assert health["maior_lacuna_min"] == 1
    assert health["completude"] == pytest.approx(59 / 60)


def test_saude_conta_lacuna_final_e_leituras_marcadas(conn):
    insert(conn, [reading("no-01", -60 + m, quality="suspect" if m < 5 else "ok") for m in range(40)])
    health = analytics.collection_health(conn, NOW - timedelta(hours=1), NOW).iloc[0]
    assert health["maior_lacuna_min"] == 20                 # nada desde o minuto -21
    assert health["leituras_marcadas"] == 5


def test_saude_deixa_de_fora_nos_de_teste_salvo_se_pedidos(conn):
    insert(conn, [reading("no-01", -1), reading("teste-https", -1)])
    start = NOW - timedelta(hours=1)
    assert list(analytics.collection_health(conn, start, NOW)["device_id"]) == ["no-01"]
    assert list(analytics.collection_health(conn, start, NOW, ["teste-https"])["device_id"]) == ["teste-https"]


# ---------------------------------------------------------------- faixas de qualidade do ar

@pytest.mark.parametrize("pm25, band", [
    (0.0, "Boa"), (25.0, "Boa"), (25.1, "Moderada"), (75.0, "Ruim"), (125.0, "Muito ruim"), (125.1, "Péssima"),
])
def test_cada_limite_pertence_a_faixa_de_baixo(pm25, band):
    assert analytics.air_quality(pm25) == band


@pytest.mark.parametrize("pm25", [None, float("nan"), -1.0])
def test_sem_valor_valido_nao_ha_faixa(pm25):
    assert analytics.air_quality(pm25) is None


def test_faixas_sao_as_mesmas_do_app():
    """O app Android confere o mesmo arquivo, então as duas pontas não se afastam sem um teste falhar."""
    shared = json.loads((Path(__file__).parents[2] / "shared" / "air-quality-bands.json").read_text(encoding="utf-8"))
    assert [(b["label"], b["upper_bound"]) for b in shared] == [
        (label, None if math.isinf(bound) else bound) for bound, label in analytics.AIR_QUALITY_BANDS]


# ---------------------------------------------------------------- nós em produção

def test_nos_em_producao_tem_leituras_e_nao_sao_de_teste(conn):
    insert(conn, [reading("no-02", -1), reading("no-01", -1), reading("teste-https", -1)])
    with conn:
        conn.execute("INSERT INTO devices (device_id, first_seen) VALUES ('no-03', ?)", (db.iso(NOW),))
    assert analytics.production_devices(conn) == ["no-01", "no-02"]


# ---------------------------------------------------------------- previsto × observado

def test_comparacao_com_persistencia_e_modelo(conn):
    insert(conn, [reading("no-01", -180 + m, pm25=10.0 + (m // 60) * 5) for m in range(180)])  # 10, 15, 20
    with conn:
        for h, value in ((2, 14.0), (1, 21.0)):
            target = NOW - timedelta(hours=h)
            conn.execute("INSERT INTO forecasts (device_id, generated_at, target_hour, predicted_pm25, model_name,"
                         " model_version) VALUES (?, ?, ?, ?, 'ridge', 'v1')",
                         ("no-01", db.iso(target - timedelta(minutes=5)), db.iso(target), value))
    comp = analytics.forecast_comparison(conn, "no-01", NOW + timedelta(minutes=30))
    assert list(comp.series.columns) == [analytics.OBSERVED, analytics.PERSISTENCE, "ridge v1"]
    assert comp.series.loc[pd.Timestamp(NOW - timedelta(hours=1)), analytics.PERSISTENCE] == 15.0

    m = comp.metrics.set_index("previsor")
    assert m.loc[analytics.PERSISTENCE, "horas"] == 2      # horas -2 e -1 (a -3 não tem hora anterior)
    assert m.loc[analytics.PERSISTENCE, "mae"] == pytest.approx(5.0)
    assert m.loc["ridge v1", "mae"] == pytest.approx(1.0)
    assert m.loc["ridge v1", "skill"] == pytest.approx(0.8)
    assert m.loc[analytics.PERSISTENCE, "skill"] == pytest.approx(0.0)


def add_forecasts(conn, name: str, version: str, values: dict[int, float]) -> None:
    """Previsões de `name version` para as horas-alvo `NOW − h` (h em horas), com o valor dado."""
    with conn:
        for h, value in values.items():
            target = NOW - timedelta(hours=h)
            conn.execute("INSERT INTO forecasts (device_id, generated_at, target_hour, predicted_pm25, model_name,"
                         " model_version) VALUES (?, ?, ?, ?, ?, ?)",
                         ("no-01", db.iso(target - timedelta(minutes=5)), db.iso(target), value, name, version))


def hourly_levels(conn, levels: list[float]) -> None:
    """Uma leitura por minuto em cada uma das últimas horas cheias, com o PM2,5 de `levels` (a mais antiga primeiro)."""
    hours = len(levels)
    insert(conn, [reading("no-01", -60 * hours + m, pm25=levels[m // 60]) for m in range(60 * hours)])


def test_persistencia_e_modelo_sao_comparados_nas_mesmas_horas(conn):
    hourly_levels(conn, [10.0, 15.0, 25.0, 20.0])
    add_forecasts(conn, "ridge", "v0", {2: 24.0, 1: 21.0})   # o modelo só previu duas das três horas com persistência
    m = analytics.forecast_comparison(conn, "no-01", NOW + timedelta(minutes=30)).metrics.set_index("previsor")

    assert m.loc[analytics.PERSISTENCE, "horas"] == m.loc["ridge v0", "horas"] == 2
    assert m.loc[analytics.PERSISTENCE, "mae"] == pytest.approx(7.5)         # erros de 10 e 5; a hora -3 (5) fica fora
    assert m.loc[analytics.PERSISTENCE, "rmse"] == pytest.approx(math.sqrt(62.5))
    assert m.loc["ridge v0", "mae"] == pytest.approx(1.0)
    assert m.loc["ridge v0", "skill"] == pytest.approx(1 - 1 / math.sqrt(62.5))


def test_modelos_com_horas_diferentes_ficam_todos_nas_horas_que_tem_em_comum(conn):
    hourly_levels(conn, [10.0, 15.0, 25.0, 20.0])
    add_forecasts(conn, "ridge", "v0", {3: 15.0, 2: 25.0, 1: 20.0})
    add_forecasts(conn, "ridge", "v1", {1: 18.0})
    m = analytics.forecast_comparison(conn, "no-01", NOW + timedelta(minutes=30)).metrics.set_index("previsor")

    assert set(m["horas"]) == {1}                                         # só a hora -1 tem os três previsores
    assert m.loc[analytics.PERSISTENCE, "mae"] == pytest.approx(5.0)
    assert m.loc["ridge v0", "mae"] == pytest.approx(0.0)
    assert m.loc["ridge v1", "mae"] == pytest.approx(2.0)


def test_modelos_sem_hora_em_comum_ficam_cada_um_com_as_suas_horas(conn):
    hourly_levels(conn, [10.0, 15.0, 25.0, 20.0])
    add_forecasts(conn, "ridge", "v0", {3: 15.0})            # a versão antiga parou antes de a nova começar
    add_forecasts(conn, "ridge", "v1", {1: 18.0})
    m = analytics.forecast_comparison(conn, "no-01", NOW + timedelta(minutes=30)).metrics.set_index("previsor")

    assert dict(m["horas"]) == {analytics.PERSISTENCE: 3, "ridge v0": 1, "ridge v1": 1}
    assert m.loc["ridge v0", "skill"] == pytest.approx(1.0)  # acerto exato contra erro de 5 da persistência
    assert m.loc["ridge v1", "skill"] == pytest.approx(0.6)  # 1 − 2/5, cada um contra a persistência nas suas horas


def test_modelo_sem_nenhuma_hora_para_comparar_nao_derruba_a_tabela(conn):
    hourly_levels(conn, [10.0, 15.0, 25.0, 20.0])
    add_forecasts(conn, "ridge", "v0", {2: 24.0, 1: 21.0})
    add_forecasts(conn, "ridge", "v1", {0: 18.0})            # só a hora em andamento, que ainda não tem observação
    m = analytics.forecast_comparison(conn, "no-01", NOW + timedelta(minutes=30)).metrics.set_index("previsor")

    assert list(m.index) == [analytics.PERSISTENCE, "ridge v0"]
    assert set(m["horas"]) == {2}


def test_skill_score_usa_as_mesmas_horas_da_persistencia(conn):
    insert(conn, [reading("no-01", -180 + m, pm25=10.0 + (m // 60) * 5) for m in range(180)])  # 10, 15, 20
    with conn:
        # a hora -3 não tem persistência (falta a hora anterior): o acerto exato nela não pode contar
        for h, value in ((3, 10.0), (1, 21.0)):
            target = NOW - timedelta(hours=h)
            conn.execute("INSERT INTO forecasts (device_id, generated_at, target_hour, predicted_pm25, model_name,"
                         " model_version) VALUES (?, ?, ?, ?, 'ridge', 'v1')",
                         ("no-01", db.iso(target - timedelta(minutes=5)), db.iso(target), value))
    m = analytics.forecast_comparison(conn, "no-01", NOW + timedelta(minutes=30)).metrics.set_index("previsor")
    assert m.loc["ridge v1", "horas"] == 1
    assert m.loc["ridge v1", "rmse"] == pytest.approx(1.0)
    assert m.loc["ridge v1", "skill"] == pytest.approx(0.8)  # 1 − 1/5, só na hora -1


def test_skill_score_indefinido_com_persistencia_perfeita(conn):
    insert(conn, [reading("no-01", -120 + m, pm25=10.0) for m in range(120)])
    m = analytics.forecast_comparison(conn, "no-01", NOW + timedelta(minutes=30)).metrics.set_index("previsor")
    assert m.loc[analytics.PERSISTENCE, "rmse"] == 0.0
    assert pd.isna(m.loc[analytics.PERSISTENCE, "skill"])


def test_comparacao_sem_dados(conn):
    comp = analytics.forecast_comparison(conn, "no-01", NOW)
    assert comp.series.isna().all().all()
    assert comp.metrics.empty and list(comp.metrics.columns) == analytics.METRIC_COLUMNS
