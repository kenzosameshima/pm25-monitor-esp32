from load_data import load_sensor, load_cetesb
from align import sensor_to_hourly, cetesb_to_hourly
from calibrate import fit_calibration, apply_calibration
from features import build_features
from train import train
import pandas as pd

# 1. Carregar dados brutos
sensor_raw = load_sensor()
cetesb_raw = load_cetesb()

print("sensor cols:", sensor_raw.columns.tolist())
print("cetesb cols:", cetesb_raw.columns.tolist())
print(sensor_raw.head(2))


# 2. Alinhar leituras para hora cheia
sensor_h = sensor_to_hourly(sensor_raw)   # leituras do sensor para hora cheia
cetesb_h = cetesb_to_hourly(cetesb_raw)     # normalizar

# 3. Combinar os dois conjuntos para a calibração
merged = pd.merge(sensor_h, cetesb_h, on="hour", how="inner")
print(f"Overlap: {len(merged)} hours")

# 4. Utiliza regressao linear para encontrar a calibracao (a,b) entre sensor e cetesb
calib = fit_calibration(merged)

# 5. Aplica a calibracao a todas as leituras do sensor (nao apenas o periodo de overlap)
sensor_h = apply_calibration(sensor_h, calib)

# 7. Features
features = build_features(sensor_h)
print(f"Feature matrix: {features.shape}")

# 8. Treinamento e avaliacao do modelo
model, feats, test_df, preds = train(features)

# 9. Exemplo de predicao para a proxima hora
last_row = features.iloc[[-1]][feats]
next_hour_pred = model.predict(last_row)[0]
print(f"Next hour PM2.5 prediction: {next_hour_pred:.1f} µg/m³")