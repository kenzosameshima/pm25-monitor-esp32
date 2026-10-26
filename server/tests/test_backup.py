"""Testes do backup diário do banco."""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from app import db
from app.config import get_settings
from scripts import backup

T0 = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


def reading(seq: int) -> dict:
    ts = T0 + timedelta(minutes=seq)
    return {"device_id": "no-01", "boot_id": 1, "seq": seq, "ts_sensor": db.iso(ts), "ts_received": db.iso(ts),
            "pm1": None, "pm25": 10.0, "pm10": None, "pm25_cf1": None, "temperature": 20.0, "humidity": 60.0,
            "rssi": -60, "uptime_s": 0, "samples": 58, "schema_version": "1", "quality": "ok"}


@pytest.fixture
def server(tmp_path, monkeypatch):
    """Banco com 3 leituras e a pasta de backups, configurados pelo ambiente."""
    db_path = tmp_path / "pm25.db"
    conn = db.connect(str(db_path))
    db.init_db(conn)
    db.insert_batch(conn, "no-01", [reading(i) for i in range(3)], T0)
    conn.close()
    monkeypatch.setenv("PM25_DB_PATH", str(db_path))
    monkeypatch.setenv("PM25_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("PM25_BACKUP_KEEP", "2")
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def test_backup_grava_copia_integra(server, capsys):
    assert backup.main() == 0
    [copy] = (server / "backups").glob("pm25-*.db")
    with sqlite3.connect(copy) as conn:
        assert conn.execute("SELECT COUNT(*) FROM measurements").fetchone()[0] == 3
    assert "3 medições" in capsys.readouterr().out


def test_backup_mantem_so_os_mais_recentes(server):
    old = server / "backups"
    old.mkdir()
    for stamp in ("2020-01-01T0000Z", "2020-01-02T0000Z", "2020-01-03T0000Z"):
        (old / f"pm25-{stamp}.db").write_bytes(b"antigo")
    assert backup.main() == 0
    names = sorted(p.name for p in old.glob("pm25-*.db"))
    assert len(names) == 2 and names[0] == "pm25-2020-01-03T0000Z.db"       # a antiga mais nova e o backup novo


def test_sem_banco_o_backup_falha_sem_criar_nada(server, capsys):
    (server / "pm25.db").unlink()
    assert backup.main() == 1
    assert "Banco não encontrado" in capsys.readouterr().err
    assert not (server / "backups").exists()
