import os
import time
import pandas as pd
import numpy as np
from datetime import datetime
import requests
from binance.client import Client
from sklearn.linear_model import LinearRegression

# ดึงค่า API key และ secret จาก environment variables
api_key = os.getenv('BINANCE_API_KEY')
api_secret = os.getenv('BINANCE_SECRET_KEY')
line_token = os.getenv('LINE_NOTIFY_TOKEN')

# สร้างอินสแตนซ์ของ Binance Futures
client = Client(api_key, api_secret)
future_leverage = 10
tread_time_frame = '1h'

ignore_symbols = ['DONUSDT', 'USDCUSDT', 'SRMUSDT']

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
    exchange_info = client.futures_exchange_info()
    symbols = [s['symbol'] for s in exchange_info['symbols'] if s['symbol'].endswith('USDT') and s['status'] == 'TRADING']
    symbols = [symbol for symbol in symbols if symbol not in ignore_symbols]
    symbols.sort()
    return symbols

def linear_regression_channel(data, window=100, devlen=2.0):
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
        return 'LONG'
    elif data[-1] < lower_bound[-1]:
        return 'SHORT'
    else:
        return 'normal'

def check_signal(symbol, timeframe='1h', window=100, devlen=2.0):
    try:
        ohlcv = client.futures_klines(symbol=symbol, interval=timeframe, limit=window)
        if len(ohlcv) < window:
            return 'normal'

        data = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
        data['timestamp'] = pd.to_datetime(data['timestamp'], unit='ms')
        data.set_index('timestamp', inplace=True)

        # แปลงชนิดข้อมูลให้เป็น float
        data['open'] = data['open'].astype(float)
        data['high'] = data['high'].astype(float)
        data['low'] = data['low'].astype(float)
        data['close'] = data['close'].astype(float)
        data['volume'] = data['volume'].astype(float)

        close_prices = data['close'].values
        middle, upper_bound, lower_bound = linear_regression_channel(close_prices, window, devlen)

        return check_breakout(close_prices, upper_bound, lower_bound)
    except Exception as e:
        print(f"Error checking signal for {symbol}: {e}")
        return 'normal'

def future_find_signal(timeframe, window=100, devlen=2.0):
    future_exchange_info = client.futures_exchange_info()
    future_balance = future_get_balance()
    symbols = fetch_future_symbols()
    for symbol in symbols:
        signal = check_signal(symbol, timeframe, window, devlen)
        if signal == 'normal':
            future_compare_stop_loss(symbol)
        else:
            color = '🟢' if signal == 'LONG' else '🔴'
            message = f"Binance: Signal detected for {symbol}: {color} {signal}"
            try:
                print(message)
                if signal == 'LONG':
                    future_open_position(symbol, 'BUY')
                if signal == 'SHORT':
                    future_open_position(symbol, 'SELL')                
                send_line_notify(message)
                time.sleep(5)
                future_compare_stop_loss(symbol)
            except Exception as e:
                print(f"Error sending LINE message: {e}")        
        
            
def get_step_size(symbol):
    exchange_info = client.futures_exchange_info()
    for item in exchange_info['symbols']:
        if item['symbol'] == symbol:
            for filt in item['filters']:
                if filt['filterType'] == 'LOT_SIZE':
                    return float(filt['stepSize'])
    return None

def get_tick_size(symbol):
    exchange_info = client.futures_exchange_info()
    for item in exchange_info['symbols']:
        if item['symbol'] == symbol:
            for filt in item['filters']:
                if filt['filterType'] == 'PRICE_FILTER':
                    return float(filt['tickSize'])
    return None

def round_quantity(quantity, step_size):
    return (quantity // step_size) * step_size

def future_open_position(symbol, side):
    if not future_get_last_trade(symbol):
        print(f"Skip symbol {symbol} because last trade near", flush=True)
        return None

    usdt_amount = future_balance / 15.0    
    print(f"USDT amount: {usdt_amount}", flush=True)
    quantity = 0
    current_price = 0
    try:
        ticker = client.futures_symbol_ticker(symbol=symbol)
        current_price = float(ticker['price'])
        step_size = get_step_size(symbol)
        tick_size = get_tick_size(symbol)
        quantity = usdt_amount / current_price * future_leverage
        quantity = round_quantity(quantity, step_size)
    except Exception as e:
        print(f"Error calculating quantity: {e}", flush=True)
        return None
    
    try:
        time.sleep(1)
        print(f"Open position {symbol} {side} {quantity}", flush=True)
        if side == 'BUY':
            df = pd.DataFrame(client.futures_klines(symbol=symbol, interval=tread_time_frame, limit=100), columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            df = df.iloc[:-2]
            df['low'] = df['low'].astype(float)
            min_price = df['low'].min()    
            if current_price > min_price:
                print(f"Price < MIN : Long Open position {symbol} {quantity}", flush=True)
                client.futures_create_order(
                    symbol=symbol,
                    side='BUY',
                    type='MARKET',
                    quantity=quantity
                )
                send_line_notify(f"Open position {symbol} {side}")
                client.futures_create_order(
                    symbol=symbol,
                    side='SELL',
                    type='STOP_MARKET',
                    quantity=quantity,
                    stopPrice=min_price,
                    closePosition=True
                )
        if side == 'SELL':
            df = pd.DataFrame(client.futures_klines(symbol=symbol, interval=tread_time_frame, limit=100), columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            df = df.iloc[:-2]
            df['high'] = df['high'].astype(float)
            max_price = df['high'].max()
            if current_price < max_price:
                print(f"Price > MAX : Short Open position {symbol} {quantity}", flush=True)
                client.futures_create_order(
                    symbol=symbol,
                    side='SELL',
                    type='MARKET',
                    quantity=quantity
                )
                send_line_notify(f"Open position {symbol} {side}")
                client.futures_create_order(
                    symbol=symbol,
                    side='BUY',
                    type='STOP_MARKET',
                    quantity=quantity,
                    stopPrice=max_price,
                    closePosition=True
                )

    except Exception as e:
        print(f"Error: {e}", flush=True)
        send_line_notify(f"Error: {e}")
        return None

def future_get_balance():
    balance = client.futures_account_balance()
    balance_asset = 0
    for item in balance:
        if item['asset'] == 'USDT':
            balance_asset = float(item['balance'])
            break
    print(f"Balance USDT: {balance_asset}", flush=True)  
    return balance_asset

def future_get_last_trade(symbol):
    try:
        time_hour = 2
        trades = client.futures_account_trades(symbol=symbol)
        if len(trades) == 0:
            return True
        last_trade = trades[-1]
        trade_time = datetime.fromtimestamp(last_trade['time'] / 1000)
        time_diff = datetime.now() - trade_time
        if time_diff.total_seconds() < 60 * 60 * time_hour:
            return False
        return True
    except Exception as e:
        print(f"Error: {e}", flush=True)
        return False

def future_compare_stop_loss(symbol):
    print(f"Compare stop loss {symbol}", flush=True)
    tread_time_frame_stop_loss = '1h'
    limit_time_frame = 7
    try:
        position_info = client.futures_position_information(symbol=symbol)
        position_amount = float(position_info[0]['positionAmt'])
        if position_amount == 0:
            return None
        
        position_side = (position_amount > 0) and 'BUY' or 'SELL'

        future_price = float(client.futures_symbol_ticker(symbol=symbol)['price'])
        orders = client.futures_get_open_orders(symbol=symbol)
        order = None
        for item in orders:
            if item['status'] == 'NEW':
                order = item
                break
        
        if order == None:
            print(f"Order not found {symbol}", flush=True)
            if position_side == 'BUY':
                df = pd.DataFrame(client.futures_klines(symbol=symbol, interval=tread_time_frame_stop_loss, limit=limit_time_frame), columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                df.set_index('timestamp', inplace=True)
                df['low'] = df['low'].astype(float)
                bottom_price = df['low'].min()
                print(f"Reorder {symbol} {position_side} {position_amount} {bottom_price}", flush=True)
                client.futures_create_order(
                    symbol=symbol,
                    side="SELL",
                    type='STOP_MARKET',
                    quantity=position_amount,
                    stopPrice=bottom_price,
                    closePosition=True
                )
            if position_side == 'SELL':
                df = pd.DataFrame(client.futures_klines(symbol=symbol, interval=tread_time_frame_stop_loss, limit=limit_time_frame), columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                df.set_index('timestamp', inplace=True)
                df['high'] = df['high'].astype(float)
                top_price = df['high'].max()
                print(f"Reorder {symbol} {position_side} {position_amount} {top_price}", flush=True)
                client.futures_create_order(
                    symbol=symbol,
                    side="BUY",
                    type='STOP_MARKET',
                    quantity=position_amount,
                    stopPrice=top_price,
                    closePosition=True
                )            
        else:
            old_order_stop_price = float(order['stopPrice'])                
            top_price = 0
            bottom_price = 0
            df = pd.DataFrame(client.futures_klines(symbol=symbol, interval=tread_time_frame_stop_loss, limit=limit_time_frame), columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            df['high'] = df['high'].astype(float)
            df['low'] = df['low'].astype(float)
            top_price = df['high'].max()
            bottom_price = df['low'].min()
            if position_side == 'BUY':
                if old_order_stop_price < bottom_price and future_price > bottom_price:
                    print(f"Cancel order {order['orderId']} {symbol}", flush=True)
                    client.futures_cancel_order(symbol=symbol, orderId=order['orderId'])
                    time.sleep(5) 
                    print(f"Reorder {symbol} {order['side']} {position_amount} {bottom_price}", flush=True)
                    client.futures_create_order(
                        symbol=symbol,
                        side=order['side'],
                        type=order['type'],
                        quantity=position_amount,
                        stopPrice=bottom_price,
                        closePosition=True
                    )
            if position_side == 'SELL':
                if old_order_stop_price > top_price and future_price < top_price:
                    print(f"Cancel order {order['orderId']} {symbol}", flush=True)
                    client.futures_cancel_order(symbol=symbol, orderId=order['orderId'])
                    time.sleep(1) 
                    print(f"Reorder {symbol} {order['side']} {position_amount} {top_price}", flush=True)
                    client.futures_create_order(
                        symbol=symbol,
                        side=order['side'],
                        type=order['type'],
                        quantity=position_amount,
                        stopPrice=top_price,
                        closePosition=True
                    )                
    except Exception as e:
        print(f"Error: {e}", flush=True)
        return None

def future_get_position():
    positions_open = []
    positions = client.futures_position_information()
    for position in positions:
        position_amount = float(position['positionAmt'])
        if position_amount != 0:
            positions_open.append(position['symbol'])
    return positions_open

def future_find_order_no_position():
    print("Start check order no position : " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"), flush=True)
    # หา order ที่ไม่มี position ให้ยกเลิก order
    orders = client.futures_get_open_orders()
    for order in orders:
        try:
            symbol = order['symbol']
            is_position = False
            position_info = client.futures_position_information(symbol=symbol)
            position_amount = float(position_info[0]['positionAmt'])            
            if position_amount != 0:
                is_position = True
            if not is_position:
                # ถ้าไม่มียกเลิก order ที่ไม่มี position
                print(f"Cancel order {order['orderId']} {symbol}", flush=True)
                client.futures_cancel_order(symbol=symbol, orderId=order['orderId'])
        except Exception as e:
            print(f"Error: {e}", flush=True)
    print("End check order no position : " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"), flush=True)

# ดึงข้อมูล exchange และ balance
#future_exchange_info = client.futures_exchange_info()
#future_balance = future_get_balance()

# start
#future_find_order_no_position()
#future_find_signal(tread_time_frame)

while True:
    try:
        date_time_now = datetime.now()
        last_minute = date_time_now.minute
        if last_minute < 5:
            future_find_signal(tread_time_frame)
            time.sleep(120)
            future_find_order_no_position()
            # wait 5 minutes
            time.sleep(300)
    except Exception as e:
        send_line_notify(f"Error: {e}")
        print(f"Error: {e}")
    time.sleep(30)
