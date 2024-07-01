import os
import time
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from binance.client import Client
from binance.exceptions import BinanceAPIException
import requests

# ตั้งค่า API keys
api_key = os.getenv('BINANCE_API_KEY')
api_secret = os.getenv('BINANCE_SECRET_KEY')
line_notify_token = os.getenv('LINE_NOTIFY_TOKEN')

# สร้าง Binance client
client = Client(api_key, api_secret)

def get_klines(symbol, interval, limit):
    try:
        klines = client.futures_klines(symbol=symbol, interval=interval, limit=limit)
        df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)
        return df
    except BinanceAPIException as e:
        print(f"Error fetching data: {e}")
        return None

def calculate_support_resistance(df, window=20, num_levels=3):
    levels = []
    for i in range(num_levels):
        high_level = df['high'].rolling(window=window).max().iloc[-1]
        low_level = df['low'].rolling(window=window).min().iloc[-1]
        levels.append((high_level, low_level))
        window *= 2
    return levels

def plot_wave(df, levels):
    plt.figure(figsize=(12, 6))
    plt.plot(df['timestamp'], df['close'], label='Close Price')
    
    colors = ['r', 'g', 'b']
    for i, (high, low) in enumerate(levels):
        plt.axhline(y=high, color=colors[i], linestyle='--', alpha=0.5, label=f'Resistance {i+1}')
        plt.axhline(y=low, color=colors[i], linestyle=':', alpha=0.5, label=f'Support {i+1}')
    
    plt.title('BTC/USDT Price with Support and Resistance Levels')
    plt.xlabel('Time')
    plt.ylabel('Price')
    plt.legend()
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig('btc_wave.png')
    plt.close()

def send_line_notify(message, image_path=None):
    url = 'https://notify-api.line.me/api/notify'
    headers = {'Authorization': f'Bearer {line_notify_token}'}
    payload = {'message': message}
    files = {'imageFile': open(image_path, 'rb')} if image_path else None
    try:
        requests.post(url, headers=headers, data=payload, files=files)
    except requests.exceptions.RequestException as e:
        print(f"Error sending Line notification: {e}")

def get_futures_symbols():
    exchange_info = client.futures_exchange_info()
    symbols = [symbol['symbol'] for symbol in exchange_info['symbols'] if symbol['status'] == 'TRADING']
    return symbols

def main():
    interval = Client.KLINE_INTERVAL_15MINUTE
    limit = 1000

    symbols = get_futures_symbols()
    symbols = [symbol for symbol in symbols if 'USDT' in symbol and not any(char.isdigit() for char in symbol)]
    
    while True:
        for symbol in symbols:
            df = get_klines(symbol, interval, limit)
            
            if df is not None:
                levels = calculate_support_resistance(df)
                plot_wave(df, levels)
                
                current_price = float(df['close'].iloc[-1])
                previous_price = float(df['close'].iloc[-2])
                
                for i, (resistance, support) in enumerate(levels):
                    if current_price > resistance and previous_price <= resistance:
                        message = f"LONG signal: {symbol} price ({current_price}) broke above resistance {i+1} ({resistance})"
                        send_line_notify(message, 'btc_wave.png')
                    elif current_price < support and previous_price >= support:
                        message = f"SHORT signal: {symbol} price ({current_price}) broke below support {i+1} ({support})"
                        send_line_notify(message, 'btc_wave.png')
                
                print(f"{symbol} Current price: {current_price}")
                print("Support/Resistance levels:")
                for i, (resistance, support) in enumerate(levels):
                    print(f"Level {i+1}: Resistance: {resistance}, Support: {support}")
        
        time.sleep(900)  # รอ 15 นาที

if __name__ == "__main__":
    main()