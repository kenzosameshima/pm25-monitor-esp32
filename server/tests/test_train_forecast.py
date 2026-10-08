"""Testes da avaliação offline de modelos de previsão: dados sintéticos, sem depender da coleta real."""

import json
import math
import random
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("sklearn")

from app import db  # noqa: E402
from scripts import train_forecast as tf  # noqa: E402

START = datetime(2026, 9, 1, tzinfo=timezone.utc)


def series(hours: int, seed: int = 0) -> list[float]:
    """PM2,5 horário com reversão à média: a persistência erra bastante, um modelo linear acerta mais."""
    rng = random.Random(seed)
    x, out = 15.0, []
    for h in range(hours):
        daily = 6 * math.sin(2 * math.pi * (h % 24) / 24)
        x = 0.4 * x + 0.6 * (15 + daily) + rng.gauss(0, 2.5)
        out.append(max(1.0, x))
    return out


def insert_hours(conn, device: str, values: list[float], per_hour: int = 1, quality: str = "ok") -> None:
    rows = []
    for h, v in enumerate(values):
        for m in range(per_hour):
            ts = START + timedelta(hours=h, minutes=m)
            rows.append({"device_id": device, "boot_id": 1, "seq": h * 60 + m, "ts_sensor": db.iso(ts),
                         "ts_received": db.iso(ts), "pm1": None, "pm25": v, "pm10": None, "pm25_cf1": None,
                         "temperature": 20.0 + h % 24 / 4, "humidity": 60.0, "rssi": -60, "uptime_s": 0,
                         "samples": 58, "schema_version": "1", "quality": quality})
    db.insert_batch(conn, device, rows, START)


@pytest.fixture
def conn(tmp_path):
    c = db.connect(str(tmp_path / "pm25.db"))
    db.init_db(c)
    yield c
    c.close()


def test_hora_com_poucas_leituras_vira_lacuna(conn):
    insert_hours(conn, "no-01", [10.0, 20.0], per_hour=40)           # hora 0 e 1 completas
    insert_hours(conn, "no-01", [30.0], per_hour=5)                  # mesma hora 0, mesmas chaves: ignorado
    hourly = tf.hourly_series(conn, "no-01", min_samples=30)
    assert list(hourly["pm25"]) == [10.0, 20.0]
    sparse = tf.hourly_series(conn, "no-01", min_samples=41)
    assert sparse["pm25"].isna().all()


def test_leituras_com_qualidade_ruim_sao_ignoradas(conn):
    insert_hours(conn, "no-01", [10.0, 20.0, 30.0], quality="suspect")
    assert tf.hourly_series(conn, "no-01", min_samples=1).empty


def test_features_alvo_e_atrasos_sem_vazamento():
    idx = pd.date_range(START, periods=48, freq="h")
    hourly = pd.DataFrame({"pm25": np.arange(48.0), "humidity": 60.0, "temperature": 20.0, "n": 60}, index=idx)
    f = tf.make_features(hourly, "no-01")
    t = idx[30]
    assert f.loc[t, "pm25"] == 30
    assert f.loc[t, "y"] == 31                    # alvo: média da hora seguinte
    assert f.loc[t, "lag_1"] == 29 and f.loc[t, "lag_24"] == 6
    assert math.isnan(f.iloc[-1]["y"])            # a última hora não tem alvo


def test_dataset_descarta_linhas_com_lacuna_nos_atrasos(conn):
    values = series(100)
    insert_hours(conn, "no-01", values[:50])
    insert_hours(conn, "no-01", [])  # sem efeito
    frame = tf.build_dataset(conn, ["no-01"], min_samples=1)
    assert frame.index.min() == pd.Timestamp(START) + pd.Timedelta(hours=24)   # precisa de 24 h de histórico
    assert frame.index.max() == pd.Timestamp(START) + pd.Timedelta(hours=48)   # a hora 49 não tem alvo
    assert frame[tf.FEATURES].notna().all().all()


def test_divisoes_sao_cronologicas_e_sem_sobreposicao():
    idx = pd.date_range(START, periods=24 * 40, freq="h")
    folds, final = tf.make_splits(idx, test_days=7, min_train_days=14, fold_days=7)
    assert len(folds) == 2
    assert folds[0][1] == folds[1][0] and folds[-1][1] <= final[0]
    assert final[1] - final[0] == pd.Timedelta(days=7)
    frame = pd.DataFrame({"y": 0.0}, index=idx)
    for start, end in folds + [final]:
        train, test = tf.train_test(frame, start, end)
        assert train.index.max() + pd.Timedelta(hours=1) < start      # o alvo do treino é anterior ao teste
        assert test.index.min() >= start and test.index.max() < end


def test_skill_score():
    y = np.array([10.0, 12.0, 11.0, 15.0])
    p = np.array([9.0, 10.0, 12.0, 11.0])
    assert tf.metrics(y, p, p)["skill"] == pytest.approx(0.0)
    assert tf.metrics(y, y, p)["skill"] == pytest.approx(1.0)
    assert tf.metrics(y, y, p)["mae"] == 0.0
    assert tf.metrics(y, p, y)["skill"] is None                       # persistência perfeita: razão indefinida


def test_ridge_supera_a_persistencia_em_serie_com_reversao_a_media(conn):
    insert_hours(conn, "no-01", series(24 * 45, seed=1))
    frame = tf.build_dataset(conn, ["no-01"], min_samples=1)
    folds, final = tf.make_splits(frame.index, 7, 14, 7)
    res = tf.evaluate(frame, {tf.PERSISTENCE: tf.predict_persistence, "Ridge": tf.predict_ridge}, folds, final)
    assert res[tf.PERSISTENCE]["test"]["skill"] == pytest.approx(0.0)
    assert res["Ridge"]["validation"]["skill"] > 0.1
    assert res["Ridge"]["test"]["skill"] > 0.1


def test_main_gera_relatorio(conn, tmp_path, capsys):
    insert_hours(conn, "no-01", series(24 * 40, seed=2))
    insert_hours(conn, "no-02", series(24 * 40, seed=3))
    out = tmp_path / "relatorio.json"
    rc = tf.main(["--db", conn.execute("PRAGMA database_list").fetchone()[2], "--no-mlp",
                  "--min-samples", "1", "--out", str(out)])
    assert rc == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["devices"] == ["no-01", "no-02"]
    assert set(report["results"]) == {tf.PERSISTENCE, "Ridge"}
    assert report["results"]["Ridge"]["test"]["n"] > 0
    assert "Ridge" in capsys.readouterr().out


def test_main_nao_escreve_no_banco(conn):
    insert_hours(conn, "no-01", series(24 * 40))
    path = conn.execute("PRAGMA database_list").fetchone()[2]
    before = conn.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]
    tf.main(["--db", path, "--no-mlp", "--min-samples", "1"])
    assert conn.execute("SELECT COUNT(*) FROM measurements").fetchone()[0] == before
    assert conn.execute("SELECT COUNT(*) FROM forecasts").fetchone()[0] == 0


def test_dados_insuficientes_retorna_erro(conn, capsys):
    insert_hours(conn, "no-01", series(60))
    path = conn.execute("PRAGMA database_list").fetchone()[2]
    assert tf.main(["--db", path, "--no-mlp", "--min-samples", "1"]) == 1
    assert "insuficientes" in capsys.readouterr().err


def test_banco_inexistente(tmp_path, capsys):
    assert tf.main(["--db", str(tmp_path / "nao-existe.db")]) == 1
    assert "não encontrado" in capsys.readouterr().err


def test_mlp_keras_preve_com_formato_e_valores_validos(conn):
    pytest.importorskip("tensorflow")
    insert_hours(conn, "no-01", series(24 * 30, seed=4))
    frame = tf.build_dataset(conn, ["no-01"], min_samples=1)
    train, test = frame.iloc[:-100], frame.iloc[-100:]
    pred = tf.predict_mlp(train, test, seed=1, hidden=(8,), epochs=5, batch_size=64, patience=2)
    assert pred.shape == (len(test),)
    assert np.isfinite(pred).all()
    assert abs(pred.mean() - test["y"].mean()) < 10
