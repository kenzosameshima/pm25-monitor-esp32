"""Único módulo que acessa o banco. Trocar de banco significa alterar só este arquivo."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
SCHEMA_VERSION = 2
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


class SnapshotError(RuntimeError):
    """A cópia do banco não passou na verificação de integridade e foi descartada."""


def snapshot(source_path: str, dest: Path, *, single_file: bool = False) -> int:
    """Copia o banco pela API de backup do SQLite, íntegra mesmo com a API gravando, e devolve quantas leituras tem.

    A cópia é feita num arquivo `.part` e só vira `dest` depois de passar no `integrity_check`; uma cópia
    ruim, ou qualquer erro no caminho, não deixa arquivo nenhum. Um `dest` que já existe é substituído.
    Com `single_file`, a cópia sai sem WAL (arquivo único e estável, para o hash identificar os dados)."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(dest.name + ".part")
    partial.unlink(missing_ok=True)
    src = connect(source_path, readonly=True)
    dst = sqlite3.connect(partial)
    try:
        src.backup(dst)
        if single_file:
            dst.execute("PRAGMA journal_mode=DELETE")
        check = dst.execute("PRAGMA integrity_check").fetchone()[0]
        rows = dst.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]
    except BaseException:
        dst.close()
        src.close()
        partial.unlink(missing_ok=True)
        raise
    dst.close()
    src.close()
    if check != "ok":
        partial.unlink(missing_ok=True)
        raise SnapshotError(f"integrity_check retornou {check!r}")
    partial.replace(dest)
    return rows


def _migrate(conn: sqlite3.Connection) -> None:
    """Acrescenta ao banco já existente as colunas que o esquema ganhou depois (CREATE IF NOT EXISTS não as cria)."""
    columns = {r["name"] for r in conn.execute("PRAGMA table_info(measurements)")}
    if "pressure" not in columns:
        conn.execute("ALTER TABLE measurements ADD COLUMN pressure REAL")


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    _migrate(conn)
    conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    conn.commit()


_INSERT_MEASUREMENT = """
INSERT OR IGNORE INTO measurements (
    device_id, boot_id, seq, ts_sensor, ts_received, pm1, pm25, pm10, pm25_cf1,
    temperature, humidity, pressure, rssi, uptime_s, samples, schema_version, quality
) VALUES (
    :device_id, :boot_id, :seq, :ts_sensor, :ts_received, :pm1, :pm25, :pm10, :pm25_cf1,
    :temperature, :humidity, :pressure, :rssi, :uptime_s, :samples, :schema_version, :quality
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
        # A pressão é opcional: quem monta as linhas (nó sem BME280, scripts) pode omiti-la.
        conn.executemany(_INSERT_MEASUREMENT, [{"pressure": None, **r} for r in rows])
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


def has_readings(conn: sqlite3.Connection, device_id: str) -> bool:
    """Se o servidor já guardou alguma leitura do nó. Um nó cadastrado que nunca enviou dados não tem."""
    return conn.execute("SELECT 1 FROM measurements WHERE device_id = ? LIMIT 1", (device_id,)).fetchone() is not None


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


def insert_forecasts(conn: sqlite3.Connection, rows: list[dict]) -> int:
    """Grava previsões do job horário numa única transação. Retorna quantas eram novas.

    Uma previsão já gravada (mesmo nó, hora-alvo, modelo e versão) é ignorada, então rodar o job de novo
    na mesma hora não muda nada. `generated_at` e `target_hour` são datetimes com fuso."""
    values = [(r["device_id"], iso(r["generated_at"]), iso(r["target_hour"]), r["predicted_pm25"],
               r["model_name"], r["model_version"]) for r in rows]
    with conn:
        before = conn.total_changes
        conn.executemany(
            "INSERT OR IGNORE INTO forecasts (device_id, generated_at, target_hour, predicted_pm25, model_name,"
            " model_version) VALUES (?, ?, ?, ?, ?, ?)",
            values,
        )
        return conn.total_changes - before


def fetch_ingest_batches(conn: sqlite3.Connection, since: datetime) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT received_at, device_id, n_readings, n_inserted, n_duplicates FROM ingest_batches"
        " WHERE received_at >= ? ORDER BY received_at",
        (iso(since),),
    ).fetchall()


def duplicates_discarded(conn: sqlite3.Connection, device_id: str, start: datetime, end: datetime) -> int:
    """Leituras repetidas que o servidor descartou nos lotes do nó recebidos em [start, end)."""
    return conn.execute(
        "SELECT COALESCE(SUM(n_duplicates), 0) FROM ingest_batches"
        " WHERE device_id = ? AND received_at >= ? AND received_at < ?",
        (device_id, iso(start), iso(end)),
    ).fetchone()[0]


def device_overview(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Resumo por dispositivo com leituras: local, primeira e última leitura e último recebimento.

    Cada MIN/MAX é uma subconsulta por nó, resolvida pelos índices de measurements sem varrer a tabela."""
    return conn.execute(
        "SELECT * FROM (SELECT d.device_id, d.location,"
        " (SELECT MIN(ts_sensor) FROM measurements m WHERE m.device_id = d.device_id) AS first_ts,"
        " (SELECT MAX(ts_sensor) FROM measurements m WHERE m.device_id = d.device_id) AS last_ts,"
        " (SELECT MAX(ts_received) FROM measurements m WHERE m.device_id = d.device_id) AS last_received"
        " FROM devices d) WHERE first_ts IS NOT NULL ORDER BY device_id"
    ).fetchall()


def set_location(conn: sqlite3.Connection, device_id: str, location: str | None) -> bool:
    """Grava a descrição do local de instalação de um nó (None apaga). Falso se o nó nunca enviou dados."""
    with conn:
        cur = conn.execute("UPDATE devices SET location = ? WHERE device_id = ?", (location, device_id))
    return cur.rowcount == 1


def latest_measurements(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Leitura mais recente (por ts_sensor) de cada dispositivo."""
    # Parte da tabela devices (poucas linhas), não de measurements: uma busca no índice por nó.
    return conn.execute(
        f"SELECT {_MEASUREMENT_COLUMNS} FROM measurements"
        " WHERE id IN (SELECT (SELECT x.id FROM measurements x WHERE x.device_id = d.device_id"
        "                      ORDER BY x.ts_sensor DESC, x.id DESC LIMIT 1) FROM devices d)"
        " ORDER BY device_id"
    ).fetchall()
