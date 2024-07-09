import datetime
import ccxt
import pandas as pd
from datetime import datetime
import requests
from binance.client import Client
import time
import os
import numpy as np
from sklearn.linear_model import LinearRegression

# Configure API key authorization
api_key = os.getenv('BINANCE_API_KEY')
api_secret = os.getenv('BINANCE_SECRET_KEY')
client = Client(api_key, api_secret)
exchange = ccxt.binance()
ignore_symbols = ['DONUSDT', 'USDCUSDT', 'SRMUSDT']
line_token = "aMFv92TD5VFEXQ3fU9gN1sAaWWrkyVoo6VlJe95hvE7"
line_message = ""

def send_line_notify(message, token=line_token):
    try:
        """Send notifications through LINE Notify."""
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        payload = {'message': "\n"+message}
        response = requests.post("https://notify-api.line.me/api/notify", headers=headers, params=payload)
        if response.status_code == 200:
            print("LINE notification sent successfully", flush=True)
        else:
            print(f"Failed to send LINE notification. Status code: {response.status_code}", flush=True)
    except Exception as e:
        print(f"Error sending LINE message: {e}", flush=True)

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
    global line_message
    
    print("Start check signal : " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"), flush=True)
    symbols = fetch_future_symbols()
    for symbol in symbols:
        try:
            signal = check_signal(symbol, tread_time_frame, window, devlen)
            if signal != 'normal':
                if signal == 'breakout_up':
                    icon = "🟢"  # Green circle for LONG
                    color = "green"
                elif signal == 'breakout_down':
                    icon = "🔴"  # Red circle for SHORT
                    color = "red"
                
                message = f"{icon} Symbol: {symbol}, Signal: {signal} : {tread_time_frame}"
                print(message, flush=True)
                line_message += f'Symbol: {symbol}, Signal: {signal} : {tread_time_frame}\n'
        except Exception as e:
            print(f"Error: {e}", flush=True)    
            continue    
          
tread_time_frame = '1h'
print("\033[H\033[J")
first = True
while True:    
    try:
        date_time_now = datetime.now()
        last_minute = date_time_now.minute
        if last_minute == 0 or first:
            print("\033[H\033[J")
            line_message = ""
            first = False
            future_find_signal(tread_time_frame)
            if line_message != "":
                send_line_notify(line_message, line_token)
            time.sleep(120)
    except Exception as e:
        send_line_notify(f"Error: {e}")
        print(f"Error: {e}", flush=True)
    time.sleep(10)
