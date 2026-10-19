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


# ---------------- recálculo retroativo ----------------

PAST = START + timedelta(hours=100)


def replay(conn, models_dir, first, last, now=NOW):
    args = ["--db", db_path(conn), "--models-dir", str(models_dir),
            "--replay-from", db.iso(first), "--replay-to", db.iso(last)]
    return forecast_job.main(args, now=now)


def test_recalculo_grava_na_versao_retro_com_o_momento_real(conn, models_dir, capsys):
    assert replay(conn, models_dir, PAST, PAST + timedelta(hours=2)) == 0
    rows = [r for r in stored(conn) if r["device_id"] == "no-01"]
    assert [r["target_hour"] for r in rows] == [db.iso(PAST + timedelta(hours=i)) for i in range(3)]
    assert {(r["model_name"], r["model_version"]) for r in rows} == {("ridge", "v0-retro")}
    assert {r["generated_at"] for r in rows} == {db.iso(NOW)}              # quando foi recalculado, não a hora-alvo
    model = fc.load(models_dir / "ridge-v0.joblib")
    expected = model.predict(fc.latest_row(conn, "no-01", PAST + timedelta(minutes=5)))[0]
    assert rows[0]["predicted_pm25"] == pytest.approx(expected)
    assert "6 previsões gravadas, 0 já existiam" in capsys.readouterr().out  # 3 horas x 2 nós


def test_recalculo_usa_so_leituras_anteriores_a_hora_alvo(conn, models_dir, tmp_path):
    assert replay(conn, models_dir, PAST, PAST) == 0
    stored_value = [r["predicted_pm25"] for r in stored(conn) if r["device_id"] == "no-01"][0]
    # um banco que acaba na hora anterior à hora-alvo, sem nenhuma leitura posterior, dá o mesmo valor
    truncated = db.connect(str(tmp_path / "truncado.db"))
    db.init_db(truncated)
    insert_hours(truncated, "no-01", series(HOURS, seed=1)[:100], per_hour=45)
    model = fc.load(models_dir / "ridge-v0.joblib")
    expected = model.predict(fc.latest_row(truncated, "no-01", PAST + timedelta(minutes=5)))[0]
    truncated.close()
    assert stored_value == pytest.approx(expected)


def test_recalculo_nao_toca_hora_que_ja_tem_previsao_em_tempo_real(conn, models_dir, capsys):
    assert run(conn, models_dir) == 0
    capsys.readouterr()
    assert replay(conn, models_dir, TARGET, TARGET) == 0
    assert {r["model_version"] for r in stored(conn)} == {"v0"}
    assert "0 previsões gravadas, 0 já existiam" in capsys.readouterr().out


def test_recalculo_de_novo_nao_duplica(conn, models_dir):
    assert replay(conn, models_dir, PAST, PAST + timedelta(hours=1)) == 0
    first = stored(conn)
    assert replay(conn, models_dir, PAST, PAST + timedelta(hours=1), now=NOW + timedelta(days=1)) == 0
    assert stored(conn) == first


def test_recalculo_sem_dados_na_hora_nao_grava(conn, models_dir, capsys):
    assert replay(conn, models_dir, START - timedelta(hours=30), START - timedelta(hours=30)) == 0
    assert stored(conn) == []
    assert "sem dados suficientes: no-01" in capsys.readouterr().out


@pytest.mark.parametrize("args", [
    ["--replay-from", "2026-09-05T10:00:00Z"],                                   # falta o fim
    ["--replay-from", "2026-09-05T10:30:00Z", "--replay-to", "2026-09-05T11:30:00Z"],  # hora não cheia
    ["--replay-from", "2026-09-05T12:00:00Z", "--replay-to", "2026-09-05T10:00:00Z"],  # fim antes do início
    ["--replay-from", "2026-09-01T00:00:00Z", "--replay-to", "2026-09-20T00:00:00Z"],  # intervalo grande demais
])
def test_recalculo_recusa_argumentos_invalidos(conn, models_dir, args):
    with pytest.raises(SystemExit) as exit_:
        forecast_job.main(["--db", db_path(conn), "--models-dir", str(models_dir), *args], now=NOW)
    assert exit_.value.code == 2
    assert stored(conn) == []
