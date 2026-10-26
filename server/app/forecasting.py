"""Previsão da média horária de PM2,5 da hora seguinte: dados, modelos e arquivo do modelo treinado.

A avaliação offline (scripts.train_forecast), o treino do modelo de produção (scripts.fit_forecast) e
o job horário (scripts.forecast_job) passam todos por aqui, então as variáveis que um modelo vê em
produção são as mesmas do treino e da avaliação.

A tarefa: com as médias conhecidas até a hora t, prever a média de PM2,5 da hora t+1. Os modelos
aprendem a variação em relação à persistência (PM2,5 de t+1 menos o de t) e devolvem o nível previsto.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from importlib import metadata
from pathlib import Path

import numpy as np
import pandas as pd

from app import analytics, db

LAGS = (1, 2, 3, 6, 12, 24)
FEATURES = ["pm25", *[f"lag_{k}" for k in LAGS], "humidity", "temperature", "hour_sin", "hour_cos"]
MIN_SAMPLES = analytics.MIN_READINGS_PER_HOUR  # minutos com leitura para uma hora entrar na série
MIN_TRAIN_ROWS = 100    # abaixo disso o treino não é confiável
_REQUIRED = ["pm25", *[f"lag_{k}" for k in LAGS]]  # sem elas a linha não entra; umidade e temperatura são imputadas
_IMPUTED = ["humidity", "temperature"]
_EPOCH = datetime(2000, 1, 1, tzinfo=timezone.utc)
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# Hiperparâmetros fixados antes de ver os dados reais (ver README, "Avaliação de modelos de previsão").
DEFAULTS = {
    "ridge": {"alpha": 10.0},
    "gboost": {"learning_rate": 0.1, "max_iter": 100, "max_leaf_nodes": 31, "min_samples_leaf": 20, "seed": 42},
    "mlp": {"hidden": (32, 16), "lr": 1e-3, "epochs": 200, "batch_size": 32, "patience": 15,
            "val_fraction": 0.15, "seed": 42},
}


# ---------------------------------------------------------------- dados

def hourly_series(conn, device: str, min_samples: int = MIN_SAMPLES, start: datetime = _EPOCH,
                  end: datetime | None = None, drop_suspect: bool = True) -> pd.DataFrame:
    """Médias horárias de PM2,5, umidade e temperatura do nó, com `n` leituras por hora.

    Indexada pela hora (UTC), sem saltos entre a primeira e a última hora com leitura em [start, end);
    horas com menos de `min_samples` leituras, e as suspeitas de sensor sem partículas (ver
    `analytics.hourly_means`, `suspeita`), ficam com as médias em NaN, a menos que `drop_suspect` seja falso.
    As métricas do período e a comparação com a CETESB usam esta mesma série. Sem `end`, vai até amanhã."""
    end = end or datetime.now(timezone.utc) + timedelta(days=1)
    hourly = analytics.hourly_means(conn, start, end, [device], min_readings=min_samples, drop_suspect=drop_suspect)
    columns = ["pm25", "humidity", "temperature", "n", "suspeita"]
    if hourly.empty:
        return pd.DataFrame(columns=columns)
    return hourly.set_index("hora").rename_axis("ts")[columns]


def _features(hourly: pd.DataFrame, device: str) -> pd.DataFrame:
    """Uma linha por hora t do nó, com as variáveis conhecidas até t e o alvo y = PM2,5 médio de t+1."""
    if hourly.empty:
        return pd.DataFrame(columns=[*FEATURES, "y", "device_id"])
    f = pd.DataFrame(index=hourly.index)
    f["pm25"] = hourly["pm25"].astype(float)
    for k in LAGS:                       # a série não tem saltos: k linhas atrás é k horas atrás
        f[f"lag_{k}"] = f["pm25"].shift(k)
    f["humidity"] = hourly["humidity"].astype(float)
    f["temperature"] = hourly["temperature"].astype(float)
    f["hour_sin"] = np.sin(2 * np.pi * f.index.hour / 24)
    f["hour_cos"] = np.cos(2 * np.pi * f.index.hour / 24)
    f["y"] = f["pm25"].shift(-1)
    f["device_id"] = device
    return f


def dataset(conn, device_ids: list[str] | None = None, min_samples: int = MIN_SAMPLES) -> pd.DataFrame:
    """Linhas de treino e avaliação de todos os nós: FEATURES, o alvo `y` e `device_id`.

    O índice é a hora t (UTC), em ordem cronológica. Só entram horas com média válida (pelo menos
    `min_samples` leituras), com todos os atrasos e com o alvo. Sem `device_ids`, usa `analytics.production_devices(conn)`."""
    ids = analytics.production_devices(conn) if device_ids is None else device_ids
    frames = [_features(hourly_series(conn, d, min_samples), d).dropna(subset=[*_REQUIRED, "y"]) for d in ids]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame(columns=[*FEATURES, "y", "device_id"])
    return pd.concat(frames).sort_index(kind="stable")


def latest_row(conn, device: str, now: datetime, min_samples: int = MIN_SAMPLES) -> pd.DataFrame:
    """As variáveis da última hora completa t antes de `now`, para prever t+1, a hora em andamento.

    Devolve uma linha com FEATURES e `device_id`, indexada por t, ou um DataFrame vazio se t ou algum
    atraso não tiver média válida. Como t+1 contém `now`, a previsão sempre antecede o valor observado."""
    t = pd.Timestamp(now).tz_convert("UTC").floor("h") - pd.Timedelta(hours=1)
    hourly = hourly_series(conn, device, min_samples, start=t - pd.Timedelta(hours=max(LAGS)),
                           end=t + pd.Timedelta(hours=1))
    f = _features(hourly, device)
    return f.loc[f.index == t].dropna(subset=_REQUIRED).drop(columns="y")


# ---------------------------------------------------------------- modelos

def _ridge(x, y, *, alpha):
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    return make_pipeline(StandardScaler(), Ridge(alpha=alpha)).fit(x, y)


def _gboost(x, y, *, learning_rate, max_iter, max_leaf_nodes, min_samples_leaf, seed):
    from sklearn.ensemble import HistGradientBoostingRegressor

    # Sem parada antecipada: o padrão "auto" a liga só acima de 10 000 linhas e valida numa amostra aleatória
    return HistGradientBoostingRegressor(learning_rate=learning_rate, max_iter=max_iter, max_leaf_nodes=max_leaf_nodes,
                                         min_samples_leaf=min_samples_leaf, early_stopping=False,
                                         random_state=seed).fit(x, y)


def _mlp(x, y, *, hidden, lr, epochs, batch_size, patience, val_fraction, seed):
    """MLP treinada época a época (`partial_fit`), com parada antecipada no bloco final do treino.

    O `early_stopping` do próprio MLPRegressor sorteia a validação; aqui ela é o bloco mais recente, em
    ordem cronológica, e os pesos da melhor época são restaurados ao fim."""
    from sklearn.neural_network import MLPRegressor
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler().fit(x)
    xs = scaler.transform(x)
    n_val = max(1, int(len(xs) * val_fraction))
    xfit, yfit, xval, yval = xs[:-n_val], y[:-n_val], xs[-n_val:], y[-n_val:]
    model = MLPRegressor(hidden_layer_sizes=tuple(hidden), activation="relu", solver="adam", learning_rate_init=lr,
                         batch_size=batch_size, alpha=0.0, shuffle=True, random_state=seed)
    best_loss, best_weights, waited = np.inf, None, 0
    for _ in range(epochs):
        model.partial_fit(xfit, yfit)  # uma época, com os lotes embaralhados pela semente
        val_loss = float(np.mean((model.predict(xval) - yval) ** 2))
        if val_loss < best_loss:
            best_loss, waited = val_loss, 0
            best_weights = ([w.copy() for w in model.coefs_], [b.copy() for b in model.intercepts_])
        else:
            waited += 1
            if waited >= patience:
                break
    model.coefs_, model.intercepts_ = best_weights
    return Pipeline([("scaler", scaler), ("mlp", model)])


_BUILDERS = {"ridge": _ridge, "gboost": _gboost, "mlp": _mlp}


@dataclass(frozen=True)
class Forecaster:
    """Um modelo treinado. `predict` recebe linhas de `dataset` ou `latest_row`."""

    kind: str            # "ridge", "gboost" ou "mlp": vira model_name em forecasts
    params: dict         # hiperparâmetros usados
    estimator: object    # prevê a variação em relação à persistência a partir de FEATURES
    medians: dict        # umidade e temperatura do treino, para imputar horas sem esses sensores
    trained_on: dict     # linhas, nós, primeira e última hora t do treino
    sklearn: str         # versão do scikit-learn do treino; o arquivo só carrega com a mesma versão
    version: str | None = None  # vira model_version em forecasts; definida por scripts.fit_forecast

    def predict(self, rows: pd.DataFrame) -> np.ndarray:
        """PM2,5 médio previsto para a hora seguinte a cada linha, em µg/m³ (nunca negativo)."""
        x = rows[FEATURES].fillna(self.medians).to_numpy(float)
        return np.maximum(0.0, rows["pm25"].to_numpy(float) + self.estimator.predict(x))


def fit(kind: str, train: pd.DataFrame, **params) -> Forecaster:
    """Treina um modelo `kind` ("ridge", "gboost" ou "mlp") com linhas de `dataset`.

    `params` substitui hiperparâmetros de DEFAULTS[kind]; um nome que o modelo não tem é erro."""
    if kind not in _BUILDERS:
        raise ValueError(f"Modelo desconhecido: {kind!r} (use {', '.join(_BUILDERS)})")
    unknown = set(params) - set(DEFAULTS[kind])
    if unknown:
        raise TypeError(f"Hiperparâmetros que {kind} não tem: {', '.join(sorted(unknown))}")
    used = {**DEFAULTS[kind], **params}
    medians = {c: float(v) for c, v in train[_IMPUTED].median().fillna(0.0).items()}
    x = train[FEATURES].fillna(medians).to_numpy(float)
    y = (train["y"] - train["pm25"]).to_numpy(float)
    trained_on = {"rows": len(train), "devices": sorted(set(train["device_id"])),
                  "first_hour": db.iso(train.index.min()), "last_hour": db.iso(train.index.max())}
    return Forecaster(kind, used, _BUILDERS[kind](x, y, **used), medians, trained_on, metadata.version("scikit-learn"))


# ---------------------------------------------------------------- arquivo do modelo

def file_name(kind: str, version: str) -> str:
    """Nome do arquivo de um modelo: <kind>-<version>.joblib. Erro se a versão tiver caracteres inválidos."""
    if not _VERSION.match(version):
        raise ValueError(f"Versão inválida: {version!r} (use letras, números, ponto, hífen ou sublinhado)")
    return f"{kind}-{version}.joblib"


def save(forecaster: Forecaster, version: str, models_dir: str) -> Path:
    """Grava o modelo com a versão dada. Erro se o arquivo já existir: uma versão gravada em forecasts
    tem que corresponder a um único modelo."""
    import joblib

    path = Path(models_dir) / file_name(forecaster.kind, version)
    if path.exists():
        raise FileExistsError(f"{path} já existe; use outra versão")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    joblib.dump(replace(forecaster, version=version), tmp)
    tmp.replace(path)
    return path


def load(path: str | Path) -> Forecaster:
    """Carrega um modelo gravado por `save`. É um pickle: só carregue arquivos gerados neste servidor.

    Erro se o scikit-learn instalado não for o do treino, porque o pickle não é garantido entre versões."""
    import joblib

    forecaster = joblib.load(path)
    if not isinstance(forecaster, Forecaster) or forecaster.version is None:
        raise ValueError(f"{path} não é um modelo gravado por scripts.fit_forecast")
    installed = metadata.version("scikit-learn")
    if forecaster.sklearn != installed:
        raise ValueError(f"{path} foi treinado com scikit-learn {forecaster.sklearn}, e o instalado é o {installed}: "
                         "treine de novo com scripts.fit_forecast")
    return forecaster


def load_all(models_dir: str) -> tuple[list[Forecaster], list[str]]:
    """Todos os modelos de `models_dir`, em ordem de nome, e as mensagens de erro dos que não carregaram."""
    loaded, errors = [], []
    for path in sorted(Path(models_dir).glob("*.joblib")):
        try:
            loaded.append(load(path))
        except Exception as exc:  # um arquivo ruim não impede os outros modelos
            errors.append(f"{path.name}: {exc}")
    return loaded, errors
