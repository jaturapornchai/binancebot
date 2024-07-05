import datetime
import ccxt
import pandas as pd
from datetime import datetime
import requests
from binance.client import Client
import time
import numpy as np
from sklearn.linear_model import LinearRegression

# Configure API key authorization
api_key = os.getenv('BINANCE_API_KEY')
api_secret = os.getenv('BINANCE_SECRET_KEY')
client = Client(api_key, api_secret)
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

def linear_regression_channel(data, window, devlen):
    X = np.arange(window).reshape(-1, 1)
    model = LinearRegression()
    upper_bound = []
    lower_bound = []
    middle = []
    for i in range(len(data) - window + 1):
        y = data[i:i+window]
        model.fit(X, y)
        trend = model.predict(X)
        residuals = y - trend
        std_res = np.std(residuals)
        middle.append(trend[-1])
        upper_bound.append(trend[-1] + std_res * devlen)
        lower_bound.append(trend[-1] - std_res * devlen)
    return middle, upper_bound, lower_bound

def check_breakout(data, upper_bound, lower_bound):
    if data[-1] > upper_bound[-1]:
        return 'breakout_up'
    elif data[-1] < lower_bound[-1]:
        return 'breakout_down'
    else:
        return 'normal'

def check_signal(symbol, tread_time_frame='1h', window=100, devlen=2):
    limit = 1000  
    since = exchange.milliseconds() - 1000 * 60 * 60 * 24 * 20  

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
    
    close_prices = data['close'].values
    middle, upper_bound, lower_bound = linear_regression_channel(close_prices, window, devlen)

    return check_breakout(close_prices, upper_bound, lower_bound)

def future_find_signal(tread_time_frame, window=100, devlen=2):
    print("Start check signal : " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"), flush=True)
    symbols = fetch_future_symbols()
    for symbol in symbols:
        try:
            signal = check_signal(symbol, tread_time_frame, window, devlen)
            if signal != 'normal':
                message = f"Symbol: {symbol}, Signal: {signal} : {tread_time_frame}"
                print(message, flush=True)
                send_line_notify(message)
        except Exception as e:
            print(f"Error: {e}", flush=True)    
            continue    
    print("End check signal : " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"), flush=True)

tread_time_frame = '4h'
print("\033[H\033[J")
future_find_signal(tread_time_frame)
while True:    
    try:
        date_time_now = datetime.now()
        last_minute = date_time_now.minute
        if last_minute == 0:
            future_find_signal(tread_time_frame)
            time.sleep(120)
    except Exception as e:
        send_line_notify(f"Error: {e}")
        print(f"Error: {e}", flush=True)
    time.sleep(10)
