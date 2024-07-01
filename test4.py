import os
import time
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from binance.client import Client
from binance.exceptions import BinanceAPIException
import requests
import ccxt


# ตั้งค่า API keys
api_key = os.getenv('BINANCE_API_KEY')
api_secret = os.getenv('BINANCE_SECRET_KEY')
line_notify_token = os.getenv('LINE_NOTIFY_TOKEN')
tread_time_frame = '15m'
future_leverage = 10
exchange = ccxt.binance()

# สร้าง Binance client
client = Client(api_key, api_secret)

def get_klines(symbol, interval, limit):
    try:
        klines = client.futures_klines(symbol=symbol, interval=interval, limit=limit)
        df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df['close'] = df['close'].astype(float)
        df['volume'] = df['volume'].astype(float)
        return df
    except BinanceAPIException as e:
        print(f"Error fetching data: {e}")
        return None

def calculate_support_resistance(df):
    volume_threshold = df['volume'].mean() * 2
    high_volume_prices = df[df['volume'] > volume_threshold]['close']
    
    if len(high_volume_prices) < 2:
        return None, None

    support = high_volume_prices.min()
    resistance = high_volume_prices.max()
    
    return support, resistance

def plot_wave(symbol,df, support, resistance):
    plt.figure(figsize=(12, 6))
    plt.plot(df['timestamp'], df['close'], label='Close Price')
    plt.axhline(y=support, color='g', linestyle='--', label='Support')
    plt.axhline(y=resistance, color='r', linestyle='--', label='Resistance')
    plt.title(symbol + ' Price with Support and Resistance')
    plt.xlabel('Time')
    plt.ylabel('Price')
    plt.legend()
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig('btc_wave.png')
    plt.close()

def send_line_notify(message, image_path=None):
    url = 'https://notify-api.line.me/api/notify'
    headers = {'Authorization': f'Bearer {line_notify_token}'}
    payload = {'message': message}
    files = {'imageFile': open(image_path, 'rb')} if image_path else None
    try:
        requests.post(url, headers=headers, data=payload, files=files)
    except requests.exceptions.RequestException as e:
        print(f"Error sending Line notification: {e}")

def get_futures_symbols():
    exchange_info = client.futures_exchange_info()
    symbols = [symbol['symbol'] for symbol in exchange_info['symbols'] if symbol['status'] == 'TRADING']
    return symbols

def get_step_size(symbol):
    for item in future_exchange_info['symbols']:
        if item['symbol'] == symbol:
            for filt in item['filters']:
                if filt['filterType'] == 'LOT_SIZE':
                    return float(filt['stepSize'])
    return None

def get_tick_size(symbol):
    for item in future_exchange_info['symbols']:
        if item['symbol'] == symbol:
            for filt in item['filters']:
                if filt['filterType'] == 'PRICE_FILTER':
                    return float(filt['tickSize'])
    return None

def round_quantity(quantity, step_size):
    return (quantity // step_size) * step_size


def future_open_position(symbol, side):
    # future_change_margin_type_and_leverage(symbol)
    # ตรวจสอบและเปลี่ยน leverage เป็น 5x ถ้าเป็นอย่างอื่น
    #usdt_amount = future_balance / 200.0    
    usdt_amount = future_balance / 5.0    
    print(f"USDT amount: {usdt_amount}", flush=True)
    quantity = 0
    diff_percent_max = 3
    # คำนวณจำนวน contracts จากจำนวนเงิน USDT
    current_price = 0
    try:
        current_price = float(client.futures_symbol_ticker(symbol=symbol)['price'])
        step_size = get_step_size(symbol)
        tick_size = get_tick_size(symbol)
        quantity = usdt_amount / current_price * future_leverage
        quantity = round_quantity(quantity, step_size)
    except Exception as e:
        print(f"Error calculating quantity: {e}", flush=True)
        return None
    
    # ฟังก์ชันเปิด Position ใน Binance Futures
    try:
        # เปิด Position
        # รอ 1 วินาที หลังจากปิด Position เพื่อป้องกันการเปิด Position ซ้ำ
        time.sleep(1)
        print(f"Open position {symbol} {side} {quantity}", flush=True)
        if side == 'BUY':
            # หาราคาย้อนหลัง 24 time frame ในราคาที่ต่ำที่สุด 
            df = pd.DataFrame(exchange.fetch_ohlcv(symbol, timeframe=tread_time_frame, limit=29), columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            # ไม่รวม 2 time frame นับจากปัจจุบัน
            df = df.iloc[:-2]
            min_price = df['low'].min()    
            # ราคาปัจจุบัน ห่างจากราคาต่ำสุดไม่เกิน diff_percent_max
            diff_price = (min_price - current_price) * -1
            diff_percent = (diff_price * 100) / min_price
            print(f"min_price: {min_price} current_price:{current_price} diff_price: {diff_price} diff_percent: {diff_percent}", flush=True)            
            if current_price > min_price and diff_percent < diff_percent_max:
                print(f"Price < MIN : Long Open position {symbol} {quantity}", flush=True)
                client.futures_create_order(
                    symbol=symbol,
                    side='BUY',
                    type='MARKET',
                    quantity=quantity,
                    recvWindow=5000
                )
                # สร้าง stop loss ที่ราคา min_price 
                client.futures_create_order(
                    symbol=symbol,
                    side='SELL',
                    type='STOP_MARKET',
                    quantity=quantity,
                    stopPrice=min_price,
                    closePosition=True,
                    recvWindow=5000
                )
        if side == 'SELL':
            # หาราคาย้อนหลัง 24 time frame ในราคาที่สูงที่สุด 
            df = pd.DataFrame(exchange.fetch_ohlcv(symbol, timeframe=tread_time_frame, limit=29), columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            # ไม่รวม 2 time frame นับจากปัจจุบัน
            df = df.iloc[:-2]
            max_price = df['high'].max()
            if current_price < max_price:
                print(f"Price > MAX : Short Open position {symbol} {quantity}", flush=True)
                client.futures_create_order(
                    symbol=symbol,
                    side='SELL',
                    type='MARKET',
                    quantity=quantity,
                    recvWindow=5000
                )
                # สร้าง stop loss ที่ราคา max_price 
                client.futures_create_order(
                    symbol=symbol,
                    side='BUY',
                    type='STOP_MARKET',
                    quantity=quantity,
                    stopPrice=max_price,
                    closePosition=True,
                    recvWindow=5000
                )

    except Exception as e:
        print(f"Error: {e}", flush=True)
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

def future_compare_stop_loss(symbol):
    print(f"Compare stop loss {symbol}", flush=True)
    tread_time_frame_stop_loss = '5m'
    limit_time_frame = 14
    # สร้าง stop loss ให้กับ position ที่เปิดอยู่
    try:
        position_info = client.futures_position_information(symbol=symbol)
        position_amount = float(position_info[0]['positionAmt'])
        position_side = (position_amount > 0) and 'BUY' or 'SELL'

        # ถ้ามี ให้ตรวจสอบ ราคา ให้เหมาะสม
        future_price = float(client.futures_symbol_ticker(symbol=symbol)['price'])
        # ค้นหา order ที่เปิดอยู่
        orders = client.futures_get_all_orders(symbol=symbol)
        order = None
        for item in orders:
            if item['status'] == 'NEW':
                order = item
                break
        
        if order == None:
            print(f"Order not found {symbol}", flush=True)
            # สร้าง stop loss ให้กับ position ที่ไม่มี stop loss
            if position_side == 'BUY':
                # หาราคาต่ำสุด และราคาสูงสุด ย้อนหลังไป limit_time_frame
                df = pd.DataFrame(exchange.fetch_ohlcv(symbol, timeframe=tread_time_frame_stop_loss, limit=limit_time_frame), columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                df.set_index('timestamp', inplace=True)
                bottom_price = df['low'].min()
                print(f"Reorder {symbol} {position_side} {position_amount} {bottom_price}", flush=True)
                client.futures_create_order(
                    symbol=symbol,
                    side="SELL",
                    type='STOP_MARKET',
                    quantity=position_amount,
                    stopPrice=bottom_price,
                    closePosition=True,
                    recvWindow=5000
                )
            if position_side == 'SELL':
                # หาราคาต่ำสุด และราคาสูงสุด ย้อนหลังไป limit_time_frame
                df = pd.DataFrame(exchange.fetch_ohlcv(symbol, timeframe=tread_time_frame_stop_loss, limit=limit_time_frame), columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                df.set_index('timestamp', inplace=True)
                top_price = df['high'].max()
                print(f"Reorder {symbol} {position_side} {position_amount} {top_price}", flush=True)
                client.futures_create_order(
                    symbol=symbol,
                    side="BUY",
                    type='STOP_MARKET',
                    quantity=position_amount,
                    stopPrice=top_price,
                    closePosition=True,
                    recvWindow=5000
                )            
        else:
            old_order_stop_price = float(order['stopPrice'])                
            top_price = 0
            bottom_price = 0
            # หาราคาต่ำสุด และราคาสูงสุด ย้อนหลังไป limit_time_frame
            df = pd.DataFrame(exchange.fetch_ohlcv(symbol, timeframe=tread_time_frame_stop_loss, limit=limit_time_frame), columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            top_price = df['high'].max()
            bottom_price = df['low'].min()
            if position_side == 'BUY':
                # ถ้าราคา order เดิม ต่ำกว่า bottom_price ให้ยกเลิก order แล้วสร้าง order ใหม่
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
                        closePosition=True,
                        recvWindow=5000
                    )
            if position_side == 'SELL':
                # ถ้าราคา order เดิม สูงกว่า top_price ให้ยกเลิก order แล้วสร้าง order ใหม่
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
                        closePosition=True,
                        recvWindow=5000
                    )                
    except Exception as e:
        print(f"Error: {e}", flush=True)
        return None

def future_get_position():
    # ดึงข้อมูล Position ที่เปิดอยู่ return symbols ใช้ binance api
    positions_open = []
    positions = client.futures_position_information()
    for position in positions:
        position_amount = float(position['positionAmt'])
        if position_amount != 0:
            positions_open.append(position['symbol'])
    return positions_open


def main():
    global future_balance 
    global future_exchange_info

    future_balance = future_get_balance()
    future_exchange_info = client.futures_exchange_info()

    interval = Client.KLINE_INTERVAL_15MINUTE
    limit = 1000

    symbols = get_futures_symbols()
    symbols = [symbol for symbol in symbols if 'USDT' in symbol and not any(char.isdigit() for char in symbol)]
    
    while True:
        future_exchange_info = client.futures_exchange_info()
        future_balance = future_get_balance()

        positions = future_get_position()
        for position in positions:
            future_compare_stop_loss(position)

        for symbol in symbols:
            df = get_klines(symbol, interval, limit)
            
            if df is not None:
                support, resistance = calculate_support_resistance(df)
                
                if support is not None and resistance is not None:
                   
                    current_price = float(df['close'].iloc[-1])
                    
                    if current_price > resistance:
                        message = f"LONG signal: {symbol} price ({current_price}) broke above resistance ({resistance})"
                        plot_wave(symbol,df, support, resistance)
                        send_line_notify(message, 'btc_wave.png')
                    elif current_price < support:
                        message = f"SHORT signal: {symbol} price ({current_price}) broke below support ({support})"
                        plot_wave(symbol,df, support, resistance)
                        send_line_notify(message, 'btc_wave.png')
                        if symbol not in positions:
                            future_open_position(symbol, 'SELL')                   
                else:
                    print("Not enough data to calculate support and resistance")
        # รอ 5 นาที
        time.sleep(5 * 60)  

if __name__ == "__main__":
    main()
