import os
import random
import requests
import pandas as pd
import talib
import sys
import time
from binance.client import Client
from binance.enums import *
import numpy as np
import math

# Binance API credentials
api_key = 'FpwthNz84887fuWpz9lEIsLm1zwZB9YV8ZO2FjVQ6v2k6lmR8nv1oKZZOoJSY0il'
api_secret = 'nszlVyvoFAZPVIXdWnJyhaxgiujMTTUmFN4Ncix3rKBtLhF2kO8hhCZhnwIeu3gt'

# LINE Notify token
line_token = "cbBeuaCxvJcxe1wxovmMADeRsnktbFvyLizTceJpzbh"

# Trading parameters
dollar_amount = 50  # Order amount in USD
leverage = 10
take_profit_percentage = 15
stop_loss_percentage = 10

client = Client(api_key, api_secret)

def send_line_notify(message):
    headers = {
        'Authorization': f'Bearer {line_token}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    payload = {'message': message}
    response = requests.post("https://notify-api.line.me/api/notify", headers=headers, params=payload)
    return response.status_code

def fetch_symbols():
    info = client.futures_exchange_info()
    symbols = [item['symbol'] for item in info['symbols'] if 'USDT' in item['symbol']]
    return symbols

def check_existing_position(client, symbol):
    """Check if there is an existing position for the symbol."""
    positions = client.futures_position_information()
    for position in positions:
        if position['symbol'] == symbol and float(position['positionAmt']) != 0:
            return True
    return False

def get_trade_signal(client, symbol):
    # Fetch historical data for the Futures market with a 15-minute interval
    candles = client.futures_klines(symbol=symbol, interval='4h')

    # Create DataFrame
    df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
    df['close'] = df['close'].astype(float)

    # Calculate RSI
    rsi = talib.RSI(df['close'], timeperiod=14)

    # Check for sufficient data
    if len(df) >= 4:
        # Check for bullish divergence
        if df['low'].iloc[-4] > df['low'].iloc[-2] and rsi.iloc[-4] < rsi.iloc[-2]:
            return 'long'

        # Check for bearish divergence
        elif df['high'].iloc[-4] < df['high'].iloc[-2] and rsi.iloc[-4] > rsi.iloc[-2]:
            return 'short'

        else:
            return 'normal'
    else:
        return 'insufficient data'
            
def adjust_to_precision(value, precision):
    format_str = "{:0.0" + str(precision) + "f}"
    return float(format_str.format(value))

def get_precision_from_step_size(step_size):
    # Count the number of decimals in the step size
    str_step_size = str(step_size).rstrip('0')
    decimal_index = str_step_size.find('.')
    return len(str_step_size) - decimal_index - 1 if decimal_index != -1 else 0

def get_symbol_info(client, symbol):
    info = client.futures_exchange_info()
    for s in info['symbols']:
        if s['symbol'] == symbol:
            filters = {f['filterType']: f for f in s['filters']}
            return {
                'quantityPrecision': get_precision_from_step_size(filters['LOT_SIZE']['stepSize']),
                'pricePrecision': get_precision_from_step_size(filters['PRICE_FILTER']['tickSize'])
            }
    raise ValueError(f"Symbol info for {symbol} not found")


def main():
    filename = "demofile.txt"
    if os.path.exists(filename):
        os.remove("demofile.txt")
    else:
        print("The file does not exist")
    try:
        # เรียง symbol ด้วยการ random
        random.shuffle(symbols)        
        for symbol in symbols:
            # ไม่เอา symbol ที่มีตัวเลข
            if (any(char.isdigit() for char in symbol)):
                continue
            # ไม่เอา symbol ที่มี _ 
            if (any(char == '_' for char in symbol)):
                continue
            
            try:
                # print(f"Fetching {symbol}...")
                trend = get_trade_signal(client,symbol)
                bullish_div = False
                bearish_div = False
                bearish_div = True
                if trend == 'long':
                    bullish_div = True
                    print(f"bullish_div: {symbol} : {bullish_div}")
                    os.system(f"echo {symbol} >> demofile.txt")
                elif trend == 'short':
                    bearish_div = True              
                    print(f"bearish_div: {symbol} : {bearish_div}")
                    os.system(f"echo {symbol} >> demofile.txt")
                
            except Exception as e:
                print(f"2 : Error: {str(e)}") 
                if "Invalid symbol" in str(e):
                    symbols.remove(symbol)
                    print(f"Remove {symbol} from list")
                if "insufficient" in str(e):
                    print(f"Insufficient balance for this order.")
                    break
                
    except Exception as e:
        print(f"1: Error: {str(e)}")
        if "Invalid symbol" in str(e):
            symbols.remove(symbol)
            print(f"Remove {symbol} from list")

    
    
if __name__ == "__main__":
    symbols = fetch_symbols()    
    main()
