"""Testes das consultas do módulo do banco."""

from datetime import datetime, timedelta, timezone

import pytest

from app import db

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def reading(device: str, seq: int) -> dict:
    ts = T0 + timedelta(minutes=seq)
    return {"device_id": device, "boot_id": 1, "seq": seq, "ts_sensor": db.iso(ts), "ts_received": db.iso(ts),
            "pm1": None, "pm25": 10.0, "pm10": None, "pm25_cf1": None, "temperature": 20.0, "humidity": 60.0,
            "rssi": -60, "uptime_s": 0, "samples": 58, "schema_version": "1", "quality": "ok"}


@pytest.fixture
def conn(tmp_path):
    c = db.connect(str(tmp_path / "pm25.db"))
    db.init_db(c)
    yield c
    c.close()


def test_lote_guarda_a_versao_do_firmware_de_quem_enviou(conn):
    db.insert_batch(conn, "no-01", [reading("no-01", 0)], T0, firmware="v1")
    db.insert_batch(conn, "no-01", [reading("no-01", 1)], T0 + timedelta(minutes=1))
    assert [r[0] for r in conn.execute("SELECT firmware FROM ingest_batches ORDER BY id")] == ["v1", None]


def test_banco_antigo_ganha_a_coluna_do_firmware(tmp_path):
    path = str(tmp_path / "antigo.db")
    old = db.connect(path)
    with old:   # ingest_batches como era antes da coluna `firmware`
        old.execute("CREATE TABLE ingest_batches (id INTEGER PRIMARY KEY, received_at TEXT NOT NULL,"
                    " device_id TEXT NOT NULL, n_readings INTEGER NOT NULL, n_inserted INTEGER NOT NULL,"
                    " n_duplicates INTEGER NOT NULL, remote_addr TEXT)")
        old.execute("INSERT INTO ingest_batches (received_at, device_id, n_readings, n_inserted, n_duplicates)"
                    " VALUES ('2026-10-01T12:00:00Z', 'no-01', 1, 1, 0)")
    db.init_db(old)
    db.insert_batch(old, "no-01", [reading("no-01", 0)], T0, firmware="v2")
    assert [r[0] for r in old.execute("SELECT firmware FROM ingest_batches ORDER BY id")] == [None, "v2"]
    old.close()


def test_ultima_versao_do_firmware_vem_do_lote_mais_recente_que_a_informou(conn):
    db.insert_batch(conn, "no-01", [reading("no-01", 0)], T0, firmware="v1")
    db.insert_batch(conn, "no-01", [reading("no-01", 1)], T0 + timedelta(minutes=1), firmware="v2")
    db.insert_batch(conn, "no-01", [reading("no-01", 2)], T0 + timedelta(minutes=2))   # firmware antigo, sem o campo
    db.insert_batch(conn, "no-02", [reading("no-02", 0)], T0)
    assert db.latest_firmware(conn) == {"no-01": "v2"}               # no-02 nunca informou


def test_banco_ainda_nao_migrado_nao_quebra_quem_so_le(tmp_path):
    path = str(tmp_path / "antigo.db")
    old = db.connect(path)
    with old:
        old.execute("CREATE TABLE devices (device_id TEXT PRIMARY KEY, first_seen TEXT NOT NULL, location TEXT,"
                    " notes TEXT)")
        old.execute("CREATE TABLE ingest_batches (id INTEGER PRIMARY KEY, received_at TEXT NOT NULL,"
                    " device_id TEXT NOT NULL, n_readings INTEGER NOT NULL, n_inserted INTEGER NOT NULL,"
                    " n_duplicates INTEGER NOT NULL, remote_addr TEXT)")
    old.close()
    reader = db.connect(path, readonly=True)
    assert db.latest_firmware(reader) == {}
    reader.close()


def test_no_com_leituras_tem_leituras(conn):
    db.insert_batch(conn, "no-01", [reading("no-01", 0)], T0)
    assert db.has_readings(conn, "no-01")


def test_no_desconhecido_nao_tem_leituras(conn):
    db.insert_batch(conn, "no-01", [reading("no-01", 0)], T0)
    assert not db.has_readings(conn, "no-02")


def test_no_cadastrado_sem_leituras_nao_tem_leituras(conn):
    with conn:
        conn.execute("INSERT INTO devices (device_id, first_seen) VALUES ('no-03', ?)", (db.iso(T0),))
    assert not db.has_readings(conn, "no-03")
