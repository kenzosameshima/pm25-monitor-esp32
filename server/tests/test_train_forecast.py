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
    assert tf.MIN_SAMPLES == 45
    insert_hours(conn, "no-01", [10.0, 20.0], per_hour=50)
    insert_hours(conn, "no-02", [10.0, 20.0], per_hour=44)
    assert list(tf.hourly_series(conn, "no-01")["pm25"]) == [10.0, 20.0]
    assert tf.hourly_series(conn, "no-02")["pm25"].isna().all()           # 44 < 45 leituras: hora ausente
    assert tf.hourly_series(conn, "no-01", min_samples=51)["pm25"].isna().all()


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


# ---------------- Reprodutibilidade, previsões do teste final e várias sementes ----------------

def db_path(conn):
    return conn.execute("PRAGMA database_list").fetchone()[2]


def fake_mlp(train, test, seed=42, **_):
    """Substitui a MLP nos testes, sem TensorFlow: persistência deslocada por um valor que depende da semente."""
    return test["pm25"].to_numpy(float) + (seed % 5) * 0.5


@pytest.fixture
def mlp_falsa(monkeypatch):
    import sys
    import types

    monkeypatch.setitem(sys.modules, "tensorflow", types.ModuleType("tensorflow"))
    monkeypatch.setattr(tf, "predict_mlp", fake_mlp)


def run_main(conn, tmp_path, *extra):
    insert_hours(conn, "no-01", series(24 * 40, seed=2))
    insert_hours(conn, "no-02", series(24 * 40, seed=3))
    out = tmp_path / "relatorio.json"
    rc = tf.main(["--db", db_path(conn), "--min-samples", "1", "--out", str(out), *extra])
    return rc, json.loads(out.read_text(encoding="utf-8")) if out.exists() else None


def test_relatorio_registra_versoes_e_hash_do_banco(conn, tmp_path):
    import hashlib
    import platform
    import sklearn

    rc, report = run_main(conn, tmp_path, "--no-mlp")
    assert rc == 0
    env = report["environment"]
    assert env["python"] == platform.python_version()
    assert env["numpy"] == np.__version__ and env["pandas"] == pd.__version__
    assert env["scikit-learn"] == sklearn.__version__
    assert set(env) == {"python", "numpy", "pandas", "scikit-learn", "tensorflow"}   # None se não instalado
    path = db_path(conn)
    with open(path, "rb") as fh:
        assert report["database"]["sha256"] == hashlib.sha256(fh.read()).hexdigest()
    assert report["database"]["file"] == "pm25.db"


def test_predictions_csv_traz_previsoes_do_teste_final(conn, tmp_path):
    csv_path = tmp_path / "previsao_teste.csv"
    rc, report = run_main(conn, tmp_path, "--no-mlp", "--predictions-csv", str(csv_path))
    assert rc == 0
    df = pd.read_csv(csv_path)
    assert list(df.columns) == ["hora", "no", "observado", "persistencia", "ridge"]   # sem mlp com --no-mlp
    assert len(df) == report["results"]["Ridge"]["test"]["n"] == report["results"][tf.PERSISTENCE]["test"]["n"]
    assert set(df["no"]) == {"no-01", "no-02"}
    assert df.groupby("no")["hora"].apply(lambda h: h.is_monotonic_increasing).all()
    assert all(h.endswith("Z") for h in df["hora"])
    assert pd.Timestamp(df["hora"].min()) > pd.Timestamp(report["test_window"][0])    # só horas do teste final

    # as colunas reproduzem as métricas do relatório
    rmse = float(np.sqrt(np.mean((df["ridge"] - df["observado"]) ** 2)))
    assert rmse == pytest.approx(report["results"]["Ridge"]["test"]["rmse"])
    # a persistência prevista para a hora h é o valor observado em h − 1 (mesmo nó, horas seguidas)
    for _, g in df.groupby("no"):
        g = g.assign(t=pd.to_datetime(g["hora"]))
        consecutive = g["t"].diff() == pd.Timedelta(hours=1)
        assert (g["persistencia"][consecutive] == g["observado"].shift(1)[consecutive]).all()


def test_sem_predictions_csv_nenhum_arquivo_e_criado(conn, tmp_path):
    rc, _ = run_main(conn, tmp_path, "--no-mlp")
    assert rc == 0
    assert sorted(p.name for p in tmp_path.iterdir() if p.suffix == ".csv") == []


def test_predictions_csv_inclui_a_mlp_da_semente_de_referencia(conn, tmp_path, mlp_falsa):
    csv_path = tmp_path / "previsao_teste.csv"
    rc, _ = run_main(conn, tmp_path, "--predictions-csv", str(csv_path), "--seeds", "3")
    assert rc == 0
    df = pd.read_csv(csv_path)
    assert list(df.columns) == ["hora", "no", "observado", "persistencia", "ridge", "mlp"]
    assert np.allclose(df["mlp"] - df["persistencia"], (42 % 5) * 0.5)                 # semente 42, não 43 nem 44


def test_evaluate_com_predictions_nao_muda_as_metricas(conn):
    insert_hours(conn, "no-01", series(24 * 40, seed=5))
    frame = tf.build_dataset(conn, ["no-01"], min_samples=1)
    folds, final = tf.make_splits(frame.index, 7, 14, 7)
    models = {tf.PERSISTENCE: tf.predict_persistence, "Ridge": tf.predict_ridge}
    base = tf.evaluate(frame, models, folds, final)
    captured: dict = {}
    assert tf.evaluate(frame, models, folds, final, predictions=captured) == base
    assert set(captured["models"]) == set(models) and len(captured["hour"]) == base["Ridge"]["test"]["n"]


def test_agregacao_de_sementes_media_e_desvio_amostral():
    def m(rmse, skill):
        return {"n": 10, "mae": 0.0, "rmse": rmse, "skill": skill}

    per_seed = [{"seed": 42, "validation": m(1.0, 0.1), "test": m(2.0, 0.2)},
                {"seed": 43, "validation": m(2.0, 0.2), "test": m(4.0, 0.3)},
                {"seed": 44, "validation": m(3.0, 0.3), "test": m(6.0, 0.4)}]
    agg = tf.aggregate_seeds(per_seed)
    assert agg["seeds"] == [42, 43, 44]
    assert agg["validation"] == {"rmse_mean": pytest.approx(2.0), "rmse_std": pytest.approx(1.0),
                                 "skill_mean": pytest.approx(0.2), "skill_std": pytest.approx(0.1)}
    assert agg["test"]["rmse_mean"] == pytest.approx(4.0) and agg["test"]["rmse_std"] == pytest.approx(2.0)
    assert agg["per_seed"] == per_seed


def test_seeds_repete_o_treino_e_reporta_media_e_desvio(conn, tmp_path, mlp_falsa):
    rc, report = run_main(conn, tmp_path, "--seeds", "3")
    assert rc == 0
    mlp = report["results"]["MLP (Keras)"]
    agg = mlp["seeds"]
    assert agg["seeds"] == [42, 43, 44] and report["hyperparameters"]["seeds"] == 3
    # a semente de referência continua sendo a 42: é o resultado principal e a primeira da lista
    assert agg["per_seed"][0]["test"] == mlp["test"] and agg["per_seed"][0]["validation"] == mlp["validation"]

    # confere com um cálculo independente, semente a semente
    frame = tf.build_dataset(db_conn(conn), ["no-01", "no-02"], min_samples=1)
    folds, final = tf.make_splits(frame.index, 7, 14, 7)
    rmses = [tf.evaluate(frame, {"m": fake_mlp}, folds, final, seed=s)["m"]["test"]["rmse"] for s in (42, 43, 44)]
    assert [r["test"]["rmse"] for r in agg["per_seed"]] == pytest.approx(rmses)
    assert agg["test"]["rmse_mean"] == pytest.approx(np.mean(rmses))
    assert agg["test"]["rmse_std"] == pytest.approx(np.std(rmses, ddof=1))
    assert rmses[0] != rmses[1]                       # as sementes de fato mudam o resultado


def test_uma_semente_mantem_o_formato_anterior(conn, tmp_path, mlp_falsa):
    rc, report = run_main(conn, tmp_path)               # --seeds padrão: 1
    assert rc == 0
    assert "seeds" not in report["results"]["MLP (Keras)"]
    assert report["hyperparameters"]["seeds"] == 1


def test_seeds_invalido_retorna_erro(conn, tmp_path, capsys):
    insert_hours(conn, "no-01", series(24 * 40))
    assert tf.main(["--db", db_path(conn), "--min-samples", "1", "--seeds", "0"]) == 1
    assert "pelo menos 1" in capsys.readouterr().err
    assert tf.main(["--db", db_path(conn), "--min-samples", "1", "--no-mlp", "--seeds", "3"]) == 1
    assert "--no-mlp" in capsys.readouterr().err


def db_conn(conn):
    return db.connect(db_path(conn), readonly=True)
