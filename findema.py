import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import requests
from typing import List
import schedule
import time
import os

line_token = "aMFv92TD5VFEXQ3fU9gN1sAaWWrkyVoo6VlJe95hvE7"

def send_line_notify(message):
    try:
        headers = {
            'Authorization': f'Bearer {line_token}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        payload = {'message': message}
        response = requests.post("https://notify-api.line.me/api/notify", headers=headers, params=payload)
        if response.status_code == 200:
            print("LINE notification sent successfully", flush=True)
        else:
            print(f"Failed to send LINE notification. Status code: {response.status_code}", flush=True)
    except Exception as e:
        print(f"Error sending LINE message: {e}", flush=True)

def save_to_file(data: List[str], filename: str):
    line_message = "EMA Crossover Signals:\n"
    with open(filename, 'w') as f:
        for symbol in data:
            line_message += f"{symbol}\n"            
            f.write(f"{symbol}\n")

def get_futures_symbols() -> List[str]:
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    response = requests.get(url)
    data = response.json()
    return [symbol['symbol'] for symbol in data['symbols'] if symbol['status'] == 'TRADING' and symbol['symbol'].endswith('USDT')]

def get_market_data(symbol, timeframe, limit):
    url = f"https://fapi.binance.com/fapi/v1/klines"
    params = {
        "symbol": symbol,
        "interval": timeframe,
        "limit": limit
    }
    response = requests.get(url, params=params)
    data = response.json()
    return data

def calculate_ema(data, period):
    return data.ewm(span=period, adjust=False).mean()

def analyze_ema_crossover(symbol, timeframe='1h'):
    data = get_market_data(symbol, timeframe, 90)
    
    df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df['close'] = df['close'].astype(float)
    df.set_index('timestamp', inplace=True)
    
    df['ema7'] = calculate_ema(df['close'], 7)
    df['ema21'] = calculate_ema(df['close'], 21)
    df['ema90'] = calculate_ema(df['close'], 90)
    
    current = df.iloc[-1]
    
    # คำนวณเปอร์เซ็นต์ความต่างระหว่าง EMA
    ema21_90_diff = abs(current['ema21'] - current['ema90']) / current['ema90'] * 100
    
    if (current['ema7'] > current['ema21'] > current['ema90'] and ema21_90_diff <= 1):
        return "LONG"
    elif (current['ema7'] < current['ema21'] < current['ema90'] and ema21_90_diff <= 1):
        return "SHORT"
    else:
        return "NO_SIGNAL"

def analyze_all_symbols():
    symbols = get_futures_symbols()
    signals = []
    for symbol in symbols:
        try:
            signal = analyze_ema_crossover(symbol)
            print(f"{datetime.now()}: {symbol}: {signal}", flush=True)
            if signal != "NO_SIGNAL":
                signals.append(f"{symbol}")
                send_line_notify(f"{symbol}: {signal}")
        except Exception as e:
            print(f"{datetime.now()}: Error analyzing {symbol}: {str(e)}", flush=True)
    
    if signals:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"ema.txt"
        save_to_file(signals, filename)
        print(f"{datetime.now()}: Analysis complete. Results saved to {filename}", flush=True)
    else:
        print(f"{datetime.now()}: Analysis complete. No signals detected.", flush=True)

def main():
    print("Starting EMA Crossover Trading Strategy", flush=True)
    print("The program will run every hour.", flush=True)
    analyze_all_symbols()
    schedule.every(15).minutes.do(analyze_all_symbols)

    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except Exception as e:
            print(f"An error occurred: {str(e)}", flush=True)
            send_line_notify(f"An error occurred: {str(e)}")
            time.sleep(60)

if __name__ == "__main__":
    main()
