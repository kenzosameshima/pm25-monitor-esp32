"""Comparação das médias horárias de PM2,5 de cada nó com as de uma estação da CETESB (referência).

Lê o banco em modo somente leitura e o CSV exportado do QUALAR (MP2.5, média horária). Não grava no
banco. Gera, em --out-dir:

- comparacao_cetesb.json: por nó, número de horas pareadas, viés, MAE, RMSE, correlação de Pearson e
  reta de regressão (nó em função da CETESB), no total e separando as horas com umidade relativa média
  acima de --humidity-limit (>) e até esse limite (<=);
- comparacao_cetesb_pares.csv: uma linha por hora pareada (hora de início em UTC, nó, PM2,5 do nó,
  PM2,5 da CETESB, umidade do nó), base do gráfico de dispersão.

Definições:

- Hora do nó: média horária válida, pela mesma função e regra (MIN_SAMPLES) da avaliação dos modelos.
- Hora da CETESB: o rótulo do CSV é o fim da hora (01:00 = 00:00 a 01:00; 24:00 = 23:00 a 24:00), no
  horário de Brasília (UTC-3, sem horário de verão, como em period_metrics.py). `--hour-label start`
  trata o rótulo como início. Fontes da convenção: a documentação do pacote qualR (rOpenSci, v0.9.7,
  docs.ropensci.org/qualR), que descreve a média horária do QUALAR como a média até a hora do rótulo
  e a meia-noite como 24:00, e o próprio arquivo exportado, que vai de 01:00 a 24:00 sem 00:00. Os
  arquivos LEIA-ME oficiais do QUALAR não puderam ser consultados (acesso bloqueado), então a
  convenção ainda é uma suposição a confirmar com a CETESB; se estiver errada, todo o pareamento fica
  deslocado em 1 h.
- Par: hora com valor válido nos dois. Valores vazios da CETESB e horas inválidas do nó ficam de fora.
- Viés: média de (nó - CETESB); positivo significa que o nó lê mais alto que a referência.
- Correlação e regressão: só com pelo menos MIN_PAIRS pares e as duas séries variando.
- Horas sem umidade no nó entram no total, mas em nenhuma das faixas (contadas em "sem_umidade").
- Os valores da CETESB são inteiros, o que limita a resolução da comparação.

Uso: python -m scripts.compare_cetesb --cetesb cetesb_pm25.csv [--db CAMINHO] [--out-dir resultados]
                                      [--start AAAA-MM-DD] [--end AAAA-MM-DD] [--devices no-01]
                                      [--hour-label end|start]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from app import db
from app.config import get_settings
from scripts.period_metrics import BRT, TEST_DEVICE_PREFIX, period_bounds
from scripts.train_forecast import MIN_SAMPLES, hourly_series

HUMIDITY_LIMIT = 75.0  # % de umidade relativa; acima disso o PMS5003 tende a superestimar
MIN_PAIRS = 24         # abaixo disso a correlação e a regressão não são reportadas como confiáveis
PAIR_COLUMNS = ["hora_utc", "device_id", "pm25_no", "pm25_cetesb", "umidade"]
_DATE = re.compile(r"\d{2}/\d{2}/\d{4}$")
# Rótulos do cabeçalho do QUALAR (sem acento e em minúsculas) e a chave usada no relatório.
_HEADER_KEYS = {"nome da estacao": "estacao", "codigo da estacao": "codigo_estacao"}


# ---------------------------------------------------------------- leitura do CSV da CETESB

def _plain(text: str) -> str:
    """Minúsculas e sem acentos, para reconhecer os rótulos do cabeçalho em qualquer codificação."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().strip().lower()


def _hour_start(day: str, hour: str, hour_label: str) -> datetime:
    """Início da hora em UTC a partir da data DD/MM/AAAA e do rótulo HH:00 em horário de Brasília."""
    hh, _, mm = hour.partition(":")
    if mm != "00" or not hh.isdigit() or int(hh) > 24:
        raise ValueError(f"hora inválida: {hour!r} (esperado HH:00, de 00:00 a 24:00)")
    d, m, y = (int(x) for x in day.split("/"))
    try:
        label = datetime(y, m, d, tzinfo=BRT) + timedelta(hours=int(hh))  # 24:00 -> 00:00 do dia seguinte
    except ValueError:
        raise ValueError(f"data inválida: {day!r}") from None
    start = label - timedelta(hours=1) if hour_label == "end" else label
    return start.astimezone(timezone.utc)


def _value(text: str) -> float:
    """Valor do CSV com vírgula ou ponto decimal; vazio vira NaN."""
    if not text:
        return np.nan
    try:
        return float(text.replace(",", "."))
    except ValueError:
        raise ValueError(f"valor não numérico: {text!r}") from None


def read_cetesb(path: str, hour_label: str = "end") -> tuple[pd.Series, dict]:
    """Série horária da CETESB indexada pela hora de início em UTC, com a estação e o rótulo lido.

    Aceita UTF-8 (com ou sem BOM) ou Latin-1 (padrão do QUALAR), separador ';' e vírgula decimal.
    Linhas que começam com data precisam ter exatamente Data;Hora;valor; as demais são cabeçalho.
    """
    if hour_label not in ("end", "start"):
        raise ValueError("hour_label deve ser 'end' ou 'start'")
    raw = Path(path).read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")  # exportação do QUALAR
    meta: dict = dict.fromkeys(_HEADER_KEYS.values())
    values: dict = {}
    for number, line in enumerate(text.splitlines(), 1):
        fields = [f.strip() for f in line.split(";")]
        if _DATE.match(fields[0]):
            while len(fields) > 3 and not fields[-1]:
                fields.pop()  # ';' sobrando no fim da linha
            if len(fields) != 3:
                raise ValueError(f"linha {number}: esperado Data;Hora;valor (uma só coluna de valores), veio {line!r}")
            try:
                start = _hour_start(fields[0], fields[1], hour_label)
                value = _value(fields[2])
            except ValueError as exc:
                raise ValueError(f"linha {number}: {exc}") from None
            if start in values:
                raise ValueError(f"linha {number}: hora repetida no arquivo ({fields[0]} {fields[1]})")
            values[start] = value
        elif len(fields) >= 2 and fields[0].endswith(":"):
            key = _HEADER_KEYS.get(_plain(fields[0][:-1]))
            if key:
                meta[key] = fields[1]
    if not values:
        raise ValueError("nenhuma linha de dados no formato DD/MM/AAAA;HH:00;valor")
    series = pd.Series(values).sort_index()
    series.index = pd.DatetimeIndex(series.index, tz="UTC")
    info = {**meta, "arquivo": Path(path).name,
            "rotulo_hora": "fim da hora" if hour_label == "end" else "início da hora",
            "horas_no_arquivo": int(len(series)), "horas_vazias": int(series.isna().sum())}
    return series, info


# ---------------------------------------------------------------- estatística

def agreement(node: pd.Series, ref: pd.Series) -> dict:
    """Viés, erros e relação linear (nó em função da CETESB) entre duas séries já pareadas."""
    n = int(len(node))
    out: dict = {"n": n}
    if n == 0:
        return out
    diff = node - ref
    out |= {"media_no": round(float(node.mean()), 2), "media_cetesb": round(float(ref.mean()), 2),
            "vies": round(float(diff.mean()), 2), "mae": round(float(diff.abs().mean()), 2),
            "rmse": round(float(np.sqrt((diff ** 2).mean())), 2)}
    if n < MIN_PAIRS:
        out["aviso"] = f"menos de {MIN_PAIRS} pares: correlação e regressão não calculadas"
    elif ref.nunique() < 2 or node.nunique() < 2:
        # nunique, e não std > 0: valores iguais podem dar desvio de 1e-15 por arredondamento
        out["aviso"] = "série constante: correlação e regressão indefinidas"
    else:
        slope, intercept = np.polyfit(ref.to_numpy(float), node.to_numpy(float), 1)
        r = float(np.corrcoef(ref.to_numpy(float), node.to_numpy(float))[0, 1])
        out |= {"pearson_r": round(r, 3), "r2": round(r * r, 3),
                "inclinacao": round(float(slope), 3), "intercepto": round(float(intercept), 2)}
    return out


def by_humidity(pairs: pd.DataFrame, limit: float) -> dict:
    """Concordância no total e por faixa de umidade; cada hora pareada cai em uma só faixa ou em sem_umidade."""
    groups = {"umidade_alta": pairs["umidade"] > limit, "umidade_baixa": pairs["umidade"] <= limit}
    out = {"total": agreement(pairs["pm25_no"], pairs["pm25_cetesb"])}
    for name, mask in groups.items():
        out[name] = agreement(pairs.loc[mask, "pm25_no"], pairs.loc[mask, "pm25_cetesb"])
    out["sem_umidade"] = int(pairs["umidade"].isna().sum())
    return out


# ---------------------------------------------------------------- pareamento e execução

def paired(conn, device: str, ref: pd.Series, start: datetime, end: datetime, min_samples: int) -> pd.DataFrame:
    """Horas do período com média válida no nó e valor na CETESB, nas colunas de PAIR_COLUMNS."""
    hourly = hourly_series(conn, device, min_samples)
    if hourly.empty:
        return pd.DataFrame(columns=PAIR_COLUMNS)
    hourly = hourly[(hourly.index >= start) & (hourly.index < end)]
    df = pd.DataFrame({"pm25_no": hourly["pm25"], "umidade": hourly["humidity"]}).join(
        ref.rename("pm25_cetesb"), how="inner")
    df = df.dropna(subset=["pm25_no", "pm25_cetesb"])
    df.index.name = "hora_utc"
    return df.reset_index().assign(device_id=device)[PAIR_COLUMNS]


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
            report["nos"][device] = by_humidity(df, humidity_limit)
    finally:
        conn.close()

    out_dir.mkdir(parents=True, exist_ok=True)
    # allow_nan=False: o JSON sai válido ou o script falha, nunca com NaN/Infinity no arquivo
    (out_dir / "comparacao_cetesb.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    frames = [f for f in frames if len(f)]
    pairs = pd.concat(frames) if frames else pd.DataFrame(columns=PAIR_COLUMNS)
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
    print(f"CETESB: {info['estacao']} ({info['horas_no_arquivo']} h no arquivo, rótulo = {info['rotulo_hora']})")
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
