"""Rotas de leitura do app de consulta: estado dos nós, médias horárias, saúde da coleta e previsões.

Só respondem ao token de leitura (PM25_READ_TOKEN), separado dos tokens dos nós, e abrem o banco em
modo somente leitura. As regras vêm de analytics, as mesmas do dashboard. Horários em UTC; o
`generated_at` de cada resposta é o relógio do servidor, para o app calcular a idade dos dados sem
depender do relógio do celular.
"""

from datetime import datetime, timedelta, timezone
from typing import Annotated, Iterator, Literal

import pandas as pd
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request, status
from pydantic import BaseModel

from . import analytics, db
from .config import get_settings
from .guard import require_bearer

MAX_RANGE = timedelta(days=31)
STATUS = {"em_operacao": "online", "atrasado": "late", "sem_dados": "silent"}
PREDICTOR_NAMES = {analytics.PERSISTENCE: "persistence"}


# ---------------------------------------------------------------- contrato das respostas

class LatestReading(BaseModel):
    ts: datetime
    pm25: float | None
    pm10: float | None
    pm1: float | None
    temperature: float | None
    humidity: float | None
    rssi: int | None
    quality: str


class DeviceState(BaseModel):
    device_id: str
    location: str | None
    status: Literal["online", "late", "silent"]
    minutes_since_last: float | None  # desde o último recebimento pelo servidor
    last_received: datetime | None
    latest: LatestReading | None


class DeviceList(BaseModel):
    generated_at: datetime
    late_after_min: int
    silent_after_min: int
    devices: list[DeviceState]


class HourlyPoint(BaseModel):
    hour: datetime  # início da hora
    readings: int
    valid: bool     # readings >= min_readings; senão as médias vêm nulas
    pm25: float | None
    pm10: float | None
    pm1: float | None
    temperature: float | None
    humidity: float | None


class HourlySeries(BaseModel):
    generated_at: datetime
    device_id: str
    start: datetime
    end: datetime
    min_readings: int
    hours: list[HourlyPoint]


class Health(BaseModel):
    generated_at: datetime
    device_id: str
    start: datetime
    end: datetime
    completeness: float
    largest_gap_min: int
    lost_messages: int
    restarts: int
    duplicates_discarded: int
    flagged_readings: int


class ForecastHour(BaseModel):
    hour: datetime
    observed: float | None
    predictions: dict[str, float | None]


class PredictorScore(BaseModel):
    predictor: str
    hours: int
    mae: float
    rmse: float
    skill: float | None


class Forecast(BaseModel):
    generated_at: datetime
    device_id: str
    predictors: list[str]
    hours: list[ForecastHour]
    scores: list[PredictorScore]


# ---------------------------------------------------------------- acesso

def authorize_read(request: Request, authorization: str | None = Header(default=None)) -> None:
    """Exige 'Authorization: Bearer <token de leitura>'. Falhas contam para o mesmo bloqueio de IP da ingestão."""
    settings = get_settings()
    if not settings.read_token:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Leitura desligada: defina PM25_READ_TOKEN")
    require_bearer(request, authorization, lambda token: settings.is_read_token(token) or None)


def get_read_conn() -> Iterator:
    conn = db.connect(get_settings().db_path, readonly=True)
    try:
        yield conn
    finally:
        conn.close()


router = APIRouter(prefix="/v1/devices", tags=["leitura"], dependencies=[Depends(authorize_read)])
DeviceId = Annotated[str, Path(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")]


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _require_device(conn, device_id: str) -> None:
    if analytics.is_test_device(device_id) or device_id not in db.last_seen(conn, [device_id]):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Nó sem leituras")


def _plain(value):
    """Valor de pandas para JSON: NaN e NaT viram None, Timestamp vira datetime."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    return value.item() if hasattr(value, "item") else value


def _records(df: pd.DataFrame) -> list[dict]:
    return [{k: _plain(v) for k, v in row.items()} for row in df.to_dict("records")]


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None:
        raise HTTPException(422, f"{name} precisa indicar o fuso, ex.: 2026-10-01T12:00:00Z")
    return value.astimezone(timezone.utc)


# ---------------------------------------------------------------- rotas

@router.get("", response_model=DeviceList)
def list_devices(conn=Depends(get_read_conn)):
    """Estado de cada nó e a leitura mais recente; dispositivos de teste ficam de fora."""
    now = _now()
    status = analytics.device_status(conn, now)
    devices = []
    for r in _records(status[~status["device_id"].map(analytics.is_test_device).astype(bool)]):
        latest = None
        if r["ts_sensor"] is not None:
            latest = {"ts": r["ts_sensor"], **{k: r[k] for k in (*analytics.VARIABLES, "rssi", "quality")}}
        devices.append({"device_id": r["device_id"], "location": r["location"], "status": STATUS[r["status"]],
                        "minutes_since_last": r["minutes_since"], "last_received": r["last_received"],
                        "latest": latest})
    return {"generated_at": now, "late_after_min": analytics.LATE_AFTER_MIN,
            "silent_after_min": analytics.SILENT_AFTER_MIN, "devices": devices}


@router.get("/{device_id}/hourly", response_model=HourlySeries)
def hourly(device_id: DeviceId,
           start: datetime | None = Query(None, description="início, em ISO 8601 com fuso; padrão: 24 h antes do fim"),
           end: datetime | None = Query(None, description="fim (exclusivo); padrão: agora"),
           hours: int | None = Query(None, ge=1, le=744,
                                     description="em vez de start: as últimas N horas completas antes do fim"),
           conn=Depends(get_read_conn)):
    """Médias horárias, uma linha por hora de [start, end), inclusive as horas sem leitura.

    O início é arredondado para baixo até a hora cheia. Intervalo de no máximo 31 dias. Com `hours`, o
    fim padrão é a hora cheia atual, então a hora em andamento (sempre incompleta) fica de fora e a
    janela vem do relógio do servidor, não do cliente.
    """
    now = _now()
    if hours is not None and start is not None:
        raise HTTPException(422, "Use start ou hours, não os dois")
    if hours is not None:
        end = _aware(end, "end") if end else now.replace(minute=0, second=0)
        start = end - timedelta(hours=hours)
    else:
        end = _aware(end, "end") if end else now
        start = _aware(start, "start") if start else end - timedelta(hours=24)
    start = start.replace(minute=0, second=0, microsecond=0)
    if not start < end or end - start > MAX_RANGE:
        raise HTTPException(422, "Intervalo inválido: start < end, até 31 dias")
    _require_device(conn, device_id)

    hours = pd.date_range(start, end, freq="h", inclusive="left")
    h = analytics.hourly_means(conn, start, end, [device_id]).set_index("hora").reindex(hours)
    h["n"] = h["n"].fillna(0).astype(int)
    points = [{"hour": hour, "readings": int(n), "valid": bool(n >= analytics.MIN_READINGS_PER_HOUR),
               **{k: row[k] for k in analytics.VARIABLES}}
              for hour, n, row in zip(hours, h["n"], _records(h))]
    return {"generated_at": now, "device_id": device_id, "start": start, "end": end,
            "min_readings": analytics.MIN_READINGS_PER_HOUR, "hours": points}


@router.get("/{device_id}/health", response_model=Health)
def health(device_id: DeviceId, hours: int = Query(24, ge=1, le=168), conn=Depends(get_read_conn)):
    """Saúde da coleta nas últimas `hours` horas: completude, lacunas, perdas, reinícios e duplicatas."""
    now = _now()
    _require_device(conn, device_id)
    start = now - timedelta(hours=hours)
    row = _records(analytics.collection_health(conn, start, now, [device_id]))[0]
    return {"generated_at": now, "device_id": device_id, "start": start, "end": now,
            "completeness": row["completude"], "largest_gap_min": row["maior_lacuna_min"],
            "lost_messages": row["mensagens_perdidas"], "restarts": row["reinicios"],
            "duplicates_discarded": row["duplicatas_descartadas"], "flagged_readings": row["leituras_marcadas"]}


@router.get("/{device_id}/forecast", response_model=Forecast)
def forecast(device_id: DeviceId, hours: int = Query(48, ge=1, le=168), conn=Depends(get_read_conn)):
    """Observado × previsto por hora, com a persistência e os modelos gravados, e as métricas de cada previsor."""
    now = _now()
    _require_device(conn, device_id)
    comparison = analytics.forecast_comparison(conn, device_id, now, hours=hours)
    series = comparison.series.rename(columns=PREDICTOR_NAMES)
    predictors = [c for c in series.columns if c != analytics.OBSERVED]
    points = [{"hour": hour, "observed": row[analytics.OBSERVED], "predictions": {p: row[p] for p in predictors}}
              for hour, row in zip(series.index, _records(series))]
    scores = comparison.metrics.replace({"previsor": PREDICTOR_NAMES}).rename(columns={"previsor": "predictor", "horas": "hours"})
    return {"generated_at": now, "device_id": device_id, "predictors": predictors, "hours": points,
            "scores": _records(scores)}
