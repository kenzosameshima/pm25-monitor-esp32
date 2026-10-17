"""Testes da avaliação offline de modelos de previsão: dados sintéticos, sem depender da coleta real."""

import json

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("sklearn")

from app import db  # noqa: E402
from app import forecasting as fc  # noqa: E402
from scripts import train_forecast as tf  # noqa: E402
from tests.forecast_data import START, conn, db_path, insert_hours, series  # noqa: E402,F401

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
    frame = fc.dataset(conn, ["no-01"], min_samples=1)
    folds, final = tf.make_splits(frame.index, 7, 14, 7)
    res = tf.evaluate(frame, {tf.PERSISTENCE: tf.predict_persistence, "Ridge": tf.predict_ridge}, folds, final)
    assert res[tf.PERSISTENCE]["test"]["skill"] == pytest.approx(0.0)
    assert res["Ridge"]["validation"]["skill"] > 0.1
    assert res["Ridge"]["test"]["skill"] > 0.1


def test_main_gera_relatorio(conn, tmp_path, capsys):
    insert_hours(conn, "no-01", series(24 * 40, seed=2))
    insert_hours(conn, "no-02", series(24 * 40, seed=3))
    out = tmp_path / "relatorio.json"
    rc = tf.main(["--db", db_path(conn), "--no-mlp",
                  "--min-samples", "1", "--out", str(out)])
    assert rc == 0
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["devices"] == ["no-01", "no-02"]
    assert set(report["results"]) == {tf.PERSISTENCE, "Ridge", tf.GBOOST}
    assert report["results"]["Ridge"]["test"]["n"] > 0
    assert "Ridge" in capsys.readouterr().out


def test_main_nao_escreve_no_banco(conn):
    insert_hours(conn, "no-01", series(24 * 40))
    path = db_path(conn)
    before = conn.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]
    tf.main(["--db", path, "--no-mlp", "--min-samples", "1"])
    assert conn.execute("SELECT COUNT(*) FROM measurements").fetchone()[0] == before
    assert conn.execute("SELECT COUNT(*) FROM forecasts").fetchone()[0] == 0


def test_dados_insuficientes_retorna_erro(conn, capsys):
    insert_hours(conn, "no-01", series(60))
    path = db_path(conn)
    assert tf.main(["--db", path, "--no-mlp", "--min-samples", "1"]) == 1
    assert "insuficientes" in capsys.readouterr().err


def test_banco_inexistente(tmp_path, capsys):
    assert tf.main(["--db", str(tmp_path / "nao-existe.db")]) == 1
    assert "não encontrado" in capsys.readouterr().err


def test_gradient_boosting_supera_a_persistencia_em_serie_com_reversao_a_media(conn):
    insert_hours(conn, "no-01", series(24 * 45, seed=1))
    frame = fc.dataset(conn, ["no-01"], min_samples=1)
    folds, final = tf.make_splits(frame.index, 7, 14, 7)
    res = tf.evaluate(frame, {tf.GBOOST: tf.predict_gboost}, folds, final)
    # a série é linear: as árvores a aproximam em degraus e ganham menos que o Ridge, mas ganham
    assert res[tf.GBOOST]["validation"]["skill"] > 0.05
    assert res[tf.GBOOST]["test"]["skill"] > 0.05


# ---------------- Reprodutibilidade, previsões do teste final e várias sementes ----------------

def fake_mlp(train, test, seed=42, **_):
    """Substitui a MLP nos testes, mais rápida: persistência deslocada por um valor que depende da semente."""
    return test["pm25"].to_numpy(float) + (seed % 5) * 0.5


@pytest.fixture
def mlp_falsa(monkeypatch):
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
    assert set(env) == {"python", "numpy", "pandas", "scikit-learn"}
    path = db_path(conn)
    with open(path, "rb") as fh:
        assert report["database"]["sha256"] == hashlib.sha256(fh.read()).hexdigest()
    assert report["database"]["file"] == "pm25.db"


def test_predictions_csv_traz_previsoes_do_teste_final(conn, tmp_path):
    csv_path = tmp_path / "previsao_teste.csv"
    rc, report = run_main(conn, tmp_path, "--no-mlp", "--predictions-csv", str(csv_path))
    assert rc == 0
    df = pd.read_csv(csv_path)
    assert list(df.columns) == ["hora", "no", "observado", "persistencia", "ridge", "gboost"]   # sem mlp com --no-mlp
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
    assert list(df.columns) == ["hora", "no", "observado", "persistencia", "ridge", "gboost", "mlp"]
    assert np.allclose(df["mlp"] - df["persistencia"], (42 % 5) * 0.5)                 # semente 42, não 43 nem 44


def test_evaluate_com_predictions_nao_muda_as_metricas(conn):
    insert_hours(conn, "no-01", series(24 * 40, seed=5))
    frame = fc.dataset(conn, ["no-01"], min_samples=1)
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
    mlp = report["results"][tf.MLP]
    agg = mlp["seeds"]
    assert agg["seeds"] == [42, 43, 44] and report["hyperparameters"]["seeds"] == 3
    # a semente de referência continua sendo a 42: é o resultado principal e a primeira da lista
    assert agg["per_seed"][0]["test"] == mlp["test"] and agg["per_seed"][0]["validation"] == mlp["validation"]

    # confere com um cálculo independente, semente a semente
    frame = fc.dataset(db_conn(conn), ["no-01", "no-02"], min_samples=1)
    folds, final = tf.make_splits(frame.index, 7, 14, 7)
    rmses = [tf.evaluate(frame, {"m": fake_mlp}, folds, final, seed=s)["m"]["test"]["rmse"] for s in (42, 43, 44)]
    assert [r["test"]["rmse"] for r in agg["per_seed"]] == pytest.approx(rmses)
    assert agg["test"]["rmse_mean"] == pytest.approx(np.mean(rmses))
    assert agg["test"]["rmse_std"] == pytest.approx(np.std(rmses, ddof=1))
    assert rmses[0] != rmses[1]                       # as sementes de fato mudam o resultado


def test_uma_semente_mantem_o_formato_anterior(conn, tmp_path, mlp_falsa):
    rc, report = run_main(conn, tmp_path)               # --seeds padrão: 1
    assert rc == 0
    assert "seeds" not in report["results"][tf.MLP]
    assert report["hyperparameters"]["seeds"] == 1


def test_seeds_invalido_retorna_erro(conn, tmp_path, capsys):
    insert_hours(conn, "no-01", series(24 * 40))
    assert tf.main(["--db", db_path(conn), "--min-samples", "1", "--seeds", "0"]) == 1
    assert "pelo menos 1" in capsys.readouterr().err
    assert tf.main(["--db", db_path(conn), "--min-samples", "1", "--no-mlp", "--seeds", "3"]) == 1
    assert "--no-mlp" in capsys.readouterr().err


def db_conn(conn):
    return db.connect(db_path(conn), readonly=True)
