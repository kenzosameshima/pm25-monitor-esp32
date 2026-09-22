"""Testes do dashboard com o AppTest do Streamlit: o script roda sem navegador sobre um banco sintético."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
import streamlit as st  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

from app import db  # noqa: E402
from app.config import get_settings  # noqa: E402
from scripts.simulate_sensor import synthetic  # noqa: E402

DASHBOARD = str(Path(__file__).resolve().parents[1] / "dashboard" / "app.py")


def populate(path: Path, hours: int = 30) -> None:
    conn = db.connect(str(path))
    db.init_db(conn)
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    for device, boots in (("no-01", 1), ("no-02", 2)):
        state: dict = {}
        rows = []
        for i in range(hours * 60):
            if device == "no-02" and 1000 <= i < 1060:
                continue  # uma hora sem dados no nó 2
            ts = now - timedelta(minutes=hours * 60 - i)
            boot = 1 if (boots == 1 or i < hours * 30) else 2
            seq = i if boot == 1 else i - hours * 30
            r = synthetic(ts, state)
            rows.append({"device_id": device, "boot_id": boot, "seq": seq, "ts_sensor": db.iso(ts),
                         "ts_received": db.iso(ts), "uptime_s": 60 * i, "schema_version": "1",
                         "quality": "ok", **r})
        db.insert_batch(conn, device, rows, now)
    with conn:
        for h in range(1, 12):
            target = now.replace(minute=0) - timedelta(hours=h)
            conn.execute(
                "INSERT INTO forecasts (device_id, generated_at, target_hour, predicted_pm25, model_name, model_version)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                ("no-01", db.iso(target - timedelta(minutes=1)), db.iso(target), 15.0 + h % 3, "ridge", "v1"))
    conn.close()


@pytest.fixture
def app_env(tmp_path, monkeypatch):
    monkeypatch.setenv("PM25_DB_PATH", str(tmp_path / "pm25.db"))
    monkeypatch.setenv("PM25_DEVICE_TOKENS", "no-01:token-do-no-01-0000000000")
    get_settings.cache_clear()
    st.cache_data.clear()
    yield tmp_path / "pm25.db"
    get_settings.cache_clear()
    st.cache_data.clear()


def test_sem_banco_mostra_aviso(app_env):
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception
    assert "Nenhum dado" in at.warning[0].value


def test_dashboard_renderiza_as_tres_abas(app_env):
    populate(app_env)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert [t.label for t in at.tabs] == ["Status", "Séries", "Previsto × observado"]
    assert len(at.metric) == 8  # 4 indicadores por sensor
    assert at.metric[0].label == "PM2,5"

    # tabela de saúde da coleta: o nó 2 teve uma hora sem dados e um reinício
    health = at.dataframe[0].value.set_index("Sensor")
    assert health.loc["no-02", "Reinícios"] == 1
    assert health.loc["no-02", "Maior lacuna (min)"] >= 59
    assert health.loc["no-01", "Mensagens perdidas"] == 0

    # previsto × observado: persistência e o modelo gravado, com skill score
    metrics = at.dataframe[1].value.set_index("Previsor")
    assert {"Persistência", "ridge v1"} <= set(metrics.index)
    assert "Skill score" in metrics.columns


def test_troca_para_resolucao_de_um_minuto(app_env):
    populate(app_env, hours=3)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    at.radio[0].set_value("1 minuto").run()
    assert not at.exception, at.exception
