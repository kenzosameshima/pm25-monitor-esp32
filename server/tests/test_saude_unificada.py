"""A saúde da coleta tem uma definição só: o painel, a API de leitura (e o app) e o period_metrics dão o mesmo número.

A janela é fixa: os minutos esperados vão do início ao fim dela, mesmo para um nó que só começou no meio. O trecho
antes da primeira leitura entra na completude e na maior lacuna (no period_metrics, como "bordas").
"""

from datetime import datetime, timedelta, timezone

import pytest

from app import analytics, db
from scripts import period_metrics as pmx

START = datetime(2026, 9, 1, 3, 0, tzinfo=timezone.utc)  # 00:00 em Brasília
END = START + timedelta(days=1)


def readings(first=0, last=1439, acq=(), lost=(), down=()):
    """(minuto, boot_id, seq) de uma leitura por minuto; `acq` sem leitura e sem consumir seq, `lost` consome seq,
    `down` desligado, com novo boot_id depois."""
    out, boot, seq, reboot = [], 1, 0, False
    for m in range(first, last + 1):
        if m in down:
            reboot = True
            continue
        if reboot:
            boot, seq, reboot = boot + 1, 0, False
        if m in acq:
            continue
        if m in lost:
            seq += 1
            continue
        out.append((m, boot, seq))
        seq += 1
    return out


def insert(conn, device, plan, received_at=END):
    rows = []
    for m, boot, seq in plan:
        ts = db.iso(START + timedelta(minutes=m))
        rows.append({"device_id": device, "boot_id": boot, "seq": seq, "ts_sensor": ts, "ts_received": ts,
                     "pm1": None, "pm25": 10.0, "pm10": None, "pm25_cf1": None, "temperature": 20.0,
                     "humidity": 60.0, "rssi": -60, "uptime_s": 0, "samples": 58, "schema_version": "1",
                     "quality": "ok"})
    return db.insert_batch(conn, device, rows, received_at)


@pytest.fixture
def conn(tmp_path):
    c = db.connect(str(tmp_path / "pm25.db"))
    db.init_db(c)
    yield c
    c.close()


CENARIOS = {
    "dia completo": dict(),
    "no instalado no meio do dia": dict(first=251, last=1439),
    "parado antes do fim": dict(first=0, last=1379),
    "todas as origens de lacuna": dict(first=60, last=1379, acq=range(100, 110), lost=range(400, 405),
                                       down=range(700, 703)),
}


@pytest.mark.parametrize("scenario", CENARIOS)
def test_painel_e_period_metrics_dao_o_mesmo_numero(conn, scenario):
    insert(conn, "no-01", readings(**CENARIOS[scenario]))
    panel = analytics.collection_health(conn, START, END, ["no-01"]).iloc[0]
    period, _ = pmx.operational_metrics(conn, "no-01", START, END, 1)
    assert panel["completude"] == pytest.approx(period["completude"], abs=1e-4)
    for panel_key, period_key in (("maior_lacuna_min", "maior_lacuna_min"), ("mensagens_perdidas", "mensagens_perdidas"),
                                  ("reinicios", "reinicios"), ("duplicatas_descartadas", "duplicatas_descartadas")):
        assert panel[panel_key] == period[period_key], panel_key


def test_duplicatas_batem_nos_dois(conn):
    plan = readings(last=59)
    insert(conn, "no-01", plan, received_at=START + timedelta(hours=1))
    insert(conn, "no-01", plan, received_at=START + timedelta(hours=2))  # reenvio: 60 duplicatas
    panel = analytics.collection_health(conn, START, END, ["no-01"]).iloc[0]
    period, _ = pmx.operational_metrics(conn, "no-01", START, END, 1)
    assert panel["duplicatas_descartadas"] == period["duplicatas_descartadas"] == 60


def test_no_que_comeca_no_meio_da_janela_conta_o_trecho_anterior(conn):
    insert(conn, "no-01", readings(first=720, last=1439))  # primeira leitura ao meio-dia
    panel = analytics.collection_health(conn, START, END, ["no-01"]).iloc[0]
    assert panel["completude"] == pytest.approx(0.5)
    assert panel["maior_lacuna_min"] == 720


def test_o_minuto_em_andamento_nao_conta_como_esperado_nem_como_lacuna(conn):
    insert(conn, "no-01", readings(last=600))
    now = START + timedelta(minutes=600, seconds=30)  # o minuto 600 ainda está fechando
    panel = analytics.collection_health(conn, START, now, ["no-01"]).iloc[0]
    assert panel["completude"] == 1.0 and panel["maior_lacuna_min"] == 0


def test_janela_sem_leituras_tem_a_lacuna_da_janela_inteira(conn):
    insert(conn, "no-01", readings(first=0, last=59))
    later = START + timedelta(hours=5)
    panel = analytics.collection_health(conn, later, later + timedelta(hours=2), ["no-01"]).iloc[0]
    assert panel["completude"] == 0.0 and panel["maior_lacuna_min"] == 120
