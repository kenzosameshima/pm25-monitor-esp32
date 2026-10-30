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

# Hora suspeita: o sensor respondeu, mas quase não viu partículas (leituras de PM2,5 em zero ou perto disso por
# horas, o que o ar de uma cidade não faz). A regra foi fixada olhando a distribuição das médias horárias de
# 09 a 26/10/2026: fora desses episódios, a menor média horária foi 1,36 µg/m³.
SUSPECT_LOW_PM25 = 0.5      # µg/m³: uma leitura abaixo disso conta como "sem partículas"
SUSPECT_LOW_SHARE = 0.25    # a hora é suspeita se pelo menos esta fração das leituras está nesse caso...
SUSPECT_MEAN_BELOW = 1.0    # ...ou se a média do PM2,5 da hora fica abaixo disto (µg/m³)

HOURLY_COLUMNS = ["device_id", "hora", "n", *VARIABLES, "suspeita"]
STATUS_COLUMNS = ["device_id", "location", "first_ts", "last_received", "status", "minutes_since",
                  "ts_sensor", *VARIABLES, "rssi", "quality", "firmware"]
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


def band_position(pm25) -> float | None:
    """Onde um PM2,5 cai numa escala de 0 a 1 que dá a cada faixa o mesmo comprimento.

    Dentro de cada faixa a posição é proporcional ao valor. A última faixa não tem teto: a escala a mostra
    até o dobro do seu limite inferior (de 125 a 250), e o que passa disso fica no fim. None sem valor válido.
    """
    if pm25 is None or pd.isna(pm25) or pm25 < 0:
        return None
    finite = [bound for bound, _ in AIR_QUALITY_BANDS[:-1]]
    starts, ends = [0.0, *finite], [*finite, 2 * finite[-1]]
    for i, (start, end) in enumerate(zip(starts, ends)):
        if pm25 <= end:
            return (i + (pm25 - start) / (end - start)) / len(ends)
    return 1.0


def is_zero_reading(pm1, pm25, pm10) -> bool:
    """Se uma leitura tem todas as partículas que o nó enviou em zero (e ao menos o PM2,5).

    É o padrão que o ADR 0004 trata como suspeito, mas numa leitura só ele não decide se o sensor parou de ver
    partículas ou se o ar está muito limpo: por isso quem mostra a leitura não lhe dá faixa de qualidade do ar.
    """
    if pm25 is None or pd.isna(pm25):
        return False
    sent = [v for v in (pm1, pm25, pm10) if v is not None and not pd.isna(v)]
    return all(v == 0 for v in sent)


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
                 min_readings: int = MIN_READINGS_PER_HOUR, only_ok: bool = True,
                 drop_suspect: bool = True) -> pd.DataFrame:
    """Médias horárias por nó, com leituras de ts_sensor em [start, end).

    Uma linha por nó e hora, sem saltos, da primeira à última hora com leitura do nó; `n` conta as
    leituras usadas. Horas com menos de `min_readings` leituras ficam com as médias em NaN.
    Com `only_ok`, só entram leituras de qualidade 'ok'.

    `suspeita` marca a hora válida em que o sensor quase não viu partículas: pelo menos SUSPECT_LOW_SHARE das
    leituras abaixo de SUSPECT_LOW_PM25, ou média do PM2,5 abaixo de SUSPECT_MEAN_BELOW. Vale só com `only_ok`
    (o filtro de qualidade ligado). Uma hora suspeita fica com as médias em NaN, como a de poucas leituras,
    a menos que `drop_suspect` seja falso: então a marca continua e as médias ficam, para análises de
    sensibilidade e para conferir a regra contra uma estação de referência.
    """
    df = _measurements(conn, start, end, devices)
    if only_ok and not df.empty:
        df = df[df["quality"] == "ok"]
    if df.empty:
        return pd.DataFrame(columns=HOURLY_COLUMNS)
    parts = []
    for device, d in df.groupby("device_id"):
        d = d.assign(_low=(d["pm25"] < SUSPECT_LOW_PM25).astype(int))
        grouped = d.set_index("ts_sensor").sort_index().resample("1h")
        h = grouped[list(VARIABLES)].mean()
        h["n"] = grouped["pm25"].count()
        h["suspeita"] = False
        if only_ok:
            lows = grouped["_low"].sum()
            h["suspeita"] = (h["n"] >= min_readings) & ((lows >= SUSPECT_LOW_SHARE * h["n"])
                                                        | (h["pm25"] < SUSPECT_MEAN_BELOW))
        h.loc[h["n"] < min_readings, list(VARIABLES)] = np.nan
        if drop_suspect:
            h.loc[h["suspeita"], list(VARIABLES)] = np.nan
        parts.append(h.rename_axis("hora").reset_index().assign(device_id=device))
    return pd.concat(parts, ignore_index=True)[HOURLY_COLUMNS]


EXCLUSION_COLUMNS = ["hora", "device_id", "causa"]
NO_READINGS, FEW_READINGS, SUSPECT_HOUR = "sem leituras", "poucas leituras", "suspeita"
EXCLUSION_CAUSES = (NO_READINGS, FEW_READINGS, SUSPECT_HOUR)


def hour_exclusions(hourly: pd.DataFrame, *, until: datetime | None = None,
                    min_readings: int = MIN_READINGS_PER_HOUR) -> pd.DataFrame:
    """As horas do `hourly_means` que ficaram sem média, com a causa de cada uma (EXCLUSION_CAUSES).

    'sem leituras': nenhuma leitura na hora. 'poucas leituras': leituras, mas menos que `min_readings`.
    'suspeita': leituras suficientes em que o sensor quase não viu partículas (ADR 0004). Só entram as horas
    entre a primeira e a última leitura de cada nó no período, como em `hourly_means`; com `until` (UTC), cada
    nó é estendido como 'sem leituras' até a última hora que terminou antes desse instante, para um nó que
    parou aparecer parado até agora. Também com `until`, a hora ainda em andamento fica de fora: ela tem
    poucas leituras só porque não acabou.
    """
    if hourly.empty:
        return pd.DataFrame(columns=EXCLUSION_COLUMNS)
    suspect = hourly["suspeita"].astype(bool)
    out = hourly[suspect | (hourly["n"] < min_readings)]
    if until is not None:
        out = out[out["hora"] + pd.Timedelta(hours=1) <= pd.Timestamp(until)]
    cause = np.select([suspect[out.index], out["n"] == 0], [SUSPECT_HOUR, NO_READINGS], FEW_READINGS)
    parts = [pd.DataFrame({"hora": out["hora"], "device_id": out["device_id"], "causa": cause})]
    if until is not None:
        end = pd.Timestamp(until).floor("h")
        for device, last in hourly.groupby("device_id")["hora"].max().items():
            stopped = pd.date_range(last + pd.Timedelta(hours=1), end, freq="h", inclusive="left")
            parts.append(pd.DataFrame({"hora": stopped, "device_id": device, "causa": NO_READINGS}))
    return (pd.concat(parts, ignore_index=True).sort_values(["device_id", "hora"], ignore_index=True)
            [EXCLUSION_COLUMNS])


STATE_COLUMNS = ["hora", "device_id", "estado", "n"]
VALID_HOUR = "válida"


def hour_states(hourly: pd.DataFrame, *, until: datetime | None = None,
                min_readings: int = MIN_READINGS_PER_HOUR) -> pd.DataFrame:
    """Todas as horas do `hourly_means` com o estado de cada uma e os minutos que tiveram leitura (`n`).

    O estado é VALID_HOUR para a hora com média, ou a causa de a hora ter ficado sem média (EXCLUSION_CAUSES), a mesma de
    `hour_exclusions`, que decide quais horas são essas, inclusive o que fazer com `until`. As horas que `until` estende
    para um nó que parou têm 0 minutos. A hora em andamento só aparece se já tem média: sem ela, fica de fora.
    """
    if hourly.empty:
        return pd.DataFrame(columns=STATE_COLUMNS)
    excluded = hour_exclusions(hourly, until=until, min_readings=min_readings).rename(columns={"causa": "estado"})
    minutes = hourly.set_index(["device_id", "hora"])["n"]
    excluded["n"] = [int(minutes.get((device, hour), 0)) for device, hour in zip(excluded["device_id"], excluded["hora"])]
    valid = hourly[~hourly["suspeita"].astype(bool) & (hourly["n"] >= min_readings)]
    valid = pd.DataFrame({"hora": valid["hora"], "device_id": valid["device_id"], "estado": VALID_HOUR, "n": valid["n"]})
    return (pd.concat([excluded, valid], ignore_index=True).sort_values(["device_id", "hora"], ignore_index=True)
            [STATE_COLUMNS].astype({"n": int}))


RUN_COLUMNS = ["device_id", "estado", "inicio", "fim", "horas"]


def state_runs(states: pd.DataFrame) -> pd.DataFrame:
    """Os blocos de horas seguidas do mesmo estado em cada nó, a partir de `hour_states`.

    `inicio` é o começo da primeira hora do bloco e `fim`, o fim da última (uma hora depois do começo dela); `horas` é
    quantas há. Uma hora que falta no meio, ou a troca de nó, começa outro bloco.
    """
    if states.empty:
        return pd.DataFrame(columns=RUN_COLUMNS)
    ordered = states.sort_values(["device_id", "hora"], ignore_index=True)
    new_run = ((ordered["device_id"] != ordered["device_id"].shift())
               | (ordered["estado"] != ordered["estado"].shift())
               | (ordered["hora"].diff() != pd.Timedelta(hours=1)))
    runs = ordered.groupby(new_run.cumsum(), sort=True).agg(
        device_id=("device_id", "first"), estado=("estado", "first"), inicio=("hora", "min"), ultima=("hora", "max"),
        horas=("hora", "size"))
    runs["fim"] = runs["ultima"] + pd.Timedelta(hours=1)
    return runs.reset_index(drop=True)[RUN_COLUMNS]


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
    out["firmware"] = out["device_id"].map(db.latest_firmware(conn))
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
    """Métricas de cada previsor, todos nas mesmas horas.

    As horas avaliadas são as que têm observação, persistência e previsão de todos os modelos: só
    assim o MAE e o RMSE de uma linha se comparam com os das outras, e o skill score compara o
    previsor e a persistência sobre as mesmas horas, como na avaliação offline. Sem modelo, a
    persistência fica com todas as horas que tem. Se os modelos não têm nenhuma hora em comum (uma
    versão parou antes de a outra começar), cada um fica com as suas e a persistência com todas.
    """
    scorable = series[[OBSERVED, PERSISTENCE]].dropna().index
    own = {c: scorable.intersection(series[c].dropna().index)
           for c in series.columns if c not in (OBSERVED, PERSISTENCE)}
    own = {c: hours for c, hours in own.items() if not hours.empty}
    shared = scorable
    for hours in own.values():
        shared = shared.intersection(hours)
    windows = {PERSISTENCE: shared, **dict.fromkeys(own, shared)}
    if own and shared.empty:
        windows = {PERSISTENCE: scorable, **own}
    rows = []
    for name, index in windows.items():
        if index.empty:
            continue
        hours = series.loc[index]
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
