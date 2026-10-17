"""Job horário de previsão: grava em `forecasts` a previsão de cada modelo para a hora em andamento.

Uso: python -m scripts.forecast_job [--db CAMINHO] [--models-dir PASTA]
Agendado para alguns minutos depois da hora cheia (HH:05), para as últimas leituras da hora chegarem.

Para cada nó (sem os de teste) e cada modelo de PM25_MODELS_DIR (padrão data/models, arquivos gerados
por scripts.fit_forecast), usa as médias até a última hora completa t e prevê a média de PM2,5 de t+1,
a hora em andamento. A previsão é gravada antes de a hora-alvo terminar, então sempre antecede o valor
observado (validação prospectiva); uma hora perdida, com o servidor desligado, não é preenchida depois.
Nó cuja hora t ou algum atraso não tem média válida fica sem previsão nessa hora. Rodar de novo na mesma
hora não duplica nada: a tabela tem UNIQUE por nó, hora-alvo, modelo e versão.

É o único processo além da API que grava no banco: uma transação curta por execução, só na tabela
`forecasts`. O modo WAL serializa as gravações, e a conexão espera até 10 s por uma trava.
Requer as dependências de requirements-ml.txt.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

import pandas as pd

from app import db, forecasting
from app.config import get_settings


def forecasts_for(conn, models: list[forecasting.Forecaster], now: datetime) -> tuple[list[dict], list[str]]:
    """Linhas para `forecasts` (uma por nó e modelo) e os nós sem dados suficientes. Não grava nada."""
    rows, skipped = [], []
    for device in forecasting.devices(conn):
        row = forecasting.latest_row(conn, device, now)
        if row.empty:
            skipped.append(device)
            continue
        target = (row.index[0] + pd.Timedelta(hours=1)).to_pydatetime()
        for model in models:
            rows.append({"device_id": device, "generated_at": now, "target_hour": target,
                         "predicted_pm25": float(model.predict(row)[0]),
                         "model_name": model.kind, "model_version": model.version})
    return rows, skipped


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--db", default=None, help="caminho do SQLite (padrão: PM25_DB_PATH)")
    p.add_argument("--models-dir", default=None, help="pasta dos modelos (padrão: PM25_MODELS_DIR)")
    return p.parse_args(argv)


def main(argv=None, now: datetime | None = None) -> int:
    """Retorna 1 se nenhum modelo carregar ou se algum arquivo de modelo falhar (os outros rodam)."""
    args = parse_args(argv)
    settings = get_settings()
    path = args.db or settings.db_path
    models_dir = args.models_dir or settings.models_dir
    now = now or datetime.now(timezone.utc)
    stamp = db.iso(now)

    models, errors = forecasting.load_all(models_dir)
    for error in errors:
        print(f"{stamp} modelo ignorado: {error}", file=sys.stderr)
    if not models:
        print(f"{stamp} nenhum modelo em {models_dir}: treine um com scripts.fit_forecast.", file=sys.stderr)
        return 1
    if not os.path.exists(path):  # db.connect criaria um banco vazio
        print(f"{stamp} banco não encontrado: {path}", file=sys.stderr)
        return 1

    conn = db.connect(path)
    try:
        rows, skipped = forecasts_for(conn, models, now)
        inserted = db.insert_forecasts(conn, rows)
    finally:
        conn.close()

    for r in rows:
        print(f"{stamp} {r['device_id']} {r['model_name']} {r['model_version']}: "
              f"hora {db.iso(r['target_hour'])} -> {r['predicted_pm25']:.1f} µg/m³")
    print(f"{stamp} {inserted} previsões gravadas, {len(rows) - inserted} já existiam; "
          f"sem dados suficientes: {', '.join(skipped) or 'nenhum nó'}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
