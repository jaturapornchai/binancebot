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

def fetch_symbols():
   # Use the futures API endpoint
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    response = requests.get(url)
    data = response.json()

    symbols = []
    for symbol in data["symbols"]:
        # Check if the symbol is open for trading and it's a perpetual contract (ends with 'USDT')
        if symbol["status"] == "TRADING" and symbol["contractType"] == "PERPETUAL" and symbol["symbol"].endswith("USDT"):
            symbols.append(symbol["symbol"])

    # Assuming ignore_symbols is defined somewhere
    # Remove ignore_symbols
    symbols = [symbol for symbol in symbols if symbol not in ignore_symbols]

    # Remove symbols that contain 'UPUSDT' or 'DOWNUSDT'
    symbols = [symbol for symbol in symbols if 'UPUSDT' not in symbol and 'DOWNUSDT' not in symbol]

    return symbols

def find_volume(symbol, timeframe='15m'):
    # Initialize the exchange - make sure to configure this part with your chosen exchange
    exchange = ccxt.binance()  # Example using Binance; adjust accordingly

    bars = exchange.fetch_ohlcv(symbol, timeframe, limit=44)

    # Create a DataFrame with the fetched data
    df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

    # Convert timestamp from milliseconds to a datetime format
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

    # Convert volume to float and then to millions
    df['volume'] = df['volume'].astype(float) / 1000000

    # Calculate the average volume of the periods excluding the latest
    avg_volume = df['volume'].iloc[:-1].mean()

    # Get the volume for the last 15-minute period
    last_volume = df['volume'].iloc[-1]

    increase = last_volume > avg_volume * 3

    return increase

if __name__ == "__main__":
    find_name = '0_spot_symbols.txt'
    first = True
    found_symbols = []
    while True:
        # ดึงเวลาปัจจุบัน ทำงานเมื่อ ครบ 15 นาที นับจากเวลาที่เริ่มต้น ชั่วโมง
        now = datetime.datetime.now()
        if now.minute % 30 == 0 or first:
            if not first:
                time.sleep(30)
            first = False
            found_symbols_list_new = []
            try:
                spot_symbols = [symbol for symbol in fetch_symbols() if '_' not in symbol and not any(char.isdigit() for char in symbol)]
                spot_symbols.sort()
                for symbol in spot_symbols:
                    try:
                        if find_volume(symbol):
                            if symbol not in found_symbols:
                                print(symbol)
                                found_symbols.append(symbol)
                                found_symbols_list_new.append(symbol + '\n')
                    except Exception as e:
                        print('error : ' + str(e))
                if len(found_symbols_list_new) > 0:
                    send_line_notify('Found symbols\n' + ''.join(found_symbols_list_new))
                # ลบไฟล์เดิมทิ้ง
                open(find_name, 'w').close()    
                with open(find_name, 'w') as f:
                    for symbol in found_symbols:
                        f.write(symbol + '.p\n')
                print('*** done ***')
                # รอ 60 วินาที
                time.sleep(60)
            except Exception as e:
                print('error : ' + str(e))        
        time.sleep(1)

