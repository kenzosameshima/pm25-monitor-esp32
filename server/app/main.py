"""API de ingestão. Recebe lotes de leituras dos nós e só responde 201 depois de gravar no banco."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Iterator

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from . import db
from .config import get_settings
from .models import Batch, IngestResult, quality_flags


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if not settings.device_tokens:
        raise RuntimeError("Nenhum dispositivo configurado: defina PM25_DEVICE_TOKENS no .env")
    conn = db.connect(settings.db_path)
    try:
        db.init_db(conn)
    finally:
        conn.close()
    yield


app = FastAPI(title="PM2,5 — API de ingestão", version="1.0.0", lifespan=lifespan)


def get_conn() -> Iterator:
    conn = db.connect(get_settings().db_path)
    try:
        yield conn
    finally:
        conn.close()


def authenticate(authorization: str | None = Header(default=None)) -> str:
    """Identifica o dispositivo pelo token enviado em 'Authorization: Bearer <token>'."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token ausente")
    device = get_settings().device_for_token(authorization.removeprefix("Bearer ").strip())
    if device is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido")
    return device


def _client(request: Request) -> str | None:
    return request.client.host if request.client else None


@app.exception_handler(RequestValidationError)
async def record_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Payload fora do contrato: guarda para auditoria e responde 422.

    O nó descarta lotes recusados com 4xx (exceto 401, 403, 408 e 429) para não ficar preso
    reenviando o mesmo dado inválido; por isso o registro aqui é a única cópia que sobra.
    """
    body = exc.body
    device_id = body.get("device_id") if isinstance(body, dict) else None
    conn = db.connect(get_settings().db_path)
    try:
        db.record_invalid(
            conn,
            reason=str(exc.errors())[:2000],
            raw_payload=body,
            received_at=datetime.now(timezone.utc),
            remote_addr=_client(request),
            device_id=device_id if isinstance(device_id, str) else None,
        )
    finally:
        conn.close()
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(exc.errors())})


@app.post("/v1/measurements", status_code=status.HTTP_201_CREATED, response_model=IngestResult)
def ingest(batch: Batch, request: Request, device: str = Depends(authenticate), conn=Depends(get_conn)):
    now = datetime.now(timezone.utc)
    if batch.device_id != device:
        db.record_invalid(
            conn,
            reason=f"device_id '{batch.device_id}' não corresponde ao token de '{device}'",
            raw_payload=batch.model_dump(mode="json"),
            received_at=now,
            remote_addr=_client(request),
            device_id=device,
        )
        raise HTTPException(status.HTTP_403_FORBIDDEN, "device_id não corresponde ao token")

    received = db.iso(now)
    rows = [
        {
            "device_id": batch.device_id,
            "boot_id": r.boot_id,
            "seq": r.seq,
            "ts_sensor": db.iso(r.ts),
            "ts_received": received,
            "pm1": r.pm1,
            "pm25": r.pm25,
            "pm10": r.pm10,
            "pm25_cf1": r.pm25_cf1,
            "temperature": r.temperature,
            "humidity": r.humidity,
            "rssi": r.rssi,
            "uptime_s": r.uptime_s,
            "samples": r.samples,
            "schema_version": batch.schema_version,
            "quality": quality_flags(r, now),
        }
        for r in batch.readings
    ]
    inserted, duplicates = db.insert_batch(conn, batch.device_id, rows, now, _client(request))
    return IngestResult(inserted=inserted, duplicates=duplicates)


@app.get("/health")
def health(conn=Depends(get_conn)) -> dict:
    db.ping(conn)
    return {"status": "ok", "time": db.iso(datetime.now(timezone.utc))}
