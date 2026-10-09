"""Comparação das médias horárias de PM2,5 de cada nó com as de uma estação da CETESB (referência).

Lê o banco em modo somente leitura e o CSV exportado do QUALAR (MP2.5, média horária). Não grava no
banco. Gera, em --out-dir:

- comparacao_cetesb.json: por nó, número de horas pareadas, viés, MAE, RMSE, correlação de Pearson e
  reta de regressão (nó em função da CETESB), no total e separando umidade relativa média da hora
  acima e abaixo de --humidity-limit;
- comparacao_cetesb_pares.csv: uma linha por hora pareada (hora de início em UTC, nó, valor do nó,
  valor da CETESB, umidade), base do gráfico de dispersão.

Definições:

- Hora do nó: média horária válida, pela mesma função e regra (MIN_SAMPLES) da avaliação dos modelos.
- Hora da CETESB: o rótulo do CSV é o fim da hora (01:00 = 00:00 a 01:00; 24:00 = 23:00 a 24:00), no
  horário de Brasília. `--hour-label start` trata o rótulo como início. A convenção deve ser
  conferida no manual da CETESB; se estiver errada, todo o pareamento fica deslocado em 1 h.
- Par: hora com valor válido nos dois. Valores vazios da CETESB e horas inválidas do nó ficam de fora.
- Viés: média de (nó - CETESB); positivo significa que o nó lê mais alto que a referência.
- Os valores da CETESB são inteiros, o que limita a resolução da comparação.

Uso: python -m scripts.compare_cetesb --cetesb cetesb_pm25.csv [--db CAMINHO] [--out-dir resultados]
                                      [--start AAAA-MM-DD] [--end AAAA-MM-DD] [--devices no-01]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from app import db
from app.config import get_settings
from scripts.period_metrics import TEST_DEVICE_PREFIX, period_bounds
from scripts.train_forecast import MIN_SAMPLES, hourly_series

BRT = timezone(timedelta(hours=-3))
HUMIDITY_LIMIT = 75.0  # % de umidade relativa; acima disso o PMS5003 tende a superestimar
MIN_PAIRS = 24         # abaixo disso a correlação e a regressão não são reportadas como confiáveis
_DATE_LINE = re.compile(r"^\s*(\d{2})/(\d{2})/(\d{4});(\d{1,2}):(\d{2});\s*([^;]*)\s*$")


def read_cetesb(path: str, hour_label: str = "end") -> tuple[pd.Series, dict]:
    """Série horária da CETESB indexada pela hora de início em UTC, com a estação e o rótulo lido."""
    if hour_label not in ("end", "start"):
        raise ValueError("hour_label deve ser 'end' ou 'start'")
    raw = Path(path).read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")  # exportação do QUALAR
    meta, values = {}, {}
    for line in text.splitlines():
        m = _DATE_LINE.match(line)
        if not m:
            if ":;" in line:
                key, _, val = line.partition(":;")
                meta[key.strip()] = val.strip()
            continue
        day, month, year, hh, mm, val = m.groups()
        if mm != "00":
            raise ValueError(f"horário fora da hora cheia: {line!r}")
        label = datetime(int(year), int(month), int(day), tzinfo=BRT) + timedelta(hours=int(hh))  # 24:00 -> dia seguinte
        start = label - timedelta(hours=1) if hour_label == "end" else label
        number = val.replace(",", ".").strip()
        values[start.astimezone(timezone.utc)] = float(number) if number else np.nan
    if not values:
        raise ValueError("nenhuma linha de dados no formato DD/MM/AAAA;HH:00;valor")
    series = pd.Series(values).sort_index()
    series.index = pd.DatetimeIndex(series.index, tz="UTC")
    info = {"estacao": meta.get("Nome da estação"), "arquivo": Path(path).name,
            "rotulo_hora": "fim da hora" if hour_label == "end" else "início da hora",
            "horas_no_arquivo": int(len(series)), "horas_vazias": int(series.isna().sum())}
    for key, val in meta.items():
        if key.lower().startswith("c") and "esta" in key.lower():
            info["codigo_estacao"] = val
    return series, info


def agreement(node: pd.Series, ref: pd.Series) -> dict:
    """Viés, erros e relação linear entre duas séries já pareadas."""
    n = int(len(node))
    out: dict = {"n": n}
    if n == 0:
        return out
    diff = node - ref
    out |= {"media_no": round(float(node.mean()), 2), "media_cetesb": round(float(ref.mean()), 2),
            "vies": round(float(diff.mean()), 2), "mae": round(float(diff.abs().mean()), 2),
            "rmse": round(float(np.sqrt((diff ** 2).mean())), 2)}
    if n >= MIN_PAIRS and ref.std() > 0 and node.std() > 0:
        slope, intercept = np.polyfit(ref.to_numpy(float), node.to_numpy(float), 1)
        r = float(np.corrcoef(ref, node)[0, 1])
        out |= {"pearson_r": round(r, 3), "r2": round(r * r, 3),
                "inclinacao": round(float(slope), 3), "intercepto": round(float(intercept), 2)}
    elif n < MIN_PAIRS:
        out["aviso"] = f"menos de {MIN_PAIRS} pares: correlação e regressão não calculadas"
    return out


def paired(conn, device: str, ref: pd.Series, start: datetime, end: datetime, min_samples: int) -> pd.DataFrame:
    hourly = hourly_series(conn, device, min_samples)
    if hourly.empty:
        return pd.DataFrame(columns=["hora_utc", "no", "node", "cetesb", "umidade"])
    hourly = hourly[(hourly.index >= start) & (hourly.index < end)]
    df = pd.DataFrame({"node": hourly["pm25"], "umidade": hourly["humidity"]}).join(ref.rename("cetesb"), how="inner")
    df = df.dropna(subset=["node", "cetesb"])
    df.index.name = "hora_utc"
    df = df.reset_index()
    df.insert(1, "no", device)
    return df


def run(db_path: str, cetesb_path: str, out_dir: Path, start: date | None, end: date | None,
        devices: list[str] | None, hour_label: str, humidity_limit: float, min_samples: int) -> dict:
    ref, info = read_cetesb(cetesb_path, hour_label)
    first = ref.index.min().astimezone(BRT).date()
    last = ref.index.max().astimezone(BRT).date()
    start, end = start or first, end or last
    start_utc, end_utc, _ = period_bounds(start, end)

    conn = db.connect(db_path, readonly=True)
    try:
        ids = devices if devices is not None else [
            r[0] for r in conn.execute("SELECT device_id FROM devices ORDER BY device_id")
            if not r[0].startswith(TEST_DEVICE_PREFIX)]
        report: dict = {"periodo": {"inicio": start.isoformat(), "fim": end.isoformat(), "fuso": "America/Sao_Paulo (UTC-3)"},
                        "cetesb": info, "regras": {"min_leituras_por_hora": min_samples, "limite_umidade_pct": humidity_limit,
                                                   "min_pares": MIN_PAIRS}, "nos": {}}
        frames = []
        for device in ids:
            df = paired(conn, device, ref, start_utc, end_utc, min_samples)
            frames.append(df)
            humid = df["umidade"]
            report["nos"][device] = {
                "total": agreement(df["node"], df["cetesb"]),
                "umidade_alta": agreement(df.loc[humid > humidity_limit, "node"], df.loc[humid > humidity_limit, "cetesb"]),
                "umidade_baixa": agreement(df.loc[humid <= humidity_limit, "node"], df.loc[humid <= humidity_limit, "cetesb"]),
                "sem_umidade": int(humid.isna().sum()),
            }
    finally:
        conn.close()

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "comparacao_cetesb.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    pairs = pd.concat(frames) if frames else pd.DataFrame()
    pairs.to_csv(out_dir / "comparacao_cetesb_pares.csv", index=False)
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cetesb", required=True, help="CSV de MP2,5 (média horária) exportado do QUALAR")
    ap.add_argument("--db", default=None, help="banco de dados (padrão: PM25_DB_PATH); use o congelado na avaliação final")
    ap.add_argument("--out-dir", default="resultados", help="pasta de saída (padrão: resultados)")
    ap.add_argument("--start", type=date.fromisoformat, default=None, help="primeiro dia (padrão: início do arquivo)")
    ap.add_argument("--end", type=date.fromisoformat, default=None, help="último dia, inclusive (padrão: fim do arquivo)")
    ap.add_argument("--devices", default=None, help="nós separados por vírgula (padrão: todos, menos os de teste)")
    ap.add_argument("--hour-label", choices=["end", "start"], default="end",
                    help="o rótulo HH:00 da CETESB marca o fim (padrão) ou o início da hora")
    ap.add_argument("--humidity-limit", type=float, default=HUMIDITY_LIMIT, help="umidade (%%) que separa os dois grupos")
    ap.add_argument("--min-samples", type=int, default=MIN_SAMPLES, help="leituras por hora para a hora do nó valer")
    args = ap.parse_args(argv)

    db_path = args.db or get_settings().db_path
    if not Path(db_path).exists():
        print(f"Banco não encontrado: {db_path}", file=sys.stderr)
        return 1
    if not Path(args.cetesb).exists():
        print(f"Arquivo da CETESB não encontrado: {args.cetesb}", file=sys.stderr)
        return 1
    try:
        report = run(db_path, args.cetesb, Path(args.out_dir), args.start, args.end,
                     args.devices.split(",") if args.devices else None, args.hour_label,
                     args.humidity_limit, args.min_samples)
    except ValueError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2

    info = report["cetesb"]
    print(f"CETESB: {info.get('estacao')} ({info['horas_no_arquivo']} h no arquivo, rótulo = {info['rotulo_hora']})")
    for device, node in report["nos"].items():
        t = node["total"]
        if not t["n"]:
            print(f"{device}: nenhuma hora pareada no período")
            continue
        r = f", r = {t['pearson_r']:.2f}" if "pearson_r" in t else ""
        print(f"{device}: {t['n']} h pareadas, viés {t['vies']:+.1f} µg/m³, RMSE {t['rmse']:.1f}{r}")
    print(f"Saídas em {Path(args.out_dir).resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
