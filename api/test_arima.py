import os
import psycopg2
import pandas as pd
import numpy as np
from datetime import datetime

print("Connecting to PostgreSQL...")
try:
    conn = psycopg2.connect(
        host="postgres",
        port=5432,
        dbname="graphalpha",
        user="graphalpha",
        password="changeme"
    )
    print("Postgres connection successful!")
    
    # 1. Query signal_archive strategies and tickers
    print("\n--- Listing Strategies and Tickers in signal_archive ---")
    query = "SELECT DISTINCT strategy, ticker FROM signal_archive LIMIT 20;"
    df = pd.read_sql(query, conn)
    print(df)
    
    # Check count of rows in signal_archive
    count_query = "SELECT COUNT(*) FROM signal_archive;"
    count_df = pd.read_sql(count_query, conn)
    print(f"\nTotal rows in signal_archive: {count_df.iloc[0, 0]}")

    # Check some sample rows
    if count_df.iloc[0, 0] > 0:
        sample_query = "SELECT timestamp, strategy, ticker, score FROM signal_archive ORDER BY timestamp DESC LIMIT 5;"
        sample_df = pd.read_sql(sample_query, conn)
        print(f"\nSample signals:\n{sample_df}")
    
    conn.close()
except Exception as e:
    print(f"Postgres error: {e}")

# 2. Test statsmodels ARIMA fit
print("\nTesting statsmodels ARIMA...")
try:
    from statsmodels.tsa.arima.model import ARIMA
    print("Successfully imported statsmodels ARIMA")
    
    # Generate dummy random walk data
    np.random.seed(42)
    dummy_data = np.cumsum(np.random.normal(0, 1, 100)) + 100
    
    print("Fitting dummy ARIMA(1, 1, 1)...")
    model = ARIMA(dummy_data, order=(1, 1, 1))
    fitted = model.fit()
    print("Fit successful!")
    print(f"AIC: {fitted.aic}")
    
    print("Forecasting...")
    forecast_result = fitted.get_forecast(steps=5)
    print(f"Forecast: {forecast_result.predicted_mean}")
    
except Exception as e:
    print(f"ARIMA error: {e}")
