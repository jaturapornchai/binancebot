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

api_key = 'SQ76bBv6YxOKN1lcwNbtVz8v3Yn0NkDmKW9nDCTjQB6oB6nlOx4VCSgLe80IJcwr'
api_secret = 'OFVk4eZLqkoenok6dmnTFKzs5Ol1tA1uBTX8ipM6UDxEbIJQN5zOdH94U2uRZqFq'
line_token = "cbBeuaCxvJcxe1wxovmMADeRsnktbFvyLizTceJpzbh"
client = Client(api_key, api_secret)
mytimeframe = '1h'
# Constants
dollar_amount = 20  # Order amount in USD
leverage = 10
exchange = ccxt.binance()
ignore_symbols = ['DONUSDT', 'USDCUSDT', 'SRMUSDT']

def change_leverage(symbol):
    try:
        response = client.futures_change_leverage(symbol=symbol, leverage=leverage)
        print(f"Leverage changed for {symbol} to {leverage}: {response}")
    except Exception as e:
        print(f"Failed to change leverage for {symbol}: {e}")
        
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

def remove_order_lost_position():
    # ค้นหา position ที่ไม่มี stop loss หรือ trailing stop
    positions = client.futures_position_information()
    for position in positions:
        position_amount = float(position['positionAmt'])        
        if position_amount != 0:
            symbol = position['symbol']
            orders = client.futures_get_open_orders(symbol=symbol)
            have_stop_loss = False
            have_take_profit = False
            have_trailing_stop = False
            for order in orders:
                if order['type'] == 'STOP_MARKET':
                    have_stop_loss = True
                if order['type'] == 'TAKE_PROFIT_MARKET':
                    have_take_profit = True
                if order['type'] == 'TRAILING_STOP_MARKET':
                    have_trailing_stop = True
            if not have_stop_loss or not have_take_profit:
                print(f"ไม่มี stop loss หรือ take profit สำหรับ {symbol} จะทำการปิด position")
                client.futures_create_order(
                    symbol=symbol,
                    side="SELL" if position_amount > 0 else "BUY",
                    type="MARKET",
                    quantity=abs(position_amount)
                )
            """if not have_trailing_stop:
                print(f"ไม่มี trailing stop สำหรับ {symbol} จะทำการปิด position")
                client.futures_create_order(
                    symbol=symbol,
                    side="SELL" if position_amount > 0 else "BUY",
                    type="MARKET",
                    quantity=abs(position_amount)
                )"""

    positions = client.futures_position_information()
    orders = client.futures_get_open_orders()
    for order in orders:
        have_position = False
        for position in positions:
            if float(position['positionAmt']) != 0 and position['symbol'] == order['symbol']:
                have_position = True
                break
        if not have_position:
            xsymbol = order['symbol']
            print(f"ลบ order {xsymbol} ค้าง {order['orderId']} สำเร็จ : 2")
            client.futures_cancel_order(
                symbol=order['symbol'],
                orderId=order['orderId']
            )
    
    # ค้นหา position ที่ไม่มี order != 2 อัน ลบ position นั้นออก
    positions = client.futures_position_information()
    for position in positions:
        position_amount = float(position['positionAmt'])
        if position_amount != 0:
            symbol = position['symbol']
            orders = client.futures_get_open_orders(symbol=symbol)
            if len(orders) != 2:
                print(f"ลบ position ที่ไม่มี order ไม่เท่ากับ 2 อัน {symbol} สำเร็จ : 3")
                client.futures_create_order(
                    symbol=symbol,
                    side="SELL" if position_amount > 0 else "BUY",
                    type="MARKET",
                    quantity=abs(position_amount)
                )
                # ลบ order ที่เหลือออก
                orders = client.futures_get_open_orders(symbol=symbol)
                for order in orders:
                    print(f"ลบ {symbol} order ค้าง {order['orderId']} สำเร็จ : 4")
                    client.futures_cancel_order(
                        symbol=order['symbol'],
                        orderId=order['orderId']
                    )

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

def place_order_future(client, symbol, direction, dollar_amount):  
    print(f"Future Placing order for {symbol}...")
    # ถ้ามี position เดิม และ สถานะไม่เหมือนกัน ให้ปิด position เดิมก่อน
    positions = client.futures_position_information()
    for position in positions:
        position_amount = float(position['positionAmt'])
        if position_amount != 0 and position['symbol'] == symbol:
            current_signal =  (position_amount < 0 and 'short') or (position_amount > 0 and 'long')
            if current_signal == direction:
                return 
            else:
                message = f"{symbol}: Signal changed from {current_signal} to {direction}. Closing position."
                client.futures_create_order(
                    symbol=symbol,
                    side="SELL" if position_amount > 0 else "BUY",
                    type="MARKET",
                    quantity=abs(position_amount)
                )
                # ลบ order ที่เหลือออก
                orders = client.futures_get_open_orders(symbol=symbol)
                for order in orders:
                    print(f"ลบ {symbol} order ค้าง {order['orderId']} สำเร็จ : 1")
                    client.futures_cancel_order(
                        symbol=order['symbol'],
                        orderId=order['orderId']
                    )
          
    symbol_info = get_symbol_info(client, symbol)
    quantity_precision = symbol_info['quantityPrecision']
    price_precision = symbol_info['pricePrecision']

    # Fetch current market price
    current_price = float(client.get_symbol_ticker(symbol=symbol)['price'])
    quantity = dollar_amount / current_price
    quantity = adjust_to_precision(quantity, quantity_precision)

    try:
        client.futures_change_margin_type(symbol=symbol, marginType='CROSSED')
    except Exception as e:
        pass

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

        # ค้นหาราคาต่ำสุดย้อนหลัง 8 bars
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=mytimeframe, limit=8)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        low_price = df['low'].min()
        # กำหนด stop loss ต่ำกว่า low ที่เจอได้ 1%
        stop_loss_price = low_price - ((low_price * (1 / 100)) / leverage)
        stop_loss_price = adjust_to_precision(stop_loss_price, price_precision)
        # take profit เป็น 1.5 เท่าของ enter_price , stop loss
        take_profit_price = enter_price + ((enter_price - stop_loss_price) * 1.5)
        take_profit_price = adjust_to_precision(take_profit_price, price_precision)

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
        
        # สร้าง tailing stop
        client.futures_create_order(
            symbol=symbol,
            side='SELL',
            type='TRAILING_STOP_MARKET',
            quantity=quantity,
            activationPrice=take_profit_price,
            callbackRate=0.5,
        )
        

        """# สร้าง take profit order
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
        
        # ดึง order ที่เพิ่งสร้าง มาใช้งานต่อ
        order = client.futures_get_order(
            symbol=symbol,
            orderId=order['orderId']
        )
        # get enter price
        enter_price = float(order['avgPrice'])
        order_id = order['orderId']
        # ค้นหาราคาสูงสุดย้อนหลัง 28 bars
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=mytimeframe, limit=28)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        high_price = df['high'].max()
        # กำหนด stop loss สูงกว่า high ที่เจอได้ 1%
        stop_loss_price = high_price + ((high_price * (1 / 100)) / leverage)
        stop_loss_price = adjust_to_precision(stop_loss_price, price_precision)
        take_profit_price = enter_price - ((stop_loss_price - enter_price) * 1.5)
        take_profit_price = adjust_to_precision(take_profit_price, price_precision)
        
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
        """
        # สร้าง tailing stop
        client.futures_create_order(
            symbol=symbol,
            side='BUY',
            type='TRAILING_STOP_MARKET',
            quantity=quantity,
            activationPrice=take_profit_price,
            callbackRate=0.5,
        )
        """
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

    return order

############################################################################

def find_volume(symbol, timeframe='1h'):
    # Initialize the exchange - make sure to configure this part with your chosen exchange
    exchange = ccxt.binance()  # Example using Binance; adjust accordingly
    
    # Fetch the last 45 periods to include the previous period for comparison
    bars = exchange.fetch_ohlcv(symbol, timeframe, limit=144)

    # Create a DataFrame with the fetched data
    df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

    # Convert timestamp from milliseconds to a datetime format
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

    # Calculate the average volume of the previous 44 periods
    avg_volume = df['volume'].iloc[:-1].mean()

    # Get the volume for the last period
    last_volume = df['volume'].iloc[-1]

    if last_volume > avg_volume * 4:
        return 'long'
    else:
        return 'hold'
                              
def main():
    find_name = 'found_volume.txt'
    first_run = True
    spot_symbols = fetch_symbols()
    found_symbols = []
    while True:
        if datetime.datetime.now().minute == 0 or first_run:
            first_run = False
            """try:
                remove_order_lost_position()
            except Exception as e:
                print(f'Error: {e}')            """
            try:
                print('*** start ***')
                # random 
                np.random.shuffle(spot_symbols)
                for symbol in spot_symbols:                    
                    try:
                        #change_leverage(symbol)
                        signal =  find_volume(symbol)
                        if signal == 'short' or signal == 'long':
                            print(signal + " " + symbol)
                            if symbol not in found_symbols:
                                found_symbols.append(symbol)
                            #place_order_future(client, symbol, signal, dollar_amount)
                            send_line_notify(f"Found {signal} signal for {symbol}")
                    except Exception as e:
                        print(f'Error: {e}' + " " + symbol)
                        # if e find 'invalid' remove from spot_symbols
                        if 'insufficient' in str(e):
                            print(f"Insufficient balance stop.")
                            break
                        if 'Invalid' in str(e):
                            spot_symbols.remove(symbol)                        
                    
                # ลบไฟล์เดิมทิ้ง
                open(find_name, 'w').close()    
                with open(find_name, 'w') as f:
                    for symbol in found_symbols:
                        f.write(symbol + '.p\n')
                print('*** finish ***')
            except Exception as e:
                print(f'Error: {e}')
        time.sleep(10)

if __name__ == "__main__":
    main()
