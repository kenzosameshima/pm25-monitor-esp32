"""Dados sintéticos para os testes de previsão: séries horárias gravadas como leituras de um minuto."""

import math
import random
from datetime import datetime, timedelta, timezone

import pytest

from app import db

START = datetime(2026, 9, 1, tzinfo=timezone.utc)


def series(hours: int, seed: int = 0) -> list[float]:
    """PM2,5 horário com reversão à média: a persistência erra bastante, um modelo linear acerta mais."""
    rng = random.Random(seed)
    x, out = 15.0, []
    for h in range(hours):
        daily = 6 * math.sin(2 * math.pi * (h % 24) / 24)
        x = 0.4 * x + 0.6 * (15 + daily) + rng.gauss(0, 2.5)
        out.append(max(1.0, x))
    return out


def insert_hours(conn, device: str, values: list[float], per_hour: int = 1, quality: str = "ok") -> None:
    """Grava `per_hour` leituras por hora a partir de START, todas com o valor da hora."""
    rows = []
    for h, v in enumerate(values):
        for m in range(per_hour):
            ts = START + timedelta(hours=h, minutes=m)
            rows.append({"device_id": device, "boot_id": 1, "seq": h * 60 + m, "ts_sensor": db.iso(ts),
                         "ts_received": db.iso(ts), "pm1": None, "pm25": v, "pm10": None, "pm25_cf1": None,
                         "temperature": 20.0 + h % 24 / 4, "humidity": 60.0, "rssi": -60, "uptime_s": 0,
                         "samples": 58, "schema_version": "1", "quality": quality})
    db.insert_batch(conn, device, rows, START)


def db_path(conn) -> str:
    return conn.execute("PRAGMA database_list").fetchone()[2]


@pytest.fixture
def conn(tmp_path):
    c = db.connect(str(tmp_path / "pm25.db"))
    db.init_db(c)
    yield c
    c.close()
