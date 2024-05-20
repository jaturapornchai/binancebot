from sklearn.linear_model import LinearRegression
import os
import time
import ccxt
import numpy as np
import pandas as pd
from binance.client import Client
import requests
from scipy.stats import linregress

api_key = 'FpwthNz84887fuWpz9lEIsLm1zwZB9YV8ZO2FjVQ6v2k6lmR8nv1oKZZOoJSY0il'
api_secret = 'nszlVyvoFAZPVIXdWnJyhaxgiujMTTUmFN4Ncix3rKBtLhF2kO8hhCZhnwIeu3gt'
line_token = "cbBeuaCxvJcxe1wxovmMADeRsnktbFvyLizTceJpzbh"
ignore_symbols = ['DONUSDT','USDCUSDT','SRMUSDT','MOVRUSDT']
save_symbols = []
exchange = ccxt.binance({
    'apiKey': api_key,
    'secret': api_secret
})

# Connect to Binance
client = Client(api_key, api_secret)

def send_line_notify(message):
    headers = {
        'Authorization': f'Bearer {line_token}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    payload = {'message': message}
    requests.post("https://notify-api.line.me/api/notify", headers=headers, params=payload)

def fetch_future_symbols():
    info = client.futures_exchange_info()
    symbols = [item['symbol'] for item in info['symbols'] if 'USDT' in item['symbol'] and item['status'] == 'TRADING']
    symbols = [symbol for symbol in symbols if not any(char.isdigit() for char in symbol)]
    symbols = [symbol for symbol in symbols if symbol not in ignore_symbols]
    symbols.sort()
    return symbols


# Function to fetch historical data from Binance
def fetch_binance_data(symbol, interval):
    url = 'https://api.binance.com/api/v3/klines'
    params = {
        'symbol': symbol,
        'interval': interval,
        'limit': 500
    }
    response = requests.get(url, params=params)
    data = response.json()
    df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
    df['close'] = df['close'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    return df

# RSI calculation
def rsi(df, period=14):
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# Checking for pivot points
def pivot_points(series, lbL, lbR, type='low'):
    rolled_series = series.rolling(window=lbL + lbR + 1, center=True)
    if type == 'low':
        return (rolled_series.min() == series).to_numpy()
    else:
        return (rolled_series.max() == series).to_numpy()

# Main function to detect divergences
def find_divergences(symbol):
    df = fetch_binance_data(symbol, '1h')
    df['rsi'] = rsi(df)

    lbL, lbR = 5, 5

    # Finding pivot points
    rsi_pivot_lows = pivot_points(df['rsi'], lbL, lbR, 'low')
    rsi_pivot_highs = pivot_points(df['rsi'], lbL, lbR, 'high')
    price_pivot_lows = pivot_points(df['low'], lbL, lbR, 'low')
    price_pivot_highs = pivot_points(df['high'], lbL, lbR, 'high')

    # Comparing pivot points
    regular_bullish = np.any(rsi_pivot_lows[-(lbR + 1):] & ~price_pivot_lows[-(lbR + 1):])
    hidden_bullish = np.any(rsi_pivot_lows[-(lbR + 1):] & price_pivot_lows[-(lbR + 1):])
    regular_bearish = np.any(rsi_pivot_highs[-(lbR + 1):] & ~price_pivot_highs[-(lbR + 1):])
    hidden_bearish = np.any(rsi_pivot_highs[-(lbR + 1):] & price_pivot_highs[-(lbR + 1):])

    # Generating Alert Messages
    if regular_bullish:
        return "Regular Bullish Divergence Detected"
    elif hidden_bullish:
        return "Hidden Bullish Divergence Detected"
    elif regular_bearish:
        return "Regular Bearish Divergence Detected"
    elif hidden_bearish:
        return "Hidden Bearish Divergence Detected"
    else:
        return ""
    
if __name__ == "__main__":
    future_symbols = [symbol for symbol in fetch_future_symbols() if '_' not in symbol and not any(char.isdigit() for char in symbol)]
    print(f'Checking {len(future_symbols)} symbols...')
    file_name = 'listcoinall.txt'
    # try delete file
    try:
        os.remove(file_name)
    except:
        pass
    # save to listcoin.txt
    with open(file_name, 'w') as f:
        for item in future_symbols:
            f.write("%s.p\n" % item)
    while True:
        if int(time.strftime('%M')) % 15 == 0 or 1 == 1:
            for symbol in future_symbols:
                try:        
                    signal = find_divergences(symbol)
                    if (signal != ""):
                        print(f'\033[94m{symbol} มีสัญญาณ {signal}\033[0m')
                        save_symbols.append(symbol)
                    if signal == 'long':
                        # font blue
                        print(f'\033[94m{symbol} มีสัญญาณ Long\033[0m')
                        save_symbols.append(symbol)
                        send_line_notify(f'{symbol} มีสัญญาณ Long')
                    elif signal == 'short':
                        # font red
                        print(f'\033[91m{symbol} มีสัญญาณ Short\033[0m')                        
                        save_symbols.append(symbol)
                        send_line_notify(f'{symbol} มีสัญญาณ Short')
                    else:
                        # แสดงจุด ไม่ขึ้นบรรทัดใหม่
                        pass

                except Exception as e:
                    print(f'Error processing {symbol}: {e}')
                    future_symbols.remove(symbol)
                
            if len(save_symbols) > 0:
                print(f'มีสัญญาณทั้งหมด {len(save_symbols)} สัญญาณ')
                file_name = 'listcoin.txt'
                # try delete file
                try:
                    os.remove(file_name)
                except:
                    pass
                # save to listcoin.txt
                with open(file_name, 'w') as f:
                    for item in save_symbols:
                        f.write("%s\n" % item)
        time.sleep(10)
        if int(time.strftime('%M')) % 4 == 0:
            # กรณี position หมด ให้ส่ง line notify
            print('Check position')
            positions = client.futures_position_information()
            count = 0
            for position in positions:
                position_amount = float(position['positionAmt'])
                if position_amount != 0:
                    count += 1
            if count == 0:
                send_line_notify('Position หมดแล้ว กรุณาเช็คด่วน')
        break
                        
