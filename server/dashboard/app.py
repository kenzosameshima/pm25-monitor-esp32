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
from dashboard.duration import duration_text  # noqa: E402
from dashboard.last_reading import last_reading_html  # noqa: E402
from dashboard.scale import band_scale_html  # noqa: E402
from dashboard.trend import period_text, trend_head_html  # noqa: E402

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
PAGE_STYLE = """<style>
/* O padrão do Streamlit (6rem em cima, 10rem embaixo) cria scroll em abas que caberiam na tela. */
[data-testid='stMainBlockContainer'] {padding-top: 3.5rem; padding-bottom: 2rem}
/* Em tela larga, a margem de cima, o título de 44 px e os respiros em volta das abas gastavam um quarto da altura
   antes do primeiro conteúdo. Menores, deixam o conteúdo mais acima. Abaixo de 640 px (o celular) nada muda: lá a
   barra do Streamlit cobriria uma margem menor. A barra fica por cima do conteúdo e tem fundo sólido, então com a
   margem menor ela esconderia o título: ela passa a ser transparente. */
@media (min-width: 640px) {
[data-testid='stHeader'] {background: transparent}
[data-testid='stMainBlockContainer'] {padding-top: 1.75rem}
[data-testid='stMainBlockContainer'] [data-testid='stHeading'] h1 {font-size: 1.75rem; line-height: 1.2; padding-top: 0; padding-bottom: .25rem}
[data-testid='stTabs'] [role='tabpanel'] {padding-top: .5rem}
/* O cartão de um nó gastava 470 px: o nome do nó grande, 16 px entre cada bloco e 24 px entre a escala e as métricas. */
[data-testid='stVerticalBlock'][class*='st-key-node-'] {gap: .75rem; padding: .75rem; --aq-gap: .75rem}
[data-testid='stVerticalBlock'][class*='st-key-hero-'] {gap: .5rem}
[class*='st-key-node-'] [data-testid='stHeading'] h3 {font-size: 1.4rem; line-height: 1.3; padding-top: 0; padding-bottom: 0}
[class*='st-key-node-'] [data-testid='stHeading'] [data-testid='stMarkdownContainer'] {margin-bottom: 0}
[class*='st-key-hero-'] .aq-scale {margin-bottom: .25rem}
[class*='st-key-hero-'] [data-testid='stMetric'] > div {display: grid; grid-template-columns: auto 1fr; align-items: center; column-gap: .75rem}
[class*='st-key-hero-'] [data-testid='stMetricLabel'] {grid-column: 1 / -1}
}
/* Texto auxiliar: o Streamlit o deixa a 60% de opacidade, o que dá 3,7:1 no tema claro. A 75% passa de 4,5:1
   nos dois temas e ainda fica abaixo do texto principal. */
[data-testid='stCaptionContainer'] {opacity: .75 !important}
/* Algarismos de largura fixa, para os valores não dançarem a cada atualização; o PM2,5 é a razão da página e
   fica maior que os demais indicadores do cartão. */
[data-testid='stMetricValue'] {font-variant-numeric: tabular-nums}
[class*='st-key-node-'] [data-testid='stMetricValue'] {font-size: 1.75rem}
[class*='st-key-hero-'] [data-testid='stMetricValue'] {font-size: 3.2rem; font-weight: 600; line-height: 1.05}
/* A unidade do PM2,5 vem menor e com peso normal ao lado do valor: dentro do próprio valor ela competiria com ele. */
[class*='st-key-hero-']:not([class*='st-key-hero-empty-']) [data-testid='stMetricValue'] div::after {content: " µg/m³"; font-size: .4em; font-weight: 400; margin-left: .2em}
/* Num nó sem dados, o "PM2,5 —" diz que não há leitura atual. Com a última leitura aberta, os valores dela ocupam o
   lugar e o "—" só repetiria a ausência: o bloco encolhe e some, e volta quando o expansor começa a fechar. O expansor
   (um elemento details) só perde o atributo open quando acaba de fechar, mas marca o conteúdo como inert já no
   início: a regra olha o conteúdo ainda ativo, para o bloco não esperar a animação do expansor para voltar. A altura
   anima pela fileira da grade (de 1fr a 0fr) e a margem negativa desconta o espaço entre blocos do cartão (--aq-gap),
   que um bloco sem altura ainda deixaria. Sem o sinal de menor aqui dentro: o sanitizador do st.html descarta o bloco
   de estilo inteiro se achar um. */
[class*='st-key-node-'] {--aq-gap: 1rem}
[class*='st-key-node-'] [data-testid='stLayoutWrapper']:has(> [class*='st-key-hero-empty-']) {display: grid; grid-template-rows: 1fr;
    transition: grid-template-rows .25s ease, opacity .25s ease, margin-bottom .25s ease, visibility 0s}
[class*='st-key-node-'] [class*='st-key-hero-empty-'] {min-height: 0; overflow: hidden}
[class*='st-key-node-']:has(details[open] [data-testid='stExpanderDetails']:not([inert])) [data-testid='stLayoutWrapper']:has(> [class*='st-key-hero-empty-']) {grid-template-rows: 0fr; opacity: 0; margin-bottom: calc(-1 * var(--aq-gap)); visibility: hidden;
    transition: grid-template-rows .25s ease, opacity .25s ease, margin-bottom .25s ease, visibility 0s .25s}
@media (prefers-reduced-motion: reduce) {
[class*='st-key-node-'] [data-testid='stLayoutWrapper']:has(> [class*='st-key-hero-empty-']) {transition: none !important}
}
/* Escala das faixas de qualidade do ar sob o PM2,5. */
.aq-scale {position: relative; max-width: 24rem; margin: .1rem 0 1.5rem}
.aq-track {display: flex; gap: 2px; height: .5rem; border-radius: .25rem; overflow: hidden}
.aq-track span {flex: 1}
.aq-marker {position: absolute; top: -.35rem; width: 4px; height: 1.2rem; transform: translateX(-50%);
            border-radius: 2px; background: #1f2330; box-shadow: 0 0 0 2px #fff}
.aq-ticks {position: relative; height: 1rem; margin-top: .35rem; font-size: .75rem; opacity: .75;
           font-variant-numeric: tabular-nums}
.aq-ticks span {position: absolute; transform: translateX(-50%)}
/* A linha acima de um gráfico de linhas: o período e a unidade (ou a variável) de um lado, a legenda e os avisos do outro. */
.aq-trend-head {display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: .25rem 1rem;
                font-size: .875rem}
.aq-label, .aq-key-off {opacity: .75}
.aq-label.aq-title {font-size: 1rem; font-weight: 600; opacity: 1}
.aq-keys {display: flex; flex-wrap: wrap; align-items: center; gap: .25rem 1rem}
.aq-key i {display: inline-block; width: .6rem; height: .6rem; border-radius: 50%; margin-right: .35rem}
/* A última leitura de um nó sem dados, no expansor: o aviso, os valores em grade sobre um fundo próprio e o sinal. */
.aq-last {display: grid; gap: .5rem}
.aq-last-title {font-weight: 600}
.aq-last-note, .aq-last-foot {font-size: .875rem; opacity: .75}
.aq-last-grid {display: grid; grid-template-columns: repeat(auto-fit, minmax(6.5rem, 1fr)); gap: .75rem; padding: .75rem;
               border-radius: .5rem; background: color-mix(in srgb, currentColor 6%, transparent)}
.aq-last-label {display: block; font-size: .875rem; opacity: .75}
.aq-last-value {display: block; font-size: 1.4rem; font-variant-numeric: tabular-nums}
</style>"""
st.html(PAGE_STYLE)


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


def suspect_criteria() -> str:
    """A regra das horas suspeitas e o que ela não decide, para quem quer saber por que uma hora ficou de fora."""
    low = f"{analytics.SUSPECT_LOW_PM25:.1f}".replace(".", ",")
    mean = f"{analytics.SUSPECT_MEAN_BELOW:.1f}".replace(".", ",")
    return (f"Uma hora é suspeita quando pelo menos {analytics.SUSPECT_LOW_SHARE:.0%} dos minutos têm PM2,5 abaixo de "
            f"{low} µg/m³, ou quando a média fica abaixo de {mean} µg/m³. A regra parte de que ficar quase sem "
            "partículas por uma hora inteira é raro. A causa pode ser falha do sensor ou ar muito limpo, e a regra "
            "ainda precisa ser conferida contra a estação da CETESB.")


def show_hour_notes(exclusions: pd.DataFrame) -> None:
    """O resumo das horas sem média e, num expansor só, a regra das médias, o detalhe por sensor e o critério das
    suspeitas: cada número aparece uma vez, e o que explica o número fica a um clique."""
    if not exclusions.empty:
        st.caption(exclusion_note(exclusions))
    with st.expander("Critérios e detalhamento por sensor"):
        st.caption(f"A média de uma hora só vale com pelo menos {MIN_READINGS_PER_HOUR} minutos de leitura "
                   f"({MIN_READINGS_PER_HOUR / 60:.0%}).")
        if not exclusions.empty:
            st.caption(exclusion_details(exclusions))
            if (exclusions["causa"] == analytics.SUSPECT_HOUR).any():
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


def last_reading_block(dev: pd.Series, reading_at: datetime) -> str:
    """A última leitura de um nó sem dados recentes, dita como histórico para não passar por valor atual."""
    values = [("PM2,5 (µg/m³)", fmt(dev["pm25"], "")), ("PM10 (µg/m³)", fmt(dev["pm10"], "")),
              ("Temperatura", fmt(dev["temperature"], " °C")), ("Umidade", fmt(dev["humidity"], "%"))]
    return last_reading_html(reading_at, values, fmt(dev["rssi"], " dBm", 0) if pd.notna(dev["rssi"]) else None)


def flagged_note(quality: str) -> str:
    return f":red[O servidor marcou esta leitura como implausível ({quality}).]"


def zero_reading_note(pm1, pm25, pm10) -> str:
    """Aviso do cartão de um nó em operação cuja leitura chegou toda em zero, citando só o que o nó enviou."""
    names = [name for name, value in (("PM1", pm1), ("PM2,5", pm25), ("PM10", pm10)) if pd.notna(value)]
    listed = names[0] if len(names) == 1 else f"{', '.join(names[:-1])} e {names[-1]}"
    return (f"Leitura zerada ({listed} em 0,0): o sensor pode não estar vendo partículas. "
            "Por isso o cartão fica sem faixa de qualidade do ar.")


STATUS_LABELS = {"em_operacao": "🟢 em operação", "atrasado": "🟡 atrasado", "sem_dados": "🔴 sem dados"}
HEALTH_LABELS = {
    "device_id": "Sensor",
    "completude": "Completude",
    "maior_lacuna_min": "Maior lacuna",
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
               rule: float | None = None, rule_label: str | None = None, color: str = "device_id",
               legend: str = "Sensor", domain: list[str] | None = None, compact: bool = False,
               headless: bool = False) -> alt.Chart:
    """Linhas por nó, uma cor fixa para cada. O título fica acima, na horizontal; `domain` (datas ISO sem fuso)
    fixa o eixo do tempo. `headless` tira o título e a legenda de dentro do gráfico: a página os escreve numa linha
    acima e a área das linhas fica do mesmo tamanho. `compact` é o gráfico das últimas 6 horas: só a hora nos
    rótulos, uma linha fina com marcas de 30 em 30 minutos no eixo e o ponto só sob o mouse (o do tooltip), menos os
    das leituras isoladas, que sem vizinhas não formariam linha."""
    data = with_segments(data[[x, y, color]].dropna(), x, color, max_gap)
    data = data.assign(valor=data[y].map(decimal_comma))      # o tooltip do Vega escreveria o ponto decimal
    names = sorted(data[color].unique())
    sensors = color == "device_id"
    if compact:                                               # uma leitura sem vizinha a menos de `max_gap` não forma linha
        data = data.assign(isolado=data.groupby("segmento")[x].transform("size") == 1)
    # Doze marcas em 6 horas: uma a cada 30 minutos. O intervalo explícito (`TimeIntervalStep`) deixa o gráfico em
    # branco no Streamlit; a contagem numérica não.
    ticks = 12 if compact else alt.Undefined
    base = alt.Chart(data).encode(
        x=alt.X(f"{x}:T", title=None, axis=alt.Axis(format="%H:%M" if compact else "%d/%m %H:%M", tickCount=ticks),
                scale=alt.Scale(domain=domain) if domain else alt.Undefined),
        y=alt.Y(f"{y}:Q", title=None, scale=alt.Scale(zero=False),
                axis=alt.Axis(labelExpr="replace(datum.label, '.', ',')", minExtent=Y_AXIS_WIDTH)),
        color=alt.Color(f"{color}:N", title=legend, legend=None if headless else alt.Legend(orient="top"),
                        scale=alt.Scale(domain=names, range=[sensor_color(n) for n in names])
                        if sensors else alt.Undefined),
        detail="segmento:N",
        tooltip=[
            alt.Tooltip(f"{x}:T", title="Horário", format="%d/%m %H:%M"),
            alt.Tooltip(f"{color}:N", title=legend),
            alt.Tooltip("valor:N", title=title),
        ],
    )
    if compact:
        hover = alt.selection_point(name="hover", fields=[x], nearest=True, on="pointerover", clear="pointerout",
                                    empty=False)
        dots = base.mark_point(filled=True, size=36)
        chart = (base.mark_line(strokeWidth=2)
                 + dots.encode(opacity=alt.condition(hover, alt.value(1), alt.value(0))).add_params(hover)
                 + dots.transform_filter("datum.isolado"))
    else:
        chart = base.mark_line(point=len(data) <= 400)
    if rule is not None:
        limit = alt.Chart(pd.DataFrame({"limite": [rule]}))
        chart = chart + limit.mark_rule(strokeDash=[4, 4], color="gray").encode(y="limite:Q")
        if rule_label:                          # o nome da linha tracejada, no canto esquerdo e logo acima dela
            chart = chart + limit.mark_text(align="left", baseline="bottom", dx=4, dy=-3, color="gray").encode(
                x=alt.value(0), y="limite:Q", text=alt.value(rule_label))
    # No Streamlit a altura inclui título, legenda e eixos: 330 deixa para a área das linhas cerca de 200 px, e sem
    # título nem legenda 240 deixam o mesmo tanto.
    description = chart_description(data, x, y, title, names)
    if headless:
        return chart.properties(height=240, description=description)
    return chart.properties(height=330, description=description, title=alt.TitleParams(title, anchor="start"))


def humidity_note(data: pd.DataFrame) -> str:
    """Quanto dos registros de cada nó passou do limite de umidade, e por que isso importa para o PM2,5."""
    share = data.groupby("device_id")["humidity"].apply(lambda s: (s > HIGH_HUMIDITY).mean())
    parts = ", ".join(f"{dev}: {p:.0%}" for dev, p in share.items())
    return (f"Registros com umidade acima de {HIGH_HUMIDITY:.0f}% ({parts}) podem ter PM2,5 "
            "superestimado pela absorção de água nas partículas.")


def chart_description(data: pd.DataFrame, x: str, y: str, title: str, names: list[str]) -> str:
    """O texto que o leitor de tela lê no lugar do gráfico de linhas: o que ele mostra, o período e a faixa de valores."""
    if data.empty:
        return f"Gráfico de linhas: {title}, sem valores no período."
    return (f"Gráfico de linhas: {title} por sensor ({', '.join(names)}), de {data[x].min():%d/%m %H:%M} a "
            f"{data[x].max():%d/%m %H:%M}; valores de {decimal_comma(data[y].min())} a {decimal_comma(data[y].max())}.")


def cause_counts(exclusions: pd.DataFrame) -> str:
    """As horas de `exclusions` contadas por causa: "96 sem leituras, 9 com poucas leituras e 54 suspeitas"."""
    count = exclusions["causa"].value_counts()
    wording = {analytics.NO_READINGS: lambda n: f"{n} sem leituras",
               analytics.FEW_READINGS: lambda n: f"{n} com poucas leituras",
               analytics.SUSPECT_HOUR: lambda n: f"{n} {'suspeita' if n == 1 else 'suspeitas'}"}
    parts = [say(int(count[cause])) for cause, say in wording.items() if count.get(cause, 0)]
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " e " + parts[-1]


def exclusion_note(exclusions: pd.DataFrame) -> str:
    """Quantas horas ficaram sem média em cada causa, para quem quer o número além da faixa colorida. Com mais de um
    sensor, são horas de sensores diferentes somadas, e o texto diz isso."""
    label = "Horas sem média (soma dos sensores)" if exclusions["device_id"].nunique() > 1 else "Horas sem média"
    return f"{label}: {cause_counts(exclusions)}."


def exclusion_details(exclusions: pd.DataFrame) -> str:
    """Uma linha por sensor com as horas sem média de cada causa."""
    lines = [f"- **{device}:** {cause_counts(group)}." for device, group in exclusions.groupby("device_id")]
    return "Por sensor:" + "\n" + "\n".join(lines)


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
    ).properties(                                                  # 26 px por nó, sem depender da legenda
        height=alt.Step(26),
        description=(f"Faixa das horas sem média, uma linha por sensor ({', '.join(sorted(hours['device_id'].unique()))}), "
                     f"com a causa de cada hora. {exclusion_note(exclusions)}"))


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
        with col, st.container(border=True, key=f"node-{device}"):
            location = by_id.at[device, "location"] if device in by_id.index else None
            st.subheader(f"{device} · {location}" if isinstance(location, str) else device)
            if device not in by_id.index:
                st.caption("⚪ aguardando instalação · nenhuma leitura recebida")
                continue
            dev = by_id.loc[device]
            minutes = None if pd.isna(dev["minutes_since"]) else dev["minutes_since"]
            reading_at = dev["ts_sensor"].tz_convert(LOCAL_TZ)
            when = reading_at.strftime("%d/%m %H:%M")
            st.caption(f"{STATUS_LABELS[dev['status']]} · último envio {ago(minutes)} · leitura de {when}")
            if dev["status"] == "sem_dados":
                # Sem envio recente, o último valor não diz como o ar está agora (um sensor parado em zero
                # apareceria como "Boa"): o valor atual fica vazio e a última leitura, dita histórica, no expansor.
                with st.container(key=f"hero-empty-{device}"):
                    st.metric("PM2,5", "—")
                with st.expander("Última leitura recebida"):
                    st.html(last_reading_block(dev, reading_at))
                    if dev["quality"] != "ok":
                        st.caption(flagged_note(dev["quality"]))
            else:
                # O PM2,5 abre o cartão, grande e com a escala das faixas sob ele; os outros indicadores ficam numa
                # linha só, menores.
                # Com tudo em zero não se sabe se o sensor parou de ver partículas ou se o ar está limpo: a leitura
                # aparece, mas sem a faixa que a chamaria de "Boa".
                zeroed = analytics.is_zero_reading(dev["pm1"], dev["pm25"], dev["pm10"])
                band, color = (None, "off") if zeroed else air_quality(dev["pm25"]) or (None, "off")
                with st.container(key=f"hero-{device}"):
                    st.metric("PM2,5", fmt(dev["pm25"], ""), delta=band, delta_color=color, delta_arrow="off",
                              help="Faixas da CETESB para a média de 24 horas; aplicadas à leitura de um minuto, "
                                   "servem só de referência.")
                    if zeroed:
                        st.caption(zero_reading_note(dev["pm1"], dev["pm25"], dev["pm10"]))
                    position = None if zeroed else analytics.band_position(dev["pm25"])
                    if position is not None:
                        st.html(band_scale_html(position, f"PM2,5 de {fmt(dev['pm25'], ' µg/m³')}, na faixa {band}"))
                a, b, c = st.columns(3)
                # A unidade vai no rótulo: "50,9 µg/m³" não cabe numa coluna de um terço do cartão e era cortado.
                a.metric("PM10 (µg/m³)", fmt(dev["pm10"], ""))
                b.metric("Temperatura", fmt(dev["temperature"], " °C"))
                c.metric("Umidade", fmt(dev["humidity"], "%"))
                # O sinal e o firmware dizem como o nó está, não como está o ar: ficam no rodapé do cartão.
                if pd.notna(dev["rssi"]):
                    st.caption(f"Sinal Wi-Fi: {fmt(dev['rssi'], ' dBm', 0)}")
                if dev["quality"] != "ok":
                    st.caption(flagged_note(dev["quality"]))
            if isinstance(dev["firmware"], str):
                st.caption(f"Firmware: {dev['firmware']}")

    # O gráfico vem antes da tabela: a primeira tela responde "qual é a leitura, está atualizada e como evolui".
    recent = load_measurements(now - timedelta(hours=6), now + timedelta(minutes=1), tuple(status["device_id"]))
    tz = ZoneInfo(LOCAL_TZ)
    first, last = (now - timedelta(hours=6)).astimezone(tz), now.astimezone(tz)
    st.markdown("#### PM2,5 · últimas 6 horas")
    # Um nó sem leitura na janela some do gráfico: o aviso ao lado da legenda diz que ele não foi esquecido.
    sent = sorted(set(recent["device_id"])) if not recent.empty else []
    missing = [d for d in devices if d in by_id.index and d not in sent]
    st.html(trend_head_html(f"{period_text(first, last)} · µg/m³", [(d, sensor_color(d)) for d in sent], missing))
    if not recent.empty:
        st.altair_chart(line_chart(recent.assign(hora=local_naive(recent["ts_sensor"])), "hora", "pm25",
                                   VARIABLES["pm25"], pd.Timedelta(minutes=5), compact=True, headless=True),
                        width="stretch")

    window_start = now - timedelta(hours=24)
    health = load_health(window_start, now).rename(columns=HEALTH_LABELS)
    st.markdown("#### Saúde da coleta nas últimas 24 horas")
    # O texto da barra de progresso só sai com ponto decimal, então a barra fica sem texto e o número, com vírgula,
    # vai numa coluna ao lado; o Styler escreve as células com vírgula e a tabela continua ordenável pelo valor.
    health.insert(2, "%", health["Completude"])
    styled = health.style.format(decimal=",", na_rep="—")
    # Com `subset`: um formatter em dicionário também redefine as colunas que ficam de fora dele.
    styled = styled.format(lambda v: decimal_comma(v * 100, 2) + "%", subset=["%"], na_rep="—")
    # A maior lacuna segue em minutos no valor (a coluna ordena por ele) e se lê em horas quando passa de uma.
    styled = styled.format(duration_text, subset=["Maior lacuna"], na_rep="—")
    st.dataframe(
        styled, hide_index=True,
        # Azul neutro: a barra de completude não deve parecer um alerta mesmo com 99%.
        # Largura pequena nas duas colunas da completude: com a coluna a mais, a tabela passava da largura da tela.
        column_config={"Completude": st.column_config.ProgressColumn(format=" ", min_value=0, max_value=1,
                                                                      color="blue", width="small"),
                       "%": st.column_config.Column(width="small")},
    )
    with st.expander("Como interpretar os indicadores"):
        # Uma definição por coluna da tabela, no vocabulário do glossário.
        st.caption(
            "- **Completude:** fração dos minutos esperados que têm leitura; a barra e o percentual mostram o mesmo valor.\n"
            "- **Maior lacuna:** o maior período seguido sem leitura na janela.\n"
            "- **Mensagens perdidas:** lacunas de sequência dentro de uma mesma inicialização do nó.\n"
            "- **Reinícios:** inicializações do nó além da primeira.\n"
            "- **Duplicatas descartadas:** leituras reenviadas por um nó e ignoradas pelo servidor por já estarem "
            "guardadas.\n"
            "- **Leituras marcadas:** leituras que o servidor considerou implausíveis; ficam guardadas, mas não entram "
            "nas médias horárias por padrão.")
        st.caption("Minutos sem leitura e sem lacuna de sequência sugerem falha do sensor, e não da rede, mas o painel "
                   "não confirma a causa.")


def series_tab(devices_all: list[str]) -> None:
    today = datetime.now(ZoneInfo(LOCAL_TZ)).date()
    # Duas linhas: o que olhar (sensores e variáveis, cada um em metade da largura) e o recorte dos dados (período,
    # resolução e leituras marcadas, mais a exportação do que eles mostram). A segunda é uma linha que dá a cada controle
    # o que o conteúdo pede e quebra se não couber: em colunas de largura fixa, o botão "1 minuto" e o rótulo do filtro
    # apareciam cortados numa janela de 1024 px. Alinhada pela base, a caixa de datas do período personalizado não solta
    # os demais controles.
    c1, c2 = st.columns(2)
    devices = c1.multiselect("Sensores", devices_all, default=devices_all)
    variables = c2.multiselect("Variáveis", list(VARIABLES), default=["pm25", "humidity"], format_func=VARIABLES.get)
    row = st.container(horizontal=True, vertical_alignment="bottom", gap="medium")
    choice = row.segmented_control("Período", [*PERIOD_PRESETS, "Personalizado"], default="7 dias") or "7 dias"
    if choice == "Personalizado":
        period = row.date_input("Datas", value=(today - timedelta(days=6), today), max_value=today,
                                format="DD/MM/YYYY", width=260)
    else:
        period = (today - timedelta(days=PERIOD_PRESETS[choice] - 1), today)
    resolution = (row.segmented_control("Resolução", ["Média horária", "1 minuto"], default="Média horária")
                  or "Média horária")
    only_ok = row.checkbox("Ocultar leituras marcadas", value=True,
                           help="Leituras que o servidor marcou como implausíveis: valor fora da faixa física ou horário "
                                "impossível. Ficam guardadas; desmarque para incluí-las nos gráficos.")

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
        # O eixo vai do início do período até agora; um nó que parou aparece sem leituras até lá.
        until = min(end, now_utc())
        domain = [start.astimezone(tz).replace(tzinfo=None).isoformat(),
                  until.astimezone(tz).replace(tzinfo=None).isoformat()]
        exclusions = analytics.hour_exclusions(hourly.rename(columns={"minutos": "n"}), until=until)
        if not exclusions.empty:
            strip = exclusion_strip(exclusions, domain)
        if data.empty:
            st.info(f"Sem horas com pelo menos {MIN_READINGS_PER_HOUR} minutos de leitura no período escolhido.")
            show_hour_notes(exclusions)
            if strip is not None:
                st.altair_chart(strip, width="stretch")
            return
        data["hora_local"] = local_naive(data["hora"])
        show_hour_notes(exclusions)
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
        nodes = sorted(data.loc[data[var].notna(), "device_id"].unique())
        st.html(trend_head_html(VARIABLES[var], [(n, sensor_color(n)) for n in nodes], title=True))
        st.altair_chart(line_chart(data, "hora_local", var, VARIABLES[var], max_gap, rule=rule, domain=domain,
                                   rule_label=f"{rule:.0f}%" if rule else None, headless=True), width="stretch")
        if var == "humidity" and data["humidity"].notna().any():    # a explicação fica junto do gráfico a que se refere
            st.caption(humidity_note(data))
        if i == 0 and strip is not None:      # a faixa vale para todas as variáveis: as horas sem média são as mesmas
            st.altair_chart(strip, width="stretch")

    # O botão entra no fim da linha dos filtros, lá em cima, e só existe quando há dados a exportar.
    export = data.drop(columns=["hora_local"])
    row.download_button("Exportar CSV", export.to_csv(index=False).encode("utf-8"),
                        file_name=f"pm25_{period[0]}_{period[1]}.csv", mime="text/csv",
                        help="Baixa os dados dos gráficos, no período e na resolução escolhidos.")


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
    long["valor"] = long["pm25"].map(decimal_comma)          # o tooltip do Vega escreveria o ponto decimal
    long = with_segments(long, "hora_local", "serie", pd.Timedelta(hours=1))
    models = [c for c in table.columns if c not in SERIES_COLORS]
    colors = SERIES_COLORS | dict(zip(models, MODEL_COLORS * len(models)))
    chart = alt.Chart(long).mark_line(point=True).encode(
        x=alt.X("hora_local:T", title=None, axis=alt.Axis(format="%d/%m %H:%M")),
        y=alt.Y("pm25:Q", title=VARIABLES["pm25"], scale=alt.Scale(zero=False),
                axis=alt.Axis(labelExpr="replace(datum.label, '.', ',')")),
        color=alt.Color("serie:N", title=None,
                        scale=alt.Scale(domain=list(colors), range=list(colors.values()))),
        detail="segmento:N",
        strokeDash=alt.condition(alt.datum.serie == "Observado", alt.value([1, 0]), alt.value([5, 4])),
        tooltip=[alt.Tooltip("hora_local:T", title="Hora", format="%d/%m %H:%M"), alt.Tooltip("serie:N", title="Série"),
                 alt.Tooltip("valor:N", title="PM2,5")],
    ).properties(height=320, description=f"Gráfico de linhas do PM2,5 por hora: {', '.join(colors)}.")
    st.altair_chart(chart, width="stretch")

    metrics = comparison.metrics.replace({"previsor": SERIES_LABELS}).rename(columns=METRIC_LABELS)
    if not metrics.empty:
        # O Styler escreve os números com vírgula (o formato da coluna do Streamlit só sabe o ponto).
        st.dataframe(metrics.style.format(decimal=",", precision=2, na_rep="—"), hide_index=True)
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
