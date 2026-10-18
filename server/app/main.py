"""API de ingestão e consulta.

Recebe lotes de leituras dos nós e só responde 201 depois de gravar no banco. As rotas de leitura do
app de consulta ficam em read_api.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Iterator

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from . import db, read_api
from .config import get_settings
from .guard import AuthThrottle, BodySizeLimit, client_ip, require_bearer
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
    app.state.throttle = AuthThrottle(settings.auth_max_fails, settings.auth_block_s)
    yield


app = FastAPI(title="PM2,5 — API de ingestão e consulta", version="1.1.0", lifespan=lifespan)
app.add_middleware(BodySizeLimit, limit=lambda: get_settings().max_body_bytes)
app.include_router(read_api.router)


def get_conn() -> Iterator:
    conn = db.connect(get_settings().db_path)
    try:
        yield conn
    finally:
        conn.close()


INGEST_PATH = "/v1/measurements"


def authenticate(request: Request, authorization: str | None = Header(default=None)) -> str:
    """Identifica o dispositivo pelo 'Authorization: Bearer <token>'.

    Token ausente ou inválido recebe o mesmo 401, é registrado sem o token e conta para o bloqueio do IP.
    """
    def record_failure(ip: str | None) -> None:
        conn = db.connect(get_settings().db_path)
        try:
            db.record_invalid(
                conn,
                reason="Falha de autenticação: token " + ("ausente" if not authorization else "inválido"),
                raw_payload="",
                received_at=datetime.now(timezone.utc),
                remote_addr=ip,
            )
        finally:
            conn.close()

    return require_bearer(request, authorization, get_settings().device_for_token, record_failure)


@app.exception_handler(RequestValidationError)
async def record_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Payload fora do contrato: guarda para auditoria e responde 422.

    O nó descarta lotes recusados com 4xx (exceto 401, 403, 408 e 429) para não ficar preso
    reenviando o mesmo dado inválido; por isso o registro aqui é a única cópia que sobra.

    Só a ingestão é auditada, e só com token de nó válido: o FastAPI lê o JSON antes das dependências,
    então um corpo malformado chega aqui sem ter passado por `authenticate`.
    """
    if request.url.path != INGEST_PATH:
        return await request_validation_exception_handler(request, exc)
    try:
        # O registro leva o nó dono do token; o device_id do corpo vem do cliente e fica só no raw_payload.
        device = authenticate(request, request.headers.get("authorization"))
    except HTTPException as denied:
        return await http_exception_handler(request, denied)
    conn = db.connect(get_settings().db_path)
    try:
        db.record_invalid(
            conn,
            reason=str(exc.errors())[:2000],
            raw_payload=exc.body,
            received_at=datetime.now(timezone.utc),
            remote_addr=client_ip(request),
            device_id=device,
        )
    finally:
        conn.close()
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(exc.errors())})


@app.post(INGEST_PATH, status_code=status.HTTP_201_CREATED, response_model=IngestResult)
def ingest(batch: Batch, request: Request, device: str = Depends(authenticate), conn=Depends(get_conn)):
    now = datetime.now(timezone.utc)
    if batch.device_id != device:
        db.record_invalid(
            conn,
            reason=f"device_id '{batch.device_id}' não corresponde ao token de '{device}'",
            raw_payload=batch.model_dump(mode="json"),
            received_at=now,
            remote_addr=client_ip(request),
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
    inserted, duplicates = db.insert_batch(conn, batch.device_id, rows, now, client_ip(request))
    return IngestResult(inserted=inserted, duplicates=duplicates)


@app.get("/health")
def health(conn=Depends(get_conn)) -> dict:
    db.ping(conn)
    return {"status": "ok", "time": db.iso(datetime.now(timezone.utc))}
