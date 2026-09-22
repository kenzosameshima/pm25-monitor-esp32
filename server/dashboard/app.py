"""Dashboard de monitoramento de PM2,5 (Streamlit).

Lê o banco SQLite em modo somente leitura; o modo WAL permite ler enquanto a API grava.
Uso, a partir da pasta server/:   streamlit run dashboard/app.py
"""

import sys
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import altair as alt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app import db  # noqa: E402
from app.config import get_settings  # noqa: E402

LOCAL_TZ = "America/Sao_Paulo"
MIN_MINUTES_PER_HOUR = 45  # 75% dos minutos: critério para uma média horária válida
HIGH_HUMIDITY = 75.0       # acima disso, sensores ópticos tendem a superestimar o PM2,5
VARIABLES = {
    "pm25": "PM2,5 (µg/m³)",
    "pm10": "PM10 (µg/m³)",
    "pm1": "PM1,0 (µg/m³)",
    "temperature": "Temperatura (°C)",
    "humidity": "Umidade relativa (%)",
}

st.set_page_config(page_title="PM2,5 — monitoramento", page_icon="🌫️", layout="wide")
alt.data_transformers.disable_max_rows()


# ---------------------------------------------------------------- dados

def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(second=0, microsecond=0)


def _read(fn, *args):
    path = get_settings().db_path
    if not Path(path).exists():
        return []
    conn = db.connect(path, readonly=True)
    try:
        return fn(conn, *args)
    finally:
        conn.close()


def _frame(rows, time_cols) -> pd.DataFrame:
    df = pd.DataFrame([dict(r) for r in rows])
    for col in time_cols:
        if col in df:
            df[col] = pd.to_datetime(df[col], utc=True)
    return df


@st.cache_data(ttl=30)
def load_overview() -> pd.DataFrame:
    return _frame(_read(db.device_overview), ["first_ts", "last_ts", "last_received"])


@st.cache_data(ttl=30)
def load_latest() -> pd.DataFrame:
    return _frame(_read(db.latest_measurements), ["ts_sensor", "ts_received"])


@st.cache_data(ttl=30)
def load_measurements(start: datetime, end: datetime, devices: tuple) -> pd.DataFrame:
    return _frame(_read(db.fetch_measurements, start, end, list(devices)), ["ts_sensor", "ts_received"])


@st.cache_data(ttl=30)
def load_batches(since: datetime) -> pd.DataFrame:
    return _frame(_read(db.fetch_ingest_batches, since), ["received_at"])


@st.cache_data(ttl=60)
def load_forecasts(start: datetime, end: datetime, devices: tuple) -> pd.DataFrame:
    return _frame(_read(db.fetch_forecasts, start, end, list(devices)), ["generated_at", "target_hour"])


def local_naive(series: pd.Series) -> pd.Series:
    """Horário local sem fuso, para o gráfico mostrar a hora de Brasília em qualquer navegador."""
    return series.dt.tz_convert(LOCAL_TZ).dt.tz_localize(None)


def hourly(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Médias horárias por sensor, só para horas com pelo menos 45 minutos de leitura."""
    if df.empty:
        return pd.DataFrame(columns=["device_id", "hora", "minutos", *cols])
    grouped = df.assign(hora=df["ts_sensor"].dt.floor("h")).groupby(["device_id", "hora"])
    out = grouped[cols].mean()
    out["minutos"] = grouped.size()
    return out[out["minutos"] >= MIN_MINUTES_PER_HOUR].reset_index()


# ---------------------------------------------------------------- formatação

def fmt(value, unit: str, decimals: int = 1) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value:.{decimals}f}{unit}"


def ago(minutes: float | None) -> str:
    if minutes is None:
        return "nunca"
    if minutes < 1:
        return "agora"
    if minutes < 60:
        return f"há {int(minutes)} min"
    if minutes < 48 * 60:
        return f"há {minutes / 60:.1f} h"
    return f"há {minutes / 1440:.0f} dias"


def status_of(last_received, now: datetime) -> tuple[str, float | None]:
    if last_received is None or pd.isna(last_received):
        return "🔴 sem dados", None
    minutes = (now - last_received).total_seconds() / 60
    if minutes < 3:
        return "🟢 em operação", minutes
    if minutes < 15:
        return "🟡 atrasado", minutes
    return "🔴 sem dados", minutes


def with_segments(data: pd.DataFrame, x: str, color: str, max_gap: pd.Timedelta) -> pd.DataFrame:
    """Numera trechos contínuos de cada série, para o gráfico não ligar pontos separados por uma lacuna."""
    d = data.sort_values([color, x]).copy()
    jump = d.groupby(color)[x].diff() > max_gap
    d["segmento"] = d[color].astype(str) + "-" + jump.groupby(d[color]).cumsum().astype(int).astype(str)
    return d


def line_chart(data: pd.DataFrame, x: str, y: str, title: str, max_gap: pd.Timedelta,
               rule: float | None = None, color: str = "device_id", legend: str = "Sensor") -> alt.Chart:
    data = with_segments(data[[x, y, color]].dropna(), x, color, max_gap)
    chart = alt.Chart(data).mark_line(point=len(data) <= 400).encode(
        x=alt.X(f"{x}:T", title=None, axis=alt.Axis(format="%d/%m %H:%M")),
        y=alt.Y(f"{y}:Q", title=title, scale=alt.Scale(zero=False)),
        color=alt.Color(f"{color}:N", title=legend),
        detail="segmento:N",
        tooltip=[
            alt.Tooltip(f"{x}:T", title="Horário", format="%d/%m %H:%M"),
            alt.Tooltip(f"{color}:N", title=legend),
            alt.Tooltip(f"{y}:Q", title=title, format=".1f"),
        ],
    )
    if rule is not None:
        chart = chart + alt.Chart(pd.DataFrame({"limite": [rule]})).mark_rule(
            strokeDash=[4, 4], color="gray").encode(y="limite:Q")
    return chart.properties(height=260)


# ---------------------------------------------------------------- saúde da coleta

def collection_health(df: pd.DataFrame, overview: pd.DataFrame, batches: pd.DataFrame,
                      window_start: datetime, now: datetime) -> pd.DataFrame:
    rows = []
    for _, dev in overview.iterrows():
        d = df[df["device_id"] == dev["device_id"]] if not df.empty else df
        start = max(window_start, dev["first_ts"].to_pydatetime())
        expected = max(1, int((now - start).total_seconds() // 60))
        minutes = d["ts_sensor"].drop_duplicates().sort_values() if not d.empty else pd.Series(dtype="object")
        if len(minutes):
            gaps = (minutes.diff().dt.total_seconds() / 60 - 1).fillna(0)
            trailing = (now - minutes.iloc[-1]).total_seconds() / 60 - 1
            largest_gap = max(gaps.max(), trailing, 0)
            per_boot = d.groupby("boot_id")["seq"].agg(["min", "max", "nunique"])
            lost = int((per_boot["max"] - per_boot["min"] + 1 - per_boot["nunique"]).sum())
            restarts = max(0, d["boot_id"].nunique() - 1)
        else:
            largest_gap, lost, restarts = (now - start).total_seconds() / 60, 0, 0
        dup = 0
        if not batches.empty:
            dup = int(batches.loc[batches["device_id"] == dev["device_id"], "n_duplicates"].sum())
        rows.append({
            "Sensor": dev["device_id"],
            "Completude": min(1.0, len(minutes) / expected),
            "Maior lacuna (min)": int(round(largest_gap)),
            "Mensagens perdidas": lost,
            "Reinícios": restarts,
            "Duplicatas descartadas": dup,
            "Leituras marcadas": int((d["quality"] != "ok").sum()) if not d.empty else 0,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- abas

@st.fragment(run_every="60s")
def status_tab() -> None:
    now = now_utc()
    overview, latest = load_overview(), load_latest()
    if overview.empty:
        st.info("Nenhuma leitura recebida ainda. Ligue um nó sensor ou rode o simulador (veja o README).")
        return

    cols = st.columns(len(overview))
    for col, (_, dev) in zip(cols, overview.iterrows()):
        last = latest[latest["device_id"] == dev["device_id"]].iloc[0]
        label, minutes = status_of(dev["last_received"], now)
        when = last["ts_sensor"].tz_convert(LOCAL_TZ).strftime("%d/%m %H:%M")
        with col:
            st.subheader(dev["device_id"])
            st.caption(f"{label} · último envio {ago(minutes)} · leitura de {when}")
            a, b = st.columns(2)
            a.metric("PM2,5", fmt(last["pm25"], " µg/m³"))
            b.metric("Umidade", fmt(last["humidity"], "%"))
            a.metric("Temperatura", fmt(last["temperature"], " °C"))
            b.metric("Sinal Wi-Fi", fmt(last["rssi"], " dBm", 0))

    window_start = now - timedelta(hours=24)
    devices = tuple(overview["device_id"])
    df = load_measurements(window_start, now + timedelta(minutes=1), devices)
    health = collection_health(df, overview, load_batches(window_start), window_start, now)
    st.markdown("#### Saúde da coleta nas últimas 24 horas")
    st.dataframe(
        health, hide_index=True,
        column_config={"Completude": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1)},
    )
    st.caption("Mensagens perdidas são lacunas de sequência dentro de uma mesma inicialização do nó; "
               "minutos sem leitura e sem lacuna de sequência indicam falha do sensor, não da rede.")

    recent = df[df["ts_sensor"] >= now - timedelta(hours=6)] if not df.empty else df
    if not recent.empty:
        st.markdown("#### PM2,5 nas últimas 6 horas")
        st.altair_chart(line_chart(recent.assign(hora=local_naive(recent["ts_sensor"])), "hora", "pm25",
                                   VARIABLES["pm25"], pd.Timedelta(minutes=5)), width="stretch")


def series_tab(devices_all: list[str]) -> None:
    today = datetime.now(ZoneInfo(LOCAL_TZ)).date()
    c1, c2, c3 = st.columns([2, 2, 1])
    devices = c1.multiselect("Sensores", devices_all, default=devices_all)
    period = c2.date_input("Período", value=(today - timedelta(days=6), today), max_value=today, format="DD/MM/YYYY")
    resolution = c3.radio("Resolução", ["Média horária", "1 minuto"])
    variables = st.multiselect("Variáveis", list(VARIABLES), default=["pm25", "humidity"], format_func=VARIABLES.get)
    only_ok = st.checkbox("Ocultar leituras marcadas como implausíveis", value=True)

    if not isinstance(period, tuple) or len(period) != 2:
        st.info("Escolha a data inicial e a final.")
        return
    if not devices or not variables:
        st.info("Escolha ao menos um sensor e uma variável.")
        return

    tz = ZoneInfo(LOCAL_TZ)
    start = datetime.combine(period[0], time(), tz).astimezone(timezone.utc)
    end = datetime.combine(period[1] + timedelta(days=1), time(), tz).astimezone(timezone.utc)
    df = load_measurements(start, end, tuple(devices))
    if not df.empty and only_ok:
        df = df[df["quality"] == "ok"]
    if df.empty:
        st.info("Sem leituras no período escolhido.")
        return

    if resolution == "Média horária":
        data = hourly(df, list(VARIABLES))
        data["hora_local"] = local_naive(data["hora"])
        st.caption(f"Médias de horas com pelo menos {MIN_MINUTES_PER_HOUR} minutos de leitura (75%).")
        max_gap = pd.Timedelta(hours=1)
    else:
        data = df.assign(hora_local=local_naive(df["ts_sensor"]))
        max_gap = pd.Timedelta(minutes=5)

    for var in variables:
        rule = HIGH_HUMIDITY if var == "humidity" else None
        st.altair_chart(line_chart(data, "hora_local", var, VARIABLES[var], max_gap, rule=rule), width="stretch")

    if "humidity" in data and data["humidity"].notna().any():
        share = (data.groupby("device_id")["humidity"].apply(lambda s: (s > HIGH_HUMIDITY).mean()))
        parts = ", ".join(f"{dev}: {p:.0%}" for dev, p in share.items())
        st.caption(f"Registros com umidade acima de {HIGH_HUMIDITY:.0f}% ({parts}) podem ter PM2,5 "
                   "superestimado pela absorção de água nas partículas.")

    export = data.drop(columns=["hora_local"]).copy()
    st.download_button("Baixar dados (CSV)", export.to_csv(index=False).encode("utf-8"),
                       file_name=f"pm25_{period[0]}_{period[1]}.csv", mime="text/csv")


def forecast_metrics(table: pd.DataFrame) -> pd.DataFrame:
    """MAE, RMSE e skill score (em relação à persistência) nas horas com observação e previsão."""
    rows = []
    predictors = [c for c in table.columns if c != "Observado"]
    rmse_persist = None
    for name in predictors:
        both = table[["Observado", name]].dropna()
        if both.empty:
            continue
        err = both[name] - both["Observado"]
        rmse = float(np.sqrt((err ** 2).mean()))
        if name == "Persistência":
            rmse_persist = rmse
        rows.append({"Previsor": name, "Horas": len(both), "MAE (µg/m³)": float(err.abs().mean()),
                     "RMSE (µg/m³)": rmse})
    out = pd.DataFrame(rows)
    if not out.empty and rmse_persist:
        out["Skill score"] = 1 - out["RMSE (µg/m³)"] / rmse_persist
    return out


def forecast_tab(devices_all: list[str]) -> None:
    device = st.selectbox("Sensor", devices_all, key="forecast_device")
    now = now_utc()
    current_hour = now.replace(minute=0)
    start = current_hour - timedelta(hours=48)
    end = current_hour + timedelta(hours=2)

    df = load_measurements(start - timedelta(hours=1), end, (device,))
    if not df.empty:
        df = df[df["quality"] == "ok"]
    hours = pd.date_range(start - timedelta(hours=1), current_hour + timedelta(hours=1), freq="h", tz="UTC")
    observed = hourly(df, ["pm25"]).set_index("hora")["pm25"].reindex(hours)

    table = pd.DataFrame({"Observado": observed, "Persistência": observed.shift(1)})
    forecasts = load_forecasts(start, end, (device,))
    if not forecasts.empty:
        forecasts["previsor"] = forecasts["model_name"] + " " + forecasts["model_version"]
        latest = forecasts.sort_values("generated_at").groupby(["target_hour", "previsor"]).last()
        pivot = latest["predicted_pm25"].unstack("previsor").reindex(hours)
        table = table.join(pivot)
    table = table.loc[start:]

    long = table.reset_index(names="hora").melt("hora", var_name="serie", value_name="pm25").dropna()
    if long.empty:
        st.info("Ainda não há horas completas para comparar.")
        return
    long["hora_local"] = local_naive(long["hora"])
    long = with_segments(long, "hora_local", "serie", pd.Timedelta(hours=1))
    chart = alt.Chart(long).mark_line(point=True).encode(
        x=alt.X("hora_local:T", title=None, axis=alt.Axis(format="%d/%m %H:%M")),
        y=alt.Y("pm25:Q", title=VARIABLES["pm25"], scale=alt.Scale(zero=False)),
        color=alt.Color("serie:N", title=None),
        detail="segmento:N",
        strokeDash=alt.condition(alt.datum.serie == "Observado", alt.value([1, 0]), alt.value([5, 4])),
        tooltip=[alt.Tooltip("hora_local:T", title="Hora", format="%d/%m %H:%M"), alt.Tooltip("serie:N", title="Série"),
                 alt.Tooltip("pm25:Q", title="PM2,5", format=".1f")],
    ).properties(height=320)
    st.altair_chart(chart, width="stretch")

    metrics = forecast_metrics(table)
    if not metrics.empty:
        st.dataframe(metrics, hide_index=True, column_config={
            "MAE (µg/m³)": st.column_config.NumberColumn(format="%.2f"),
            "RMSE (µg/m³)": st.column_config.NumberColumn(format="%.2f"),
            "Skill score": st.column_config.NumberColumn(format="%.2f"),
        })
    st.caption("Persistência prevê que a próxima hora repete a média da hora anterior; é o baseline que "
               "qualquer modelo precisa superar (skill score acima de zero).")
    if forecasts.empty:
        st.info("Nenhuma previsão de modelo registrada ainda. Quando o job horário estiver no ar, as previsões "
                "gravadas na tabela forecasts aparecem aqui ao lado da persistência.")


# ---------------------------------------------------------------- página

st.title("Monitoramento de PM2,5")
overview = load_overview()
if overview.empty:
    st.warning(f"Nenhum dado em {get_settings().db_path}. Inicie a API e ligue um nó sensor ou o simulador.")
    st.stop()

devices_all = list(overview["device_id"])
tab_status, tab_series, tab_forecast = st.tabs(["Status", "Séries", "Previsto × observado"])
with tab_status:
    status_tab()
with tab_series:
    series_tab(devices_all)
with tab_forecast:
    forecast_tab(devices_all)
