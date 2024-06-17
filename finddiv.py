import datetime
import ccxt
import pandas as pd
from datetime import datetime
import requests
from binance.client import Client
import time

# Configure API key authorization
api_key = 'wpq57Bbcr4Wg1jW6iZt5qJ46YEewH7E89eyz31185wqqOjQt1r9n4a3mj1yLUmdN'
api_secret = '8wuq8dMQOdsHMOSgjDLQYsPQF3J8CtdMSXu7VrB6ZNhS4VJ94ZM4b5qfu20jtnLU'
client = Client(api_key, api_secret)
tread_time_frame = '1h'
exchange = ccxt.binance()
ignore_symbols = ['DONUSDT', 'USDCUSDT', 'SRMUSDT']
line_token = "cbBeuaCxvJcxe1wxovmMADeRsnktbFvyLizTceJpzbh"

def send_line_notify(message):
    """Send notifications through LINE Notify."""
    headers = {
        'Authorization': f'Bearer ' + line_token,
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    payload = {'message': message}
    response = requests.post("https://notify-api.line.me/api/notify", headers=headers, params=payload)
    return response.status_code

def fetch_future_symbols():
    info = client.futures_exchange_info()
    symbols = [item['symbol'] for item in info['symbols'] if 'USDT' in item['symbol'] and item['status'] == 'TRADING']
    symbols = [symbol for symbol in symbols if not any(char.isdigit() for char in symbol)]
    symbols = [symbol for symbol in symbols if symbol not in ignore_symbols]
    symbols.sort()    
    return symbols

def rsi(df, periods=14, ema=True):
    close_delta = df['close'].diff()
    
    if ema:
        up = close_delta.clip(lower=0)
        down = -1 * close_delta.clip(upper=0)
        ma_up = up.ewm(com=periods-1, adjust=True, min_periods=periods).mean()
        ma_down = down.ewm(com=periods-1, adjust=True, min_periods=periods).mean()
    else:
        up = close_delta[close_delta > 0].reindex_like(df)
        down = -1 * close_delta[close_delta < 0].reindex_like(df)
        ma_up = up.rolling(window=periods, min_periods=0).mean()
        ma_down = down.rolling(window=periods, min_periods=0).mean()
    
    rs = ma_up / ma_down
    return 100 - (100 / (1 + rs))

def find_swing_points(data, rsi_col='rsi', lb=5):
    swing_highs = []
    swing_lows = []
    
    for i in range(lb, len(data) - lb):
        if data[rsi_col].iloc[i] == max(data[rsi_col].iloc[i - lb:i + lb + 1]):
            swing_highs.append((data.index[i], data[rsi_col].iloc[i]))
        if data[rsi_col].iloc[i] == min(data[rsi_col].iloc[i - lb:i + lb + 1]):
            swing_lows.append((data.index[i], data[rsi_col].iloc[i]))
    
    return swing_highs, swing_lows

def find_divergence(data, swing_highs, swing_lows):
    divergences = {'bullish': [], 'bearish': []}
    
    for i in range(1, len(swing_lows)):
        if swing_lows[i][1] > swing_lows[i - 1][1] and data['close'][swing_lows[i][0]] < data['close'][swing_lows[i - 1][0]]:
            divergences['bullish'].append(swing_lows[i])
    
    for i in range(1, len(swing_highs)):
        if swing_highs[i][1] < swing_highs[i - 1][1] and data['close'][swing_highs[i][0]] > data['close'][swing_highs[i - 1][0]]:
            divergences['bearish'].append(swing_highs[i])
    
    return divergences

def check_div_signal(symbol):
    # จำนวนแท่งข้อมูลที่ดึงต่อครั้ง
    limit = 1000  
    # ดึงข้อมูลย้อนหลัง 10 วัน
    since = exchange.milliseconds() - 1000 * 60 * 60 * 24 * 10  

    # ดึงข้อมูลในช่วงเวลาที่กำหนด
    bars = []
    while True:
        ohlcv = exchange.fetch_ohlcv(symbol, tread_time_frame, since, limit)
        if not ohlcv:
            break
        since = ohlcv[-1][0] + 1
        bars.extend(ohlcv)
        if len(ohlcv) < limit:
            break

    data = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    data['timestamp'] = pd.to_datetime(data['timestamp'], unit='ms')
    data.set_index('timestamp', inplace=True)

    data['rsi'] = rsi(data, periods=14)
    swing_highs, swing_lows = find_swing_points(data)
    divergences = find_divergence(data, swing_highs, swing_lows)

    latest_divergence = None

    if divergences['bullish']:
        latest_bullish_divergence = divergences['bullish'][-1][0]
        time_since_bullish = (data.index[-1] - latest_bullish_divergence) // pd.Timedelta(minutes=60)
        if time_since_bullish < 6:
            latest_divergence = 'long'

    if divergences['bearish']:
        latest_bearish_divergence = divergences['bearish'][-1][0]
        time_since_bearish = (data.index[-1] - latest_bearish_divergence) // pd.Timedelta(minutes=60)
        if time_since_bearish < 6:
            latest_divergence = 'short'

    if not latest_divergence:
        latest_divergence = 'normal'

    return latest_divergence

def future_find_signal():
    print("Start check signal : " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"), flush=True)
    symbols = fetch_future_symbols()
    for symbol in symbols:
        try:
            signal = check_div_signal(symbol)
            if signal == 'short':
                print(f"Symbol: {symbol}, Signal: {signal}", flush=True)

            if signal == 'long':
                print(f"Symbol: {symbol}, Signal: {signal}", flush=True)
        except Exception as e:
            print(f"Error: {e}", flush=True)    
            continue    
    print("End check signal : " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"), flush=True)

def future_get_balance():
    balance = client.futures_account_balance()
    balance_asset = 0
    for item in balance:
        if item['asset'] == 'USDT':
            balance_asset = float(item['balance'])
            break
    print(f"Balance USDT: {balance_asset}", flush=True)  
    return balance_asset

# clear screen terminal
print("\033[H\033[J")
future_find_signal()
