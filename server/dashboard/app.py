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
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app import analytics, db  # noqa: E402
from app.analytics import HIGH_HUMIDITY, MIN_READINGS_PER_HOUR, OBSERVED, PERSISTENCE  # noqa: E402
from app.config import get_settings  # noqa: E402

LOCAL_TZ = "America/Sao_Paulo"
MAX_MINUTE_DAYS = 7  # o período padrão da aba Séries (7 dias) ainda cabe em resolução de 1 minuto
VARIABLES = {
    "pm25": "PM2,5 (µg/m³)",
    "pm10": "PM10 (µg/m³)",
    "pm1": "PM1,0 (µg/m³)",
    "temperature": "Temperatura (°C)",
    "humidity": "Umidade relativa (%)",
}

# Ícone em arquivo: um emoji como page_icon depende da fonte do sistema e quase some em 16 px.
st.set_page_config(page_title="PM2,5 — monitoramento", page_icon=str(Path(__file__).with_name("favicon.svg")),
                   layout="wide")
alt.data_transformers.disable_max_rows()
# O padrão do Streamlit (6rem em cima, 10rem embaixo) cria scroll em abas que caberiam na tela.
st.html("<style>[data-testid='stMainBlockContainer'] {padding-top: 3.5rem; padding-bottom: 2rem}</style>")


# ---------------------------------------------------------------- dados

def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(second=0, microsecond=0)


def _read(fn, *args, missing, **kwargs):
    """Roda fn(conn, ...) com o banco em modo somente leitura; sem o arquivo do banco, devolve `missing`."""
    path = get_settings().db_path
    if not Path(path).exists():
        return missing
    conn = db.connect(path, readonly=True)
    try:
        return fn(conn, *args, **kwargs)
    finally:
        conn.close()


@st.cache_data(ttl=30)
def load_status(now: datetime) -> pd.DataFrame:
    return _read(analytics.device_status, now, missing=pd.DataFrame(columns=analytics.STATUS_COLUMNS))


@st.cache_data(ttl=30)
def load_health(start: datetime, now: datetime) -> pd.DataFrame:
    return _read(analytics.collection_health, start, now, missing=pd.DataFrame(columns=analytics.HEALTH_COLUMNS))


def expected_devices(status: pd.DataFrame) -> list[str]:
    """Nós com leitura mais os cadastrados em PM25_DEVICE_TOKENS que ainda não enviaram, sem os de teste."""
    ids = set(status["device_id"]) | set(get_settings().device_ids)
    return sorted(d for d in ids if not analytics.is_test_device(d))


@st.cache_data(ttl=30)
def load_measurements(start: datetime, end: datetime, devices: tuple) -> pd.DataFrame:
    df = pd.DataFrame([dict(r) for r in _read(db.fetch_measurements, start, end, list(devices), missing=[])])
    if not df.empty:
        df["ts_sensor"] = pd.to_datetime(df["ts_sensor"], utc=True)
    return df


@st.cache_data(ttl=30)
def load_hourly(start: datetime, end: datetime, devices: tuple, only_ok: bool) -> pd.DataFrame:
    """Só as horas válidas, com `n` renomeado para minutos (como sai no CSV)."""
    hourly = _read(analytics.hourly_means, start, end, list(devices), only_ok=only_ok,
                   missing=pd.DataFrame(columns=analytics.HOURLY_COLUMNS))
    return hourly.dropna(subset=["pm25"]).rename(columns={"n": "minutos"})


@st.cache_data(ttl=60)
def load_forecast(device: str, now: datetime) -> analytics.ForecastComparison:
    return _read(analytics.forecast_comparison, device, now, missing=None)


def local_naive(series: pd.Series) -> pd.Series:
    """Horário local sem fuso, para o gráfico mostrar a hora de Brasília em qualquer navegador."""
    return series.dt.tz_convert(LOCAL_TZ).dt.tz_localize(None)


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


STATUS_LABELS = {"em_operacao": "🟢 em operação", "atrasado": "🟡 atrasado", "sem_dados": "🔴 sem dados"}
HEALTH_LABELS = {
    "device_id": "Sensor",
    "completude": "Completude",
    "maior_lacuna_min": "Maior lacuna (min)",
    "mensagens_perdidas": "Mensagens perdidas",
    "reinicios": "Reinícios",
    "duplicatas_descartadas": "Duplicatas descartadas",
    "leituras_marcadas": "Leituras marcadas",
}
SERIES_LABELS = {OBSERVED: "Observado", PERSISTENCE: "Persistência"}
METRIC_LABELS = {"previsor": "Previsor", "horas": "Horas", "mae": "MAE (µg/m³)", "rmse": "RMSE (µg/m³)",
                 "skill": "Skill score"}
# Observado em azul e o baseline em cinza; os modelos ficam com cores que não se confundem com nenhum dos dois.
SERIES_COLORS = {"Observado": "#3b82f6", "Persistência": "#9ca3af"}
MODEL_COLORS = ["#f97316", "#10b981", "#a855f7", "#ec4899"]

BAND_COLORS = {"Boa": "green", "Moderada": "yellow", "Ruim": "orange", "Muito ruim": "red", "Péssima": "violet"}


def air_quality(pm25) -> tuple[str, str] | None:
    """Nome e cor da faixa de qualidade do ar de um valor de PM2,5; None sem valor."""
    band = analytics.air_quality(pm25)
    return None if band is None else (band, BAND_COLORS[band])


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


# ---------------------------------------------------------------- abas

@st.fragment(run_every="60s")
def status_tab() -> None:
    now = now_utc()
    status = load_status(now)
    if status.empty:
        st.info("Nenhuma leitura recebida ainda. Ligue um nó sensor ou rode o simulador (veja o README).")
        return

    by_id = status.set_index("device_id")
    devices = expected_devices(status)
    for col, device in zip(st.columns(len(devices)), devices):
        with col:
            st.subheader(device)
            if device not in by_id.index:
                st.caption("⚪ aguardando instalação · nenhuma leitura recebida")
                continue
            dev = by_id.loc[device]
            minutes = None if pd.isna(dev["minutes_since"]) else dev["minutes_since"]
            when = dev["ts_sensor"].tz_convert(LOCAL_TZ).strftime("%d/%m %H:%M")
            if isinstance(dev["location"], str):
                st.caption(dev["location"])
            st.caption(f"{STATUS_LABELS[dev['status']]} · último envio {ago(minutes)} · leitura de {when}")
            # Uma linha de colunas por grupo: a faixa sob o PM2,5 não desalinha a linha de baixo.
            a, b = st.columns(2)
            band, color = air_quality(dev["pm25"]) or (None, "off")
            a.metric("PM2,5", fmt(dev["pm25"], " µg/m³"), delta=band, delta_color=color, delta_arrow="off",
                     help="Faixas da CETESB para a média de 24 horas; aplicadas à leitura de um minuto, "
                          "servem só de referência.")
            b.metric("PM10", fmt(dev["pm10"], " µg/m³"))
            a, b, c = st.columns(3)
            a.metric("Temperatura", fmt(dev["temperature"], " °C"))
            b.metric("Umidade", fmt(dev["humidity"], "%"))
            c.metric("Sinal Wi-Fi", fmt(dev["rssi"], " dBm", 0))
            if dev["quality"] != "ok":
                st.caption(f":red[O servidor marcou esta leitura como implausível ({dev['quality']}).]")

    window_start = now - timedelta(hours=24)
    health = load_health(window_start, now).rename(columns=HEALTH_LABELS)
    st.markdown("#### Saúde da coleta nas últimas 24 horas")
    st.dataframe(
        health, hide_index=True,
        # Azul neutro: na cor primária (vermelha) a barra parece um alerta mesmo com 99% de completude.
        column_config={"Completude": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1,
                                                                      color="blue")},
    )
    st.caption("Mensagens perdidas são lacunas de sequência dentro de uma mesma inicialização do nó; "
               "minutos sem leitura e sem lacuna de sequência indicam falha do sensor, não da rede.")

    recent = load_measurements(now - timedelta(hours=6), now + timedelta(minutes=1), tuple(status["device_id"]))
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
    if resolution == "Média horária":
        data = load_hourly(start, end, tuple(devices), only_ok)
        if data.empty:
            st.info(f"Sem horas com pelo menos {MIN_READINGS_PER_HOUR} minutos de leitura no período escolhido.")
            return
        data["hora_local"] = local_naive(data["hora"])
        st.caption(f"Médias de horas com pelo menos {MIN_READINGS_PER_HOUR} minutos de leitura (75%).")
        max_gap = pd.Timedelta(hours=1)
    else:
        # Cada minuto vira um ponto no navegador: períodos longos travariam a página.
        if (period[1] - period[0]).days + 1 > MAX_MINUTE_DAYS:
            st.info(f"A resolução de 1 minuto mostra até {MAX_MINUTE_DAYS} dias. "
                    "Escolha um período menor ou use a média horária.")
            return
        df = load_measurements(start, end, tuple(devices))
        if not df.empty and only_ok:
            df = df[df["quality"] == "ok"]
        if df.empty:
            st.info("Sem leituras no período escolhido.")
            return
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

    export = data.drop(columns=["hora_local"])
    st.download_button("Baixar dados (CSV)", export.to_csv(index=False).encode("utf-8"),
                       file_name=f"pm25_{period[0]}_{period[1]}.csv", mime="text/csv")


def forecast_tab(devices_all: list[str]) -> None:
    device = st.selectbox("Sensor", devices_all, key="forecast_device")
    comparison = load_forecast(device, now_utc())
    table = comparison.series.rename(columns=SERIES_LABELS)
    has_models = len(table.columns) > len(SERIES_LABELS)

    long =table.reset_index(names="hora").melt("hora", var_name="serie", value_name="pm25").dropna()
    if long.empty:
        st.info("Ainda não há horas completas para comparar.")
        return
    long["hora_local"] = local_naive(long["hora"])
    long = with_segments(long, "hora_local", "serie", pd.Timedelta(hours=1))
    models = [c for c in table.columns if c not in SERIES_COLORS]
    colors = SERIES_COLORS | dict(zip(models, MODEL_COLORS * len(models)))
    chart = alt.Chart(long).mark_line(point=True).encode(
        x=alt.X("hora_local:T", title=None, axis=alt.Axis(format="%d/%m %H:%M")),
        y=alt.Y("pm25:Q", title=VARIABLES["pm25"], scale=alt.Scale(zero=False)),
        color=alt.Color("serie:N", title=None,
                        scale=alt.Scale(domain=list(colors), range=list(colors.values()))),
        detail="segmento:N",
        strokeDash=alt.condition(alt.datum.serie == "Observado", alt.value([1, 0]), alt.value([5, 4])),
        tooltip=[alt.Tooltip("hora_local:T", title="Hora", format="%d/%m %H:%M"), alt.Tooltip("serie:N", title="Série"),
                 alt.Tooltip("pm25:Q", title="PM2,5", format=".1f")],
    ).properties(height=320)
    st.altair_chart(chart, width="stretch")

    metrics = comparison.metrics.replace({"previsor": SERIES_LABELS}).rename(columns=METRIC_LABELS)
    if not metrics.empty:
        st.dataframe(metrics, hide_index=True, column_config={
            "MAE (µg/m³)": st.column_config.NumberColumn(format="%.2f"),
            "RMSE (µg/m³)": st.column_config.NumberColumn(format="%.2f"),
            "Skill score": st.column_config.NumberColumn(format="%.2f"),
        })
    st.caption("Persistência prevê que a próxima hora repete a média da hora anterior; é o baseline que "
               "qualquer modelo precisa superar (skill score acima de zero).")
    if not has_models:
        st.info("Nenhuma previsão de modelo registrada ainda. Quando o job horário estiver no ar, as previsões "
                "gravadas na tabela forecasts aparecem aqui ao lado da persistência.")


# ---------------------------------------------------------------- página

st.title("Monitoramento de PM2,5")
overview = load_status(now_utc())
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
