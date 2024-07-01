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

def get_historical_klines(symbol, interval, limit=1000):
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

def detect_divergence(data, window=None):
    if window is None:
        window = len(data) // 10  # Use 10% of the data length as default window

    price_highs = data['high'].rolling(window=window, center=True).max()
    price_lows = data['low'].rolling(window=window, center=True).min()
    
    rsi_highs = data['rsi'].rolling(window=window, center=True).max()
    rsi_lows = data['rsi'].rolling(window=window, center=True).min()
    
    bullish_div = (price_lows.diff() < 0) & (rsi_lows.diff() > 0)
    bearish_div = (price_highs.diff() > 0) & (rsi_highs.diff() < 0)
    
    return bullish_div, bearish_div

def analyze_elliott_wave(symbol, interval):
    try:
        data = get_historical_klines(symbol, interval)
        data = add_indicators(data)
        waves = find_elliott_waves(data)
        
        bullish_div, bearish_div = detect_divergence(data)

        if not waves:
            return f'No clear Elliott Wave pattern ({interval})', 'neutral', None

        last_wave = waves[-1]
        wave_type, start_idx, end_idx = last_wave

        # Check if the wave completed within the last 3 periods
        last_3_periods = data.index[-1] - pd.Timedelta(interval) * 3
        if data.index[end_idx] < last_3_periods:
            return f'No recent Elliott Wave pattern ({interval})', 'neutral', None

        if wave_type == 'b' and bearish_div.iloc[-1]:
            return f'Potential Wave B complete with bearish divergence (Strong Short) ({interval})', 'strong_short_alert', wave_type
        elif wave_type == 'b':
            return f'Potential Wave B complete (Prepare for Short) ({interval})', 'short_alert', wave_type
        elif wave_type == '2' and bullish_div.iloc[-1]:
            return f'Potential Wave 2 complete with bullish divergence (Strong Long) ({interval})', 'strong_long_alert', wave_type
        elif wave_type == '2':
            return f'Potential Wave 2 complete (Prepare for Long) ({interval})', 'long_alert', wave_type
        
        return f'Current wave: {wave_type.upper()} ({interval})', 'neutral', wave_type

    except Exception as e:
        print(f"Error analyzing Elliott Wave for {symbol} on {interval}: {e}")
        return f'Error ({interval})', 'neutral', None

def main():
    intervals = [
        Client.KLINE_INTERVAL_1HOUR,
        Client.KLINE_INTERVAL_4HOUR,
        Client.KLINE_INTERVAL_1DAY
    ]

    firsttime = True

    while True:
        now = datetime.now()
        
        # ตรวจสอบว่าอยู่ใน 5 นาทีแรกของชั่วโมงหรือไม่
        if now.minute < 5 or firsttime:
            firsttime = False
            try:
                symbols = get_futures_symbols()
                symbols = [symbol for symbol in symbols if 'USDT' in symbol and not any(char.isdigit() for char in symbol)]
                
                all_signals = {}

                for interval in intervals:
                    print(f"\nAnalyzing Elliott Waves and Divergences for {len(symbols)} symbols on {interval} timeframe...")

                    for symbol in symbols:
                        analysis, signal, wave = analyze_elliott_wave(symbol, interval)
                        
                        if symbol not in all_signals:
                            all_signals[symbol] = []
                        
                        all_signals[symbol].append((interval, analysis, signal, wave))

                        # Small delay to avoid hitting rate limits
                        time.sleep(0.5)

                print("\nSummary of signals across all timeframes:")
                for symbol, signals in all_signals.items():
                    # Check if all signals are "No recent Elliott Wave pattern"
                    if all("No recent Elliott Wave pattern" in analysis for _, analysis, _, _ in signals):
                        continue  # Skip this symbol and move to the next one

                    print(f"\n{symbol}:")
                    for interval, analysis, signal, wave in signals:
                        if signal in ['strong_short_alert', 'short_alert']:
                            print(f"  {RED}{interval}: {analysis}{RESET}")
                        elif signal in ['strong_long_alert', 'long_alert']:
                            print(f"  {GREEN}{interval}: {analysis}{RESET}")
                        elif wave in ['1', '3', '5']:
                            print(f"  {GREEN}{interval}: {analysis}{RESET}")
                        elif wave in ['2', '4', 'a', 'b', 'c']:
                            print(f"  {RED}{interval}: {analysis}{RESET}")
                        else:
                            print(f"  {interval}: {analysis}")
                    
                    # ส่งการแจ้งเตือนสำหรับสัญญาณที่น่าสนใจ
                    important_signals = [s for s in signals if s[2] in ['strong_short_alert', 'short_alert', 'strong_long_alert', 'long_alert']]
                    if important_signals:
                        notification_message = f"{symbol} Signals:\n" + "\n".join([f"{interval}: {analysis}" for interval, analysis, _, _ in important_signals])
                        send_line_notify(notification_message)

                print(f"\nAnalysis completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                
                # รอจนกว่าจะถึงชั่วโมงถัดไป
                next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
                sleep_time = (next_hour - datetime.now()).total_seconds()
                print(f"Waiting for {sleep_time:.2f} seconds until next analysis...")
                time.sleep(sleep_time)
            
            except Exception as e:
                print(f"An error occurred: {e}")
                print("Retrying in 1 minute...")
                time.sleep(60)
        else:
            # รอจนกว่าจะถึง 5 นาทีแรกของชั่วโมงถัดไป
            next_analysis = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            sleep_time = (next_analysis - now).total_seconds()
            print(f"Waiting for {sleep_time:.2f} seconds until next analysis window...")
            time.sleep(sleep_time)

if __name__ == "__main__":
    main()