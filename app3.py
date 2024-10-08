from scipy import stats
import pandas as pd
from typing import List
import numpy as np
from binance.client import Client
import time
import datetime
import requests
import pandas as pd
import numpy as np
import math

# สร้าง client สำหรับการเชื่อมต่อ Binance API
api_key = 'wpq57Bbcr4Wg1jW6iZt5qJ46YEewH7E89eyz31185wqqOjQt1r9n4a3mj1yLUmdN'
api_secret = '8wuq8dMQOdsHMOSgjDLQYsPQF3J8CtdMSXu7VrB6ZNhS4VJ94ZM4b5qfu20jtnLU'
client = Client(api_key, api_secret)
future_leverage = 5
symbols = []
tread_time_frame = '5m'
ignore_symbols = ['USDCUSDT']
usdt_open_position = 10

def sync_time_with_server():
    try:
        server_time = client.futures_time()
        return int(server_time['serverTime'])
    except Exception as e:
        print(f"Error syncing time with server: {e}")
        return int(time.time() * 1000)

def price_step_size(symbol):
    exchange_info = client.futures_exchange_info()
    for item in exchange_info['symbols']:
        if item['symbol'] == symbol:
            for filt in item['filters']:
                if filt['filterType'] == 'PRICE_FILTER':
                    return float(filt['tickSize'])
    return None
                   
def future_get_usdt_balance():
    balance = client.futures_account_balance()
    balance_usdt = 0
    for item in balance:
        if item['asset'] == 'USDT':
            balance_usdt = float(item['balance'])
            break
    return balance_usdt

def get_step_size(symbol):
    exchange_info = client.futures_exchange_info()
    for item in exchange_info['symbols']:
        if item['symbol'] == symbol:
            for filt in item['filters']:
                if filt['filterType'] == 'LOT_SIZE':
                    return float(filt['stepSize'])
    return None

def get_take_profit_and_stop_loss(symbol, entry_price, side, risk_reward_ratio=2):
    # ดึงข้อมูลราคาย้อนหลังเพื่อคำนวณ
    try:
        interval = tread_time_frame
        klines = client.futures_klines(symbol=symbol, interval=interval, limit=500)
    except Exception as e:
        print(f"Error fetching klines: {e}")
        return None, None

    closes = np.array([float(kline[4]) for kline in klines])
    length = 100
    _, upper_channel, lower_channel, _ = calculate_linear_regression_channel(closes, length)

    if side == 'BUY':
        # Stop Loss: ใช้ Lower Channel หรือกำหนดจาก ATR
        stop_loss = lower_channel
        
        # Take Profit: คำนวณจาก Risk-Reward Ratio
        take_profit = entry_price + (entry_price - stop_loss) * risk_reward_ratio

    elif side == 'SELL':
        # Stop Loss: ใช้ Upper Channel หรือกำหนดจาก ATR
        stop_loss = upper_channel
        
        # Take Profit: คำนวณจาก Risk-Reward Ratio
        take_profit = entry_price - (stop_loss - entry_price) * risk_reward_ratio

    # ปรับให้เป็นไปตาม tick size
    price_step = price_step_size(symbol)
    if price_step:
        stop_loss = round(stop_loss / price_step) * price_step
        take_profit = round(take_profit / price_step) * price_step

    return round(take_profit, 8), round(stop_loss, 8)

def future_create_position(symbol, side):
    print(f"Opening position for {symbol} ({side})", flush=True)
    future_change_margin_type_and_leverage(symbol)
    ticker = client.futures_symbol_ticker(symbol=symbol)
    current_price = float(ticker['price'])
    step_size = get_step_size(symbol)
    quantity = usdt_open_position / current_price * future_leverage
    quantity = (quantity // step_size) * step_size
    
    # ซิงค์เวลา
    offset = sync_time_with_server()
    
    if side == 'BUY':
        openOrder = client.futures_create_order(symbol=symbol, side='BUY', type='MARKET', quantity=quantity)
        # สร้าง order take profit และ stop loss อ้างอิง orenOrder ที่เปิด
        take_profit, stop_loss = get_take_profit_and_stop_loss(symbol, current_price, side)
        if take_profit and stop_loss:
            client.futures_create_order(symbol=symbol, side='SELL', type='TAKE_PROFIT', quantity=quantity, stopPrice=take_profit, closePosition=True,order = openOrder['orderId'])
            client.futures_create_order(symbol=symbol, side='SELL', type='STOP_MARKET', quantity=quantity, stopPrice=stop_loss, closePosition=True,order = openOrder['orderId'])
        
    elif side == 'SELL':
        openOrder = client.futures_create_order(symbol=symbol, side='SELL', type='MARKET', quantity=quantity, timestamp=int(time.time() * 1000 + offset))
        # สร้าง order take profit และ stop loss อ้างอิง orenOrder ที่เปิด
        take_profit, stop_loss = get_take_profit_and_stop_loss(symbol, current_price, side)
        if take_profit and stop_loss:
            client.futures_create_order(symbol=symbol, side='BUY', type='TAKE_PROFIT', quantity=quantity, stopPrice=take_profit, closePosition=True,order = openOrder['orderId'])
            client.futures_create_order(symbol=symbol, side='BUY', type='STOP_MARKET', quantity=quantity, stopPrice=stop_loss, closePosition=True,order = openOrder['orderId'])
                                                                                                                                                                 
    time.sleep(1)
    #check_position(symbol, current_price)

# ตรวจสอบ position ที่ไม่มี stop loss และ take profit แล้วปิดทิ้ง เพิ่มจะสร้างใหม่
def check_position(symbol,open_price):
    positions = client.futures_position_information()
    for position in positions:
        if position['symbol'] == symbol:
            position_amount = float(position['positionAmt'])
            if position['positionSide'] == 'BOTH' and position_amount != 0:            
                # ดึง order id
                print(f"Checking position for {symbol}", flush=True)

                # ลบ order stop loss และ take profit ทิ้ง
                try:
                    client.futures_cancel_all_open_orders(symbol=symbol)
                    time.sleep(1)
                except Exception as e:
                    print(f"Error cancelling orders for {symbol}: {e}", flush=True)
                # ดึงราคาต่ำสุดและสูงสุด ย้อนหลังไป 14 time frame (tread_time_frame)
                try:
                    klines = client.futures_klines(symbol=symbol, interval=tread_time_frame, limit=14)
                except Exception as e:
                    print(f"Error fetching klines: {e}", flush=True)
                    return None
                lows = np.array([float(kline[3]) for kline in klines])
                highs = np.array([float(kline[2]) for kline in klines])
                low_min = np.min(lows[:-1])
                high_max = np.max(highs[:-1])
                print(f"Lowest low: {low_min}, Highest high: {high_max}", flush=True)
                
                # ถ้า BUY position ให้สร้าง stop loss โดยใช้ low_min
                if position_amount > 0:
                    try:
                        price_step = price_step_size(symbol)  # ดึง tick size สำหรับคู่เหรียญ
                        stop_loss_price = low_min
                        if price_step:
                            stop_loss_price = round(stop_loss_price / price_step) * price_step
                        stop_loss_price = round(stop_loss_price, 8)
                        print(f"Stop loss price: {stop_loss_price}", flush=True)
                        client.futures_create_order(symbol=symbol, side='SELL', type='STOP_MARKET', quantity=abs(position_amount), stopPrice=stop_loss_price,closePosition=True)
                        time.sleep(1)
                        take_profit_price = open_price + (open_price - stop_loss_price)
                        if price_step:
                            take_profit_price = round(take_profit_price / price_step) * price_step  # ปรับราคาให้เป็นไปตาม tick size
                        take_profit_price = round(take_profit_price, 8)
                        print(f"Take profit price: {take_profit_price}", flush=True)
                        client.futures_create_order(symbol=symbol, side='SELL', type='TAKE_PROFIT_MARKET', quantity=abs(position_amount), stopPrice=take_profit_price,closePosition=True)
                    except Exception as e:
                        print(f"Error setting stop loss for {symbol}: {e}", flush=True)

                # ถ้า SELL position ให้สร้าง stop loss โดยใช้ high_max
                elif position_amount < 0:
                    try:
                        price_step = price_step_size(symbol)  # ดึง tick size สำหรับคู่เหรียญ
                        stop_loss_price = high_max
                        if price_step:
                            stop_loss_price = round(stop_loss_price / price_step) * price_step
                        stop_loss_price = round(stop_loss_price, 8)
                        print(f"Stop loss price: {stop_loss_price}", flush=True)
                        client.futures_create_order(symbol=symbol, side='BUY', type='STOP_MARKET', quantity=abs(position_amount), stopPrice=stop_loss_price,closePosition=True)
                        time.sleep(1)
                        take_profit_price = open_price - (stop_loss_price - open_price)
                        if price_step:
                            take_profit_price = round(take_profit_price / price_step) * price_step  # ปรับราคาให้เป็นไปตาม tick size
                        take_profit_price = round(take_profit_price, 8)
                        print(f"Take profit price: {take_profit_price}", flush=True)
                        client.futures_create_order(symbol=symbol, side='BUY', type='TAKE_PROFIT_MARKET', quantity=abs(position_amount), stopPrice=take_profit_price,closePosition=True)
                    except Exception as e:
                        print(f"Error setting stop loss for {symbol}: {e}", flush=True)

def future_change_margin_type_and_leverage(symbol):
    try:
        # Change to cross margin if it's isolated margin
        positions = client.futures_position_information(symbol=symbol)
        if positions[0]['marginType'] == 'isolated':
            print(f"Change margin type to CROSS for {symbol}", flush=True)
            client.futures_change_margin_type(symbol=symbol, marginType='CROSSED')
            time.sleep(2)
    except Exception as e:
        print(f"Error: {e}", flush=True)
    
    try:
        positions = client.futures_position_information(symbol=symbol)
        current_leverage = positions[0]['leverage']
        if int(current_leverage) != future_leverage:
            print(f"Change leverage to {future_leverage} for {symbol}", flush=True)
            client.futures_change_leverage(symbol=symbol, leverage=future_leverage)
    except Exception as e:
        print(f"Error checking or setting leverage: {e}", flush=True)
        
def fetch_future_symbols():
    def get_futures_symbols() -> List[str]:
        url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
        response = requests.get(url)
        data = response.json()
        return [symbol['symbol'] for symbol in data['symbols'] if symbol['status'] == 'TRADING']

    def get_latest_prices(symbols: List[str]) -> dict:
        url = "https://fapi.binance.com/fapi/v1/ticker/price"
        response = requests.get(url)
        data = response.json()
        return {item['symbol']: float(item['price']) for item in data if item['symbol'] in symbols}

    def get_24h_volume(symbols: List[str]) -> dict:
        url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
        response = requests.get(url)
        data = response.json()
        return {item['symbol']: float(item['volume']) for item in data if item['symbol'] in symbols}

    symbols = get_futures_symbols()
    prices = get_latest_prices(symbols)
    volumes = get_24h_volume(symbols)

    filtered_symbols = []
    for symbol in symbols:
        # เอาที่นามสกุล USDT
        if symbol.endswith('USDT') and symbol not in ignore_symbols:
            if symbol in prices and symbol in volumes:
                volume_usdt = prices[symbol] * volumes[symbol]
                if volume_usdt > 1000000:
                    filtered_symbols.append(symbol)

    # ลบที่มีตัวเลข
    filtered_symbols = [x for x in filtered_symbols if not any(c.isdigit() for c in x)]

    np.random.shuffle(filtered_symbols)
    print(f"Filtered symbols: {filtered_symbols}", flush=True)
    return filtered_symbols

def remove_order_no_position():
    offset = sync_time_with_server()
    # เพิ่ม recvWindow เข้าไปใน request
    try:
        orders = client.futures_get_open_orders(timestamp=int(time.time() * 1000 + offset), recvWindow=5000)
    except Exception as e:
        print(f"Error fetching open orders: {e}")
        return

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
                client.futures_cancel_order(symbol=symbol, orderId=order['orderId'], recvWindow=5000)
        except Exception as e:
            print(f"Error: {e}", flush=True)

def find_high_low(symbol):
    try:
        interval = tread_time_frame
        klines = client.futures_klines(symbol=symbol, interval=interval, limit=144)
        # remove 14 time frame
        klines = klines[14:]
    except Exception as e:
        print(f"Error fetching klines: {e}", flush=True)
        return None, None

    # แปลงข้อมูลเป็น numpy array
    highs = np.array([float(kline[2]) for kline in klines])  # ราคาสูงสุด
    lows = np.array([float(kline[3]) for kline in klines])   # ราคาต่ำสุด

    # หาจุดสูงสุดและต่ำสุด
    highest_price = np.max(highs)
    lowest_price = np.min(lows)

    return highest_price, lowest_price


def calculate_linear_regression_channel(data, length):
    y = data[-length:]
    x = np.arange(length)
    
    slope, intercept, _, _, _ = stats.linregress(x, y)
    
    line = x * slope + intercept
    
    deviations = y - line
    std_dev = np.std(deviations)
    
    upper_channel = line + std_dev * 2
    lower_channel = line - std_dev * 2
    
    return line[-1], upper_channel[-1], lower_channel[-1], slope

def get_buy_sell_signal(symbol):
    try:
        interval = tread_time_frame
        klines = client.futures_klines(symbol=symbol, interval=interval, limit=500)
    except Exception as e:
        print(f"Error fetching klines: {e}")
        return None

    # เตรียมข้อมูลราคาปิด
    closes = np.array([float(kline[4]) for kline in klines])
    
    # คำนวณ Linear Regression Channel
    length = 100
    last_price = closes[-1]
    _, upper_channel, lower_channel, _ = calculate_linear_regression_channel(closes, length)
    
    # สัญญาณ Buy: ราคาปัจจุบันต่ำกว่าเส้นล่าง
    if last_price < lower_channel:
        return "BUY"
    
    # สัญญาณ Sell: ราคาปัจจุบันสูงกว่าเส้นบน
    elif last_price > upper_channel:
        return "SELL"
    
    # ไม่มีสัญญาณ
    return None
                 
def get_all_future_position_and_save_to_file():
    file_name = 'positions.txt'
    # delete file
    open(file_name, 'w').close()
    positions = client.futures_position_information()
    for position in positions:
        with open(file_name, 'a') as f:
            if float(position['positionAmt']) != 0:
                f.write(f"{position['symbol']}.p\n")
    print("Done", flush=True)        
    
first_run = True
while True:
    now = datetime.datetime.now()
    #get_all_future_position_and_save_to_file()
    if now.minute % 5 == 0 or first_run:
        print(f"Current time: {now}", flush=True)
        remove_order_no_position()
        first_run = False 
        try:
            positions = client.futures_position_information()          
            symbols = fetch_future_symbols()
            for symbol in symbols:
                try:
                    have_position = False
                    for position in positions:
                        if position['symbol'] == symbol and float(position['positionAmt']) != 0:
                            have_position = True
                            break
                    if not have_position:
                        # ลบ order 
                        orders = client.futures_get_open_orders(symbol=symbol)
                        for order in orders:
                            client.futures_cancel_order(symbol=symbol, orderId=order['orderId'])
                        signal = get_buy_sell_signal(symbol)
                        print(f"Signal for {symbol}: {signal}", flush=True)
                        if signal == "BUY":
                            future_create_position(symbol, 'BUY')
                        elif signal == "SELL":
                            future_create_position(symbol, 'SELL')
                except Exception as e:
                    print(f"Error: {e}", flush=True)

            time.sleep(2)
            print("Done", flush=True)

        except Exception as e:
            print(f"Error: {e}", flush=True)
        
        time.sleep(30)

    time.sleep(1)
