"""Job horário de previsão: grava em `forecasts` a previsão de cada modelo para a hora em andamento.

Uso: python -m scripts.forecast_job [--db CAMINHO] [--models-dir PASTA]
     python -m scripts.forecast_job --backfill-hours 24
     python -m scripts.forecast_job --replay-from AAAA-MM-DDTHH:00:00Z --replay-to AAAA-MM-DDTHH:00:00Z
Agendado para alguns minutos depois da hora cheia (HH:05), para as últimas leituras da hora chegarem.

Para cada nó (sem os de teste) e cada modelo de PM25_MODELS_DIR (padrão data/models, arquivos gerados
por scripts.fit_forecast), usa as médias até a última hora completa t e prevê a média de PM2,5 de t+1,
a hora em andamento. A previsão é gravada antes de a hora-alvo terminar, então sempre antecede o valor
observado (validação prospectiva); uma hora perdida, com o servidor desligado, não é preenchida pelo job.
Nó cuja hora t ou algum atraso não tem média válida fica sem previsão nessa hora.

Recálculo retroativo (--replay-from e --replay-to, horas-alvo inclusive): para as horas-alvo que ficaram sem
previsão, por exemplo porque o nó guardou as leituras numa queda de conexão e as enviou depois, refaz a
previsão com o mesmo cálculo do job, usando só as leituras com horário de sensor anterior à hora-alvo.
Como não foi gravada antes do fato, vai para a versão "<versão>-retro" (por exemplo `ridge v0-retro`),
uma série à parte nas comparações, e `generated_at` guarda o momento real do recálculo. Hora que já tem a
previsão em tempo real do mesmo modelo não é recalculada.
Com --backfill-hours N, cada execução normal também recalcula, do mesmo jeito, as horas-alvo já encerradas das
últimas N horas que ainda não têm previsão (nem em tempo real nem retroativa), então uma queda do nó ou do túnel
é coberta sozinha na execução seguinte à volta dos dados. Hora sem dados suficientes é tentada de novo a cada
execução, até sair da janela. Rodar de novo na mesma
hora não duplica nada: a tabela tem UNIQUE por nó, hora-alvo, modelo e versão.

É o único processo além da API que grava no banco: uma transação curta por execução, só na tabela
`forecasts`. O modo WAL serializa as gravações, e a conexão espera até 10 s por uma trava.
Requer as dependências de requirements-ml.txt.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

from app import analytics, db, forecasting
from app.config import get_settings


def forecasts_for(conn, models: list[forecasting.Forecaster], now: datetime) -> tuple[list[dict], list[str]]:
    """Linhas para `forecasts` (uma por nó e modelo) e os nós sem dados suficientes. Não grava nada."""
    rows, skipped = [], []
    for device in analytics.production_devices(conn):
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


RETRO_SUFFIX = "-retro"
MAX_REPLAY_HOURS = 7 * 24


def replay_rows(conn, models: list[forecasting.Forecaster], targets: list[datetime],
                generated_at: datetime) -> tuple[list[dict], list[str]]:
    """Previsões retroativas das horas-alvo `targets`, na versão "<versão>-retro". Não grava nada.

    Cada hora é calculada como o job a calcularia às HH:05, só com as leituras de sensor anteriores à hora-alvo.
    Pula as horas que já têm a previsão em tempo real do modelo; as sem dados suficientes voltam em `skipped`."""
    rows, skipped = [], []
    for device in analytics.production_devices(conn):
        for target in targets:
            real = {(m, v) for m, v in conn.execute(
                "SELECT model_name, model_version FROM forecasts WHERE device_id = ? AND target_hour = ?",
                (device, db.iso(target)))}
            wanted = [m for m in models
                      if (m.kind, m.version) not in real and (m.kind, m.version + RETRO_SUFFIX) not in real]
            if not wanted:
                continue
            row = forecasting.latest_row(conn, device, target + pd.Timedelta(minutes=5))
            if row.empty:
                skipped.append(f"{device} {db.iso(target)}")
                continue
            for model in wanted:
                rows.append({"device_id": device, "generated_at": generated_at, "target_hour": target,
                             "predicted_pm25": float(model.predict(row)[0]),
                             "model_name": model.kind, "model_version": model.version + RETRO_SUFFIX})
    return rows, skipped


def _hour(value: str) -> datetime:
    try:
        parsed = db.parse_iso(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"use AAAA-MM-DDTHH:00:00Z, recebi {value!r}")
    if parsed.minute or parsed.second:
        raise argparse.ArgumentTypeError(f"a hora-alvo precisa ser cheia, recebi {value!r}")
    return parsed


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--db", default=None, help="caminho do SQLite (padrão: PM25_DB_PATH)")
    p.add_argument("--models-dir", default=None, help="pasta dos modelos (padrão: PM25_MODELS_DIR)")
    p.add_argument("--backfill-hours", type=int, default=0, metavar="N",
                   help="também recalcula as horas encerradas das últimas N horas que ficaram sem previsão (0 desliga)")
    p.add_argument("--replay-from", type=_hour, default=None, help="primeira hora-alvo a recalcular (UTC, hora cheia)")
    p.add_argument("--replay-to", type=_hour, default=None, help="última hora-alvo a recalcular (inclusive)")
    args = p.parse_args(argv)
    if (args.replay_from is None) != (args.replay_to is None):
        p.error("--replay-from e --replay-to andam juntos")
    if not 0 <= args.backfill_hours <= MAX_REPLAY_HOURS:
        p.error(f"--backfill-hours precisa estar entre 0 e {MAX_REPLAY_HOURS}")
    if args.backfill_hours and args.replay_from is not None:
        p.error("--backfill-hours não se combina com --replay-from e --replay-to")
    if args.replay_from is not None:
        span = (args.replay_to - args.replay_from) / timedelta(hours=1)
        if not 0 <= span < MAX_REPLAY_HOURS:
            p.error(f"o intervalo precisa ter de 1 a {MAX_REPLAY_HOURS} horas, com --replay-from <= --replay-to")
    return args


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
        if args.replay_from is not None:
            hours = int((args.replay_to - args.replay_from) / timedelta(hours=1)) + 1
            targets = [args.replay_from + timedelta(hours=i) for i in range(hours)]
            rows, skipped = replay_rows(conn, models, targets, now)
        else:
            rows, skipped = forecasts_for(conn, models, now)
            if args.backfill_hours:
                current = now.replace(minute=0, second=0, microsecond=0)   # hora em andamento: já coberta acima
                targets = [current - timedelta(hours=h) for h in range(args.backfill_hours, 0, -1)]
                retro, _ = replay_rows(conn, models, targets, now)
                rows += retro
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
