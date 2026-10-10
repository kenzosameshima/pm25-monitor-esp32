from pathlib import Path

SRC_DIR  = Path(__file__).resolve().parent
ROOT_DIR = SRC_DIR.parent

DATA_DIR = ROOT_DIR / "data"
SENSOR_FILE = DATA_DIR / "pm25_raw.csv"
CETESB_FILE = DATA_DIR / "cetesb_pm25_raw.csv"

# sensor
SENSOR_COLUMNS = ["row_id", "sensor_id", "session_id", "session_counter", "ts_sensor", "ts_received", "pm25_a", "pm25_b", "pm25_c", "pm25_d",
                   "temperature", "humidity", "rssi", "uptime", "samples", "schema_ver", "quality"]

SENSOR_TS_COL = "ts_sensor"
SENSOR_VAL_COL = "pm25_b"
SENSOR_TEMP_COL = "temperature"
SENSOR_HUM_COL = "humidity"
SENSOR_QUAL_COL = "quality"
SENSOR_ENCODING = "utf-8"

# cetesb
CETESB_SKIPROWS = 8 # 4 linhas de metadados + cabeçalho + linha das unidades
CETESB_SEP = ";"        
CETESB_COLUMNS = ["date", "hour", "cetesb_pm25"]   
CETESB_TS_COL = "timestamp"                
CETESB_VAL_COL = "cetesb_pm25"
CETESB_DATE_FMT = "%d/%m/%Y"                 
CETESB_HOUR_FMT = "%H:%M"
CETESB_ENCODING = "latin-1"     # Para ler acentos e cedilha corretamente

TIMEZONE = "America/Sao_Paulo" 
MIN_READINGS_PER_HOUR = 45 # 75%
HOURLY_FREQ = "1h"    