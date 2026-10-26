"""Testes do módulo de previsão: dados de treino, linha do job, modelos e arquivo do modelo."""

from dataclasses import replace
from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("sklearn")

from app import forecasting as fc  # noqa: E402
from tests.forecast_data import START, conn, insert_hours, series  # noqa: E402,F401


def at(hours: int) -> pd.Timestamp:
    return pd.Timestamp(START) + pd.Timedelta(hours=hours)


# ---------------------------------------------------------------- dados

def test_hora_com_poucas_leituras_nao_entra(conn):
    assert fc.MIN_SAMPLES == 45
    insert_hours(conn, "no-01", series(30), per_hour=50)
    insert_hours(conn, "no-02", series(30), per_hour=44)          # 44 < 45 leituras: nenhuma hora vale
    frame = fc.dataset(conn, ["no-01", "no-02"])
    assert set(frame["device_id"]) == {"no-01"} and len(frame) == 30 - 24 - 1
    assert fc.dataset(conn, ["no-01"], min_samples=51).empty


def test_leituras_com_qualidade_ruim_sao_ignoradas(conn):
    insert_hours(conn, "no-01", series(30), quality="suspect")
    assert fc.dataset(conn, ["no-01"], min_samples=1).empty


def test_features_alvo_e_atrasos_sem_vazamento(conn):
    insert_hours(conn, "no-01", [float(h) for h in range(50)])
    frame = fc.dataset(conn, ["no-01"], min_samples=1)
    assert frame.index.min() == at(24)                            # precisa de 24 h de histórico
    assert frame.index.max() == at(48)                            # a hora 49 não tem alvo
    row = frame.loc[at(30)]
    assert row["pm25"] == 30 and row["y"] == 31                   # alvo: média da hora seguinte
    assert row["lag_1"] == 29 and row["lag_24"] == 6
    assert frame[fc.FEATURES].notna().all().all()


def test_dataset_sem_lista_deixa_de_fora_os_nos_de_teste(conn):
    insert_hours(conn, "no-01", series(30))
    insert_hours(conn, "teste-https", series(30))
    assert set(fc.dataset(conn, min_samples=1)["device_id"]) == {"no-01"}


def test_latest_row_usa_a_ultima_hora_completa(conn):
    insert_hours(conn, "no-01", [float(h) for h in range(30)])
    row = fc.latest_row(conn, "no-01", at(30) + timedelta(minutes=5), min_samples=1)
    assert list(row.index) == [at(29)]                            # prevê a hora 30, em andamento
    assert row.iloc[0]["pm25"] == 29 and row.iloc[0]["lag_24"] == 5
    assert "y" not in row


def test_latest_row_vazia_sem_a_hora_ou_sem_os_atrasos(conn):
    insert_hours(conn, "no-01", series(30))
    assert fc.latest_row(conn, "no-01", at(31) + timedelta(minutes=5), min_samples=1).empty   # hora 30 sem dados
    assert fc.latest_row(conn, "no-01", at(24) + timedelta(minutes=5), min_samples=1).empty   # sem a hora -1
    assert fc.latest_row(conn, "no-02", at(25), min_samples=1).empty                          # nó sem leituras


def test_latest_row_tem_as_mesmas_variaveis_do_treino(conn):
    insert_hours(conn, "no-01", series(24 * 3, seed=7))
    frame = fc.dataset(conn, ["no-01"], min_samples=1)
    for t in frame.index[::7]:
        row = fc.latest_row(conn, "no-01", t + timedelta(hours=1, minutes=5), min_samples=1)
        pd.testing.assert_series_equal(row.iloc[0][fc.FEATURES], frame.loc[t, fc.FEATURES], check_names=False)


# ---------------------------------------------------------------- modelos

@pytest.fixture
def train_test(conn):
    insert_hours(conn, "no-01", series(24 * 30, seed=4))
    frame = fc.dataset(conn, ["no-01"], min_samples=1)
    return frame.iloc[:-100], frame.iloc[-100:]


def test_fit_registra_o_treino_e_preve_cada_linha(train_test):
    train, test = train_test
    model = fc.fit("ridge", train)
    assert model.params == fc.DEFAULTS["ridge"] and model.version is None
    assert model.trained_on["rows"] == len(train) and model.trained_on["devices"] == ["no-01"]
    pred = model.predict(test)
    assert pred.shape == (len(test),) and np.isfinite(pred).all()


def test_previsao_nunca_e_negativa(train_test):
    class Queda:
        def predict(self, x):
            return np.full(len(x), -1000.0)

    train, test = train_test
    assert (replace(fc.fit("ridge", train), estimator=Queda()).predict(test) == 0).all()


def test_fit_recusa_modelo_ou_hiperparametro_desconhecido(train_test):
    train, _ = train_test
    with pytest.raises(ValueError, match="desconhecido"):
        fc.fit("lstm", train)
    with pytest.raises(TypeError, match="alfa"):
        fc.fit("ridge", train, alfa=1.0)


def test_gradient_boosting_usa_os_hiperparametros_dados(train_test):
    train, _ = train_test
    model = fc.fit("gboost", train, max_iter=7)
    assert model.estimator.n_iter_ == 7 and model.params["learning_rate"] == 0.1


MLP_FAST = dict(hidden=(8,), epochs=5, batch_size=64, patience=2)


def test_mlp_preve_com_valores_plausiveis(train_test):
    train, test = train_test
    pred = fc.fit("mlp", train, seed=1, **MLP_FAST).predict(test)
    assert np.isfinite(pred).all()
    assert abs(pred.mean() - test["y"].mean()) < 10


def test_mlp_e_reproduzivel_pela_semente(train_test):
    train, test = train_test
    a, b = (fc.fit("mlp", train, seed=1, **MLP_FAST).predict(test) for _ in range(2))
    assert np.array_equal(a, b)
    assert not np.array_equal(a, fc.fit("mlp", train, seed=2, **MLP_FAST).predict(test))


def test_mlp_com_mais_epocas_nao_muda_o_modelo_depois_do_melhor_ponto(train_test):
    """Parada antecipada e restauração da melhor época: um limite de épocas além do ponto de parada é indiferente."""
    train, test = train_test
    short, long = (fc.fit("mlp", train, seed=1, hidden=(8,), epochs=epochs, batch_size=64, patience=3).predict(test)
                   for epochs in (300, 3000))
    assert np.array_equal(short, long)


# ---------------------------------------------------------------- arquivo do modelo

def test_save_e_load_preservam_o_modelo(train_test, tmp_path):
    train, test = train_test
    model = fc.fit("ridge", train)
    path = fc.save(model, "v0", str(tmp_path / "models"))
    assert path.name == "ridge-v0.joblib"
    loaded = fc.load(path)
    assert loaded.version == "v0" and loaded.kind == "ridge"
    assert np.array_equal(loaded.predict(test), model.predict(test))


def test_versao_gravada_nao_e_sobrescrita(train_test, tmp_path):
    train, _ = train_test
    fc.save(fc.fit("ridge", train), "v0", str(tmp_path))
    with pytest.raises(FileExistsError):
        fc.save(fc.fit("ridge", train, alpha=1.0), "v0", str(tmp_path))
    with pytest.raises(ValueError, match="Versão inválida"):
        fc.save(fc.fit("ridge", train), "../v1", str(tmp_path))


def test_load_recusa_outra_versao_do_scikit_learn(train_test, tmp_path, monkeypatch):
    train, _ = train_test
    path = fc.save(fc.fit("ridge", train), "v0", str(tmp_path))
    monkeypatch.setattr(fc.metadata, "version", lambda name: "0.0.0")
    with pytest.raises(ValueError, match="treine de novo"):
        fc.load(path)


def test_load_all_ignora_arquivo_ruim_e_conta_o_erro(train_test, tmp_path):
    train, _ = train_test
    fc.save(fc.fit("ridge", train), "v0", str(tmp_path))
    (tmp_path / "estragado.joblib").write_bytes(b"isto nao e um modelo")
    (tmp_path / "anotacoes.txt").write_text("fora do padrão de nome")
    models, errors = fc.load_all(str(tmp_path))
    assert [(m.kind, m.version) for m in models] == [("ridge", "v0")]
    assert len(errors) == 1 and errors[0].startswith("estragado.joblib")
