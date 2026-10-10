import pandas as pd
from config import (
    SENSOR_TS_COL, SENSOR_VAL_COL,
    CETESB_TS_COL, CETESB_VAL_COL,
    MIN_READINGS_PER_HOUR,
    HOURLY_FREQ,
)

def sensor_to_hourly(df):
    df = df.copy().set_index(SENSOR_TS_COL).sort_index()
    hourly = df[SENSOR_VAL_COL].resample(HOURLY_FREQ).agg(["mean", "count"])
    hourly.columns = ["sensor_pm25", "n_readings"]
    hourly = hourly[hourly["n_readings"] >= MIN_READINGS_PER_HOUR]
    hourly = hourly.drop(columns="n_readings").reset_index()
    hourly = hourly.rename(columns={SENSOR_TS_COL: "hour"})
    return hourly


def cetesb_to_hourly(df):
    df = df.copy()
    df["hour"] = df[CETESB_TS_COL].dt.floor("h")
    return (
        df.groupby("hour")[CETESB_VAL_COL]
          .mean()
          .reset_index()
          .rename(columns={CETESB_VAL_COL: "cetesb_pm25"})
    )