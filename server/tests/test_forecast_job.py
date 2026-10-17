"""Testes do job horário de previsão, com dados sintéticos e modelos treinados na hora."""

from datetime import timedelta

import pytest

pytest.importorskip("sklearn")

from app import analytics, db  # noqa: E402
from app import forecasting as fc  # noqa: E402
from scripts import forecast_job  # noqa: E402
from tests.forecast_data import START, conn, db_path, insert_hours, series  # noqa: E402,F401

HOURS = 24 * 10
NOW = START + timedelta(hours=HOURS, minutes=5)    # a hora HOURS - 1 é a última completa
TARGET = START + timedelta(hours=HOURS)


@pytest.fixture
def models_dir(conn, tmp_path):
    insert_hours(conn, "no-01", series(HOURS, seed=1), per_hour=45)
    insert_hours(conn, "no-02", series(HOURS, seed=2), per_hour=45)
    insert_hours(conn, "teste-https", series(HOURS, seed=3), per_hour=45)
    path = tmp_path / "models"
    fc.save(fc.fit("ridge", fc.dataset(conn)), "v0", str(path))
    return path


def run(conn, models_dir, now=NOW):
    return forecast_job.main(["--db", db_path(conn), "--models-dir", str(models_dir)], now=now)


def stored(conn):
    return [dict(r) for r in conn.execute("SELECT * FROM forecasts ORDER BY device_id")]


def test_grava_a_previsao_da_hora_em_andamento_para_cada_no(conn, models_dir, capsys):
    assert run(conn, models_dir) == 0
    rows = stored(conn)
    assert [r["device_id"] for r in rows] == ["no-01", "no-02"]    # nó de teste fica de fora
    model = fc.load(models_dir / "ridge-v0.joblib")
    for r in rows:
        assert r["target_hour"] == db.iso(TARGET) and r["generated_at"] == db.iso(NOW)
        assert (r["model_name"], r["model_version"]) == ("ridge", "v0")
        expected = model.predict(fc.latest_row(conn, r["device_id"], NOW))[0]
        assert r["predicted_pm25"] == pytest.approx(expected)
    assert "2 previsões gravadas, 0 já existiam" in capsys.readouterr().out


def test_rodar_de_novo_na_mesma_hora_nao_duplica(conn, models_dir, capsys):
    assert run(conn, models_dir) == 0
    first = stored(conn)
    assert run(conn, models_dir, now=NOW + timedelta(minutes=20)) == 0
    assert stored(conn) == first                                   # a primeira previsão da hora fica
    assert "0 previsões gravadas, 2 já existiam" in capsys.readouterr().out


def test_previsao_aparece_no_previsto_x_observado(conn, models_dir):
    assert run(conn, models_dir) == 0
    comparison = analytics.forecast_comparison(conn, "no-01", NOW)
    assert "ridge v0" in comparison.series.columns                  # a série que o dashboard e o app mostram
    assert comparison.series.loc[TARGET, "ridge v0"] == pytest.approx(stored(conn)[0]["predicted_pm25"])


def test_no_sem_a_ultima_hora_fica_sem_previsao(conn, models_dir, capsys):
    insert_hours(conn, "no-03", series(HOURS - 3), per_hour=45)     # parou de enviar há 3 horas
    assert run(conn, models_dir) == 0
    assert "no-03" not in {r["device_id"] for r in stored(conn)}
    assert "sem dados suficientes: no-03" in capsys.readouterr().out


def test_sem_modelo_ou_sem_banco_retorna_erro(conn, models_dir, tmp_path, capsys):
    assert run(conn, tmp_path / "vazia") == 1
    assert "nenhum modelo" in capsys.readouterr().err
    missing = tmp_path / "nao-existe.db"
    assert forecast_job.main(["--db", str(missing), "--models-dir", str(models_dir)], now=NOW) == 1
    assert "banco não encontrado" in capsys.readouterr().err and not missing.exists()
    assert stored(conn) == []


def test_modelo_ruim_nao_impede_os_outros(conn, models_dir, capsys):
    (models_dir / "estragado.joblib").write_bytes(b"isto nao e um modelo")
    assert run(conn, models_dir) == 1                              # o agendador registra a falha
    assert len(stored(conn)) == 2
    assert "modelo ignorado: estragado.joblib" in capsys.readouterr().err


def test_dois_modelos_gravam_lado_a_lado(conn, models_dir):
    fc.save(fc.fit("gboost", fc.dataset(conn), max_iter=10), "v1", str(models_dir))
    assert run(conn, models_dir) == 0
    assert {(r["model_name"], r["model_version"]) for r in stored(conn)} == {("gboost", "v1"), ("ridge", "v0")}
