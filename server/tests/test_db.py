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
