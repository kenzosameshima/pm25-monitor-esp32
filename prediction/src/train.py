import xgboost as xgb
import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

def train(df, target="sensor_pm25_calibrated"):
    drop_cols = [target, "hour"]
    feats = [c for c in df.columns if c not in drop_cols]

    split = int(len(df) * 0.8)
    train_df, test_df = df.iloc[:split], df.iloc[split:]

    model = xgb.XGBRegressor(
        n_estimators=600, learning_rate=0.05, max_depth=6,
        subsample=0.8, colsample_bytree=0.8,
        early_stopping_rounds=40, eval_metric="mae"
    )
    model.fit(train_df[feats], train_df[target],
              eval_set=[(test_df[feats], test_df[target])], verbose=False)

    preds = model.predict(test_df[feats])
    print(f"MAE:  {mean_absolute_error(test_df[target], preds):.2f}")
    print(f"RMSE: {np.sqrt(mean_squared_error(test_df[target], preds)):.2f}")
    print(f"R²:   {r2_score(test_df[target], preds):.3f}")
    return model, feats, test_df, preds