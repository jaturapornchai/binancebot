import talib
import random
import time
import ccxt
from binance.client import Client
from binance.enums import *
from scipy.stats import linregress
import requests
import pandas as pd
import numpy as np
import requests

api_get_data = "T7G74UYA8Q2GU7M0"
api_key = 'FpwthNz84887fuWpz9lEIsLm1zwZB9YV8ZO2FjVQ6v2k6lmR8nv1oKZZOoJSY0il'
api_secret = 'nszlVyvoFAZPVIXdWnJyhaxgiujMTTUmFN4Ncix3rKBtLhF2kO8hhCZhnwIeu3gt'
client = Client(api_key, api_secret)
# LINE Notify token
line_token = "cbBeuaCxvJcxe1wxovmMADeRsnktbFvyLizTceJpzbh"
dollar_amount = 50  # Order amount in USD
leverage = 10
take_profit_percentage = 25
stop_loss_percentage = 25

def send_line_notify(message):
    headers = {
        'Authorization': f'Bearer {line_token}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    payload = {'message': message}
    response = requests.post("https://notify-api.line.me/api/notify", headers=headers, params=payload)
    return response.status_code

def trade_signal(symbol):
    # Initialize exchange (using Binance as an example)
    exchange = ccxt.binance()

    # Fetch historical data
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=100)

    # Convert to DataFrame
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    
    # Calculate MACD
    # Short term EMA
    df['ema12'] = df['close'].ewm(span=12, adjust=False).mean()
    # Long term EMA
    df['ema26'] = df['close'].ewm(span=26, adjust=False).mean()
    # MACD
    df['macd'] = df['ema12'] - df['ema26']
    # Signal line
    df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()

    # Determine the trading signal
    latest_macd = df['macd'].iloc[-1]
    latest_signal = df['signal'].iloc[-1]

    if latest_macd > latest_signal:
        return 'long'
    elif latest_macd < latest_signal:
        return 'short'
    else:
        return 'normal'
    

def check_trade_signal(symbol):
    # Initialize exchange (using Binance as an example)
    exchange = ccxt.binance()

    # Fetch historical data
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=100)

    # Convert to DataFrame
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    
    # Calculate MACD
    # Short term EMA
    df['ema12'] = df['close'].ewm(span=12, adjust=False).mean()
    # Long term EMA
    df['ema26'] = df['close'].ewm(span=26, adjust=False).mean()
    # MACD
    df['macd'] = df['ema12'] - df['ema26']
    # Signal line
    df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()

    # Determine the trading signal
    latest_macd = df['macd'].iloc[-1]
    latest_signal = df['signal'].iloc[-1]
    previous_macd = df['macd'].iloc[-2]
    previous_signal = df['signal'].iloc[-2]

    if latest_macd > latest_signal and previous_macd <= previous_signal and latest_macd < 0:
        return 'long'
    elif latest_macd < latest_signal and previous_macd >= previous_signal and latest_macd > 0:
        return 'short'
    else:
        return 'normal'
    
def trade_signal(symbol):
    # Initialize exchange (using Binance as an example)
    exchange = ccxt.binance()

    # Fetch historical data
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=100)

    # Convert to DataFrame
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    
    # Calculate MACD
    # Short term EMA
    df['ema12'] = df['close'].ewm(span=12, adjust=False).mean()
    # Long term EMA
    df['ema26'] = df['close'].ewm(span=26, adjust=False).mean()
    # MACD
    df['macd'] = df['ema12'] - df['ema26']
    # Signal line
    df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()

    # Determine the trading signal
    latest_macd = df['macd'].iloc[-1]
    latest_signal = df['signal'].iloc[-1]

    if latest_macd > latest_signal:
        return 'long'
    elif latest_macd < latest_signal:
        return 'short'
    else:
        return 'normal'
    
def fetch_symbols():
    info = client.futures_exchange_info()
    symbols = [item['symbol'] for item in info['symbols'] if 'USDT' in item['symbol']]
    return symbols

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

    # Fetch current market price
    current_price = float(client.get_symbol_ticker(symbol=symbol)['price'])
    quantity = dollar_amount / current_price
    quantity = adjust_to_precision(quantity, quantity_precision)

    # Set leverage
    client.futures_change_leverage(symbol=symbol, leverage=leverage)

    positions = client.futures_position_information()
    for position in positions:
        if position['symbol'] == symbol and float(position['positionAmt']) != 0:
            # ปิด position ที่มีอยู่ก่อนหน้า    
            client.futures_create_order(
                symbol=symbol,
                side="SELL" if float(position['positionAmt']) > 0 else "BUY",
                type="MARKET",
                quantity=abs(float(position['positionAmt']))
            )
            break        

    if (direction == 'long'):
        # Place order
        order = client.futures_create_order(
            symbol=symbol,
            side="BUY",
            type="MARKET",
            quantity=quantity
        )
        """
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
        )"""
    elif (direction == 'short'):
        # Place order
        order = client.futures_create_order(
            symbol=symbol,
            side="SELL",
            type="MARKET",
            quantity=quantity
        )
        """
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
        )"""

    return order

def findShortLong():
    random.shuffle(symbols)        
    for symbol in symbols:
        if any(char.isdigit() for char in symbol) or '_' in symbol:
            continue
        try:
            signal = check_trade_signal(symbol)
            if signal == 'long':
                direction = 'long'
                message = f"{symbol}: Bullish signal detected! Opening long position."
                place_leveraged_order(client, symbol, direction, dollar_amount, leverage, take_profit_percentage, stop_loss_percentage)
                send_line_notify(message)
            elif signal == 'short':                
                direction = 'short'
                message = f"{symbol}: Bearish signal detected! Opening short position."
                place_leveraged_order(client, symbol, direction, dollar_amount, leverage, take_profit_percentage, stop_loss_percentage)
                send_line_notify(message)
            
        except Exception as e:
            print(f"Error encountered while processing {symbol}: {e}")
            # ตรวจสอบ error insufficient ให้หยุด
            if "insufficient" in str(e):
                break
            # ตรวจสอบ error invalid ให้ลบ symbol นั้นออก
            if "Invalid symbol" in str(e) or "pass an index" in str(e):             
                symbols.remove(symbol)

def recheckPosition():
    positions = client.futures_position_information()
    for position in positions:
        position_amount = float(position['positionAmt'])
        if position_amount != 0:
            current_signal =  (position_amount < 0 and 'short') or (position_amount > 0 and 'long')
            symbol = position['symbol']
            signal = trade_signal(symbol)
            if signal != current_signal:
                message = f"{symbol}: Signal changed from {current_signal} to {signal}. Closing position."
                client.futures_create_order(
                    symbol=symbol,
                    side="SELL" if position_amount > 0 else "BUY",
                    type="MARKET",
                    quantity=abs(position_amount)
                )
                send_line_notify(message)
            
if __name__ == "__main__":
    symbols = fetch_symbols()    
    recheckPosition()
    findShortLong()
    while True:
        if time.localtime(time.time()).tm_min == 4:
            findShortLong()
            time.sleep(60)
        else:
            time.sleep(10)
        # ทุก 5 นาที ตรวจสอบ position ว่ามีการเปลี่ยนแปลงหรือไม่
        if time.localtime(time.time()).tm_min % 5 == 0:
            recheckPosition()
        
