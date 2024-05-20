import time
import requests
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from datetime import datetime
import numpy as np
import requests
from scipy.stats import linregress
from binance.client import Client
import time
from scipy.stats import linregress
from bs4 import BeautifulSoup
import traceback
import concurrent.futures
import datetime
import random
import time
import ccxt
from binance.client import Client
from binance.enums import *
import requests
import pandas as pd
import requests
import talib
import ta
import numpy as np
import pandas_datareader as pdr
import datetime

api_key = 'FpwthNz84887fuWpz9lEIsLm1zwZB9YV8ZO2FjVQ6v2k6lmR8nv1oKZZOoJSY0il'
api_secret = 'nszlVyvoFAZPVIXdWnJyhaxgiujMTTUmFN4Ncix3rKBtLhF2kO8hhCZhnwIeu3gt'
client = Client(api_key, api_secret)
# LINE Notify token
line_token = "cbBeuaCxvJcxe1wxovmMADeRsnktbFvyLizTceJpzbh"
dollar_amount = 75  # Order amount in USD
leverage = 10
timeframe = '1h'
exchange = ccxt.binance()
future_symbols = []
spot_symbols = []
exchange_rate_thai = 0.0
ignore_symbols = ['DONUSDT','USDCUSDT','SRMUSDT']

def send_line_notify(message):
    headers = {
        'Authorization': f'Bearer {line_token}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    payload = {'message': message}
    response = requests.post("https://notify-api.line.me/api/notify", headers=headers, params=payload)
    return response.status_code

def get_exchange_rate_thai():
    url = 'https://www.x-rates.com/calculator/?from=USD&to=THB&amount=1'
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')

    rate = soup.find('span', class_='ccOutputTrail').previous_sibling
    # return double
    return float(rate)

def fetch_spot_symbols():
    url = "https://api.binance.com/api/v3/exchangeInfo"
    response = requests.get(url)
    data = response.json()

    symbols = []
    for symbol in data["symbols"]:
        if symbol["status"] == "TRADING" and symbol["isSpotTradingAllowed"] and symbol["symbol"].endswith("USDT"):
            symbols.append(symbol["symbol"])

    # remove ignore_symbols
    symbols = [symbol for symbol in symbols if symbol not in ignore_symbols]
    ## remove ถ้ามีคำว่า UPUSDT หรือ DOWNUSDT อยู่ในชื่อ symbol
    symbols = [symbol for symbol in symbols if 'UPUSDT' not in symbol]
    symbols = [symbol for symbol in symbols if 'DOWNUSDT' not in symbol]
    return symbols

def fetch_data(symbol, timeframe='1h', limit=500):
    exchange = ccxt.binance()  # Using Binance as the exchange
    candles = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    return df

# Calculate RSI
def calculate_rsi(df, period=14):
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    df['rsi'] = rsi
    return df

# Example of a simple breakout detection (to be adapted for your specific logic)
def detect_breakouts(df):
    # This is a placeholder function. You need to define how you detect breakouts based on RSI and trendlines.
    # For instance, you might look for RSI moving above a certain threshold or crossing a trendline you've defined.
    breakouts = df[df['rsi'] > 70]  # Simplified example: detecting when RSI goes above 70
    return breakouts

def find_break(symbol):
    # Fetch data
    df = fetch_data(symbol, timeframe)
    # Calculate RSI
    df = calculate_rsi(df)
    # Detect breakouts
    breakouts = detect_breakouts(df)
    return len(breakouts) > 0

if __name__ == "__main__":
    find_name = 'spot_symbols.txt'
    first = True
    found_symbols = []
    while True:
        # ดึงเวลาปัจจุบัน ทำงานเมื่อ ครบ 15 นาที นับจากเวลาที่เริ่มต้น ชั่วโมง
        now = datetime.datetime.now()
        if now.minute % 5 == 0 or first:
            if not first:
                time.sleep(30)
            first = False
            found_symbols_list_new = []
            try:
                spot_symbols = [symbol for symbol in fetch_spot_symbols() if '_' not in symbol and not any(char.isdigit() for char in symbol)]
                spot_symbols.sort()
                for symbol in spot_symbols:
                    if find_break(symbol):
                        if symbol not in found_symbols:
                            print(symbol)
                            found_symbols.append(symbol)
                            found_symbols_list_new.append(symbol + '\n')
                if len(found_symbols_list_new) > 0:
                    send_line_notify('Found symbols\n' + ''.join(found_symbols_list_new))
                # ลบไฟล์เดิมทิ้ง
                open(find_name, 'w').close()    
                with open(find_name, 'w') as f:
                    for symbol in found_symbols:
                        f.write(symbol + '\n')
                print('*** done ***')
                # รอ 60 วินาที
                time.sleep(60)
            except:
                print('error')        
        time.sleep(1)

