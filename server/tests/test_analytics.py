"""Testes das regras de análise compartilhadas pelo dashboard, pelos scripts e pela API de leitura."""

from datetime import datetime, timedelta, timezone

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
