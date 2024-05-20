import ccxt
import pandas as pd
import numpy as np
import yfinance as yf
import random  
import requests
import talib
import sys
import time
from binance.client import Client
from binance.enums import *
import math

# Binance API credentials
exchange = ccxt.binance()
api_key = 'FpwthNz84887fuWpz9lEIsLm1zwZB9YV8ZO2FjVQ6v2k6lmR8nv1oKZZOoJSY0il'
api_secret = 'nszlVyvoFAZPVIXdWnJyhaxgiujMTTUmFN4Ncix3rKBtLhF2kO8hhCZhnwIeu3gt'
client = Client(api_key, api_secret)

# LINE Notify token
line_token = "cbBeuaCxvJcxe1wxovmMADeRsnktbFvyLizTceJpzbh"

# Trading parameters
dollar_amount = 50  # Order amount in USD
leverage = 10
take_profit_percentage = 10
stop_loss_percentage = 10


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

def place_leveraged_order(client, symbol, direction, dollar_amount, leverage, take_profit_percentage, stop_loss_percentage):    
    symbol_info = get_symbol_info(client, symbol)
    quantity_precision = symbol_info['quantityPrecision']
    price_precision = symbol_info['pricePrecision']

    # Check Futures account balance
    balance = client.futures_account_balance()
    usdt_balance = next(item for item in balance if item['asset'] == 'USDT')['balance']
    usdt_balance = float(usdt_balance)

    # Calculate required margin and order quantity
    if usdt_balance < 11:
        return "Insufficient balance for this order."

    # Fetch current market price
    current_price = float(client.get_symbol_ticker(symbol=symbol)['price'])
    quantity = dollar_amount / current_price
    quantity = adjust_to_precision(quantity, quantity_precision)

    # Set leverage
    client.futures_change_leverage(symbol=symbol, leverage=leverage)

    if (direction == 'long'):
        # Place order
        order = client.futures_create_order(
            symbol=symbol,
            side="BUY",
            type="MARKET",
            quantity=quantity
        )
        # ดึง order ที่เพิ่งสร้าง มาใช้งานต่อ
        order = client.futures_get_order(
            symbol=symbol,
            orderId=order['orderId']
        )
        # get enter price
        enter_price = float(order['avgPrice'])
        order_id = order['orderId']
        take_profit_price_calc = enter_price + ((enter_price * (take_profit_percentage / 100)) / leverage)
        stop_loss_price_calc = enter_price  - ((enter_price * (stop_loss_percentage / 100)) / leverage)
        take_profit_price = adjust_to_precision(take_profit_price_calc, price_precision)
        stop_loss_price = adjust_to_precision(stop_loss_price_calc, price_precision)
        # สร้าง stop loss order
        client.futures_create_order(
            symbol=symbol,
            side="SELL",
            type="STOP_MARKET",
            quantity=quantity,
            stopPrice=stop_loss_price,
            closePosition=True,
            timeInForce='GTE_GTC',
            order_id=order_id
        )
        # สร้าง take profit order
        client.futures_create_order(
            symbol=symbol,
            side="SELL",
            type="TAKE_PROFIT_MARKET",
            quantity=quantity,
            stopPrice=take_profit_price,
            closePosition=True,
            timeInForce='GTE_GTC',
            order_id=order_id
        )
        # ส่ง notify
        message = f"{symbol}: Long position opened at {enter_price} with {leverage}x leverage."
    elif (direction == 'short'):
        # Place order
        order = client.futures_create_order(
            symbol=symbol,
            side="SELL",
            type="MARKET",
            quantity=quantity
        )
        # ดึง order ที่เพิ่งสร้าง มาใช้งานต่อ
        order = client.futures_get_order(
            symbol=symbol,
            orderId=order['orderId']
        )
        # get enter price
        enter_price = float(order['avgPrice'])
        order_id = order['orderId']
        take_profit_price_calc = enter_price  - ((enter_price * (take_profit_percentage / 100)) / leverage)
        stop_loss_price_calc = enter_price  + ((enter_price * (stop_loss_percentage / 100)) / leverage)
        take_profit_price = adjust_to_precision(take_profit_price_calc, price_precision)
        stop_loss_price = adjust_to_precision(stop_loss_price_calc, price_precision)
        # สร้าง stop loss order
        client.futures_create_order(
            symbol=symbol,
            side="BUY",
            type="STOP_MARKET",
            quantity=quantity,
            stopPrice=stop_loss_price,
            closePosition=True,
            timeInForce='GTE_GTC',
            order_id=order_id
        )
        # สร้าง take profit order
        client.futures_create_order(
            symbol=symbol,
            side="BUY",
            type="TAKE_PROFIT_MARKET",
            quantity=quantity,
            stopPrice=take_profit_price,
            closePosition=True,
            timeInForce='GTE_GTC',
            order_id=order_id
        )
        # ส่ง notify
        message = f"{symbol}: Short position opened at {enter_price} with {leverage}x leverage."

    return order

def main():
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
                trend =  get_trend_status(symbol, '1h', 7, 3.0)
                print(f"trend: {symbol} :  {trend}")
                """bullish_div = False
                bearish_div = False
                if trend == 'long':
                    bullish_div = True
                    print(f"bullish_div: {symbol} : {bullish_div}")
                elif trend == 'short':
                    bearish_div = True              
                    print(f"bearish_div: {symbol} : {bearish_div}")
                
                if bullish_div:
                    if check_existing_position(client, symbol):
                        print(f"Existing position found for {symbol}, skipping...")
                    else:
                        direction = 'long'
                        message = f"{symbol}: Bullish RSI Divergence detected! Opening long position."
                        place_leveraged_order(client, symbol, direction, dollar_amount, leverage, take_profit_percentage, stop_loss_percentage)
                        send_line_notify(message)

                elif bearish_div:
                    if check_existing_position(client, symbol):
                        print(f"Existing position found for {symbol}, skipping...")
                    else:
                        direction = 'short'
                        message = f"{symbol}: Bearish RSI Divergence detected! Opening short position."
                        place_leveraged_order(client, symbol, direction, dollar_amount, leverage, take_profit_percentage, stop_loss_percentage)
                        send_line_notify(message)"""
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
    
"""---------------------------------"""
# Function to fetch historical data
def fetch_data(symbol, timeframe, limit):
    since = exchange.milliseconds() - (limit * exchange.parse_timeframe(timeframe) * 1000)
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

# Function to calculate ATR
def atr(df, period):
    data = df.copy()
    high_low = data['high'] - data['low']
    high_close = np.abs(data['high'] - data['close'].shift())
    low_close = np.abs(data['low'] - data['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = np.max(ranges, axis=1)
    return true_range.rolling(period).mean()

# Function to calculate Super Trend
def supertrend(df, atr_period, multiplier):
    hl2 = (df['high'] + df['low']) / 2
    atr_value = atr(df, atr_period)
    st = hl2 + (multiplier * atr_value)
    st_upper = st
    st_lower = st

    # Super Trend logic
    for i in range(1, len(df)):
        if df['close'][i-1] <= st_upper[i-1]:
            st[i] = max(st_upper[i], st_upper[i-1])
        else:
            st[i] = min(st_lower[i], st_lower[i-1])

    return st

# Function to determine trend status
def get_trend_status(symbol, timeframe, atr_period, multiplier):
    df = fetch_data(symbol, timeframe, 100)
    df['supertrend'] = supertrend(df, atr_period, multiplier)
    latest_close = df['close'].iloc[-1]
    latest_supertrend = df['supertrend'].iloc[-1]

    if latest_close > latest_supertrend:
        return 'up'
    elif latest_close < latest_supertrend:
        return 'down'
    else:
        return 'normal'

if __name__ == "__main__":
    symbols = fetch_symbols()    
    main()
    while True:
        # get time 
        current_time = time.localtime()
        # ตรวจดูว่าเป็นเวลา 15 นาที หรือไม่
        if current_time.tm_min == 0 or current_time.tm_min == 15 or current_time.tm_min == 30 or current_time.tm_min == 45:
            time.sleep(60)
            print(f"Run time: {current_time.tm_hour}:{current_time.tm_min}")
            main()
            time.sleep(60)
        print(f"Current time: {current_time.tm_hour}:{current_time.tm_min}")
        time.sleep(1)
