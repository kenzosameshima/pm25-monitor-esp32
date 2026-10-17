"""Treina um modelo de previsão para produção e o grava na pasta de modelos do job horário.

Uso: python -m scripts.fit_forecast --model ridge --version v0 [--db CAMINHO] [--models-dir PASTA]

Treina com todas as horas completas do banco (sem os nós de teste) e com os hiperparâmetros fixos de
app.forecasting.DEFAULTS, e grava <modelo>-<versão>.joblib em PM25_MODELS_DIR (padrão data/models).
O job horário (scripts.forecast_job) usa todos os modelos da pasta; para aposentar um, tire o arquivo
de lá. Uma versão nunca é sobrescrita: um modelo novo, ou o mesmo modelo treinado com mais dados, ganha
outra versão, para que cada linha de `forecasts` aponte para um único modelo.

A escolha do modelo vem da avaliação offline (scripts.train_forecast). Só lê o banco.
Requer as dependências de requirements-ml.txt.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from app import db, forecasting
from app.config import get_settings


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--model", required=True, choices=list(forecasting.DEFAULTS))
    p.add_argument("--version", required=True, help="ex.: v0; vira model_version em forecasts")
    p.add_argument("--db", default=None, help="caminho do SQLite (padrão: PM25_DB_PATH)")
    p.add_argument("--models-dir", default=None, help="pasta dos modelos (padrão: PM25_MODELS_DIR)")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    settings = get_settings()
    path = args.db or settings.db_path
    models_dir = args.models_dir or settings.models_dir
    try:
        target = Path(models_dir) / forecasting.file_name(args.model, args.version)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    if target.exists():  # antes de treinar, que pode demorar
        print(f"{target} já existe; use outra versão.", file=sys.stderr)
        return 1
    if not os.path.exists(path):
        print(f"Banco não encontrado: {path}", file=sys.stderr)
        return 1

    conn = db.connect(path, readonly=True)
    try:
        frame = forecasting.dataset(conn)
    finally:
        conn.close()
    if len(frame) < forecasting.MIN_TRAIN_ROWS:
        print(f"Dados insuficientes: {len(frame)} horas completas (mínimo {forecasting.MIN_TRAIN_ROWS}).",
              file=sys.stderr)
        return 1

    model = forecasting.fit(args.model, frame)
    saved = forecasting.save(model, args.version, models_dir)
    t = model.trained_on
    print(f"{args.model} {args.version}: {t['rows']} horas de {', '.join(t['devices'])}, "
          f"de {t['first_hour']} a {t['last_hour']} (hora t, UTC); scikit-learn {model.sklearn}.")
    print(f"Gravado em {saved}. O job horário passa a usá-lo na próxima execução.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
