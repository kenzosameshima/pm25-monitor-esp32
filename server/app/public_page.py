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

    run: list[tuple[float, float]] = []
    for i, value in enumerate([*hours.to_list(), math.nan]):  # o NaN do fim fecha o último trecho
        if not pd.isna(value):
            run.append((x(i), y(value)))
            continue
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


def _mean_block(hours: pd.Series) -> str:
    valid = hours.dropna()
    if valid.empty:
        return f'<p class="mean">Média das últimas {WINDOW_HOURS} horas: sem horas com média.</p>'
    mean = valid.mean()
    return (f'<p class="mean">Média das últimas {WINDOW_HOURS} horas: <strong>{_number(mean)} µg/m³</strong> '
            f'{_band(mean)} <span class="muted">({len(valid)} de {WINDOW_HOURS} horas com média)</span></p>')


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
            f'<strong>{_number(chosen["predicted_pm25"])} µg/m³</strong> {_band(chosen["predicted_pm25"])} '
            '<span class="muted">(experimental: modelo estatístico ainda em avaliação)</span></p>')


def _node_card(node: pd.Series, hours: pd.Series, forecast: str = "") -> str:
    state = f'<p class="state">{STATE_LABELS[node["status"]]} · último envio {_ago(node["minutes_since"])}</p>'
    if node["status"] == "sem_dados":
        # Sem envio recente, o último valor não diz como o ar está agora: o cartão fica sem ele, como no painel.
        reading = '<p class="pm25 muted">Sem leitura recente.</p>'
    else:
        reading = f'<p class="pm25"><span class="value">{_number(node["pm25"])}</span> µg/m³</p>'
        if analytics.is_zero_reading(node["pm1"], node["pm25"], node["pm10"]):
            # Tudo em zero não diz se o ar está limpo ou se o sensor parou de ver partículas: sem faixa.
            reading += '<p class="note">Leitura zerada: sem faixa, porque o sensor pode ter deixado de ver partículas.</p>'
        else:
            reading += (f'<p class="band">{_band(node["pm25"])} '
                        '<span class="muted">última leitura (média de 1 minuto)</span></p>')
        reading += (f'<dl class="others"><div><dt>PM10</dt><dd>{_number(node["pm10"])} µg/m³</dd></div>'
                    f'<div><dt>Temperatura</dt><dd>{_number(node["temperature"])} °C</dd></div>'
                    f'<div><dt>Umidade</dt><dd>{_number(node["humidity"], 0)}%</dd></div></dl>')
        if pd.notna(node["humidity"]) and node["humidity"] > analytics.HIGH_HUMIDITY:
            reading += (f'<p class="note">Umidade acima de {analytics.HIGH_HUMIDITY:.0f}%: com o ar úmido, sensores como '
                        'este tendem a medir PM2,5 a mais.</p>')
    chart = hourly_chart_svg(hours)
    if chart:
        chart = f'<figure class="chart">{chart}<figcaption>PM2,5 médio por hora (µg/m³), horário de Brasília</figcaption></figure>'
    place = public_location(node["location"])
    title = escape(node["device_id"]) + (f' <span class="place">· {escape(place)}</span>' if place else "")
    return (f'<section class="node"><h2>{title}</h2>{state}{reading}'
            f'{_mean_block(hours)}{forecast}{chart}</section>')


PAGE_CSS = """
:root{--bg:#f5f6f8;--card:#fff;--text:#1c232b;--muted:#5b6571;--border:#e2e5e9;--line:#2563eb;--grid:#d3d8de}
@media (prefers-color-scheme:dark){:root{--bg:#101317;--card:#191e24;--text:#e6e9ed;--muted:#9ba4ae;--border:#2a3038;
--line:#60a5fa;--grid:#343b44}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:44rem;margin:0 auto;padding:24px 16px 40px}
h1{font-size:1.5rem;line-height:1.25;margin:0 0 6px}
h2{font-size:1.15rem;margin:0}
p{margin:6px 0}
.lead,.muted,.state,.place,figcaption,footer{color:var(--muted)}
.place{font-weight:400}
.node{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px;margin:16px 0}
.state{font-size:.9rem;margin:2px 0 10px}
.value{font-size:2.6rem;font-weight:700;line-height:1.1}
.chip{display:inline-block;padding:0 10px;border-radius:999px;background:var(--c);color:#14181d;font-weight:600;
font-size:.9rem;white-space:nowrap}
.b0{--c:#3fae6b}.b1{--c:#e6c445}.b2{--c:#ee8a3a}.b3{--c:#d9483b;color:#fff}.b4{--c:#8e4fb5;color:#fff}
.others{display:flex;flex-wrap:wrap;gap:8px 24px;margin:12px 0}
dt{font-size:.8rem;color:var(--muted)}
dd{margin:0;font-weight:600}
.note{font-size:.9rem;border-left:3px solid #e6c445;padding-left:8px}
.mean,.forecast{border-top:1px solid var(--border);padding-top:10px;margin-top:10px}
figure{margin:12px 0 0}
svg{display:block;width:100%;height:auto}
svg .band{opacity:.16}
svg .grid{stroke:var(--grid);stroke-width:1}
svg text{fill:var(--muted);font-size:13px}
@media (max-width:520px){svg text{font-size:21px}}  /* o SVG encolhe com a tela; o texto do eixo, menos */
svg .line{fill:none;stroke:var(--line);stroke-width:2.5;stroke-linejoin:round;stroke-linecap:round}
svg .point{fill:var(--line)}
figcaption{font-size:.85rem}
.legend{list-style:none;padding:0;margin:8px 0;display:flex;flex-wrap:wrap;gap:6px 14px}
footer{font-size:.85rem;margin-top:24px}
"""


def _legend() -> str:
    """As faixas da CETESB com os limites de cada uma."""
    items, low = [], None
    for bound, label in analytics.AIR_QUALITY_BANDS:
        if low is None:
            span = f"até {bound:g}"
        elif bound == math.inf:
            span = f"acima de {low:g}"
        else:
            span = f"{low:g} a {bound:g}"
        items.append(f'<li><span class="chip {BAND_CLASS[label]}">{escape(label)}</span> {span}</li>')
        low = bound
    return f'<ul class="legend" aria-label="Faixas de PM2,5 da CETESB, em µg/m³">{"".join(items)}</ul>'


def render(conn, now: datetime) -> str:
    """O HTML completo da página no instante `now` (UTC)."""
    status = analytics.device_status(conn, now)
    cards = "".join(_node_card(node, _last_hours(conn, node["device_id"], now),
                               _forecast_block(conn, node["device_id"], now))
                    for _, node in status.iterrows())
    if not cards:
        cards = '<p class="empty">Nenhum nó enviou leituras ainda.</p>'
    updated = now.astimezone(LOCAL_TZ)
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Qualidade do ar · PM2,5</title>
<meta name="description" content="PM2,5 medido por sensores de baixo custo: última leitura, média de 24 horas e gráfico.">
<style>{PAGE_CSS}</style></head>
<body><main>
<header><h1>Qualidade do ar: PM2,5</h1>
<p class="lead">PM2,5 é o material particulado fino, partículas de até 2,5 micrômetros que chegam ao fundo dos pulmões.
Os valores vêm de sensores de baixo custo de um projeto de TCC, em µg/m³.</p></header>
{cards}
<section><h2>Faixas de qualidade do ar (µg/m³)</h2>{_legend()}
<p class="muted">São as faixas da CETESB para a média de 24 horas. Na leitura de um minuto, servem só de referência.</p>
</section>
<footer><p>Atualizado às {updated:%H:%M}, horário de Brasília. Recarregue a página para ver dados novos.</p>
<p>Sensores de baixo custo erram mais que os equipamentos oficiais, principalmente com o ar úmido. Estes dados não
substituem os da rede de monitoramento da CETESB.</p></footer>
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
