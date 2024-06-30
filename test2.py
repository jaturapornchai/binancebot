import os
from dotenv import load_dotenv
import pandas as pd
import numpy as np
from binance.client import Client
from binance.enums import *
import time
from datetime import datetime, timedelta
import requests

# Load environment variables
load_dotenv()
api_key = os.getenv('BINANCE_API_KEY')
api_secret = os.getenv('BINANCE_SECRET_KEY')
line_notify_token = os.getenv('LINE_NOTIFY_TOKEN')

# Initialize Binance client
client = Client(api_key, api_secret)

# Color codes
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RESET = '\033[0m'

def send_line_notify(message):
    """Send notifications through LINE Notify."""
    headers = {
        'Authorization': f'Bearer ' + line_notify_token,
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    payload = {'message': message}
    response = requests.post("https://notify-api.line.me/api/notify", headers=headers, params=payload)
    return response.status_code

def get_futures_symbols():
    exchange_info = client.futures_exchange_info()
    symbols = [symbol['symbol'] for symbol in exchange_info['symbols'] if symbol['status'] == 'TRADING']
    return symbols

def get_historical_klines(symbol, interval, limit=500):
    klines = client.futures_klines(symbol=symbol, interval=interval, limit=limit)
    df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
    df = df.astype({'open': 'float', 'high': 'float', 'low': 'float', 'close': 'float', 'volume': 'float'})
    df.set_index('timestamp', inplace=True)
    return df

def calculate_ema(data, period):
    return data.ewm(span=period, adjust=False).mean()

def calculate_rsi(data, period):
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def add_indicators(df):
    df['ema20'] = calculate_ema(df['close'], 20)
    df['ema50'] = calculate_ema(df['close'], 50)
    df['rsi'] = calculate_rsi(df['close'], 14)
    return df

def find_elliott_waves(data):
    waves = []
    wave_count = 0
    trend = 'unknown'
    corrective_wave = False

    for i in range(2, len(data)):
        if trend == 'unknown':
            if data['close'].iloc[i] > data['close'].iloc[i-1] > data['close'].iloc[i-2]:
                trend = 'up'
                waves.append(('1', i-2, i))
                wave_count = 1
            elif data['close'].iloc[i] < data['close'].iloc[i-1] < data['close'].iloc[i-2]:
                trend = 'down'
                waves.append(('1', i-2, i))
                wave_count = 1

        elif trend == 'up':
            if not corrective_wave:
                if wave_count == 1 and data['close'].iloc[i] < data['close'].iloc[i-1]:
                    waves.append(('2', waves[-1][2], i))
                    wave_count = 2
                elif wave_count == 2 and data['close'].iloc[i] > data['close'].iloc[waves[-2][2]]:
                    waves.append(('3', waves[-1][2], i))
                    wave_count = 3
                elif wave_count == 3 and data['close'].iloc[i] < data['close'].iloc[i-1]:
                    waves.append(('4', waves[-1][2], i))
                    wave_count = 4
                elif wave_count == 4 and data['close'].iloc[i] > data['close'].iloc[waves[-2][2]]:
                    waves.append(('5', waves[-1][2], i))
                    corrective_wave = True
                    wave_count = 0
            else:
                if wave_count == 0 and data['close'].iloc[i] < data['close'].iloc[i-1]:
                    waves.append(('a', waves[-1][2], i))
                    wave_count = 1
                elif wave_count == 1 and data['close'].iloc[i] > data['close'].iloc[i-1]:
                    waves.append(('b', waves[-1][2], i))
                    wave_count = 2
                elif wave_count == 2 and data['close'].iloc[i] < data['close'].iloc[waves[-2][2]]:
                    waves.append(('c', waves[-1][2], i))
                    trend = 'unknown'
                    corrective_wave = False
                    wave_count = 0

        elif trend == 'down':
            if not corrective_wave:
                if wave_count == 1 and data['close'].iloc[i] > data['close'].iloc[i-1]:
                    waves.append(('2', waves[-1][2], i))
                    wave_count = 2
                elif wave_count == 2 and data['close'].iloc[i] < data['close'].iloc[waves[-2][2]]:
                    waves.append(('3', waves[-1][2], i))
                    wave_count = 3
                elif wave_count == 3 and data['close'].iloc[i] > data['close'].iloc[i-1]:
                    waves.append(('4', waves[-1][2], i))
                    wave_count = 4
                elif wave_count == 4 and data['close'].iloc[i] < data['close'].iloc[waves[-2][2]]:
                    waves.append(('5', waves[-1][2], i))
                    corrective_wave = True
                    wave_count = 0
            else:
                if wave_count == 0 and data['close'].iloc[i] > data['close'].iloc[i-1]:
                    waves.append(('a', waves[-1][2], i))
                    wave_count = 1
                elif wave_count == 1 and data['close'].iloc[i] < data['close'].iloc[i-1]:
                    waves.append(('b', waves[-1][2], i))
                    wave_count = 2
                elif wave_count == 2 and data['close'].iloc[i] > data['close'].iloc[waves[-2][2]]:
                    waves.append(('c', waves[-1][2], i))
                    trend = 'unknown'
                    corrective_wave = False
                    wave_count = 0

    return waves

def analyze_elliott_wave(symbol, interval):
    try:
        data = get_historical_klines(symbol, interval)
        data = add_indicators(data)
        waves = find_elliott_waves(data)

        if not waves:
            return 'No clear Elliott Wave pattern', 'neutral', None

        last_wave = waves[-1]
        wave_type, start_idx, end_idx = last_wave

        # Check if the wave completed within the last 45 minutes (3 periods of 15 minutes)
        last_45_minutes = data.index[-1] - timedelta(minutes=45)
        if data.index[end_idx] < last_45_minutes:
            return 'No recent Elliott Wave pattern', 'neutral', None

        if wave_type == 'b':
            return f'Potential Wave B complete (Prepare for Short)', 'short_alert', wave_type
        
        return f'Current wave: {wave_type.upper()}', 'neutral', wave_type

    except Exception as e:
        print(f"Error analyzing Elliott Wave for {symbol}: {e}")
        return 'Error', 'neutral', None

def main():
    interval = Client.KLINE_INTERVAL_1HOUR

    while True:
        try:
            symbols = get_futures_symbols()
            symbols = [symbol for symbol in symbols if 'USDT' in symbol and not any(char.isdigit() for char in symbol)]
            elliott_signals = {}

            print(f"Analyzing Elliott Waves for {len(symbols)} symbols...")

            for symbol in symbols:
                analysis, signal, wave = analyze_elliott_wave(symbol, interval)
                elliott_signals[symbol] = (analysis, signal, wave)
                
                if signal == 'short_alert':
                    print(f"{RED}{symbol}: {analysis}{RESET}")
                    
                    # Prepare and send LINE notification
                    notification_message = f"{symbol}: {analysis}\nPrepare for SHORT"
                    send_line_notify(notification_message)

                # Small delay to avoid hitting rate limits
                time.sleep(0.5)

            print(f"\nElliott Wave analysis summary:")
            for symbol, (analysis, signal, wave) in elliott_signals.items():
                if signal == 'short_alert':
                    print(f"{RED}{symbol}: {analysis}{RESET}")
                elif wave in ['1', '3', '5']:
                    print(f"{GREEN}{symbol}: {analysis}{RESET}")
                elif wave in ['2', '4', 'a', 'b', 'c']:
                    print(f"{RED}{symbol}: {analysis}{RESET}")
            
            print(f"Total symbols analyzed: {len(elliott_signals)}")
            print(f"Symbols with Wave B alerts: {sum(1 for _, signal, _ in elliott_signals.values() if signal == 'short_alert')}")

            # Wait for 15 minutes before checking again
            print(f"Analysis completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"Waiting for 15 minutes before next analysis...")
            time.sleep(900)  # 15 minutes = 900 seconds
        except Exception as e:
            print(f"An error occurred: {e}")
            print("Retrying in 1 minute...")
            time.sleep(60)  # Wait for 1 minute before retrying

if __name__ == "__main__":
    main()