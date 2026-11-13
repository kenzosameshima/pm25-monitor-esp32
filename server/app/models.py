"""Contrato de dados v1 entre os nós sensores e a API."""

from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, field_validator, model_validator

MAX_BATCH = 500
MIN_VALID_TS = datetime(2026, 1, 1, tzinfo=timezone.utc)
MAX_FUTURE_SKEW = timedelta(minutes=5)


class Reading(BaseModel):
    """Uma leitura = média de 1 minuto do PMS5003 mais temperatura, umidade, pressão e diagnóstico."""

    model_config = ConfigDict(extra="ignore")

    boot_id: int = Field(ge=0, le=2**31 - 1)
    seq: int = Field(ge=0, le=2**31 - 1)
    ts: datetime
    pm25: FiniteFloat
    pm1: FiniteFloat | None = None
    pm10: FiniteFloat | None = None
    pm25_cf1: FiniteFloat | None = None
    temperature: FiniteFloat | None = None
    humidity: FiniteFloat | None = None
    pressure: FiniteFloat | None = None  # hPa; só o BME280 mede
    rssi: int | None = Field(default=None, ge=-127, le=0)
    uptime_s: int | None = Field(default=None, ge=0)
    samples: int | None = Field(default=None, ge=0)

    @field_validator("ts")
    @classmethod
    def _must_have_timezone(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError("ts precisa indicar o fuso horário, ex.: 2026-09-22T12:00:00Z")
        return v.astimezone(timezone.utc)


MAX_FIRMWARE_LEN = 64
MAX_RESET_REASON_LEN = 32
MAX_BOOT_ID = 2**31 - 1


def _tidy_text(v, limit: int) -> str | None:
    """Texto só de diagnóstico: sem caracteres de controle, cortado em `limit`; o que não é texto útil vira None."""
    if not isinstance(v, str):
        return None
    return "".join(c for c in v if c.isprintable()).strip()[:limit].strip() or None


class Batch(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: Literal["1"]
    device_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    # Identifica a compilação gravada no nó. Só diagnóstico: o nó descarta o lote recusado com 4xx, então
    # um valor estranho é limpo ou ignorado, nunca motivo para recusar as leituras.
    firmware: str | None = None
    # Motivo do reinício que começou a inicialização em curso do nó (`reset_boot_id`), como o firmware o nomeia
    # (esp_reset_reason). Só diagnóstico, como `firmware`: valor estranho é limpo ou ignorado, nunca recusado.
    reset_reason: str | None = None
    reset_boot_id: int | None = None
    readings: list[Reading] = Field(min_length=1, max_length=MAX_BATCH)

    @field_validator("firmware", mode="before")
    @classmethod
    def _tidy_firmware(cls, v):
        return _tidy_text(v, MAX_FIRMWARE_LEN)

    @field_validator("reset_reason", mode="before")
    @classmethod
    def _tidy_reset_reason(cls, v):
        return _tidy_text(v, MAX_RESET_REASON_LEN)

    @field_validator("reset_boot_id", mode="before")
    @classmethod
    def _tidy_reset_boot_id(cls, v):
        # bool é int em Python; True não é uma inicialização.
        return v if isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= MAX_BOOT_ID else None

    @model_validator(mode="after")
    def _boot_id_only_with_reason(self):
        if self.reset_reason is None:
            self.reset_boot_id = None  # a inicialização só diz algo junto do motivo
        return self


class IngestResult(BaseModel):
    inserted: int
    duplicates: int


def quality_flags(r: Reading, now: datetime) -> str:
    """Validação mínima na ingestão: só marca valores fisicamente implausíveis, sem descartar.

    Critérios que podem mudar depois (umidade alta, outliers) ficam no processamento em batch.
    """
    flags = []
    if r.ts > now + MAX_FUTURE_SKEW:
        flags.append("ts_futuro")
    if r.ts < MIN_VALID_TS:
        flags.append("ts_antigo")
    if not 0 <= r.pm25 <= 1000:
        flags.append("pm25_fora_faixa")
    if r.temperature is not None and not -20 <= r.temperature <= 70:
        flags.append("temp_fora_faixa")
    if r.humidity is not None and not 0 <= r.humidity <= 100:
        flags.append("umid_fora_faixa")
    if r.pressure is not None and not 300 <= r.pressure <= 1100:
        flags.append("pressao_fora_faixa")
    return ",".join(flags) if flags else "ok"
