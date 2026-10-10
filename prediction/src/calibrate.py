import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score, mean_absolute_error

def fit_calibration(merged, min_points=50):
    """
    calibra o sensor para corresponder aos dados do CETESB.
    cetesb_pm25 = a * sensor_pm25 + b nos horarios de sobreposição.
    Retorna um dicionário com modelo, coeficientes e métricas de diagnóstico.
    """
    data = merged[["sensor_pm25", "cetesb_pm25"]].dropna()
    if len(data) < min_points:
        raise ValueError(f"Only {len(data)} overlapping hours — need more for calibration.")

    X = data[["sensor_pm25"]].values
    y = data["cetesb_pm25"].values

    model = LinearRegression().fit(X, y)
    preds = model.predict(X)

    a = float(model.coef_[0])
    b = float(model.intercept_)
    r2 = r2_score(y, preds)
    mae = mean_absolute_error(y, preds)

    print("── Calibracao ─────────────────────────")
    print(f"  cetesb_pm25 = {a:.3f} * sensor_pm25 + {b:.3f}")
    print(f"  R²  = {r2:.3f}")
    print(f"  MAE = {mae:.2f} µg/m³")
    print(f"  N   = {len(data)} hours")
    print("────────────────────────────────────────")

    return {"model": model, "a": a, "b": b, "r2": r2, "mae": mae}


def apply_calibration(sensor_hourly, calib):
    """Apply a,b to the FULL sensor series (not just overlap)."""
    df = sensor_hourly.copy()
    df["sensor_pm25_calibrated"] = calib["a"] * df["sensor_pm25"] + calib["b"]
    # PM2.5 can't be negative
    df["sensor_pm25_calibrated"] = df["sensor_pm25_calibrated"].clip(lower=0)
    return df