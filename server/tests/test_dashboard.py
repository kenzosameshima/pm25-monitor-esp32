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


def populate(path: Path, hours: int = 30, devices=(("no-01", 1), ("no-02", 2))) -> None:
    conn = db.connect(str(path))
    db.init_db(conn)
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    for device, boots in devices:
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
    monkeypatch.setenv("PM25_DEVICE_TOKENS", "no-01:token-do-no-01-aB3xQ9zK7pLm2Wv8Rt")
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
    assert len(at.metric) == 10  # 5 indicadores por sensor
    assert at.metric[0].label == "PM2,5"
    assert at.metric[0].delta in {"Boa", "Moderada", "Ruim", "Muito ruim", "Péssima"}  # faixa da CETESB
    assert at.metric[1].label == "PM10"
    assert not any("implausível" in c.value for c in at.caption)

    # tabela de saúde da coleta: o nó 2 teve uma hora sem dados e um reinício
    health = at.dataframe[0].value.set_index("Sensor")
    assert health.loc["no-02", "Reinícios"] == 1
    assert health.loc["no-02", "Maior lacuna (min)"] >= 59
    assert health.loc["no-01", "Mensagens perdidas"] == 0

    # previsto × observado: persistência e o modelo gravado, com skill score
    metrics = at.dataframe[1].value.set_index("Previsor")
    assert {"Persistência", "ridge v1"} <= set(metrics.index)
    assert "Skill score" in metrics.columns


def test_esconde_no_de_teste_e_reserva_card_do_no_cadastrado_sem_dados(app_env, monkeypatch):
    monkeypatch.setenv("PM25_DEVICE_TOKENS", "no-01:token-do-no-01-aB3xQ9zK7pLm2Wv8Rt,no-02:token-do-no-02-aB3xQ9zK7pLm2Wv8Rt,"
                                             "teste-https:token-do-teste-aB3xQ9zK7pLm2Wv8Rt")
    populate(app_env, hours=3, devices=(("no-01", 1), ("teste-https", 1)))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert [h.value for h in at.subheader] == ["no-01", "no-02"]
    assert any("aguardando instalação" in c.value for c in at.caption)
    assert len(at.metric) == 5  # só o no-01 tem leitura
    assert list(at.dataframe[0].value["Sensor"]) == ["no-01"]
    assert at.multiselect[0].options == ["no-01"]


def add_dead_hours(path: Path, device: str, hours_ago: list[int]) -> None:
    """Uma hora cheia de leituras com PM1, PM2,5 e PM10 em zero, para cada `hours_ago` (horas antes da hora atual)."""
    top = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    conn = db.connect(str(path))
    for k in hours_ago:
        start = top - timedelta(hours=k)
        dead = {**synthetic(start, {}), "pm25": 0.0, "pm1": 0.0, "pm10": 0.0}
        db.insert_batch(conn, device, [{"device_id": device, "boot_id": 9, "seq": k * 60 + m, "uptime_s": 0,
                                        "schema_version": "1", "quality": "ok",
                                        "ts_sensor": db.iso(start + timedelta(minutes=m)),
                                        "ts_received": db.iso(start + timedelta(minutes=m)), **dead}
                                       for m in range(60)], start)
    conn.close()


def test_serie_horaria_conta_as_horas_suspeitas_que_ficaram_de_fora(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    add_dead_hours(app_env, "no-01", [10])
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert any("1 hora suspeita ficou de fora (no-01: 1)" in c.value for c in at.caption)


def test_aviso_das_horas_suspeitas_separa_a_contagem_por_no(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1), ("no-02", 1)))
    add_dead_hours(app_env, "no-01", [10])
    add_dead_hours(app_env, "no-02", [12, 11])
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert any("3 horas suspeitas ficaram de fora (no-01: 1, no-02: 2)" in c.value for c in at.caption)


def test_aviso_das_horas_suspeitas_so_cita_os_nos_com_horas_suspeitas(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1), ("no-02", 1)))
    add_dead_hours(app_env, "no-02", [10])
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert any("1 hora suspeita ficou de fora (no-02: 1)" in c.value for c in at.caption)


def test_sem_horas_suspeitas_a_serie_horaria_nao_menciona_o_assunto(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert not any("suspeita" in c.value for c in at.caption)


def test_mostra_a_versao_do_firmware_quando_o_no_informa(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1), ("no-02", 1)))
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    conn = db.connect(str(app_env))
    db.insert_batch(conn, "no-01", [{"device_id": "no-01", "boot_id": 1, "seq": 3 * 60, "ts_sensor": db.iso(now),
                                     "ts_received": db.iso(now), "uptime_s": 3 * 3600, "schema_version": "1",
                                     "quality": "ok", **synthetic(now, {})}], now, firmware="build Oct 26 2026")
    conn.close()
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    firmware = [c.value for c in at.caption if "Firmware" in c.value]
    assert firmware == ["Firmware: build Oct 26 2026"]               # o no-02 não informa: nada é mostrado


def test_avisa_quando_a_ultima_leitura_foi_marcada(app_env):
    populate(app_env, hours=3, devices=(("no-01", 1),))
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    conn = db.connect(str(app_env))  # a tabela é imutável: a leitura marcada entra como a mais recente
    db.insert_batch(conn, "no-01", [{"device_id": "no-01", "boot_id": 1, "seq": 3 * 60, "ts_sensor": db.iso(now),
                                     "ts_received": db.iso(now), "uptime_s": 3 * 3600, "schema_version": "1",
                                     "quality": "umid_fora_faixa", **synthetic(now, {}), "humidity": 120.0}], now)
    conn.close()
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    assert not at.exception, at.exception
    assert any("implausível (umid_fora_faixa)" in c.value for c in at.caption)


def test_troca_para_resolucao_de_um_minuto(app_env):
    populate(app_env, hours=3)
    at = AppTest.from_file(DASHBOARD, default_timeout=60).run()
    at.radio[0].set_value("1 minuto").run()
    assert not at.exception, at.exception
