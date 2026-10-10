import pandas as pd
from config import *

def load_sensor():
    df = pd.read_csv(
        SENSOR_FILE,
        header=None,
        names=SENSOR_COLUMNS,
        keep_default_na=True,)
    df[SENSOR_TS_COL] = pd.to_datetime(df[SENSOR_TS_COL], utc=True)
    df[SENSOR_TS_COL] = df[SENSOR_TS_COL].dt.tz_convert(TIMEZONE) # Para comparar com o CETESB, que está no horário de São Paulo
    df = df[df[SENSOR_QUAL_COL] == "ok"] # Filtra apenas leituras com qualidade "ok"

    for c in [SENSOR_VAL_COL, SENSOR_TEMP_COL, SENSOR_HUM_COL]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.dropna(subset=[SENSOR_TS_COL, SENSOR_VAL_COL])
    return df[[SENSOR_TS_COL, SENSOR_VAL_COL, SENSOR_TEMP_COL, SENSOR_HUM_COL]]

def load_cetesb():
    df = pd.read_csv(
        CETESB_FILE,
        sep=CETESB_SEP,
        skiprows=CETESB_SKIPROWS,
        header=None,
        names=CETESB_COLUMNS,
        encoding=CETESB_ENCODING,)
    df = df.dropna(subset=["date", "hour"], how="any") # Remove linhas com dados faltando

    # CETESB utiliza horario de 24:00, não é aceito pelo pandas, então substituímos por 00:00 do dia seguinte
    
    hour_str = df["hour"].astype(str).str.strip()
    is_hour24 = hour_str.str.startswith("24")
    clean_hour = hour_str.where(~is_hour24, "00:00")
    date = pd.to_datetime(df["date"], format=CETESB_DATE_FMT)
    date = date + pd.to_timedelta(is_hour24.astype(int), unit="D")

    ts = pd.to_datetime(
        date.dt.strftime("%Y-%m-%d") + " " + clean_hour,
        format="%Y-%m-%d %H:%M",
    ).dt.tz_localize(TIMEZONE, ambiguous="NaT", nonexistent="NaT")

    df["timestamp"] = ts
    df[CETESB_VAL_COL] = pd.to_numeric(df[CETESB_VAL_COL], errors="coerce")

    df = df.dropna(subset=["timestamp", CETESB_VAL_COL])
    return df[["timestamp", CETESB_VAL_COL]].rename(columns={CETESB_VAL_COL: "cetesb_pm25"})