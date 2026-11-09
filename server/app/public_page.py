"""Página pública (/public): o estado do ar medido pelos nós, para qualquer pessoa, sem token.

Mostra só dados agregados e o necessário para lê-los (ADR 0006). O que diz como o nó e a coleta estão (firmware, sinal,
saúde da coleta) e a avaliação dos modelos ficam no painel interno. O HTML é gerado aqui, sem JavaScript nem recurso
externo, e abre o banco só para leitura. As regras vêm de analytics, as mesmas do painel e da API de leitura.
"""

import math
import threading
import time
from datetime import datetime, timezone
from html import escape
from zoneinfo import ZoneInfo

import pandas as pd
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from . import analytics, db
from .config import get_settings

router = APIRouter()
LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
BAND_BOUNDS = [bound for bound, _ in analytics.AIR_QUALITY_BANDS[:-1]]  # 25, 50, 75 e 125 µg/m³
BAND_FILLS = ("#3fae6b", "#e6c445", "#ee8a3a", "#d9483b", "#8e4fb5")  # as do painel (dashboard/scale.py)

# Área do gráfico, em unidades do viewBox; a largura real acompanha a tela.
CHART_W, CHART_H = 480, 200
PAD_LEFT, PAD_RIGHT, PAD_TOP, PAD_BOTTOM = 40, 6, 10, 28
X_LABEL_EVERY = 6  # horas entre os rótulos do eixo horizontal


def _axis_top(peak: float) -> float:
    """O topo do eixo: o limite de faixa logo acima do maior valor; acima da última faixa, o múltiplo de 25 seguinte."""
    for bound in BAND_BOUNDS:
        if peak <= bound:
            return bound
    return math.ceil(peak / 25) * 25


def hourly_chart_svg(hours: pd.Series) -> str:
    """O SVG do PM2,5 médio por hora: `hours` tem o índice em horas UTC, seguidas, e NaN na hora sem média.

    A linha se interrompe nas horas sem média, e uma hora válida sozinha vira um ponto. As faixas da CETESB ficam ao
    fundo, e o eixo vertical vai até o limite de faixa logo acima do maior valor. Vazio se nenhuma hora tem média.
    """
    valid = hours.dropna()
    if valid.empty:
        return ""
    top = _axis_top(float(valid.max()))
    plot_w, plot_h = CHART_W - PAD_LEFT - PAD_RIGHT, CHART_H - PAD_TOP - PAD_BOTTOM
    step = plot_w / len(hours)

    def x(i: int) -> float:
        return PAD_LEFT + (i + 0.5) * step

    def y(value: float) -> float:
        return PAD_TOP + plot_h * (1 - min(value, top) / top)

    parts = []
    lows = [0.0, *BAND_BOUNDS]
    for low, high, fill in zip(lows, [*BAND_BOUNDS, math.inf], BAND_FILLS):
        if low >= top:
            break
        parts.append(f'<rect class="band" x="{PAD_LEFT}" y="{y(min(high, top)):.1f}" width="{plot_w}" '
                     f'height="{y(low) - y(min(high, top)):.1f}" fill="{fill}"/>')
    ticks = [0.0, *[b for b in BAND_BOUNDS if b < top], top]
    for tick in ticks:
        parts.append(f'<line class="grid" x1="{PAD_LEFT}" x2="{CHART_W - PAD_RIGHT}" y1="{y(tick):.1f}" y2="{y(tick):.1f}"/>')
        parts.append(f'<text class="tick" x="{PAD_LEFT - 5}" y="{y(tick):.1f}" text-anchor="end" '
                     f'dominant-baseline="middle">{tick:g}</text>')
    local = hours.index.tz_convert(LOCAL_TZ)
    for i, hour in enumerate(local):
        if hour.hour % X_LABEL_EVERY == 0:
            parts.append(f'<text class="tick-x" x="{x(i):.1f}" y="{CHART_H - 6}" text-anchor="middle">{hour.hour}h</text>')

    baseline = PAD_TOP + plot_h
    run: list[tuple[float, float]] = []
    for i, value in enumerate([*hours.to_list(), math.nan]):  # o NaN do fim fecha o último trecho
        if not pd.isna(value):
            run.append((x(i), y(value)))
            continue
        if i < len(hours):  # a hora sem média ganha uma marca no eixo: o buraco na linha não parece erro do gráfico
            parts.append(f'<rect class="gap" x="{x(i) - step / 2 + 1:.1f}" y="{baseline + 1:.1f}" '
                         f'width="{step - 2:.1f}" height="4"/>')
        if len(run) == 1:
            parts.append(f'<circle class="point" cx="{run[0][0]:.1f}" cy="{run[0][1]:.1f}" r="3"/>')
        elif run:
            points = " ".join(f"{px:.1f},{py:.1f}" for px, py in run)
            parts.append(f'<polyline class="line" points="{points}"/>')
        run = []

    label = (f"PM2,5 médio por hora nas últimas {len(hours)} horas, de {_number(valid.min())} a "
             f"{_number(valid.max())} µg/m³")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CHART_W} {CHART_H}" role="img" '
            f'aria-label="{escape(label)}"><title>{escape(label)}</title>{"".join(parts)}</svg>')


def _number(value, decimals: int = 1) -> str:
    """Número com vírgula decimal; travessão sem valor."""
    if value is None or pd.isna(value):
        return "—"
    return f"{value:.{decimals}f}".replace(".", ",")


BAND_CLASS = {label: f"b{i}" for i, (_, label) in enumerate(analytics.AIR_QUALITY_BANDS)}


def _band(pm25) -> str:
    """O selo da faixa da CETESB de um valor de PM2,5; vazio sem valor válido."""
    band = analytics.air_quality(pm25)
    return f'<span class="chip {BAND_CLASS[band]}">{escape(band)}</span>' if band else ""


STATE_LABELS = {"em_operacao": "Em operação", "atrasado": "Atrasado", "sem_dados": "Sem dados recentes"}


def _ago(minutes) -> str:
    """Há quanto tempo, em minutos, horas ou dias inteiros."""
    if minutes is None or pd.isna(minutes):
        return "nunca"
    minutes = max(0, int(minutes))
    if minutes < 1:
        return "há menos de 1 min"
    if minutes < 60:
        return f"há {minutes} min"
    if minutes < 48 * 60:
        return f"há {minutes // 60} h"
    return f"há {minutes // (24 * 60)} dias"


WINDOW_HOURS = 24


def _last_hours(conn, device: str, now: datetime) -> pd.Series:
    """PM2,5 médio de cada uma das últimas WINDOW_HOURS horas completas (NaN na hora sem média), da mais antiga à
    mais recente. A hora em andamento fica de fora: ela ainda não tem as leituras mínimas."""
    end = pd.Timestamp(now).floor("h")
    start = end - pd.Timedelta(hours=WINDOW_HOURS)
    slots = pd.date_range(start, end, freq="h", inclusive="left")
    hourly = analytics.hourly_means(conn, start.to_pydatetime(), end.to_pydatetime(), [device])
    return hourly.set_index("hora")["pm25"].reindex(slots).astype(float)


def _day_block(hours: pd.Series, forecast: str) -> str:
    """As últimas 24 horas: a média, de quantas horas ela saiu, o gráfico e a previsão. Vazio sem hora com média e sem
    previsão (num nó parado há mais de um dia, não há o que mostrar)."""
    valid = hours.dropna()
    if valid.empty and not forecast:
        return ""
    if valid.empty:
        summary = (f'<p>Nenhuma das últimas {WINDOW_HOURS} horas teve leituras suficientes para uma média.</p>')
    else:
        mean = valid.mean()
        coverage = ("" if len(valid) == WINDOW_HOURS else
                    f' Só {len(valid)} de {WINDOW_HOURS} horas tiveram leituras suficientes para entrar na conta.')
        summary = f'<p>Média de <strong>{_number(mean)} µg/m³</strong>, {_band(mean)}.{coverage}</p>'
    chart = hourly_chart_svg(hours)
    if chart:
        chart = (f'<figure>{chart}<figcaption>PM2,5 médio de cada hora, em µg/m³, no horário de Brasília. Onde a linha '
                 'some, a hora não teve leituras suficientes.</figcaption></figure>')
    return f'<h3>Últimas {WINDOW_HOURS} horas</h3>{summary}{chart}{forecast}'


def _scale(pm25) -> str:
    """A escala da CETESB, com as cinco faixas do mesmo comprimento e um marcador onde o valor cai."""
    position = analytics.band_position(pm25)
    if position is None:
        return ""
    segments = "".join(f'<span class="{BAND_CLASS[label]}"></span>' for _, label in analytics.AIR_QUALITY_BANDS)
    share = 100 / len(analytics.AIR_QUALITY_BANDS)
    ticks = "".join(f'<span style="left:{(i + 1) * share:g}%">{bound:g}</span>' for i, bound in enumerate(BAND_BOUNDS))
    return (f'<div class="scale" aria-hidden="true"><div class="track">{segments}</div>'
            f'<div class="marker" style="left:{position * 100:.1f}%"></div><div class="ticks">{ticks}</div></div>')


def _now_block(node: pd.Series) -> str:
    """A última leitura: o veredito da faixa em destaque, a escala e as outras medidas. Leitura zerada fica sem faixa."""
    reading = f'<span class="num">{_number(node["pm25"])}</span> µg/m³ de PM2,5 na última leitura, a média de 1 minuto.'
    if analytics.is_zero_reading(node["pm1"], node["pm25"], node["pm10"]):
        # Tudo em zero não diz se o ar está limpo ou se o sensor parou de ver partículas: sem faixa.
        verdict = (f'<div class="verdict neutral"><p class="reading">{reading}</p><p class="reading">Leitura zerada: '
                   'sem faixa, porque o sensor pode ter deixado de ver partículas.</p></div>')
    else:
        band = analytics.air_quality(node["pm25"])
        verdict = (f'<div class="verdict {BAND_CLASS.get(band, "neutral")}"><p class="word">{escape(band or "—")}</p>'
                   f'<p class="reading">{reading}</p></div>{_scale(node["pm25"])}')
    others = (f'<dl class="others"><div><dt>PM10</dt><dd>{_number(node["pm10"])} µg/m³</dd></div>'
              f'<div><dt>Temperatura</dt><dd>{_number(node["temperature"])} °C</dd></div>'
              f'<div><dt>Umidade</dt><dd>{_number(node["humidity"], 0)}%</dd></div></dl>')
    if pd.notna(node["humidity"]) and node["humidity"] > analytics.HIGH_HUMIDITY:
        others += (f'<p class="note">Umidade acima de {analytics.HIGH_HUMIDITY:.0f}%: com o ar úmido, sensores como este '
                   'tendem a medir PM2,5 a mais.</p>')
    return f'<h3>Agora</h3>{verdict}{others}'


def public_location(location) -> str | None:
    """O local que a página mostra: o texto antes do primeiro parêntese. Os parênteses descrevem a instalação (onde o
    nó fica preso, a que altura), o que só interessa a quem cuida dele."""
    if not isinstance(location, str):
        return None
    return location.split("(", 1)[0].strip().rstrip(",;") or None


RETRO_SUFFIX = "-retro"  # versões recalculadas depois (scripts.forecast_job): servem à avaliação, não à previsão


def _forecast_block(conn, device: str, now: datetime) -> str:
    """A previsão da hora em andamento (ou da seguinte, se o job já a fez) feita por último, sem as retroativas."""
    current = pd.Timestamp(now).floor("h")
    rows = [r for r in db.fetch_forecasts(conn, current.to_pydatetime(), (current + pd.Timedelta(hours=2)).to_pydatetime(),
                                          [device])
            if not r["model_version"].endswith(RETRO_SUFFIX)]
    if not rows:
        return ""
    target = min(r["target_hour"] for r in rows)
    chosen = max((r for r in rows if r["target_hour"] == target), key=lambda r: r["generated_at"])
    start = pd.Timestamp(target).tz_convert(LOCAL_TZ)
    end = start + pd.Timedelta(hours=1)
    return (f'<p class="forecast">Previsão para a média das {start.hour}h às {end.hour}h: '
            f'<strong>{_number(chosen["predicted_pm25"])} µg/m³</strong>, {_band(chosen["predicted_pm25"])}. '
            '<span class="muted">É experimental: um modelo estatístico ainda em avaliação.</span></p>')


def _node_card(node: pd.Series, hours: pd.Series, forecast: str = "") -> str:
    """Um nó: o lugar como título, o estado, e os blocos "Agora" e "Últimas 24 horas". Sem envio recente, o último
    valor não diz como o ar está agora: o nó fica sem o bloco "Agora", como no painel."""
    place = public_location(node["location"])
    title = escape(place or node["device_id"])
    sensor = f' <span class="nowrap">(sensor {escape(node["device_id"])})</span>' if place else ""
    state = f'<p class="state">{STATE_LABELS[node["status"]]}, último envio {_ago(node["minutes_since"])}{sensor}.</p>'
    offline = node["status"] == "sem_dados"
    now = "" if offline else _now_block(node)
    return (f'<section class="node{" off" if offline else ""}"><h2>{title}</h2>{state}{now}'
            f'{_day_block(hours, forecast)}</section>')


STATE_ORDER = {"em_operacao": 0, "atrasado": 1, "sem_dados": 2}


def _legend() -> str:
    """As faixas da CETESB com os limites de cada uma, na cor da escala."""
    items, low = [], None
    for bound, label in analytics.AIR_QUALITY_BANDS:
        if low is None:
            span = f"até {bound:g} µg/m³"
        elif bound == math.inf:
            span = f"acima de {low:g} µg/m³"
        else:
            span = f"de {low:g} a {bound:g} µg/m³"
        items.append(f'<li><span class="chip {BAND_CLASS[label]}">{escape(label)}</span> {span}</li>')
        low = bound
    return f'<ul class="legend">{"".join(items)}</ul>'


PAGE_CSS = """
:root{--haze:#e8eef2;--ink:#1d2830;--muted:#56646f;--rule:#c5d0d8;--air:#2b5a7a;--gap:#aebbc4;
--display:Bahnschrift,"DIN Alternate","Franklin Gothic Medium","Nimbus Sans Narrow",sans-serif-condensed,sans-serif;
--text:Seravek,"Gill Sans Nova",Ubuntu,Calibri,"DejaVu Sans",source-sans-pro,sans-serif}
@media (prefers-color-scheme:dark){:root{--haze:#11181d;--ink:#e2e8ec;--muted:#95a3ad;--rule:#2c3942;--air:#86b8db;
--gap:#46545e}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--haze);color:var(--ink);font:1rem/1.55 var(--text)}
main{max-width:36rem;margin:0 auto;padding:1.5rem 1rem 3rem}
h1,h2,h3,.word,.num{font-family:var(--display);font-weight:600;line-height:1.15}
h1{font-size:1.25rem;margin:0}
h2{font-size:1.95rem;margin:0}
h3{font-size:1.25rem;margin:1.75rem 0 .6rem}
p{margin:.4rem 0}
.lead,.state,.muted,figcaption,footer{color:var(--muted)}
.lead{font-size:.95rem;margin:.2rem 0 0}
.node{border-top:1px solid var(--rule);margin-top:1.5rem;padding-top:1.25rem}
.state{font-size:.9rem;margin:.3rem 0 0}
.nowrap{white-space:nowrap}
.b0{--c:#3fae6b}.b1{--c:#e6c445}.b2{--c:#ee8a3a}.b3{--c:#d9483b}.b4{--c:#8e4fb5}
.verdict{background:var(--c);color:#13202a;border-radius:6px;padding:.85rem 1rem 1rem}
.verdict.b3,.verdict.b4,.chip.b3,.chip.b4{color:#fff}
.verdict.neutral{background:none;border:1px solid var(--rule);color:var(--ink)}
.word{font-size:3.4rem;margin:0;letter-spacing:-.01em}
.reading{margin:.3rem 0 0}
.num{font-size:1.6rem;font-variant-numeric:tabular-nums}
.scale{position:relative;margin:.9rem 0 2.1rem}
.track{display:flex;height:.55rem;border-radius:3px;overflow:hidden}
.track span{flex:1;background:var(--c)}
.marker{position:absolute;top:-.3rem;width:4px;height:1.15rem;margin-left:-2px;background:var(--ink);border-radius:2px;
box-shadow:0 0 0 2px var(--haze)}
.ticks span{position:absolute;top:.9rem;transform:translateX(-50%);font-size:.75rem;color:var(--muted)}
.others{display:flex;flex-wrap:wrap;gap:.4rem 2rem;margin:0}
dt{font-size:.8rem;color:var(--muted)}
dd{margin:0;font-weight:600;font-variant-numeric:tabular-nums}
.note{font-size:.9rem;margin:.8rem 0 0;padding-left:.6rem;border-left:3px solid #e6c445}
.chip{display:inline-block;padding:0 .45rem;border-radius:3px;background:var(--c);color:#13202a;font-weight:600}
figure{margin:.9rem 0 0}
svg{display:block;width:100%;height:auto}
svg .band{opacity:.09}
svg .grid{stroke:var(--rule);stroke-width:1}
svg text{fill:var(--muted);font-family:var(--text);font-size:13px}
@media (max-width:520px){svg text{font-size:21px}}
svg .line{fill:none;stroke:var(--air);stroke-width:2.5;stroke-linejoin:round;stroke-linecap:round}
svg .point{fill:var(--air)}
svg .gap{fill:var(--gap)}
figcaption{font-size:.85rem;margin-top:.4rem}
.forecast{margin-top:1rem}
.node.off h2{font-size:1.25rem}
.about{border-top:1px solid var(--rule);margin-top:2.25rem;padding-top:1.25rem;font-size:.95rem}
.about h2{font-size:1.25rem}
.legend{list-style:none;padding:0;margin:.8rem 0}
.legend li{margin:.3rem 0}
.legend .chip{min-width:6.5rem;margin-right:.5rem}
footer{font-size:.85rem;margin-top:1.75rem}
"""


def render(conn, now: datetime) -> str:
    """O HTML completo da página no instante `now` (UTC). Os nós que estão enviando vêm antes dos parados."""
    status = analytics.device_status(conn, now)
    if not status.empty:
        status = status.assign(_order=status["status"].map(STATE_ORDER)).sort_values(["_order", "device_id"])
    cards = "".join(_node_card(node, _last_hours(conn, node["device_id"], now),
                               _forecast_block(conn, node["device_id"], now))
                    for _, node in status.iterrows())
    if not cards:
        cards = '<p class="empty">Nenhum nó enviou leituras ainda.</p>'
    updated = now.astimezone(LOCAL_TZ)
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Qualidade do ar · PM2,5</title>
<meta name="description" content="PM2,5 medido por sensores de baixo custo: a última leitura, a média de 24 horas e o gráfico.">
<style>{PAGE_CSS}</style></head>
<body><main>
<header><h1>Qualidade do ar</h1>
<p class="lead">PM2,5 medido por sensores de baixo custo de um projeto de TCC.
Atualizado às {updated:%H:%M}, horário de Brasília.</p></header>
{cards}
<section class="about"><h2>Como ler</h2>
<p>PM2,5 é o material particulado fino: partículas de até 2,5 micrômetros, que chegam ao fundo dos pulmões. A medida é
em microgramas por metro cúbico de ar (µg/m³).</p>
<p>As cores seguem as faixas da CETESB, que valem para a média de 24 horas. Na leitura de um minuto, servem só de
referência.</p>
{_legend()}
<p>Sensores de baixo custo erram mais que os equipamentos oficiais, principalmente com o ar úmido. Estes dados não
substituem os da rede de monitoramento da CETESB.</p></section>
<footer><p>Recarregue a página para ver dados novos.</p></footer>
</main></body></html>
"""


# Sem JavaScript nem recurso externo: o default-src 'none' bloqueia tudo, menos o estilo embutido. A página também não
# pode ser posta numa moldura de outro site nem mandar o próprio endereço nos links.
SECURITY_HEADERS = {
    "Content-Security-Policy": ("default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; "
                                "frame-ancestors 'none'"),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "public, max-age=60",
}


CACHE_SECONDS = 60
_cache: dict[str, tuple[float, str]] = {}  # caminho do banco -> (expira em, pelo relógio monotônico; página)
_cache_lock = threading.Lock()


def _cached_page(db_path: str) -> str:
    """A página de até CACHE_SECONDS atrás: muitos acessos seguidos não viram uma consulta ao banco cada um. Os nós
    enviam uma leitura por minuto, então o cache não esconde quase nada."""
    with _cache_lock:
        expires, page = _cache.get(db_path, (0.0, ""))
        if time.monotonic() < expires:
            return page
        conn = db.connect(db_path, readonly=True)
        try:
            page = render(conn, datetime.now(timezone.utc).replace(microsecond=0))
        finally:
            conn.close()
        _cache[db_path] = (time.monotonic() + CACHE_SECONDS, page)
        return page


@router.get("/public", response_class=HTMLResponse, include_in_schema=False)
def public_page() -> HTMLResponse:
    return HTMLResponse(_cached_page(get_settings().db_path), headers=SECURITY_HEADERS)
