"""Avaliação offline de modelos de previsão da média horária de PM2,5 (horizonte de 1 hora).

Compara a persistência (último valor observado), uma regressão linear regularizada (Ridge) e um
perceptron multicamadas (MLP) em Keras. Um único modelo é treinado com as séries de todos os nós.
A avaliação tem duas partes, ambas cronológicas:

- validação progressiva (walk-forward): janela de treino que cresce a cada dobra, sempre avaliando
  o bloco seguinte;
- teste final: os últimos `--test-days` dias, nunca usados para treino ou ajuste.

O script só lê o banco (modo somente leitura), então pode rodar com a API gravando. Não grava na
tabela `forecasts`: ela é reservada às previsões prospectivas de um job horário.

Uso: python -m scripts.train_forecast [--db CAMINHO] [--out relatorio.json] [--no-mlp]
                                      [--predictions-csv previsao_teste.csv] [--seeds N]
Requer as dependências de requirements-ml.txt.

O relatório JSON registra as versões de Python, numpy, pandas, scikit-learn e TensorFlow e o hash
SHA-256 do arquivo de banco lido. Para o hash identificar o conjunto de dados, passe o banco
congelado por `scripts.period_metrics --freeze`, não o banco em uso (no modo WAL, parte dos dados
pode estar fora do arquivo principal).

--predictions-csv grava, para o teste final, uma linha por hora e nó com as colunas hora (hora-alvo
prevista, em UTC), no, observado, persistencia, ridge e mlp (sem a coluna mlp com --no-mlp).
--seeds N repete o treino da MLP com N sementes consecutivas a partir de --seed; a primeira (42, por
padrão) é a de referência e é a que aparece nos resultados e no CSV. Com N > 1 o relatório traz
também a média e o desvio-padrão amostral do RMSE e do índice de habilidade entre as sementes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
from datetime import datetime, timedelta, timezone
from importlib import metadata

import numpy as np
import pandas as pd

from app import db
from app.config import get_settings

LAGS = (1, 2, 3, 6, 12, 24)
FEATURES = ["pm25", *[f"lag_{k}" for k in LAGS], "humidity", "temperature", "hour_sin", "hour_cos"]
MIN_SAMPLES = 45        # minutos com leitura para uma hora entrar na série (75% de cobertura)
MIN_TRAIN_ROWS = 100    # abaixo disso o treino não é confiável
EPOCH = datetime(2000, 1, 1, tzinfo=timezone.utc)
PERSISTENCE = "Persistência"


def hourly_series(conn, device_id: str, min_samples: int = MIN_SAMPLES) -> pd.DataFrame:
    """Média horária de PM2,5, umidade e temperatura; horas com poucas leituras ficam como NaN."""
    rows = db.fetch_measurements(conn, EPOCH, datetime.now(timezone.utc) + timedelta(days=1), [device_id])
    df = pd.DataFrame([dict(r) for r in rows])
    if df.empty:
        return pd.DataFrame(columns=["pm25", "humidity", "temperature", "n"])
    df = df[df["quality"] == "ok"]
    if df.empty:
        return pd.DataFrame(columns=["pm25", "humidity", "temperature", "n"])
    df = df.assign(ts=pd.to_datetime(df["ts_sensor"], utc=True)).set_index("ts").sort_index()
    grouped = df.resample("1h")
    hourly = pd.DataFrame({
        "pm25": grouped["pm25"].mean(),
        "humidity": grouped["humidity"].mean(),
        "temperature": grouped["temperature"].mean(),
        "n": grouped["pm25"].count(),
    })
    hourly.loc[hourly["n"] < min_samples, ["pm25", "humidity", "temperature"]] = np.nan
    return hourly


def make_features(hourly: pd.DataFrame, device_id: str) -> pd.DataFrame:
    """Uma linha por hora t: variáveis conhecidas até t e alvo y = PM2,5 médio da hora t+1."""
    f = pd.DataFrame(index=hourly.index)
    f["pm25"] = hourly["pm25"]
    for k in LAGS:
        f[f"lag_{k}"] = hourly["pm25"].shift(k)
    f["humidity"] = hourly["humidity"]
    f["temperature"] = hourly["temperature"]
    hour = hourly.index.hour
    f["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    f["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    f["y"] = hourly["pm25"].shift(-1)
    f["device_id"] = device_id
    return f


def build_dataset(conn, device_ids: list[str], min_samples: int = MIN_SAMPLES) -> pd.DataFrame:
    """Linhas completas (sem lacunas nos atrasos nem no alvo) de todos os nós, em ordem cronológica."""
    frames = []
    for device in device_ids:
        hourly = hourly_series(conn, device, min_samples)
        if hourly.empty:
            continue
        f = make_features(hourly, device)
        core = ["pm25", *[f"lag_{k}" for k in LAGS], "y"]
        frames.append(f.dropna(subset=core))
    if not frames:
        return pd.DataFrame(columns=[*FEATURES, "y", "device_id"])
    return pd.concat(frames).sort_index(kind="stable")


def make_splits(index: pd.DatetimeIndex, test_days: int, min_train_days: int, fold_days: int):
    """Dobras de validação progressiva e janela de teste final, todas em ordem cronológica."""
    t0, t1 = index.min(), index.max() + pd.Timedelta(hours=1)
    test_start = t1 - pd.Timedelta(days=test_days)
    folds, cur = [], t0 + pd.Timedelta(days=min_train_days)
    step = pd.Timedelta(days=fold_days)
    while cur + step <= test_start:
        folds.append((cur, cur + step))
        cur += step
    return folds, (test_start, t1)


def train_test(frame: pd.DataFrame, start, end):
    """Treino: linhas cujo alvo (hora t+1) é anterior a `start`. Teste: linhas em [start, end)."""
    train = frame[frame.index < start - pd.Timedelta(hours=1)]
    test = frame[(frame.index >= start) & (frame.index < end)]
    return train, test


def _prepare(train: pd.DataFrame, test: pd.DataFrame):
    """Imputa umidade e temperatura com a mediana do treino; o alvo é a variação em relação à persistência."""
    med = train[["humidity", "temperature"]].median().fillna(0.0)
    xtr = train[FEATURES].fillna(med)
    xte = test[FEATURES].fillna(med)
    return xtr.to_numpy(float), xte.to_numpy(float), (train["y"] - train["pm25"]).to_numpy(float)


def predict_persistence(train, test, **_) -> np.ndarray:
    return test["pm25"].to_numpy(float)


def predict_ridge(train, test, alpha: float = 10.0, **_) -> np.ndarray:
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    xtr, xte, ytr = _prepare(train, test)
    model = make_pipeline(StandardScaler(), Ridge(alpha=alpha)).fit(xtr, ytr)
    return test["pm25"].to_numpy(float) + model.predict(xte)


def predict_mlp(train, test, seed: int = 42, hidden=(32, 16), lr: float = 1e-3, epochs: int = 200,
                batch_size: int = 32, patience: int = 15, val_fraction: float = 0.15, **_) -> np.ndarray:
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
    from sklearn.preprocessing import StandardScaler
    from tensorflow import keras

    keras.utils.set_random_seed(seed)
    xtr, xte, ytr = _prepare(train, test)
    scaler = StandardScaler().fit(xtr)
    xtr, xte = scaler.transform(xtr), scaler.transform(xte)
    n_val = max(1, int(len(xtr) * val_fraction))  # validação = bloco final do treino, em ordem cronológica
    model = keras.Sequential([keras.Input(shape=(xtr.shape[1],)),
                              *[keras.layers.Dense(h, activation="relu") for h in hidden],
                              keras.layers.Dense(1)])
    model.compile(optimizer=keras.optimizers.Adam(learning_rate=lr), loss="mse")
    stop = keras.callbacks.EarlyStopping(monitor="val_loss", patience=patience, restore_best_weights=True)
    model.fit(xtr[:-n_val], ytr[:-n_val], validation_data=(xtr[-n_val:], ytr[-n_val:]),
              epochs=epochs, batch_size=batch_size, callbacks=[stop], shuffle=True, verbose=0)
    return test["pm25"].to_numpy(float) + model.predict(xte, verbose=0).ravel()


def metrics(y: np.ndarray, pred: np.ndarray, pred_persistence: np.ndarray) -> dict:
    """MAE, RMSE e skill score (1 − RMSE do modelo ÷ RMSE da persistência), como no painel."""
    err = pred - y
    rmse = float(np.sqrt(np.mean(err ** 2)))
    rmse_p = float(np.sqrt(np.mean((pred_persistence - y) ** 2)))
    return {"n": int(len(y)), "mae": float(np.mean(np.abs(err))), "rmse": rmse,
            "skill": float(1 - rmse / rmse_p) if rmse_p > 0 else None}


def evaluate(frame: pd.DataFrame, models: dict, folds, final, predictions: dict | None = None, **kw) -> dict:
    """Métricas por modelo na validação progressiva (todas as dobras juntas) e no teste final.

    Se `predictions` for um dicionário, recebe as previsões do teste final (hora-alvo, nó, observado e
    previsão de cada modelo) para exportação."""
    out = {name: {"validation": None, "test": None} for name in models}
    collected = {name: [] for name in models}
    observed, persist = [], []
    for start, end in folds:
        train, test = train_test(frame, start, end)
        if len(train) < MIN_TRAIN_ROWS or test.empty:
            continue
        observed.append(test["y"].to_numpy(float))
        persist.append(predict_persistence(train, test))
        for name, fn in models.items():
            collected[name].append(fn(train, test, **kw))
    if observed:
        y, p = np.concatenate(observed), np.concatenate(persist)
        for name in models:
            out[name]["validation"] = metrics(y, np.concatenate(collected[name]), p)
    train, test = train_test(frame, *final)
    if len(train) >= MIN_TRAIN_ROWS and not test.empty:
        y, p = test["y"].to_numpy(float), predict_persistence(train, test)
        preds = {}
        for name, fn in models.items():
            preds[name] = fn(train, test, **kw)
            out[name]["test"] = metrics(y, preds[name], p)
        if predictions is not None:
            predictions.update(hour=test.index + pd.Timedelta(hours=1), device=test["device_id"].to_numpy(),
                               observed=y, models=preds)
    return out


def aggregate_seeds(per_seed: list[dict]) -> dict:
    """Média e desvio-padrão amostral (n − 1) do RMSE e do skill entre sementes, em cada etapa.

    `per_seed` é uma lista de {"seed": s, "validation": métricas|None, "test": métricas|None}."""
    out: dict = {"seeds": [r["seed"] for r in per_seed], "per_seed": per_seed}
    for stage in ("validation", "test"):
        stage_metrics = [r[stage] for r in per_seed]
        if any(m is None for m in stage_metrics):
            out[stage] = None
            continue
        entry = {}
        for key, label in (("rmse", "rmse"), ("skill", "skill")):
            values = [m[key] for m in stage_metrics]
            if any(v is None for v in values):
                entry[f"{label}_mean"] = entry[f"{label}_std"] = None
                continue
            entry[f"{label}_mean"] = float(np.mean(values))
            entry[f"{label}_std"] = float(np.std(values, ddof=1)) if len(values) > 1 else None
        out[stage] = entry
    return out


def run_seeds(frame, folds, final, fn, first_seed: int, n_seeds: int, reference: dict, **kw) -> dict:
    """Repete o treino de `fn` com sementes consecutivas. A primeira é a de referência, cujo resultado
    (`reference`, já calculado) não é treinado de novo."""
    per_seed = [{"seed": first_seed, **reference}]
    for seed in range(first_seed + 1, first_seed + n_seeds):
        res = evaluate(frame, {"modelo": fn}, folds, final, **{**kw, "seed": seed})["modelo"]
        per_seed.append({"seed": seed, **res})
    return aggregate_seeds(per_seed)


def package_version(*names: str) -> str | None:
    for name in names:
        try:
            return metadata.version(name)
        except metadata.PackageNotFoundError:
            continue
    return None


def environment_info() -> dict:
    """Versões das bibliotecas que determinam os números do relatório (RNF06)."""
    return {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
            "scikit-learn": package_version("scikit-learn"),
            "tensorflow": package_version("tensorflow", "tensorflow-cpu", "tensorflow-intel", "tensorflow-macos")}


def database_info(path: str) -> dict:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return {"file": os.path.basename(path), "sha256": digest.hexdigest(), "size_bytes": os.path.getsize(path)}


COLUMN_NAMES = {PERSISTENCE: "persistencia", "Ridge": "ridge", "MLP (Keras)": "mlp"}


def write_predictions_csv(path: str, predictions: dict) -> int:
    """Previsões do teste final, uma linha por hora-alvo (UTC) e nó. Retorna o número de linhas."""
    frame = pd.DataFrame({
        "hora": predictions["hour"].strftime("%Y-%m-%dT%H:%M:%SZ"),
        "no": predictions["device"],
        "observado": predictions["observed"],
        **{COLUMN_NAMES[name]: values for name, values in predictions["models"].items()},
    }).sort_values(["no", "hora"], kind="stable")
    frame.to_csv(path, index=False)
    return len(frame)


def _mean_std(mean: float | None, std: float | None, fmt: str) -> str:
    if mean is None:
        return "—"
    return f"{mean:{fmt}}" if std is None else f"{mean:{fmt}} ± {std:.3f}"


def format_seeds(results: dict) -> str:
    """Linhas extras da tabela com a média ± desvio entre sementes, se houver."""
    lines = []
    for name, stages in results.items():
        agg = stages.get("seeds")
        if not agg:
            continue
        lines.append(f"\n{name}: {len(agg['seeds'])} sementes ({agg['seeds'][0]} a {agg['seeds'][-1]}), média ± desvio")
        for stage, label in (("validation", "validação"), ("test", "teste")):
            m = agg[stage]
            if m is None:
                lines.append(f"  {label:<12}—")
                continue
            lines.append(f"  {label:<12}RMSE {_mean_std(m['rmse_mean'], m['rmse_std'], '.3f')}   skill {_mean_std(m['skill_mean'], m['skill_std'], '+.3f')}")
    return "\n".join(lines)


def format_table(results: dict) -> str:
    lines = [f"{'Modelo':<14}{'Etapa':<12}{'Horas':>7}{'MAE':>9}{'RMSE':>9}{'Skill':>9}"]
    for name, stages in results.items():
        for stage, label in (("validation", "validação"), ("test", "teste")):
            m = stages[stage]
            if m is None:
                lines.append(f"{name:<14}{label:<12}{'—':>7}")
                continue
            skill = "—" if m["skill"] is None else f"{m['skill']:+.3f}"
            lines.append(f"{name:<14}{label:<12}{m['n']:>7}{m['mae']:>9.2f}{m['rmse']:>9.2f}{skill:>9}")
    return "\n".join(lines)


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--db", default=None, help="caminho do SQLite (padrão: PM25_DB_PATH)")
    p.add_argument("--out", default=None, help="grava o relatório em JSON")
    p.add_argument("--test-days", type=int, default=7)
    p.add_argument("--min-train-days", type=int, default=14)
    p.add_argument("--fold-days", type=int, default=7)
    p.add_argument("--min-samples", type=int, default=MIN_SAMPLES, help="leituras por hora para a hora valer")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--ridge-alpha", type=float, default=10.0)
    p.add_argument("--hidden", type=int, nargs="+", default=[32, 16])
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--epochs", type=int, default=200)
    p.add_argument("--batch-size", type=int, default=32)
    p.add_argument("--patience", type=int, default=15)
    p.add_argument("--no-mlp", action="store_true", help="avalia só persistência e Ridge")
    p.add_argument("--predictions-csv", default=None, help="grava as previsões do teste final em CSV")
    p.add_argument("--seeds", type=int, default=1, help="sementes da MLP (consecutivas a partir de --seed; padrão 1)")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.seeds < 1:
        print("--seeds precisa ser pelo menos 1.", file=sys.stderr)
        return 1
    if args.seeds > 1 and args.no_mlp:
        print("--seeds repete o treino da MLP e não vale com --no-mlp.", file=sys.stderr)
        return 1
    path = args.db or get_settings().db_path
    if not os.path.exists(path):
        print(f"Banco não encontrado: {path}", file=sys.stderr)
        return 1
    conn = db.connect(path, readonly=True)
    try:
        devices = [r["device_id"] for r in db.device_overview(conn)]
        frame = build_dataset(conn, devices, args.min_samples)
    finally:
        conn.close()
    if len(frame) < MIN_TRAIN_ROWS * 2:
        print(f"Dados insuficientes: {len(frame)} horas completas (mínimo {MIN_TRAIN_ROWS * 2}).", file=sys.stderr)
        return 1

    folds, final = make_splits(frame.index, args.test_days, args.min_train_days, args.fold_days)
    models = {PERSISTENCE: predict_persistence, "Ridge": predict_ridge}
    hyper = {"seed": args.seed, "ridge_alpha": args.ridge_alpha}
    if not args.no_mlp:
        try:
            import tensorflow  # noqa: F401
        except ImportError:
            print("TensorFlow não instalado: use `pip install -r requirements-ml.txt` ou --no-mlp.", file=sys.stderr)
            return 1
        models["MLP (Keras)"] = predict_mlp
        hyper.update(hidden=args.hidden, lr=args.lr, epochs=args.epochs, batch_size=args.batch_size,
                     patience=args.patience, optimizer="Adam", early_stopping=True, seeds=args.seeds)
    kw = dict(alpha=args.ridge_alpha, seed=args.seed, hidden=tuple(args.hidden), lr=args.lr, epochs=args.epochs,
              batch_size=args.batch_size, patience=args.patience)
    predictions: dict = {}
    results = evaluate(frame, models, folds, final, predictions=predictions, **kw)
    if args.seeds > 1:
        mlp = "MLP (Keras)"
        results[mlp]["seeds"] = run_seeds(frame, folds, final, predict_mlp, args.seed, args.seeds,
                                          {"validation": results[mlp]["validation"], "test": results[mlp]["test"]}, **kw)

    print(f"Horas completas: {len(frame)} ({', '.join(devices)}); dobras de validação: {len(folds)}; "
          f"teste final: {final[0]:%Y-%m-%d} a {final[1]:%Y-%m-%d}\n")
    print(format_table(results))
    if args.seeds > 1:
        print(format_seeds(results))
    if args.predictions_csv:
        if predictions:
            rows = write_predictions_csv(args.predictions_csv, predictions)
            print(f"\nPrevisões do teste final: {args.predictions_csv} ({rows} linhas)")
        else:
            print("\nSem teste final avaliável: o CSV de previsões não foi gerado.", file=sys.stderr)
    if args.out:
        report = {"generated_at": db.iso(datetime.now(timezone.utc)), "devices": devices, "rows": len(frame),
                  "horizon_hours": 1, "features": FEATURES, "folds": len(folds),
                  "test_window": [str(final[0]), str(final[1])], "hyperparameters": hyper,
                  "environment": environment_info(), "database": database_info(path), "results": results}
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        print(f"\nRelatório: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
