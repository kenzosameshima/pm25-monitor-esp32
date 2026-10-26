"""Regras de análise compartilhadas pelo dashboard, pelos scripts e pela API de leitura.

Cada função recebe a conexão e o instante de referência e devolve um DataFrame já calculado,
com horários em UTC. Formatação, rótulos e fuso de exibição ficam com quem chama.
"""

import sqlite3
from datetime import datetime
from typing import Iterable, NamedTuple

import numpy as np
import pandas as pd

from app import db

MIN_READINGS_PER_HOUR = 45  # 75% dos minutos: critério para uma média horária válida
HIGH_HUMIDITY = 75.0        # acima disso, sensores ópticos tendem a superestimar o PM2,5
LATE_AFTER_MIN = 3          # sem envio há esse tempo, o nó aparece como atrasado
SILENT_AFTER_MIN = 15       # e, a partir deste, como sem dados
TEST_DEVICE_PREFIX = "teste"  # ex.: teste-https, criado por scripts/check_https.py
VARIABLES = ("pm25", "pm10", "pm1", "temperature", "humidity")
OBSERVED = "observado"
PERSISTENCE = "persistencia"

# Faixas de PM2,5 da CETESB (µg/m³), as mesmas do app (shared/air-quality-bands.json, conferido por teste).
# O limite pertence à faixa de baixo: 25,0 é Boa.
AIR_QUALITY_BANDS = [(25.0, "Boa"), (50.0, "Moderada"), (75.0, "Ruim"), (125.0, "Muito ruim"),
                     (float("inf"), "Péssima")]

HOURLY_COLUMNS = ["device_id", "hora", "n", *VARIABLES]
STATUS_COLUMNS = ["device_id", "location", "first_ts", "last_received", "status", "minutes_since",
                  "ts_sensor", *VARIABLES, "rssi", "quality"]
HEALTH_COLUMNS = ["device_id", "completude", "maior_lacuna_min", "mensagens_perdidas", "reinicios",
                  "duplicatas_descartadas", "leituras_marcadas"]
METRIC_COLUMNS = ["previsor", "horas", "mae", "rmse", "skill"]


class ForecastComparison(NamedTuple):
    series: pd.DataFrame   # índice: hora UTC; colunas: observado, persistencia e um previsor por modelo
    metrics: pd.DataFrame  # METRIC_COLUMNS, uma linha por previsor com horas para comparar


def is_test_device(device_id: str) -> bool:
    """Dispositivos de teste ficam fora do painel e das métricas do período."""
    return device_id.startswith(TEST_DEVICE_PREFIX)


def air_quality(pm25) -> str | None:
    """Nome da faixa de qualidade do ar de um valor de PM2,5; None sem valor válido."""
    if pm25 is None or pd.isna(pm25) or pm25 < 0:
        return None
    return next(label for bound, label in AIR_QUALITY_BANDS if pm25 <= bound)


def production_devices(conn: sqlite3.Connection) -> list[str]:
    """Nós com leituras, sem os de teste, em ordem de nome."""
    return [r["device_id"] for r in db.device_overview(conn) if not is_test_device(r["device_id"])]


def _frame(rows, time_cols) -> pd.DataFrame:
    df = pd.DataFrame([dict(r) for r in rows])
    for col in time_cols:
        if col in df:
            df[col] = pd.to_datetime(df[col], utc=True)
    return df


def _measurements(conn: sqlite3.Connection, start: datetime, end: datetime,
                  devices: Iterable[str] | None) -> pd.DataFrame:
    df = _frame(db.fetch_measurements(conn, start, end, devices), ["ts_sensor", "ts_received"])
    if not df.empty:
        # Uma coluna toda nula (sensor de umidade ausente, por exemplo) viria como object.
        df[list(VARIABLES)] = df[list(VARIABLES)].astype(float)
    return df


def hourly_means(conn: sqlite3.Connection, start: datetime, end: datetime,
                 devices: Iterable[str] | None = None, *,
                 min_readings: int = MIN_READINGS_PER_HOUR, only_ok: bool = True) -> pd.DataFrame:
    """Médias horárias por nó, com leituras de ts_sensor em [start, end).

    Uma linha por nó e hora, sem saltos, da primeira à última hora com leitura do nó; `n` conta as
    leituras usadas. Horas com menos de `min_readings` leituras ficam com as médias em NaN.
    Com `only_ok`, só entram leituras de qualidade 'ok'.
    """
    df = _measurements(conn, start, end, devices)
    if only_ok and not df.empty:
        df = df[df["quality"] == "ok"]
    if df.empty:
        return pd.DataFrame(columns=HOURLY_COLUMNS)
    parts = []
    for device, d in df.groupby("device_id"):
        grouped = d.set_index("ts_sensor").sort_index().resample("1h")
        h = grouped[list(VARIABLES)].mean()
        h["n"] = grouped["pm25"].count()
        h.loc[h["n"] < min_readings, list(VARIABLES)] = np.nan
        parts.append(h.rename_axis("hora").reset_index().assign(device_id=device))
    return pd.concat(parts, ignore_index=True)[HOURLY_COLUMNS]


def _status(last_received, now: datetime) -> tuple[str, float]:
    if last_received is None or pd.isna(last_received):
        return "sem_dados", np.nan
    minutes = (now - last_received).total_seconds() / 60
    if minutes < LATE_AFTER_MIN:
        return "em_operacao", minutes
    if minutes < SILENT_AFTER_MIN:
        return "atrasado", minutes
    return "sem_dados", minutes


def device_status(conn: sqlite3.Connection, now: datetime) -> pd.DataFrame:
    """Uma linha por nó em produção: local, estado da coleta, minutos desde o último envio e a leitura mais recente.

    `status` é 'em_operacao' (envio há menos de LATE_AFTER_MIN), 'atrasado' (menos de
    SILENT_AFTER_MIN) ou 'sem_dados'. `ts_sensor` e as variáveis são da leitura mais recente.
    """
    overview = _frame(db.device_overview(conn), ["first_ts", "last_received"])
    if not overview.empty:
        overview = overview[~overview["device_id"].map(is_test_device).astype(bool)]
    if overview.empty:
        return pd.DataFrame(columns=STATUS_COLUMNS)
    latest = _frame(db.latest_measurements(conn), ["ts_sensor"])
    out = overview.merge(latest, on="device_id", how="left")
    states = [_status(last, now) for last in out["last_received"]]
    out["status"] = [s for s, _ in states]
    out["minutes_since"] = [m for _, m in states]
    return out[STATUS_COLUMNS]


def collection_health(conn: sqlite3.Connection, start: datetime, now: datetime,
                      devices: Iterable[str] | None = None) -> pd.DataFrame:
    """Saúde da coleta de cada nó em produção (ou só dos `devices` pedidos, de teste ou não) entre `start` e `now`.

    A completude conta minutos com leitura sobre os esperados desde `start` (ou desde a primeira
    leitura do nó, se for depois). Mensagens perdidas são lacunas de `seq` dentro de uma mesma
    inicialização; reinícios são as inicializações além da primeira.
    """
    overview = _frame(db.device_overview(conn), ["first_ts"])
    if not overview.empty:
        if devices is None:
            overview = overview[~overview["device_id"].map(is_test_device).astype(bool)]
        else:
            overview = overview[overview["device_id"].isin(list(devices))]
    if overview.empty:
        return pd.DataFrame(columns=HEALTH_COLUMNS)
    df = _measurements(conn, start, now + pd.Timedelta(minutes=1), list(overview["device_id"]))
    batches = _frame(db.fetch_ingest_batches(conn, start), ["received_at"])
    rows = []
    for _, dev in overview.iterrows():
        d = df[df["device_id"] == dev["device_id"]] if not df.empty else df
        first = max(start, dev["first_ts"].to_pydatetime())
        expected = max(1, int((now - first).total_seconds() // 60))
        minutes = d["ts_sensor"].drop_duplicates().sort_values() if not d.empty else pd.Series(dtype="object")
        if len(minutes):
            gaps = (minutes.diff().dt.total_seconds() / 60 - 1).fillna(0)
            trailing = (now - minutes.iloc[-1]).total_seconds() / 60 - 1
            largest_gap = max(gaps.max(), trailing, 0)
            per_boot = d.groupby("boot_id")["seq"].agg(["min", "max", "nunique"])
            lost = int((per_boot["max"] - per_boot["min"] + 1 - per_boot["nunique"]).sum())
            restarts = max(0, d["boot_id"].nunique() - 1)
        else:
            largest_gap, lost, restarts = (now - first).total_seconds() / 60, 0, 0
        dup = 0
        if not batches.empty:
            dup = int(batches.loc[batches["device_id"] == dev["device_id"], "n_duplicates"].sum())
        rows.append({
            "device_id": dev["device_id"],
            "completude": min(1.0, len(minutes) / expected),
            "maior_lacuna_min": int(round(largest_gap)),
            "mensagens_perdidas": lost,
            "reinicios": restarts,
            "duplicatas_descartadas": dup,
            "leituras_marcadas": int((d["quality"] != "ok").sum()) if not d.empty else 0,
        })
    return pd.DataFrame(rows, columns=HEALTH_COLUMNS)


def forecast_scores(y: np.ndarray, pred: np.ndarray, pred_persistence: np.ndarray) -> dict:
    """MAE, RMSE e skill score (1 − RMSE do previsor ÷ RMSE da persistência), todos nas mesmas horas.

    Os três vetores se alinham hora a hora. Com a persistência perfeita (RMSE zero), o skill score
    fica indefinido (None).
    """
    err = pred - y
    rmse = float(np.sqrt(np.mean(err ** 2)))
    rmse_p = float(np.sqrt(np.mean((pred_persistence - y) ** 2)))
    return {"n": int(len(y)), "mae": float(np.mean(np.abs(err))), "rmse": rmse,
            "skill": float(1 - rmse / rmse_p) if rmse_p > 0 else None}


def _forecast_metrics(series: pd.DataFrame) -> pd.DataFrame:
    """Métricas de cada previsor nas horas com observação, persistência e previsão do previsor.

    Exigir a persistência em todas as horas faz o skill score comparar o previsor e a persistência
    sobre as mesmas horas, como na avaliação offline.
    """
    rows = []
    for name in (c for c in series.columns if c != OBSERVED):
        hours = series[list(dict.fromkeys([OBSERVED, PERSISTENCE, name]))].dropna()
        if hours.empty:
            continue
        s = forecast_scores(hours[OBSERVED].to_numpy(float), hours[name].to_numpy(float),
                            hours[PERSISTENCE].to_numpy(float))
        rows.append({"previsor": name, "horas": s["n"], "mae": s["mae"], "rmse": s["rmse"], "skill": s["skill"]})
    return pd.DataFrame(rows, columns=METRIC_COLUMNS)


def forecast_comparison(conn: sqlite3.Connection, device: str, now: datetime,
                        hours: int = 48) -> ForecastComparison:
    """Observado × previsto para um nó nas últimas `hours` horas, até a hora seguinte à atual.

    A persistência repete a média da hora anterior. Cada modelo gravado em `forecasts` vira uma
    coluna "<model_name> <model_version>", com a previsão mais recente para cada hora-alvo.
    """
    current_hour = now.replace(minute=0, second=0, microsecond=0)
    start = current_hour - pd.Timedelta(hours=hours)
    end = current_hour + pd.Timedelta(hours=2)
    index = pd.date_range(start - pd.Timedelta(hours=1), current_hour + pd.Timedelta(hours=1), freq="h", tz="UTC")

    hourly = hourly_means(conn, start - pd.Timedelta(hours=1), end, [device])
    observed = hourly.set_index("hora")["pm25"].reindex(index)
    series = pd.DataFrame({OBSERVED: observed, PERSISTENCE: observed.shift(1)})

    forecasts = _frame(db.fetch_forecasts(conn, start, end, [device]), ["generated_at", "target_hour"])
    if not forecasts.empty:
        forecasts["previsor"] = forecasts["model_name"] + " " + forecasts["model_version"]
        latest = forecasts.sort_values("generated_at").groupby(["target_hour", "previsor"]).last()
        series = series.join(latest["predicted_pm25"].unstack("previsor").reindex(index))
    series = series.loc[start:]
    return ForecastComparison(series, _forecast_metrics(series))
