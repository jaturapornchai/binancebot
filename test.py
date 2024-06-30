import os
from dotenv import load_dotenv
import pandas as pd
import numpy as np
from binance.client import Client
from binance.enums import *
import time
from datetime import datetime

# Load environment variables
load_dotenv()
api_key = os.getenv('BINANCE_API_KEY')
api_secret = os.getenv('BINANCE_SECRET_KEY')

# Initialize Binance client
client = Client(api_key, api_secret)

# Color codes
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'

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

def find_swing_points(data, window=5):
    swing_highs = []
    swing_lows = []
    
    for i in range(window, len(data) - window):
        if all(data['high'].iloc[i] > data['high'].iloc[i-j] for j in range(1, window+1)) and \
           all(data['high'].iloc[i] > data['high'].iloc[i+j] for j in range(1, window+1)):
            swing_highs.append(i)
        
        if all(data['low'].iloc[i] < data['low'].iloc[i-j] for j in range(1, window+1)) and \
           all(data['low'].iloc[i] < data['low'].iloc[i+j] for j in range(1, window+1)):
            swing_lows.append(i)
    
    return swing_highs, swing_lows

def check_trend(data, swing_highs, swing_lows):
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return 'neutral'
    
    last_two_highs = data['high'].iloc[swing_highs[-2:]]
    last_two_lows = data['low'].iloc[swing_lows[-2:]]
    
    if last_two_highs.iloc[1] < last_two_highs.iloc[0] and last_two_lows.iloc[1] < last_two_lows.iloc[0]:
        return 'downtrend'
    elif last_two_highs.iloc[1] > last_two_highs.iloc[0] and last_two_lows.iloc[1] > last_two_lows.iloc[0]:
        return 'uptrend'
    else:
        return 'neutral'

def calculate_atr(data, period=14):
    high_low = data['high'] - data['low']
    high_close = np.abs(data['high'] - data['close'].shift())
    low_close = np.abs(data['low'] - data['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    return true_range.rolling(period).mean()

def check_entry_signal(symbol, interval):
    try:
        data = get_historical_klines(symbol, interval)
        swing_highs, swing_lows = find_swing_points(data)
        trend = check_trend(data, swing_highs, swing_lows)
        
        # Calculate ATR
        data['atr'] = calculate_atr(data)
        
        # Check if the last swing point is within the last 12 candles (3 hours in 15-minute timeframe)
        recent_swing = max(swing_highs + swing_lows)
        if recent_swing >= len(data) - 12:
            current_price = data['close'].iloc[-1]
            last_swing_high = data['high'].iloc[swing_highs[-1]]
            last_swing_low = data['low'].iloc[swing_lows[-1]]
            
            # Calculate distance from current price to swing points in terms of ATR
            atr = data['atr'].iloc[-1]
            distance_to_high = (last_swing_high - current_price) / atr
            distance_to_low = (current_price - last_swing_low) / atr
            
            if trend == 'downtrend' and distance_to_high <= 1.5:
                return 'short'
            elif trend == 'uptrend' and distance_to_low <= 1.5:
                return 'long'
        
        return 'normal'
    except Exception as e:
        print(f"Error checking entry signal for {symbol}: {e}")
        return 'error'

def main():
    interval = Client.KLINE_INTERVAL_15MINUTE
    
    while True:
        try:
            symbols = get_futures_symbols()
            entry_signals = {}
            
            print(f"Checking entry signals for {len(symbols)} symbols...")
            
            for symbol in symbols:
                signal = check_entry_signal(symbol, interval)
                if signal != 'normal' and signal != 'error':
                    if signal == 'long':
                        print(f"{GREEN}{symbol}: Potential LONG entry{RESET}")
                    elif signal == 'short':
                        print(f"{RED}{symbol}: Potential SHORT entry{RESET}")
                    entry_signals[symbol] = signal
                
                # Small delay to avoid hitting rate limits
                time.sleep(0.5)
            
            print(f"\nEntry signals summary:")
            for symbol, signal in entry_signals.items():
                if signal == 'long':
                    print(f"{GREEN}{symbol}: Potential LONG entry{RESET}")
                elif signal == 'short':
                    print(f"{RED}{symbol}: Potential SHORT entry{RESET}")
            print(f"Total symbols with entry signals: {len(entry_signals)}")
            
            # Wait for 15 minutes before checking again
            print(f"Check completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{YELLOW}Waiting for 15 minutes before next check...{RESET}")
            time.sleep(900)  # 15 minutes = 900 seconds
        except Exception as e:
            print(f"An error occurred: {e}")
            print("Retrying in 1 minute...")
            time.sleep(60)  # Wait for 1 minute before retrying

if __name__ == "__main__":
    main()