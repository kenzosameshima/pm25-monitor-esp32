"""Métricas consolidadas do período de coleta: base da Tabela 21 e do Gráfico 1 (QP1, desempenho
operacional) e da Tabela 22 e do Gráfico 2 (estatísticas descritivas de PM2,5).

Lê o banco em modo somente leitura. Gera, por nó, em --out-dir:

- periodo.json: métricas operacionais, classificação das lacunas, estatísticas de PM2,5 e
  frequência de excedência de diretrizes e padrões;
- completude_diaria.csv (Gráfico 1), perfil_hora.csv e perfil_dia_semana.csv (Gráfico 2).

Definições (todas conferíveis a mão a partir do banco):

- Período: dias de calendário do horário de Brasília (UTC-3, sem horário de verão desde 2019), de
  --start 00:00 até o fim de --end. Esperado: 1 440 leituras por dia, uma por minuto.
- Completude: minutos do período com pelo menos uma leitura recebida ÷ minutos esperados.
- Lacuna: sequência de minutos sem leitura. As bordas (do início do período até a primeira leitura
  e da última leitura até o fim) entram na completude e na maior lacuna, mas ficam fora da
  classificação por origem, que só vale entre duas leituras consecutivas.
- Origem da lacuna entre duas leituras consecutivas: reinício (o boot_id mudou); comunicação (mesmo
  boot_id e salto de seq: as mensagens perdidas, limitadas aos minutos que faltam); aquisição (os
  minutos que sobram, ou seja, intervalo sem leituras e sem salto de seq: o sensor não entregou
  dados válidos). Minutos faltantes = comunicação + aquisição + reinício + bordas.
- Mensagens perdidas: soma dos saltos de seq entre leituras consecutivas do mesmo boot_id.
- Reinícios: trocas de boot_id entre leituras consecutivas.
- Duplicatas descartadas: soma de n_duplicates dos lotes de ingest_batches recebidos no período.
- PM2,5: médias horárias válidas (hora com pelo menos MIN_SAMPLES leituras com quality "ok"), pela
  mesma função e constante usadas na avaliação dos modelos de previsão.

Uso: python -m scripts.period_metrics --start 2026-10-01 --end 2026-11-15 [--out-dir resultados] [--freeze]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
import sys
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from app import db
from app.config import get_settings
from scripts.train_forecast import MIN_SAMPLES, hourly_series

BRT = timezone(timedelta(hours=-3))
MINUTES_PER_DAY = 1440
HOURS_PER_DAY = 24
# Uma média de 24 h só conta com a mesma cobertura mínima de 75% usada para a média horária.
MIN_VALID_HOURS_PER_DAY = math.ceil(HOURS_PER_DAY * MIN_SAMPLES / 60)  # 18 horas
WEEKDAYS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
TEST_DEVICE_PREFIX = "teste"  # ex.: teste-https, criado por scripts/check_https.py

# ---- Diretrizes e padrões de PM2,5, µg/m³, média de 24 h. Valores conferidos nos textos oficiais. ----
# OMS (2021): "WHO global air quality guidelines", Tabela 0.1. Nível-guia (AQG) e metas intermediárias (IT);
# o valor de 24 h é o percentil 99 anual (3 a 4 dias de excedência por ano). A OMS não fixa limite horário
# de PM2,5.
WHO_2021_AQG_24H = 15.0
WHO_2021_IT4_24H = 25.0
WHO_2021_IT3_24H = 37.5
WHO_2021_IT2_24H = 50.0
WHO_2021_IT1_24H = 75.0
# Brasil: Resolução CONAMA nº 506, de 5/7/2024 (DOU), Anexo I, MP2,5, 24 horas. Vigência (art. 4º):
# PI-1 até 2024-12-31; PI-2 desde 2025-01-01; PI-3 desde 2033-01-01; PI-4 desde 2044-01-01; PF (igual ao
# nível-guia da OMS 2021) em data a definir. Para dados de 2026, o padrão em vigor é o PI-2.
CONAMA_506_PI1_24H = 60.0
CONAMA_506_PI2_24H = 50.0
CONAMA_506_PI3_24H = 37.0
CONAMA_506_PI4_24H = 25.0
CONAMA_506_PF_24H = 15.0

THRESHOLDS = {
    "OMS 2021 nível-guia (15)": WHO_2021_AQG_24H,
    "OMS 2021 meta intermediária 4 (25)": WHO_2021_IT4_24H,
    "OMS 2021 meta intermediária 3 (37,5)": WHO_2021_IT3_24H,
    "OMS 2021 meta intermediária 2 (50)": WHO_2021_IT2_24H,
    "OMS 2021 meta intermediária 1 (75)": WHO_2021_IT1_24H,
    "CONAMA 506/2024 PI-1 (60)": CONAMA_506_PI1_24H,
    "CONAMA 506/2024 PI-2 (50, em vigor desde 2025)": CONAMA_506_PI2_24H,
    "CONAMA 506/2024 PI-3 (37)": CONAMA_506_PI3_24H,
    "CONAMA 506/2024 PI-4 (25)": CONAMA_506_PI4_24H,
    "CONAMA 506/2024 PF (15)": CONAMA_506_PF_24H,
}


# ---------------------------------------------------------------- período

def period_bounds(start: date, end: date) -> tuple[datetime, datetime, int]:
    """Início e fim (exclusivo) do período em UTC e número de dias."""
    if end < start:
        raise ValueError("--end anterior a --start")
    start_utc = datetime(start.year, start.month, start.day, tzinfo=BRT).astimezone(timezone.utc)
    days = (end - start).days + 1
    return start_utc, start_utc + timedelta(days=days), days


def _minute(ts: datetime) -> int:
    return int(ts.timestamp() // 60)


# ---------------------------------------------------------------- métricas operacionais

def operational_metrics(conn, device: str, start: datetime, end: datetime, days: int):
    """Métricas operacionais e completude diária de um nó. Retorna (dict, linhas diárias)."""
    rows = db.fetch_measurements(conn, start, end, [device])
    start_min, end_min = _minute(start), _minute(end)
    expected = days * MINUTES_PER_DAY

    readings = [(_minute(db.parse_iso(r["ts_sensor"])), r["boot_id"], r["seq"]) for r in rows]
    readings.sort()
    minutes = {m for m, _, _ in readings}

    gaps = {"comunicacao": 0, "aquisicao": 0, "reinicio": 0}
    lost = restarts = 0
    largest = 0
    if readings:
        lead = readings[0][0] - start_min
        trail = end_min - readings[-1][0] - 1
        largest = max(lead, trail)
        for (m_a, boot_a, seq_a), (m_b, boot_b, seq_b) in zip(readings, readings[1:]):
            missing = max(0, m_b - m_a - 1)
            largest = max(largest, missing)
            if boot_a != boot_b:
                restarts += 1
                gaps["reinicio"] += missing
            else:
                seq_skipped = max(0, seq_b - seq_a - 1)
                lost += seq_skipped
                comm = min(seq_skipped, missing)
                gaps["comunicacao"] += comm
                gaps["aquisicao"] += missing - comm
        edges = lead + trail
    else:
        largest = edges = expected

    batches = conn.execute(
        "SELECT COALESCE(SUM(n_duplicates), 0) FROM ingest_batches WHERE device_id = ? AND received_at >= ? AND received_at < ?",
        (device, db.iso(start), db.iso(end)),
    ).fetchone()[0]
    rssi = [r["rssi"] for r in rows if r["rssi"] is not None]

    per_day = Counter((m - start_min) // MINUTES_PER_DAY for m in minutes)
    daily = []
    for d in range(days):
        got = per_day[d]
        day = (start.astimezone(BRT) + timedelta(days=d)).date()
        daily.append({"device_id": device, "data": day.isoformat(), "leituras": got,
                      "esperadas": MINUTES_PER_DAY, "completude": round(got / MINUTES_PER_DAY, 4)})

    metrics = {
        "periodo_dias": days,
        "leituras_esperadas": expected,
        "minutos_com_leitura": len(minutes),
        "completude": round(len(minutes) / expected, 4),
        "maior_lacuna_min": largest,
        "mensagens_perdidas": lost,
        "reinicios": restarts,
        "duplicatas_descartadas": int(batches),
        "rssi_medio_dbm": round(sum(rssi) / len(rssi), 2) if rssi else None,
        "lacunas_min": {**gaps, "bordas": edges, "total": sum(gaps.values()) + edges},
    }
    return metrics, daily


# ---------------------------------------------------------------- PM2,5

def _exceedance(values: pd.Series, limit: float) -> dict:
    above = int((values > limit).sum())
    return {"acima": above, "total": int(len(values)),
            "fracao": round(above / len(values), 4) if len(values) else None}


def pm25_metrics(conn, device: str, start: datetime, end: datetime):
    """Estatísticas das médias horárias válidas, perfis e excedências. Retorna (dict, perfil_hora, perfil_dia)."""
    hourly = hourly_series(conn, device)
    if len(hourly):
        hourly = hourly[(hourly.index >= start) & (hourly.index < end)]
    valid = hourly["pm25"].dropna() if len(hourly) else pd.Series(dtype=float)
    expected_hours = int((end - start).total_seconds() // 3600)

    stats = {"horas_validas": int(len(valid)), "horas_esperadas": expected_hours}
    if len(valid):
        stats.update({
            "media": round(float(valid.mean()), 4),
            "mediana": round(float(valid.median()), 4),
            "p5": round(float(np.percentile(valid, 5)), 4),
            "p95": round(float(np.percentile(valid, 95)), 4),
            "maximo_horario": round(float(valid.max()), 4),
            # desvio-padrão amostral (n-1)
            "desvio_padrao": round(float(valid.std(ddof=1)), 4) if len(valid) > 1 else None,
        })

    local = valid.index.tz_convert(BRT) if len(valid) else valid.index
    by_hour = valid.groupby(local.hour).agg(["count", "mean"]) if len(valid) else pd.DataFrame(columns=["count", "mean"])
    by_day = valid.groupby(local.dayofweek).agg(["count", "mean"]) if len(valid) else pd.DataFrame(columns=["count", "mean"])
    profile_hour = [{"device_id": device, "hora": int(h), "n": int(r["count"]), "media": round(float(r["mean"]), 4)}
                    for h, r in by_hour.iterrows()]
    profile_day = [{"device_id": device, "dia_semana": WEEKDAYS[int(d)], "n": int(r["count"]),
                    "media": round(float(r["mean"]), 4)} for d, r in by_day.iterrows()]

    # Médias de 24 h: dias de calendário de Brasília com pelo menos MIN_VALID_HOURS_PER_DAY horas válidas.
    daily_means = pd.Series(dtype=float)
    if len(valid):
        per_day = valid.groupby(local.date)
        daily_means = per_day.mean()[per_day.count() >= MIN_VALID_HOURS_PER_DAY]
    references = {
        name: {"limite_ug_m3": limit,
               "horas": _exceedance(valid, limit),
               "medias_24h": _exceedance(daily_means, limit)}
        for name, limit in THRESHOLDS.items()
    }
    stats["dias_validos_24h"] = int(len(daily_means))
    stats["referencias"] = references
    return stats, profile_hour, profile_day


# ---------------------------------------------------------------- conjunto congelado

def freeze_database(source_path: str, out_dir: Path, start: date, end: date) -> tuple[Path, dict]:
    """Copia o banco pela API de backup do SQLite (íntegra mesmo com a API gravando) e calcula o hash."""
    final = out_dir / f"pm25-congelado-{start.isoformat()}_{end.isoformat()}.db"
    partial = final.with_name(final.name + ".part")
    partial.unlink(missing_ok=True)
    src = db.connect(source_path, readonly=True)
    dst = sqlite3.connect(partial)
    try:
        src.backup(dst)
        # Arquivo único e estável: sem -wal/-shm, para que o hash identifique o conjunto de dados.
        dst.execute("PRAGMA journal_mode=DELETE")
        check = dst.execute("PRAGMA integrity_check").fetchone()[0]
        rows = dst.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]
    finally:
        dst.close()
        src.close()
    if check != "ok":
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"Cópia descartada: integrity_check retornou {check!r}")
    partial.replace(final)
    digest = hashlib.sha256(final.read_bytes()).hexdigest()
    return final, {
        "arquivo": final.name,
        "sha256": digest,
        "medicoes": rows,
        "intervalo": {"inicio": start.isoformat(), "fim": end.isoformat()},
        "extraido_em": db.iso(datetime.now(timezone.utc)),
    }


# ---------------------------------------------------------------- execução

def _write_csv(path: Path, rows: list[dict], columns: list[str]) -> None:
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False)


def run(db_path: str, start: date, end: date, out_dir: Path, devices: list[str] | None, freeze: bool) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    start_utc, end_utc, days = period_bounds(start, end)
    report: dict = {
        "periodo": {"inicio": start.isoformat(), "fim": end.isoformat(), "dias": days,
                    "fuso": "America/Sao_Paulo (UTC-3)", "inicio_utc": db.iso(start_utc), "fim_utc_exclusivo": db.iso(end_utc)},
        "regras": {"min_leituras_por_hora": MIN_SAMPLES, "min_horas_validas_por_dia": MIN_VALID_HOURS_PER_DAY},
    }
    if freeze:
        frozen, info = freeze_database(db_path, out_dir, start, end)
        report["congelamento"] = info
        db_path = str(frozen)  # as métricas saem da cópia, então o hash identifica os dados usados
    report["banco"] = Path(db_path).name

    conn = db.connect(db_path, readonly=True)
    try:
        ids = devices if devices is not None else [
            r[0] for r in conn.execute("SELECT device_id FROM devices ORDER BY device_id")
            if not r[0].startswith(TEST_DEVICE_PREFIX)]
        nodes, daily_rows, hour_rows, weekday_rows = {}, [], [], []
        for device in ids:
            operational, daily = operational_metrics(conn, device, start_utc, end_utc, days)
            pm25, by_hour, by_day = pm25_metrics(conn, device, start_utc, end_utc)
            nodes[device] = {"operacional": operational, "pm25": pm25}
            daily_rows += daily
            hour_rows += by_hour
            weekday_rows += by_day
    finally:
        conn.close()

    report["nos"] = nodes
    report["limiares_ug_m3_24h"] = THRESHOLDS
    report["observacao_limiares"] = (
        "Os limites são de média de 24 h. A contagem em 'horas' aplica o mesmo valor às médias horárias, "
        "apenas como referência: não existe limite horário de PM2,5 na OMS nem no CONAMA.")
    (out_dir / "periodo.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_csv(out_dir / "completude_diaria.csv", daily_rows, ["device_id", "data", "leituras", "esperadas", "completude"])
    _write_csv(out_dir / "perfil_hora.csv", hour_rows, ["device_id", "hora", "n", "media"])
    _write_csv(out_dir / "perfil_dia_semana.csv", weekday_rows, ["device_id", "dia_semana", "n", "media"])
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", required=True, type=date.fromisoformat, help="primeiro dia (AAAA-MM-DD, horário de Brasília)")
    ap.add_argument("--end", required=True, type=date.fromisoformat, help="último dia, inclusive (AAAA-MM-DD)")
    ap.add_argument("--db", default=None, help="banco de dados (padrão: PM25_DB_PATH)")
    ap.add_argument("--out-dir", default="resultados", help="pasta de saída (padrão: resultados)")
    ap.add_argument("--devices", default=None, help="nós separados por vírgula (padrão: todos, menos os de teste)")
    ap.add_argument("--freeze", action="store_true",
                    help="copia o banco para --out-dir, registra o hash e calcula as métricas sobre a cópia")
    args = ap.parse_args(argv)

    db_path = args.db or get_settings().db_path
    if not Path(db_path).exists():
        print(f"Banco não encontrado: {db_path}", file=sys.stderr)
        return 1
    try:
        report = run(db_path, args.start, args.end, Path(args.out_dir),
                     args.devices.split(",") if args.devices else None, args.freeze)
    except (ValueError, RuntimeError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2

    for device, node in report["nos"].items():
        op, pm = node["operacional"], node["pm25"]
        print(f"{device}: completude {op['completude']:.1%}, maior lacuna {op['maior_lacuna_min']} min, "
              f"{op['mensagens_perdidas']} perdidas, {op['reinicios']} reinícios, "
              f"{pm['horas_validas']}/{pm['horas_esperadas']} horas válidas")
    if "congelamento" in report:
        print(f"Banco congelado: {report['congelamento']['arquivo']} (sha256 {report['congelamento']['sha256']})")
    print(f"Saídas em {Path(args.out_dir).resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
