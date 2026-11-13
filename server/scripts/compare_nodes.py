"""Concordância entre dois nós que medem o mesmo ar (o no-02 instalado junto do no-01).

Lê o banco em modo somente leitura e não grava nele. Pareia as médias horárias de PM2,5 dos dois nós e gera,
em --out-dir:

- concordancia_nos.json: horas pareadas; por nó, quantas horas do período ficaram em cada estado (válida, sem
  leituras, poucas leituras, suspeita), quantas entraram e quantas ficaram sem par porque o outro nó não tinha
  média; e a concordância (viés, MAE, RMSE, correlação de Pearson, R², reta de regressão de A em função de B e
  Bland-Altman), no total e separando as horas com umidade relativa acima de --humidity-limit (>) e até esse
  limite (<=); e, para reproduzir, o arquivo lido com SHA-256 e as versões de Python, numpy e pandas;
- concordancia_nos_pares.csv: uma linha por hora pareada, base do gráfico de dispersão.

Definições:

- A e B: o primeiro e o segundo nó de --devices (padrão no-01,no-02). Viés é a média de (A - B); positivo
  significa que A lê mais alto que B. As contas são as de compare_cetesb (`agreement` e `by_humidity`), com B no
  lugar da estação.
- Hora: média horária válida, pela mesma regra (MIN_SAMPLES leituras, sem as horas suspeitas) do resto da
  análise. Par: hora válida nos dois nós. Com --include-suspect as horas suspeitas também entram, marcadas.
- Período: de --start a --end, em horário de Brasília (UTC-3). Um dia sozinho em --start é o começo dele e, em
  --end, o fim (dia inclusive); com hora (AAAA-MM-DDTHH:MM) vale o instante. Só contam as horas cheias dentro do
  período: a hora que o início corta ao meio fica de fora, porque nela um dos nós ainda estava em outro lugar.
  O início padrão é a mudança do no-02 para junto do no-01 (11/11/2026 14:18 em Brasília, 17:18 UTC); o fim
  padrão é agora, sem a hora em andamento.
- Congelamento: com --freeze o banco é copiado para --out-dir como no period_metrics (mesma função, nome com os
  dias do período), o hash vai para o relatório e a comparação sai da cópia. A rodada final pode também apontar
  --db para uma cópia já congelada.
- Bland-Altman: viés (a média das diferenças A - B), desvio-padrão amostral das diferenças e limites de
  concordância de 95% (viés ± 1,96 desvio), com pelo menos duas horas pareadas. Os limites supõem diferenças
  aproximadamente normais e sem tendência com o nível de PM2,5; o CSV das horas pareadas serve para conferir.
- Umidade de uma hora pareada: a média da umidade dos dois nós (a de um só, se o outro não tem). Horas sem
  umidade nos dois entram no total, mas em nenhuma das faixas (contadas em "sem_umidade").

Uso: python -m scripts.compare_nodes [--db CAMINHO] [--out-dir resultados] [--devices no-01,no-02]
                                     [--start AAAA-MM-DD[THH:MM]] [--end AAAA-MM-DD[THH:MM]] [--include-suspect]
                                     [--freeze]
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from app import analytics, db
from app.config import get_settings
from app.forecasting import MIN_SAMPLES
from scripts.compare_cetesb import HUMIDITY_LIMIT, MIN_PAIRS, agreement
from scripts.period_metrics import BRT, freeze_database
from scripts.train_forecast import database_info

MOVE_UTC = datetime(2026, 11, 11, 17, 18, tzinfo=timezone.utc)  # o no-02 passou a dividir o suporte com o no-01
DEFAULT_DEVICES = ("no-01", "no-02")
REPORT_FILE = "concordancia_nos.json"
PAIRS_FILE = "concordancia_nos_pares.csv"
PAIR_COLUMNS = ["hora_utc", "pm25_a", "pm25_b", "umidade_a", "umidade_b", "umidade", "suspeita_a", "suspeita_b"]
STATES = (analytics.VALID_HOUR, *analytics.EXCLUSION_CAUSES)
# `agreement` foi escrita para nó × CETESB; aqui os dois lados são nós.
_LABELS = {"media_no": "media_a", "media_cetesb": "media_b"}
LOA_Z = 1.96  # limites de concordância de 95% de Bland-Altman: viés ± 1,96 desvio-padrão das diferenças


# ---------------------------------------------------------------- período

def _instant(text: str, *, end: bool) -> datetime:
    """AAAA-MM-DD ou AAAA-MM-DDTHH:MM em horário de Brasília (ou com fuso explícito), devolvido em UTC."""
    try:
        day = date.fromisoformat(text)
    except ValueError:
        value = datetime.fromisoformat(text)
        return (value if value.tzinfo else value.replace(tzinfo=BRT)).astimezone(timezone.utc)
    start = datetime(day.year, day.month, day.day, tzinfo=BRT)
    return (start + timedelta(days=1) if end else start).astimezone(timezone.utc)


def start_arg(text: str) -> datetime:
    return _instant(text, end=False)


def end_arg(text: str) -> datetime:
    return _instant(text, end=True)


def full_hours(start: datetime, end: datetime) -> pd.DatetimeIndex:
    """As horas cheias (início em UTC) inteiramente dentro de [start, end)."""
    if end <= start:  # inclui --end num dia anterior ao de --start: o fim desse dia é o começo do outro
        raise ValueError("--end anterior a --start")
    first = pd.Timestamp(start).tz_convert("UTC").ceil("h")
    last = pd.Timestamp(end).tz_convert("UTC").floor("h")
    return pd.date_range(first, periods=max(0, (last - first) // pd.Timedelta(hours=1)), freq="h")


# ---------------------------------------------------------------- horas de cada nó

def hour_table(conn, device: str, hours: pd.DatetimeIndex, min_samples: int,
               include_suspect: bool = False) -> pd.DataFrame:
    """Uma linha por hora do período: pm25, umidade, suspeita, estado (STATES) e se a hora entra no pareamento.

    Entra a hora válida e, com `include_suspect`, também a suspeita (que então mantém a média)."""
    if hours.empty:
        return pd.DataFrame(columns=["pm25", "humidity", "suspeita", "estado", "usada"], index=hours)
    end = hours[-1] + pd.Timedelta(hours=1)
    hourly = analytics.hourly_means(conn, hours[0], end, [device], min_readings=min_samples,
                                    drop_suspect=not include_suspect)
    states = analytics.hour_states(hourly, min_readings=min_samples).set_index("hora")["estado"]
    table = hourly.set_index("hora")[["pm25", "humidity", "suspeita"]].reindex(hours)
    table["suspeita"] = table["suspeita"].eq(True)  # hora sem linha no hourly_means: não suspeita
    table["estado"] = states.reindex(hours).fillna(analytics.NO_READINGS)  # antes da primeira e depois da última leitura
    usable = {analytics.VALID_HOUR, analytics.SUSPECT_HOUR} if include_suspect else {analytics.VALID_HOUR}
    table["usada"] = table["estado"].isin(usable)
    return table


def pair_hours(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    """As horas que entram nos dois nós, nas colunas de PAIR_COLUMNS."""
    both = a["usada"] & b["usada"]
    pairs = pd.DataFrame({
        "pm25_a": a.loc[both, "pm25"].astype(float), "pm25_b": b.loc[both, "pm25"].astype(float),
        "umidade_a": a.loc[both, "humidity"].astype(float), "umidade_b": b.loc[both, "humidity"].astype(float),
        "suspeita_a": a.loc[both, "suspeita"], "suspeita_b": b.loc[both, "suspeita"]})
    pairs["umidade"] = pairs[["umidade_a", "umidade_b"]].mean(axis=1)  # NaN só se os dois não têm umidade
    pairs.index.name = "hora_utc"
    return pairs.reset_index()[PAIR_COLUMNS]


def hour_counts(own: pd.DataFrame, other: pd.DataFrame) -> dict:
    """Estados das horas do período, quantas entraram e quantas ficaram sem par por falta de média no outro nó."""
    counts = own["estado"].value_counts()
    return {"estados": {state: int(counts.get(state, 0)) for state in STATES},
            "usadas": int(own["usada"].sum()),
            "usadas_sem_par": int((own["usada"] & ~other["usada"]).sum())}


# ---------------------------------------------------------------- concordância

def _relabel(stats):
    if isinstance(stats, dict):
        return {_LABELS.get(k, k): _relabel(v) for k, v in stats.items()}
    return stats


def bland_altman(a: pd.Series, b: pd.Series) -> dict | None:
    """Viés, desvio-padrão amostral das diferenças A - B e limites de concordância de 95%; None com menos de 2 pares."""
    diff = a - b
    if len(diff) < 2:
        return None
    bias, sd = float(diff.mean()), float(diff.std(ddof=1))
    return {"vies": round(bias, 2), "dp_diferencas": round(sd, 3),
            "limite_inferior": round(bias - LOA_Z * sd, 2), "limite_superior": round(bias + LOA_Z * sd, 2)}


def _agreement(a: pd.Series, b: pd.Series) -> dict:
    """`agreement` do compare_cetesb mais o Bland-Altman, quando há pares para ele."""
    out = agreement(a, b)
    limits = bland_altman(a, b)
    if limits:
        out["bland_altman"] = limits
    return out


def concordance(pairs: pd.DataFrame, humidity_limit: float, include_suspect: bool = False) -> dict:
    """A conta de `by_humidity` do compare_cetesb, com A no lugar do nó e B no lugar da estação, mais o Bland-Altman.

    Com `include_suspect`, separa também as horas suspeitas em qualquer dos dois nós (`suspeitas`) das demais."""
    groups = {"total": pd.Series(True, index=pairs.index), "umidade_alta": pairs["umidade"] > humidity_limit,
              "umidade_baixa": pairs["umidade"] <= humidity_limit}
    if include_suspect:
        flag = pairs["suspeita_a"] | pairs["suspeita_b"]
        groups |= {"suspeitas": flag, "demais": ~flag}
    out: dict = {name: _agreement(pairs.loc[mask, "pm25_a"], pairs.loc[mask, "pm25_b"]) for name, mask in groups.items()}
    out["sem_umidade"] = int(pairs["umidade"].isna().sum())
    return _relabel(out)


# ---------------------------------------------------------------- execução

def run(db_path: str, out_dir: Path, devices: tuple[str, str], start: datetime, end: datetime,
        humidity_limit: float = HUMIDITY_LIMIT, min_samples: int = MIN_SAMPLES, include_suspect: bool = False,
        freeze: bool = False) -> dict:
    a, b = devices
    if a == b:
        raise ValueError("os dois nós precisam ser diferentes")
    hours = full_hours(start, end)
    report: dict = {
        "nos": {"a": a, "b": b},
        "periodo": {"inicio_utc": db.iso(start), "fim_utc": db.iso(end), "fuso": "America/Sao_Paulo (UTC-3)",
                    "primeira_hora_utc": db.iso(hours[0]) if len(hours) else None, "horas": int(len(hours))},
        "regras": {"min_leituras_por_hora": min_samples, "limite_umidade_pct": humidity_limit, "min_pares": MIN_PAIRS,
                   "horas_suspeitas_incluidas": include_suspect,
                   "umidade_do_par": "média da umidade dos dois nós", "vies": f"média de {a} - {b}"},
    }
    if freeze:
        # Os dias de Brasília do período nomeiam a cópia; o fim é exclusivo, então o último dia é o do instante anterior.
        days = (start.astimezone(BRT).date(), (end - timedelta(seconds=1)).astimezone(BRT).date())
        frozen, info = freeze_database(db_path, out_dir, *days)
        report["congelamento"] = info
        db_path = str(frozen)  # a comparação sai da cópia, então o hash identifica os dados usados
    report["banco"] = Path(db_path).name
    lido = database_info(db_path)  # sem --freeze o hash só identifica os dados se o banco for uma cópia parada
    report["banco_lido"] = {"arquivo": lido["file"], "sha256": lido["sha256"], "tamanho_bytes": lido["size_bytes"]}
    report["ambiente"] = {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__}
    conn = db.connect(db_path, readonly=True)
    try:
        table_a = hour_table(conn, a, hours, min_samples, include_suspect)
        table_b = hour_table(conn, b, hours, min_samples, include_suspect)
    finally:
        conn.close()

    pairs = pair_hours(table_a, table_b)
    report["horas"] = {"pareadas": int(len(pairs)), a: hour_counts(table_a, table_b), b: hour_counts(table_b, table_a)}
    report["concordancia"] = concordance(pairs, humidity_limit, include_suspect)

    out_dir.mkdir(parents=True, exist_ok=True)
    # allow_nan=False: o JSON sai válido ou o script falha, nunca com NaN/Infinity no arquivo
    (out_dir / REPORT_FILE).write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False),
                                       encoding="utf-8")
    pairs.to_csv(out_dir / PAIRS_FILE, index=False)
    return report


def _summary(report: dict) -> list[str]:
    a, b = report["nos"]["a"], report["nos"]["b"]
    hours = report["horas"]
    lines = [f"{a} × {b}: {report['periodo']['horas']} h cheias no período"]
    for device in (a, b):
        h = hours[device]
        lost = ", ".join(f"{state} {n}" for state, n in h["estados"].items() if state != analytics.VALID_HOUR and n)
        lines.append(f"  {device}: {h['usadas']} h usadas, {h['usadas_sem_par']} sem par no outro nó"
                     + (f"; sem média: {lost}" if lost else ""))
    total = report["concordancia"]["total"]
    if not total["n"]:
        lines.append("Nenhuma hora pareada no período")
        return lines
    r = f", r = {total['pearson_r']:.2f}" if "pearson_r" in total else ""
    lines.append(f"{total['n']} h pareadas: viés ({a} - {b}) {total['vies']:+.1f} µg/m³, RMSE {total['rmse']:.1f}{r}")
    for band in ("umidade_alta", "umidade_baixa"):
        s = report["concordancia"][band]
        if s["n"]:
            lines.append(f"  {band.replace('_', ' ')}: {s['n']} h, viés {s['vies']:+.1f}, RMSE {s['rmse']:.1f}")
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=None, help="banco de dados (padrão: PM25_DB_PATH); use o congelado na avaliação final")
    ap.add_argument("--out-dir", default="resultados", help="pasta de saída (padrão: resultados)")
    ap.add_argument("--devices", default=",".join(DEFAULT_DEVICES), help="os dois nós, A,B (padrão: no-01,no-02)")
    ap.add_argument("--start", type=start_arg, default=MOVE_UTC,
                    help="início, horário de Brasília (padrão: a mudança, 2026-11-11T14:18)")
    ap.add_argument("--end", type=end_arg, default=None, help="fim, horário de Brasília; um dia sozinho é inclusive (padrão: agora)")
    ap.add_argument("--humidity-limit", type=float, default=HUMIDITY_LIMIT, help="umidade (%%) que separa os dois grupos")
    ap.add_argument("--min-samples", type=int, default=MIN_SAMPLES, help="leituras por hora para a hora valer")
    ap.add_argument("--include-suspect", action="store_true",
                    help="análise de sensibilidade: pareia também as horas suspeitas, marcadas, e separa-as das demais")
    ap.add_argument("--freeze", action="store_true",
                    help="copia o banco para --out-dir, registra o hash e compara sobre a cópia")
    args = ap.parse_args(argv)

    devices = tuple(d.strip() for d in args.devices.split(","))
    if len(devices) != 2:
        print("Erro: --devices precisa de exatamente dois nós, A,B", file=sys.stderr)
        return 2
    db_path = args.db or get_settings().db_path
    if not Path(db_path).exists():
        print(f"Banco não encontrado: {db_path}", file=sys.stderr)
        return 1
    try:
        report = run(db_path, Path(args.out_dir), devices, args.start, args.end or datetime.now(timezone.utc),
                     args.humidity_limit, args.min_samples, args.include_suspect, args.freeze)
    except (ValueError, RuntimeError) as exc:  # RuntimeError: a cópia congelada não passou no integrity_check
        print(f"Erro: {exc}", file=sys.stderr)
        return 2
    print("\n".join(_summary(report)))
    if "congelamento" in report:
        print(f"Banco congelado: {report['congelamento']['arquivo']} (sha256 {report['congelamento']['sha256']})")
    print(f"Saídas em {Path(args.out_dir).resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
