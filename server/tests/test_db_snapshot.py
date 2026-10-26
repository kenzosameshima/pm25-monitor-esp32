"""Testes da cópia íntegra do banco, usada pelo backup diário e pelo congelamento do período."""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from app import db

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def reading(seq: int) -> dict:
    ts = T0 + timedelta(minutes=seq)
    return {"device_id": "no-01", "boot_id": 1, "seq": seq, "ts_sensor": db.iso(ts), "ts_received": db.iso(ts),
            "pm1": None, "pm25": 10.0, "pm10": None, "pm25_cf1": None, "temperature": 20.0, "humidity": 60.0,
            "rssi": -60, "uptime_s": 0, "samples": 58, "schema_version": "1", "quality": "ok"}


@pytest.fixture
def source(tmp_path):
    path = str(tmp_path / "pm25.db")
    conn = db.connect(path)
    db.init_db(conn)
    db.insert_batch(conn, "no-01", [reading(i) for i in range(50)], T0)
    conn.close()
    return path


def test_copia_tem_as_leituras_e_devolve_quantas_sao(source, tmp_path):
    dest = tmp_path / "copia" / "pm25-copia.db"
    assert db.snapshot(source, dest) == 50
    with sqlite3.connect(dest) as copy:
        assert copy.execute("SELECT COUNT(*) FROM measurements").fetchone()[0] == 50
        assert copy.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_copia_nao_deixa_arquivo_parcial(source, tmp_path):
    dest = tmp_path / "pm25-copia.db"
    db.snapshot(source, dest)
    assert sorted(p.name for p in tmp_path.iterdir() if p.name.startswith("pm25-copia")) == ["pm25-copia.db"]


def test_copia_substitui_uma_anterior_de_mesmo_nome(source, tmp_path):
    dest = tmp_path / "pm25-copia.db"
    db.snapshot(source, dest)
    conn = db.connect(source)
    db.insert_batch(conn, "no-01", [reading(100)], T0)
    conn.close()
    assert db.snapshot(source, dest) == 51


def test_arquivo_unico_nao_depende_de_wal(source, tmp_path):
    dest = tmp_path / "pm25-copia.db"
    db.snapshot(source, dest, single_file=True)
    with sqlite3.connect(dest) as copy:
        assert copy.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    assert not (tmp_path / "pm25-copia.db-wal").exists()


def test_origem_corrompida_nao_deixa_copia(source, tmp_path):
    with open(source, "r+b") as f:        # estraga páginas de dados, depois do cabeçalho
        f.seek(8192)
        f.write(b"\xff" * 4096)
    dest = tmp_path / "pm25-copia.db"
    with pytest.raises((db.SnapshotError, sqlite3.DatabaseError)):
        db.snapshot(source, dest)
    assert not dest.exists() and not dest.with_name(dest.name + ".part").exists()
