import datetime
import time
import requests
import yfinance as yf
import numpy as np
import pandas as pd
from scipy.signal import argrelextrema
import talib
import ccxt
from binance.client import Client

api_key = 'FpwthNz84887fuWpz9lEIsLm1zwZB9YV8ZO2FjVQ6v2k6lmR8nv1oKZZOoJSY0il'
api_secret = 'nszlVyvoFAZPVIXdWnJyhaxgiujMTTUmFN4Ncix3rKBtLhF2kO8hhCZhnwIeu3gt'
line_token = "cbBeuaCxvJcxe1wxovmMADeRsnktbFvyLizTceJpzbh"
client = Client(api_key, api_secret)

# Constants
dollar_amount = 75  # Order amount in USD
leverage = 10
exchange = ccxt.binance()
ignore_symbols = ['DONUSDT', 'USDCUSDT', 'SRMUSDT']

def send_line_notify(message):
    """Send notifications through LINE Notify."""
    headers = {
        'Authorization': f'Bearer {line_token}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    payload = {'message': message}
    response = requests.post("https://notify-api.line.me/api/notify", headers=headers, params=payload)
    return response.status_code

def fetch_symbols():
    """Fetch trading symbols from Binance futures market and apply filters."""
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    response = requests.get(url)
    data = response.json()

    symbols = [symbol["symbol"] for symbol in data["symbols"]
               if symbol["status"] == "TRADING" and
               symbol["contractType"] == "PERPETUAL" and
               symbol["symbol"].endswith("USDT") and
               symbol["symbol"] not in ignore_symbols and
               'UPUSDT' not in symbol["symbol"] and 'DOWNUSDT' not in symbol["symbol"]]

    return symbols

def symbol_has_divergences(symbol, period='60d', interval='15m', len=14, lbL=5, lbR=5, rangeUpper=60, rangeLower=5):
    """Check if a symbol has bullish divergences based on RSI and price action."""
    df = yf.download(symbol, period=period, interval=interval)
    if df.empty:
        return False

    df['rsi'] = talib.RSI(df['Close'], timeperiod=len)
    rsi_pivot_lows = argrelextrema(df['rsi'].values, np.less, order=lbL)[0]
    price_pivot_lows = argrelextrema(df['Low'].values, np.less, order=lbL)[0]

    valid_rsi_pivots = [i for i in rsi_pivot_lows if rangeLower <= i <= rangeUpper]
    valid_price_pivots = [i for i in price_pivot_lows if rangeLower <= i <= rangeUpper]

    divergences = []
    for rsi_pivot in valid_rsi_pivots:
        for price_pivot in valid_price_pivots:
            if lbR <= rsi_pivot - price_pivot <= lbL and df['rsi'][rsi_pivot] > df['rsi'][rsi_pivot - 1] and df['Low'][price_pivot] < df['Low'][price_pivot - 1]:
                divergences.append((price_pivot, 'Bullish Regular'))
    
    return bool(divergences)

def main():
    find_name = 'found_spot_symbols.txt'
    first_run = True
    found_symbols = []
    while True:
        now = datetime.datetime.now()
        if now.minute % 15 == 0 or first_run:
            if not first_run:
                time.sleep(30)  # Avoid multiple executions at the boundary
            first_run = False
            try:
                spot_symbols = fetch_symbols()
                found_symbols_list_new = []
                for symbol in spot_symbols:
                    if symbol_has_divergences(symbol):
                        if symbol not in found_symbols:
                            found_symbols.append(symbol)
                            found_symbols_list_new.append(symbol + '\n')
                
                if found_symbols_list_new:
                    send_line_notify('Found symbols\n' + ''.join(found_symbols_list_new))
                
                with open(find_name, 'w') as f:
                    for symbol in found_symbols:
                        f.write(symbol + '\n')
                print('*** done ***')
                time.sleep(60)  # Wait a minute before next iteration
            except Exception as e:
                print(f'Error: {e}')

if __name__ == "__main__":
    main()

    