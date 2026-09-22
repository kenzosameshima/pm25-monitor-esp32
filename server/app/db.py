"""Único módulo que acessa o banco. Trocar de banco significa alterar só este arquivo."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
SCHEMA_VERSION = 1
MAX_RAW_PAYLOAD = 64 * 1024


def iso(dt: datetime) -> str:
    """Formata um datetime como ISO 8601 em UTC, com precisão de segundos."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def connect(path: str, readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10, check_same_thread=False)
    else:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: o FastAPI pode abrir e fechar a conexão em threads diferentes,
        # mas cada conexão atende a uma única requisição por vez.
        conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        # FULL: o 201 só sai depois de a leitura estar no disco, mesmo se faltar energia no servidor.
        conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    conn.commit()


_INSERT_MEASUREMENT = """
INSERT OR IGNORE INTO measurements (
    device_id, boot_id, seq, ts_sensor, ts_received, pm1, pm25, pm10, pm25_cf1,
    temperature, humidity, rssi, uptime_s, samples, schema_version, quality
) VALUES (
    :device_id, :boot_id, :seq, :ts_sensor, :ts_received, :pm1, :pm25, :pm10, :pm25_cf1,
    :temperature, :humidity, :rssi, :uptime_s, :samples, :schema_version, :quality
)
"""


def insert_batch(
    conn: sqlite3.Connection,
    device_id: str,
    rows: list[dict[str, Any]],
    received_at: datetime,
    remote_addr: str | None = None,
) -> tuple[int, int]:
    """Grava um lote de leituras numa única transação. Retorna (inseridas, duplicadas).

    Leituras repetidas (mesmo device_id, boot_id e seq) são ignoradas, o que torna os
    reenvios do nó seguros: ele pode mandar o mesmo lote várias vezes sem duplicar dados.
    """
    received = iso(received_at)
    with conn:
        conn.execute(
            "INSERT OR IGNORE INTO devices (device_id, first_seen) VALUES (?, ?)",
            (device_id, received),
        )
        before = conn.total_changes
        conn.executemany(_INSERT_MEASUREMENT, rows)
        inserted = conn.total_changes - before
        duplicates = len(rows) - inserted
        conn.execute(
            "INSERT INTO ingest_batches (received_at, device_id, n_readings, n_inserted, n_duplicates, remote_addr)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (received, device_id, len(rows), inserted, duplicates, remote_addr),
        )
    return inserted, duplicates


def record_invalid(
    conn: sqlite3.Connection,
    reason: str,
    raw_payload: Any,
    received_at: datetime,
    remote_addr: str | None = None,
    device_id: str | None = None,
) -> None:
    if isinstance(raw_payload, bytes):
        raw = raw_payload.decode("utf-8", errors="replace")
    elif isinstance(raw_payload, str):
        raw = raw_payload
    else:
        raw = json.dumps(raw_payload, ensure_ascii=False, default=str)
    with conn:
        conn.execute(
            "INSERT INTO invalid_messages (received_at, remote_addr, device_id, reason, raw_payload)"
            " VALUES (?, ?, ?, ?, ?)",
            (iso(received_at), remote_addr, device_id, reason[:2000], raw[:MAX_RAW_PAYLOAD]),
        )


def last_seen(conn: sqlite3.Connection, device_ids: Iterable[str] | None = None) -> dict[str, datetime]:
    """Último instante em que o servidor recebeu dados de cada dispositivo."""
    rows = conn.execute(
        "SELECT device_id, MAX(ts_received) AS last FROM measurements GROUP BY device_id"
    ).fetchall()
    result = {r["device_id"]: parse_iso(r["last"]) for r in rows}
    if device_ids is not None:
        wanted = set(device_ids)
        result = {k: v for k, v in result.items() if k in wanted}
    return result


def ping(conn: sqlite3.Connection) -> None:
    conn.execute("SELECT 1").fetchone()


# ---------------- Consultas de leitura (dashboard e análises) ----------------

_MEASUREMENT_COLUMNS = (
    "device_id, boot_id, seq, ts_sensor, ts_received, pm1, pm25, pm10, pm25_cf1,"
    " temperature, humidity, rssi, samples, quality"
)


def _device_filter(device_ids: Iterable[str] | None) -> tuple[str, list[str]]:
    ids = list(device_ids or [])
    if not ids:
        return "", []
    return f" AND device_id IN ({','.join('?' * len(ids))})", ids


def fetch_measurements(
    conn: sqlite3.Connection, start: datetime, end: datetime, device_ids: Iterable[str] | None = None
) -> list[sqlite3.Row]:
    """Leituras com ts_sensor em [start, end), ordenadas por dispositivo e horário."""
    where, ids = _device_filter(device_ids)
    sql = (f"SELECT {_MEASUREMENT_COLUMNS} FROM measurements WHERE ts_sensor >= ? AND ts_sensor < ?{where}"
           " ORDER BY device_id, ts_sensor")
    return conn.execute(sql, [iso(start), iso(end), *ids]).fetchall()


def fetch_forecasts(
    conn: sqlite3.Connection, start: datetime, end: datetime, device_ids: Iterable[str] | None = None
) -> list[sqlite3.Row]:
    """Previsões cuja hora-alvo está em [start, end)."""
    where, ids = _device_filter(device_ids)
    sql = ("SELECT device_id, generated_at, target_hour, predicted_pm25, model_name, model_version"
           f" FROM forecasts WHERE target_hour >= ? AND target_hour < ?{where} ORDER BY target_hour")
    return conn.execute(sql, [iso(start), iso(end), *ids]).fetchall()


def fetch_ingest_batches(conn: sqlite3.Connection, since: datetime) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT received_at, device_id, n_readings, n_inserted, n_duplicates FROM ingest_batches"
        " WHERE received_at >= ? ORDER BY received_at",
        (iso(since),),
    ).fetchall()


def device_overview(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Resumo por dispositivo: primeira e última leitura, último recebimento e total de inicializações."""
    return conn.execute(
        "SELECT device_id, MIN(ts_sensor) AS first_ts, MAX(ts_sensor) AS last_ts,"
        " MAX(ts_received) AS last_received, COUNT(DISTINCT boot_id) AS boots, COUNT(*) AS n"
        " FROM measurements GROUP BY device_id ORDER BY device_id"
    ).fetchall()


def latest_measurements(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Leitura mais recente (por ts_sensor) de cada dispositivo."""
    return conn.execute(
        f"SELECT {_MEASUREMENT_COLUMNS} FROM measurements m"
        " WHERE m.id = (SELECT id FROM measurements x WHERE x.device_id = m.device_id"
        "               ORDER BY x.ts_sensor DESC, x.id DESC LIMIT 1)"
        " ORDER BY device_id"
    ).fetchall()
