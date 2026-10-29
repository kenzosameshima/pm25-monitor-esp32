"""Dashboard de monitoramento de PM2,5 (Streamlit).

Lê o banco SQLite em modo somente leitura; o modo WAL permite ler enquanto a API grava.
Uso, a partir da pasta server/:   streamlit run dashboard/app.py
"""

import re
import sys
import zlib
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
    """Todas as horas do período, com `n` renomeado para minutos (como sai no CSV); as sem média são as inválidas."""
    hourly = _read(analytics.hourly_means, start, end, list(devices), only_ok=only_ok,
                   missing=pd.DataFrame(columns=analytics.HOURLY_COLUMNS))
    return hourly.rename(columns={"n": "minutos"})


def suspect_hours_by_node(hourly: pd.DataFrame) -> dict[str, int]:
    """Quantas horas suspeitas cada nó tem na série horária, só dos nós que têm alguma."""
    counts = hourly[hourly["suspeita"].astype(bool)].groupby("device_id").size()
    return {str(device): int(n) for device, n in counts.items()}


def suspect_note(by_node: dict[str, int]) -> str:
    """Aviso de quantas horas a regra de sensor sem partículas deixou de fora da série horária, por nó."""
    hours = sum(by_node.values())
    verb = "hora suspeita ficou" if hours == 1 else "horas suspeitas ficaram"
    nodes = ", ".join(f"{device}: {n}" for device, n in sorted(by_node.items()))
    return f"{hours} {verb} de fora ({nodes}). O sensor quase não viu partículas nessas horas."


def suspect_criteria() -> str:
    """A regra das horas suspeitas e o que ela não decide, para quem quer saber por que uma hora ficou de fora."""
    low = f"{analytics.SUSPECT_LOW_PM25:.1f}".replace(".", ",")
    mean = f"{analytics.SUSPECT_MEAN_BELOW:.1f}".replace(".", ",")
    return (f"Uma hora é suspeita quando pelo menos {analytics.SUSPECT_LOW_SHARE:.0%} dos minutos têm PM2,5 abaixo de "
            f"{low} µg/m³, ou quando a média fica abaixo de {mean} µg/m³. A regra parte de que ficar quase sem "
            "partículas por uma hora inteira é raro. A causa pode ser falha do sensor ou ar muito limpo, e a regra "
            "ainda precisa ser conferida contra a estação da CETESB.")


def show_suspect_note(by_node: dict[str, int]) -> None:
    st.caption(suspect_note(by_node))
    with st.expander("Critério das horas suspeitas"):
        st.caption(suspect_criteria())


@st.cache_data(ttl=60)
def load_forecast(device: str, now: datetime) -> analytics.ForecastComparison:
    return _read(analytics.forecast_comparison, device, now, missing=None)


def local_naive(series: pd.Series) -> pd.Series:
    """Horário local sem fuso, para o gráfico mostrar a hora de Brasília em qualquer navegador."""
    return series.dt.tz_convert(LOCAL_TZ).dt.tz_localize(None)


# ---------------------------------------------------------------- formatação

def decimal_comma(value: float, decimals: int = 1) -> str:
    """O número com vírgula decimal, como se escreve em português."""
    return f"{value:.{decimals}f}".replace(".", ",")


def fmt(value, unit: str, decimals: int = 1) -> str:
    if value is None or pd.isna(value):
        return "—"
    return decimal_comma(value, decimals) + unit


def ago(minutes: float | None) -> str:
    if minutes is None:
        return "nunca"
    if minutes < 1:
        return "agora"
    if minutes < 60:
        return f"há {int(minutes)} min"
    if minutes < 48 * 60:
        return f"há {decimal_comma(minutes / 60)} h"
    return f"há {minutes / 1440:.0f} dias"


def last_reading_text(dev: pd.Series, when: str) -> str:
    """A última leitura de um nó sem dados recentes, dita como histórico para não passar por valor atual."""
    values = " · ".join([f"PM2,5 {fmt(dev['pm25'], ' µg/m³')}", f"PM10 {fmt(dev['pm10'], ' µg/m³')}",
                         fmt(dev["temperature"], " °C"), fmt(dev["humidity"], "%"), fmt(dev["rssi"], " dBm", 0)])
    note = "" if dev["quality"] == "ok" else f" O servidor a marcou como implausível ({dev['quality']})."
    return f"Leitura de {when}, histórico (não é o valor atual): {values}.{note}"


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

# Uma cor por nó, a mesma em todos os gráficos e abas. Ciano e magenta não se confundem entre si nem com o azul
# de "Observado", e ficam longe do vermelho, que o painel reserva para problema.
SENSOR_PALETTE = ["#22b8cf", "#e0529c", "#8b93a1", "#c9a227"]
# Horas sem média: cinza para a que não tem leitura, azul-aço para a de poucas leituras e âmbar para a suspeita.
EXCLUSION_COLORS = {analytics.NO_READINGS: "#8b93a1", analytics.FEW_READINGS: "#6aa6c8",
                    analytics.SUSPECT_HOUR: "#e2b53b"}
PERIOD_PRESETS = {"7 dias": 7, "30 dias": 30}
Y_AXIS_WIDTH = 48  # largura mínima do eixo vertical: faz a faixa das horas sem média alinhar com os gráficos de linha


def sensor_color(device: str) -> str:
    """A cor do nó, pelo número no fim do nome (no-01, no-02...); um nome sem número cai numa cor estável."""
    match = re.search(r"(\d+)$", device)
    index = int(match.group(1)) - 1 if match else zlib.crc32(device.encode())
    return SENSOR_PALETTE[index % len(SENSOR_PALETTE)]


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
               rule: float | None = None, color: str = "device_id", legend: str = "Sensor",
               domain: list[str] | None = None, time_only: bool = False, subtitle: str | None = None) -> alt.Chart:
    """Linhas por nó, uma cor fixa para cada. O título fica acima, na horizontal; `domain` (datas ISO sem fuso)
    fixa o eixo do tempo, e `time_only` mostra só a hora nos rótulos, com a data no `subtitle`."""
    data = with_segments(data[[x, y, color]].dropna(), x, color, max_gap)
    data = data.assign(valor=data[y].map(decimal_comma))      # o tooltip do Vega escreveria o ponto decimal
    names = sorted(data[color].unique())
    sensors = color == "device_id"
    chart = alt.Chart(data).mark_line(point=len(data) <= 400).encode(
        x=alt.X(f"{x}:T", title=None, axis=alt.Axis(format="%H:%M" if time_only else "%d/%m %H:%M"),
                scale=alt.Scale(domain=domain) if domain else alt.Undefined),
        y=alt.Y(f"{y}:Q", title=None, scale=alt.Scale(zero=False),
                axis=alt.Axis(labelExpr="replace(datum.label, '.', ',')", minExtent=Y_AXIS_WIDTH)),
        color=alt.Color(f"{color}:N", title=legend, legend=alt.Legend(orient="top"),
                        scale=alt.Scale(domain=names, range=[sensor_color(n) for n in names])
                        if sensors else alt.Undefined),
        detail="segmento:N",
        tooltip=[
            alt.Tooltip(f"{x}:T", title="Horário", format="%d/%m %H:%M"),
            alt.Tooltip(f"{color}:N", title=legend),
            alt.Tooltip("valor:N", title=title),
        ],
    )
    if rule is not None:
        chart = chart + alt.Chart(pd.DataFrame({"limite": [rule]})).mark_rule(
            strokeDash=[4, 4], color="gray").encode(y="limite:Q")
    # No Streamlit a altura inclui título, legenda e eixos: 330 deixa para a área das linhas cerca de 200 px.
    return chart.properties(height=330, title=alt.TitleParams(title, subtitle=subtitle or alt.Undefined,
                                                              anchor="start"))


def exclusion_note(exclusions: pd.DataFrame) -> str:
    """Quantas horas ficaram sem média em cada causa, para quem quer o número além da faixa colorida."""
    count = exclusions["causa"].value_counts()
    wording = {analytics.NO_READINGS: lambda n: f"{n} sem leituras",
               analytics.FEW_READINGS: lambda n: f"{n} com poucas leituras",
               analytics.SUSPECT_HOUR: lambda n: f"{n} {'suspeita' if n == 1 else 'suspeitas'}"}
    parts = [say(int(count[cause])) for cause, say in wording.items() if count.get(cause, 0)]
    return "Horas sem média: " + (parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " e " + parts[-1]) + "."


def exclusion_strip(exclusions: pd.DataFrame, domain: list[str]) -> alt.Chart:
    """Uma faixa por nó com as horas sem média, cada causa numa cor, alinhada ao eixo dos gráficos."""
    hours = exclusions.assign(hora_local=local_naive(exclusions["hora"]))
    hours["fim_local"] = hours["hora_local"] + pd.Timedelta(hours=1)
    return alt.Chart(hours).mark_rect().encode(
        x=alt.X("hora_local:T", title=None, scale=alt.Scale(domain=domain), axis=alt.Axis(format="%d/%m %H:%M")),
        x2="fim_local:T",
        y=alt.Y("device_id:N", title=None, axis=alt.Axis(minExtent=Y_AXIS_WIDTH)),
        color=alt.Color("causa:N", title=None, legend=alt.Legend(orient="top", direction="horizontal"),
                        scale=alt.Scale(domain=list(EXCLUSION_COLORS), range=list(EXCLUSION_COLORS.values()))),
        tooltip=[alt.Tooltip("hora_local:T", title="Hora", format="%d/%m %H:%M"),
                 alt.Tooltip("device_id:N", title="Sensor"), alt.Tooltip("causa:N", title="Causa")],
    ).properties(height=alt.Step(26))                              # 26 px por nó, sem depender da legenda


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
        with col, st.container(border=True):
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
            if dev["status"] == "sem_dados":
                # Sem envio recente, o último valor não diz como o ar está agora (um sensor parado em zero
                # apareceria como "Boa"): o valor atual fica vazio e a última leitura, dita histórica, no expansor.
                st.metric("PM2,5", "—")
                with st.expander("Ver a última leitura recebida"):
                    st.caption(last_reading_text(dev, when))
            else:
                # Uma linha de colunas por grupo: a faixa sob o PM2,5 não desalinha a linha de baixo.
                a, b = st.columns(2)
                band, color = air_quality(dev["pm25"]) or (None, "off")
                a.metric("PM2,5", fmt(dev["pm25"], " µg/m³"), delta=band, delta_color=color, delta_arrow="off",
                         help="Faixas da CETESB para a média de 24 horas; aplicadas à leitura de um minuto, "
                              "servem só de referência.")
                b.metric("PM10", fmt(dev["pm10"], " µg/m³"))
                a, b = st.columns(2)
                a.metric("Temperatura", fmt(dev["temperature"], " °C"))
                b.metric("Umidade", fmt(dev["humidity"], "%"))
                # O sinal e o firmware dizem como o nó está, não como está o ar: ficam no rodapé do cartão.
                if pd.notna(dev["rssi"]):
                    st.caption(f"Sinal Wi-Fi: {fmt(dev['rssi'], ' dBm', 0)}")
                if dev["quality"] != "ok":
                    st.caption(f":red[O servidor marcou esta leitura como implausível ({dev['quality']}).]")
            if isinstance(dev["firmware"], str):
                st.caption(f"Firmware: {dev['firmware']}")

    # O gráfico vem antes da tabela: a primeira tela responde "qual é a leitura, está atualizada e como evolui".
    recent = load_measurements(now - timedelta(hours=6), now + timedelta(minutes=1), tuple(status["device_id"]))
    tz = ZoneInfo(LOCAL_TZ)
    first, last = (now - timedelta(hours=6)).astimezone(tz), now.astimezone(tz)
    days = f"{first:%d/%m}" if first.date() == last.date() else f"{first:%d/%m} a {last:%d/%m}"
    st.markdown("#### PM2,5 nas últimas 6 horas")
    if not recent.empty:
        st.altair_chart(line_chart(recent.assign(hora=local_naive(recent["ts_sensor"])), "hora", "pm25",
                                   VARIABLES["pm25"], pd.Timedelta(minutes=5), time_only=True, subtitle=days),
                        width="stretch")
    # Um nó sem leitura na janela some do gráfico e da legenda: o aviso diz que ele não foi esquecido.
    sent = set(recent["device_id"]) if not recent.empty else set()
    missing = [d for d in devices if d in by_id.index and d not in sent]
    if missing:
        st.caption(f"{', '.join(missing)}: sem leituras nas últimas 6 horas.")

    window_start = now - timedelta(hours=24)
    health = load_health(window_start, now).rename(columns=HEALTH_LABELS)
    st.markdown("#### Saúde da coleta nas últimas 24 horas")
    st.dataframe(
        health, hide_index=True,
        # Azul neutro: a barra de completude não deve parecer um alerta mesmo com 99%.
        column_config={"Completude": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1,
                                                                      color="blue")},
    )
    st.caption("Mensagens perdidas são lacunas de sequência dentro de uma mesma inicialização do nó; "
               "minutos sem leitura e sem lacuna de sequência indicam falha do sensor, não da rede.")


def series_tab(devices_all: list[str]) -> None:
    today = datetime.now(ZoneInfo(LOCAL_TZ)).date()
    c1, c2, c3 = st.columns([2, 2, 1])
    devices = c1.multiselect("Sensores", devices_all, default=devices_all)
    choice = c2.segmented_control("Período", [*PERIOD_PRESETS, "Personalizado"], default="7 dias") or "7 dias"
    if choice == "Personalizado":
        period = c2.date_input("Datas", value=(today - timedelta(days=6), today), max_value=today,
                               format="DD/MM/YYYY")
    else:
        period = (today - timedelta(days=PERIOD_PRESETS[choice] - 1), today)
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
    strip = None
    domain = None
    if resolution == "Média horária":
        hourly = load_hourly(start, end, tuple(devices), only_ok)
        data = hourly.dropna(subset=["pm25"]).drop(columns=["suspeita"])
        suspect = suspect_hours_by_node(hourly)
        # O eixo vai do início do período até agora; um nó que parou aparece sem leituras até lá.
        until = min(end, now_utc())
        domain = [start.astimezone(tz).replace(tzinfo=None).isoformat(),
                  until.astimezone(tz).replace(tzinfo=None).isoformat()]
        exclusions = analytics.hour_exclusions(hourly.rename(columns={"minutos": "n"}), until=until)
        if not exclusions.empty:
            strip = exclusion_strip(exclusions, domain)
        if data.empty:
            st.info(f"Sem horas com pelo menos {MIN_READINGS_PER_HOUR} minutos de leitura no período escolhido.")
            if suspect:
                show_suspect_note(suspect)
            if strip is not None:
                st.caption(exclusion_note(exclusions))
                st.altair_chart(strip, width="stretch")
            return
        data["hora_local"] = local_naive(data["hora"])
        st.caption(f"Médias de horas com pelo menos {MIN_READINGS_PER_HOUR} minutos de leitura (75%).")
        if suspect:
            show_suspect_note(suspect)
        if strip is not None:
            st.caption(exclusion_note(exclusions))
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

    for i, var in enumerate(variables):
        rule = HIGH_HUMIDITY if var == "humidity" else None
        st.altair_chart(line_chart(data, "hora_local", var, VARIABLES[var], max_gap, rule=rule, domain=domain),
                        width="stretch")
        if i == 0 and strip is not None:      # a faixa vale para todas as variáveis: as horas sem média são as mesmas
            st.altair_chart(strip, width="stretch")

    if "humidity" in data and data["humidity"].notna().any():
        share = (data.groupby("device_id")["humidity"].apply(lambda s: (s > HIGH_HUMIDITY).mean()))
        parts = ", ".join(f"{dev}: {p:.0%}" for dev, p in share.items())
        st.caption(f"Registros com umidade acima de {HIGH_HUMIDITY:.0f}% ({parts}) podem ter PM2,5 "
                   "superestimado pela absorção de água nas partículas.")

    export = data.drop(columns=["hora_local"])
    st.download_button("Baixar dados (CSV)", export.to_csv(index=False).encode("utf-8"),
                       file_name=f"pm25_{period[0]}_{period[1]}.csv", mime="text/csv")


def evaluation_note(table: pd.DataFrame, metrics: pd.DataFrame) -> str:
    """Em que horas a tabela de métricas foi calculada, para ninguém comparar linhas de amostras diferentes."""
    horizon = "Previsão da média da hora seguinte"
    rated = table[[SERIES_LABELS[OBSERVED], *metrics["Previsor"]]].dropna()
    if metrics["Horas"].nunique() > 1 or len(rated) != metrics["Horas"].iloc[0]:
        return (f"{horizon}. Os previsores não têm horas em comum: cada um foi avaliado nas horas em que tem "
                "previsão, e só o skill score compara com a persistência nas mesmas horas.")
    hours = local_naive(rated.index.to_series())
    period = "" if len(rated) == 1 else f", de {hours.min():%d/%m %H:%M} a {hours.max():%d/%m %H:%M}"
    return f"{horizon}, avaliada nas mesmas {len(rated)} horas para todos os previsores{period}."


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
    if not metrics.empty:
        st.caption(evaluation_note(table, metrics))
    st.caption("Persistência repete a média da hora anterior e é a referência que qualquer modelo precisa superar. "
               "MAE é o erro médio e RMSE pesa mais os erros grandes. O skill score compara o RMSE do previsor com "
               "o da persistência nas mesmas horas: acima de zero, o modelo acerta mais que repetir a hora anterior.")
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
