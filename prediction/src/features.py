import numpy as np
import pandas as pd

def build_features(df, target="sensor_pm25_calibrated",
                   lags=[1, 2, 3, 6, 12, 24, 48]):
    df = df.copy().sort_values("hour")

    for lag in lags:
        df[f"lag_{lag}"] = df[target].shift(lag)

    for w in [3, 6, 12, 24]:
        df[f"roll_mean_{w}"] = df[target].shift(1).rolling(w).mean()
        df[f"roll_std_{w}"]  = df[target].shift(1).rolling(w).std()

    df["hour_of_day"] = df["hour"].dt.hour
    df["day_of_week"] = df["hour"].dt.dayofweek
    df["month"] = df["hour"].dt.month
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)
    df["hour_sin"] = np.sin(2 * np.pi * df["hour_of_day"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour_of_day"] / 24)

    return df.dropna().reset_index(drop=True)