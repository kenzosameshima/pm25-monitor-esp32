"""Testes do treino do modelo de produção, com dados sintéticos."""

import pytest

pytest.importorskip("sklearn")

from app import forecasting as fc  # noqa: E402
from scripts import fit_forecast  # noqa: E402
from tests.forecast_data import conn, db_path, insert_hours, series  # noqa: E402,F401


def run(conn, models_dir, *extra):
    return fit_forecast.main(["--db", db_path(conn), "--models-dir", str(models_dir), *extra])


def test_treina_e_grava_o_modelo_com_a_versao(conn, tmp_path, capsys):
    insert_hours(conn, "no-01", series(24 * 10, seed=1), per_hour=45)
    insert_hours(conn, "teste-https", series(24 * 10, seed=2), per_hour=45)
    assert run(conn, tmp_path, "--model", "ridge", "--version", "v0") == 0
    model = fc.load(tmp_path / "ridge-v0.joblib")
    assert model.version == "v0" and model.params == fc.DEFAULTS["ridge"]
    assert model.trained_on["devices"] == ["no-01"]                 # nó de teste fica de fora
    assert model.trained_on["rows"] == 24 * 10 - 24 - 1
    assert "ridge v0" in capsys.readouterr().out


def test_nao_sobrescreve_uma_versao(conn, tmp_path, capsys):
    insert_hours(conn, "no-01", series(24 * 10), per_hour=45)
    assert run(conn, tmp_path, "--model", "ridge", "--version", "v0") == 0
    before = (tmp_path / "ridge-v0.joblib").read_bytes()
    assert run(conn, tmp_path, "--model", "ridge", "--version", "v0") == 1
    assert "já existe" in capsys.readouterr().err
    assert (tmp_path / "ridge-v0.joblib").read_bytes() == before


def test_recusa_versao_invalida_e_dados_insuficientes(conn, tmp_path, capsys):
    insert_hours(conn, "no-01", series(24 * 4), per_hour=45)         # 71 horas completas, abaixo de 100
    assert run(conn, tmp_path, "--model", "ridge", "--version", "v 0") == 1
    assert "Versão inválida" in capsys.readouterr().err
    assert run(conn, tmp_path, "--model", "ridge", "--version", "v0") == 1
    assert "insuficientes" in capsys.readouterr().err
    assert not list(tmp_path.glob("*.joblib"))
