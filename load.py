import requests
import pandas as pd
from datetime import datetime, timedelta
import time

def fetch_binance_data(symbol, interval, start_time, end_time):
    endpoint = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "startTime": int(start_time.timestamp() * 1000),
        "endTime": int(end_time.timestamp() * 1000),
        "limit": 1000
    }
    
    data = []
    while start_time < end_time:
        response = requests.get(endpoint, params=params)
        candles = response.json()
        
        if not candles:
            break
        
        data.extend(candles)
        start_time = datetime.fromtimestamp(candles[-1][0] / 1000) + timedelta(hours=1)
        params["startTime"] = int(start_time.timestamp() * 1000)
        
        # เพิ่มการหน่วงเวลาเพื่อหลีกเลี่ยงการถูกจำกัดการใช้งาน API
        time.sleep(0.5)
    
    return data

def create_dataframe(data):
    columns = [
        "Open time", "Open", "High", "Low", "Close", "Volume",
        "Close time", "Quote asset volume", "Number of trades",
        "Taker buy base asset volume", "Taker buy quote asset volume", "Ignore"
    ]
    df = pd.DataFrame(data, columns=columns)
    df["Open time"] = pd.to_datetime(df["Open time"], unit="ms")
    df["Close time"] = pd.to_datetime(df["Close time"], unit="ms")
    return df

def main():
    symbol = "BTCUSDT"  # เปลี่ยนเป็นคู่เหรียญที่คุณต้องการ
    interval = "1h"
    end_time = datetime.now()
    start_time = end_time - timedelta(days=180)  # 6 เดือน
    
    print(f"Fetching data for {symbol} from {start_time} to {end_time}")
    data = fetch_binance_data(symbol, interval, start_time, end_time)
    df = create_dataframe(data)
    
    csv_filename = f"{symbol}_{interval}_historical_data_6months.csv"
    df.to_csv(csv_filename, index=False)
    print(f"Data saved to {csv_filename}")
    print(f"Total records: {len(df)}")

if __name__ == "__main__":
    main()