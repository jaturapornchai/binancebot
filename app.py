from typing import List, Tuple
import numpy as np
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
from binance.exceptions import BinanceAPIException

# สร้าง client สำหรับการเชื่อมต่อ Binance API
api_key = 'wpq57Bbcr4Wg1jW6iZt5qJ46YEewH7E89eyz31185wqqOjQt1r9n4a3mj1yLUmdN'
api_secret = '8wuq8dMQOdsHMOSgjDLQYsPQF3J8CtdMSXu7VrB6ZNhS4VJ94ZM4b5qfu20jtnLU'
client = Client(api_key, api_secret)
future_leverage = 10
symbols = []
tread_time_frame = '1h'
ignore_symbols = ['USDCUSDT']
usdt_open_position = 15
myRecvWindow = 60000  

def sync_time_with_server(client):
    server_time = client.get_server_time()
    return server_time['serverTime'] - int(time.time() * 1000)

def get_server_timestamp(client):
    return client.get_server_time()['serverTime']

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

def future_create_position(symbol, side):
    result = ""
    try:
        print(f"Opening position for {symbol} ({side})", flush=True)

        # ตรวจสอบว่ามี position อยู่หรือไม่ ถ้ามี และเป็นสัญญาณกลับกัน ให้ปิดก่อน
        """positions = client.futures_position_information(symbol=symbol)
        for position in positions:
            if float(position['positionAmt']) != 0:
                current_side = 'BUY' if float(position['positionAmt']) > 0 else 'SELL'
                if current_side != side:
                    print(f"Closing position for {symbol} ({current_side})", flush=True)
                    client.futures_create_order(symbol=symbol, side='SELL' if current_side == 'BUY' else 'BUY', type='MARKET', quantity=abs(float(position['positionAmt'])))
                    time.sleep(1)     
                    # clear stop loss and take profit
                    find_order = client.futures_get_open_orders(symbol=symbol)
                    for order in find_order:
                        client.futures_cancel_order(symbol=symbol, orderId=order['orderId'])                               
                        time.sleep(1)     
                else:
                    return ""
        """
        
        # เปลี่ยน leverage และ margin type
        future_change_margin_type_and_leverage(symbol)
        
        # ดึงราคาปัจจุบัน
        ticker = client.futures_symbol_ticker(symbol=symbol)
        current_price = float(ticker['price'])
        step_size = get_step_size(symbol)
        
        # คำนวณปริมาณการซื้อขาย (quantity)
        quantity = usdt_open_position / current_price * future_leverage
        quantity = (quantity // step_size) * step_size
        
        # สร้าง order ใหม่
        timestamp = get_server_timestamp(client)
        try:
            order = client.futures_create_order(
                symbol=symbol, 
                side=side, 
                type='MARKET', 
                quantity=quantity, 
                timestamp=timestamp, 
                recvWindow=myRecvWindow
            )
            print(f"Created new position for {symbol}: {order}", flush=True)
            time.sleep(1)
            #create_position_stop_loss_take_profit(symbol, side, quantity)
            result = "Success"
        except BinanceAPIException as e:
            print(f"Error creating new position for {symbol}: {e}", flush=True)
            raise
        
    except BinanceAPIException as e:
        print(f"Binance API Error for {symbol}: {e}", flush=True)
        result = f"BinanceAPIError: {str(e)}"
    except Exception as e:
        print(f"Unexpected error for {symbol}: {e}", flush=True)
        result = f"UnexpectedError: {str(e)}"

    return result


def create_position_stop_loss_take_profit(symbol, side, quantity):
    time.sleep(1)
    try:
        # คำนวณ timestamp โดยใช้เวลาในเครื่องบวกกับ offset
        timestamp = get_server_timestamp(client)
        
        position_info = client.futures_position_information(symbol=symbol, timestamp=timestamp, recvWindow=myRecvWindow)
        position_enter_price = float(position_info[0]['entryPrice'])
        get_price_step_size = price_step_size(symbol)
        if side == 'BUY':
            # stop loss 1%
            stop_loss = position_enter_price - (position_enter_price * 0.01)
            # take profit 
            take_profit = position_enter_price + (position_enter_price - stop_loss)
            stop_loss = math.floor(stop_loss / get_price_step_size) * get_price_step_size
            take_profit = math.floor(take_profit / get_price_step_size) * get_price_step_size
            stop_loss = round(stop_loss, 8)
            take_profit = round(take_profit, 8)
            client.futures_create_order(symbol=symbol, side='SELL', type='STOP_MARKET', stopPrice=stop_loss, quantity=abs(quantity), timestamp=timestamp, recvWindow=myRecvWindow,closePosition=True)
            time.sleep(1)
            client.futures_create_order(symbol=symbol, side='SELL', type='TAKE_PROFIT_MARKET', stopPrice=take_profit, quantity=abs(quantity), timestamp=timestamp, recvWindow=myRecvWindow,closePosition=True)
        else:
            # stop loss 1%
            stop_loss = position_enter_price + (position_enter_price * 0.01)
            # take profit 
            take_profit = position_enter_price - (stop_loss - position_enter_price)
            stop_loss = math.ceil(stop_loss / get_price_step_size) * get_price_step_size
            take_profit = math.ceil(take_profit / get_price_step_size) * get_price_step_size
            stop_loss = round(stop_loss, 8)
            take_profit = round(take_profit, 8)
            client.futures_create_order(symbol=symbol, side='BUY', type='STOP_MARKET', stopPrice=stop_loss, quantity=abs(quantity), timestamp=timestamp, recvWindow=myRecvWindow,closePosition=True)
            time.sleep(1)
            client.futures_create_order(symbol=symbol, side='BUY', type='TAKE_PROFIT_MARKET', stopPrice=take_profit, quantity=abs(quantity), timestamp=timestamp, recvWindow=myRecvWindow,closePosition=True)

    except Exception as e:
        print(f"Error checking position: {e}", flush=True)


def xcheck_position_stop_loss_take_profit():
    data_limit = 7
    time.sleep(1)
    try:
        # คำนวณ timestamp โดยใช้เวลาในเครื่องบวกกับ offset
        timestamp = get_server_timestamp(client)
        
        positions = client.futures_position_information(
            timestamp=timestamp, recvWindow=myRecvWindow)  # ใช้ timestamp และ recvWindow
        
        for position in positions:
            try:
                symbol = position['symbol']
                position_amount = float(position['positionAmt'])
                if position_amount != 0:                
                    side = 'LONG' if position_amount > 0 else 'SHORT'
                    current_price = float(client.futures_symbol_ticker(symbol=symbol)['price'])
                    get_price_step_size = price_step_size(symbol)
                    if side == 'LONG':
                        # หาราคาต่ำสุด ย้อนไป 14 time frame
                        klines = client.futures_klines(symbol=symbol, interval=tread_time_frame, limit=data_limit)
                        lows = [float(kline[3]) for kline in klines]
                        stop_loss = min(lows)
                        stop_loss = math.floor(stop_loss / get_price_step_size) * get_price_step_size
                        take_profit = ((current_price - stop_loss) * 1.2) + current_price
                        if take_profit < current_price:
                            take_profit = current_price
                        take_profit = math.ceil(take_profit / get_price_step_size) * get_price_step_size
                        position_amount = float(position['positionAmt'])
                        if position_amount > 0:
                            stop_loss = stop_loss - get_price_step_size
                            take_profit = take_profit + get_price_step_size
                        else:
                            stop_loss = stop_loss + get_price_step_size
                            take_profit = take_profit - get_price_step_size
                        take_profit = round(take_profit, 8)
                        stop_loss = round(stop_loss, 8)
                        find_order = client.futures_get_open_orders(symbol=symbol, timestamp=timestamp, recvWindow=myRecvWindow)
                        # ตรวจสอบว่ามี stop loss ถ้าไม่มีให้สร้างใหม่
                        is_stop_loss = False
                        for order in find_order:
                            if order['type'] == 'STOP_MARKET':
                                is_stop_loss = True
                                break
                        if not is_stop_loss:
                            print(f"Stop loss for {symbol}: {stop_loss}, Take profit for {symbol}: {take_profit}", flush=True)
                            client.futures_create_order(symbol=symbol, side='SELL', type='STOP_MARKET', stopPrice=stop_loss, quantity=abs(position_amount), timestamp=timestamp, recvWindow=myRecvWindow,closePosition=True)
                        # ตรวจสอบว่ามี take profit ถ้าไม่มีให้สร้างใหม่
                        is_take_profit = False
                        for order in find_order:
                            if order['type'] == 'TAKE_PROFIT_MARKET':
                                is_take_profit = True
                                break
                        if not is_take_profit:
                            client.futures_create_order(symbol=symbol, side='SELL', type='TAKE_PROFIT_MARKET', stopPrice=take_profit, quantity=abs(position_amount), timestamp=timestamp, recvWindow=myRecvWindow,closePosition=True)
                    else:
                        # หาราคาสูงสุด ย้อนไป 14 time frame
                        klines = client.futures_klines(symbol=symbol, interval=tread_time_frame, limit=data_limit)
                        highs = [float(kline[2]) for kline in klines]
                        stop_loss = max(highs)
                        stop_loss = math.ceil(stop_loss / get_price_step_size) * get_price_step_size
                        take_profit = current_price - ((stop_loss - current_price) * 1.2) 
                        if take_profit > current_price:
                            take_profit = current_price
                        take_profit = math.floor(take_profit / get_price_step_size) * get_price_step_size
                        position_amount = float(position['positionAmt'])
                        if position_amount > 0:
                            stop_loss = stop_loss + get_price_step_size
                            take_profit = take_profit - get_price_step_size
                        else:
                            stop_loss = stop_loss - get_price_step_size
                            take_profit = take_profit + get_price_step_size
                        stop_loss = round(stop_loss, 8)
                        take_profit = round(take_profit, 8)
                        find_order = client.futures_get_open_orders(symbol=symbol, timestamp=timestamp, recvWindow=myRecvWindow)
                        # ตรวจสอบว่ามี stop loss ถ้าไม่มีให้สร้างใหม่
                        is_stop_loss = False
                        for order in find_order:
                            if order['type'] == 'STOP_MARKET':
                                is_stop_loss = True
                                break
                        if not is_stop_loss:
                            print(f"Stop loss for {symbol}: {stop_loss}, Take profit for {symbol}: {take_profit}", flush=True)
                            client.futures_create_order(symbol=symbol, side='BUY', type='STOP_MARKET', stopPrice=stop_loss, quantity=abs(position_amount), timestamp=timestamp, recvWindow=myRecvWindow,closePosition=True)

                        # ตรวจสอบว่ามี take profit ถ้าไม่มีให้สร้างใหม่
                        is_take_profit = False
                        for order in find_order:
                            if order['type'] == 'TAKE_PROFIT_MARKET':
                                is_take_profit = True
                                break
                        if not is_take_profit:
                            client.futures_create_order(symbol=symbol, side='BUY', type='TAKE_PROFIT_MARKET', stopPrice=take_profit, quantity=abs(position_amount), timestamp=timestamp, recvWindow=myRecvWindow,closePosition=True)
            except Exception as e:
                print(f"Error checking position: {e}", flush=True)


    except Exception as e:
        print(f"Error checking position: {e}", flush=True)


def future_change_margin_type_and_leverage(symbol):
    try:
        # คำนวณ timestamp โดยใช้เวลาในเครื่องบวกกับ offset
        timestamp = get_server_timestamp(client)
        
        # ตรวจสอบตำแหน่งปัจจุบัน
        positions = client.futures_position_information(symbol=symbol, timestamp=timestamp, recvWindow=myRecvWindow)  # ใช้ timestamp และ recvWindow
        
        # เปลี่ยนจาก isolated margin เป็น cross margin ถ้าจำเป็น
        if positions[0]['marginType'] == 'isolated':
            print(f"Change margin type to CROSS for {symbol}", flush=True)
            client.futures_change_margin_type(symbol=symbol, marginType='CROSSED', timestamp=timestamp, recvWindow=myRecvWindow)  # ใช้ timestamp และ recvWindow
            time.sleep(1)
    
    except Exception as e:
        print(f"Error changing margin type for {symbol}: {e}", flush=True)
    
    try:
        # ตรวจสอบ leverage ปัจจุบัน
        positions = client.futures_position_information(symbol=symbol, timestamp=timestamp, recvWindow=myRecvWindow)  # ใช้ timestamp และ recvWindow
        current_leverage = positions[0]['leverage']
        
        # เปลี่ยน leverage ถ้าจำเป็น
        if int(current_leverage) != future_leverage:
            print(f"Change leverage to {future_leverage} for {symbol}", flush=True)
            client.futures_change_leverage(symbol=symbol, leverage=future_leverage, timestamp=timestamp, recvWindow=myRecvWindow)  # ใช้ timestamp และ recvWindow
    
    except Exception as e:
        print(f"Error checking or setting leverage for {symbol}: {e}", flush=True)

        
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
        if symbol.endswith('USDT') and symbol not in ignore_symbols:
            if symbol in prices and symbol in volumes:
                volume_usdt = prices[symbol] * volumes[symbol]
                if volume_usdt > 1000000:
                    filtered_symbols.append(symbol)

    filtered_symbols = [x for x in filtered_symbols if not any(c.isdigit() for c in x)]

    np.random.shuffle(filtered_symbols)
    print(f"Filtered symbols: {filtered_symbols}", flush=True)
    return filtered_symbols

def remove_order_stop_loss_or_take_profit():
    try:
        timestamp = get_server_timestamp(client)
        
        # ดึงข้อมูล open orders
        orders = client.futures_get_open_orders(timestamp=timestamp, recvWindow=myRecvWindow)  # เพิ่ม recvWindow
        
        # ตรวจสอบทุกคำสั่งที่เปิดอยู่
        for order in orders:
            try:
                symbol = order['symbol']
                # ลบ stop loss เท่านั้น
                if order['type'] == 'STOP_MARKET' or order['type'] == 'TAKE_PROFIT_MARKET':
                    client.futures_cancel_order(symbol=symbol, orderId=order['orderId'], timestamp=timestamp, recvWindow=myRecvWindow)  # เพิ่ม recvWindow
            
            except Exception as e:
                print(f"Error canceling order for {symbol}: {e}", flush=True)
    
    except Exception as e:
        print(f"Error: {e}", flush=True)

def remove_order_no_position():
    try:
        timestamp = get_server_timestamp(client)

        # ดึงข้อมูล open orders
        orders = client.futures_get_open_orders(
            timestamp=timestamp,
            recvWindow=myRecvWindow) 
        # ตรวจสอบทุกคำสั่งที่เปิดอยู่
        for order in orders:
            print(f"Checking order {order['orderId']} {order['symbol']}", flush=True)
            try:
                symbol = order['symbol']
                is_position = False
                
                # ดึงข้อมูล position
                position_info = client.futures_position_information(symbol=symbol, timestamp=timestamp, recvWindow=myRecvWindow)  
                position_amount = float(position_info[0]['positionAmt'])
                
                # ตรวจสอบว่ามี position อยู่หรือไม่
                if position_amount != 0:
                    is_position = True
                
                # ถ้าไม่มี position ให้ยกเลิก order
                if not is_position:
                    print(f"Cancel order {order['orderId']} {symbol}", flush=True)
                    client.futures_cancel_order(symbol=symbol, orderId=order['orderId'], timestamp=timestamp, recvWindow=myRecvWindow) 
                    time.sleep(1)
            
            except Exception as e:
                print(f"remove_order_no_position Error canceling order for {symbol}: {e}", flush=True)
    except Exception as e:
        print(f"remove_order_no_position Error: {e}", flush=True)

def get_all_future_position_and_save_to_file():
    file_name = 'positions.txt'
    open(file_name, 'w').close()
    positions = client.futures_position_information()
    for position in positions:
        with open(file_name, 'a') as f:
            if float(position['positionAmt']) != 0:
                f.write(f"{position['symbol']}.p\n")
    print("Done", flush=True)        
    
def remove_position_no_order():
    is_have_stop_loss = False
    is_have_trailing_stop = False
    try:
        timestamp = get_server_timestamp(client)
        
        # ดึงข้อมูล position ที่เปิดอยู่ทั้งหมด
        positions = client.futures_position_information(timestamp=timestamp, recvWindow=myRecvWindow)
        
        # ตรวจสอบทุก position
        for position in positions:
            try:
                symbol = position['symbol']
                position_amount = float(position['positionAmt'])
                if position_amount != 0:
                    is_have_stop_loss = False
                    is_have_trailing_stop = False
                    # ดึงข้อมูล open orders
                    orders = client.futures_get_open_orders(symbol=symbol, timestamp=timestamp, recvWindow=myRecvWindow)
                    # ตรวจสอบทุกคำสั่งที่เปิดอยู่
                    for order in orders:
                        if order['type'] == 'STOP_MARKET':
                            is_have_stop_loss = True
                        if order['type'] == 'TRAILING_STOP_MARKET':
                            is_have_trailing_stop = True
                    if not is_have_stop_loss or not is_have_trailing_stop:
                        # close position
                        side = 'LONG' if position_amount > 0 else 'SHORT'
                        print(f"Close position for {symbol} ({side})", flush=True)
                        client.futures_create_order(symbol=symbol, side='SELL' if side == 'LONG' else 'BUY', type='MARKET', quantity=abs(position_amount), timestamp=timestamp, recvWindow=myRecvWindow)
            except Exception as e:
                print(f"Error canceling position for {symbol}: {e}", flush=True)               
    except Exception as e:
        print(f"Error: {e}", flush=True)

    remove_order_no_position()

    





import numpy as np
from typing import List, Tuple

def find_swing_points(prices: np.array, window: int = 5) -> Tuple[List[int], List[int]]:
    """
    Find swing high and low points in price data
    Returns: Tuple of (swing highs indices, swing lows indices)
    """
    highs = []
    lows = []
    
    for i in range(window, len(prices) - window):
        # Check for swing high
        if all(prices[i] >= prices[i-window:i]) and all(prices[i] >= prices[i+1:i+window+1]):
            highs.append(i)
        # Check for swing low
        if all(prices[i] <= prices[i-window:i]) and all(prices[i] <= prices[i+1:i+window+1]):
            lows.append(i)
    
    return highs, lows

def check_swing_signal(client: Client, symbol: str, interval: str = "1h") -> str:
    """
    Check price swing points and return trading signal based on conditions:
    BUY = latest swing low is higher than absolute low and all previous swing lows
    SELL = latest swing high is lower than absolute high and all previous swing highs
    """
    # Get 288 candles of historical data
    klines = client.get_klines(
        symbol=symbol,
        interval=interval,
        limit=288
    )
    
    # Extract close prices
    prices = np.array([float(kline[4]) for kline in klines])
    
    # Find all swing points
    swing_highs, swing_lows = find_swing_points(prices)
    
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return "HOLD"
        
    # Get absolute high and low points
    absolute_high = np.max(prices)
    absolute_low = np.min(prices)
    
    # Get latest swing points
    latest_swing_high = prices[swing_highs[-1]]
    latest_swing_low = prices[swing_lows[-1]]
    
    # Get all previous swing points (excluding the latest)
    previous_swing_highs = prices[swing_highs[:-1]]
    previous_swing_lows = prices[swing_lows[:-1]]
    
    # Check BUY condition:
    # Latest swing low is higher than absolute low AND higher than all previous swing lows
    if (latest_swing_low > absolute_low and 
        all(latest_swing_low > prev_low for prev_low in previous_swing_lows)):
        return "BUY"
    
    # Check SELL condition:
    # Latest swing high is lower than absolute high AND lower than all previous swing highs
    if (latest_swing_high < absolute_high and 
        all(latest_swing_high < prev_high for prev_high in previous_swing_highs)):
        return "SELL"
    
    return "HOLD"

# Example usage:
# client = Client(api_key, api_secret)
# signal = check_swing_signal(client, "BTCUSDT", "1h")
# print(f"Trading Signal: {signal}")







first_run = True
while True:
    now = datetime.datetime.now()
    if now.minute == 0 or first_run:
        print(f"Current time Tread : {now}", flush=True)
        remove_order_no_position()
        remove_order_stop_loss_or_take_profit()         
        first_run = False 
        try:
            # ซิงค์เวลาและดึง offset จากฟังก์ชัน sync_time_with_server
            offset = sync_time_with_server(client)
            
            # คำนวณ timestamp โดยใช้เวลาในเครื่องบวกกับ offset
            timestamp = int(time.time() * 1000) + offset
            
            symbols = fetch_future_symbols()
            # ดึง position ที่เปิดอยู่ ลบออกจาก symbols
            positions = client.futures_position_information(timestamp=timestamp, recvWindow=myRecvWindow)
            for position in positions:
                if float(position['positionAmt']) != 0:
                    if position['symbol'] in symbols:
                        symbols.remove(position['symbol'])
                        
            for symbol in symbols:
                try:
                    """orders = client.futures_get_open_orders(symbol=symbol, timestamp=timestamp, recvWindow=myRecvWindow)
                    for order in orders:
                        client.futures_cancel_order(symbol=symbol, orderId=order['orderId'])"""


                    signal = check_swing_signal(client,symbol,tread_time_frame)
                    print(f"Signal: {signal} for {symbol}", flush=True)
                    
                    if signal == "BUY":
                        print(f"Signal: {signal} for {symbol}", flush=True)
                        result = future_create_position(symbol, 'BUY')
                        if "Margin" in result:
                           break
                    elif signal == "SELL":
                        print(f"Signal: {signal} for {symbol}", flush=True)
                        result = future_create_position(symbol, 'SELL')
                        if "Margin" in result:
                           break
                except Exception as e:
                    print(f"Error: {e}", flush=True)

            time.sleep(1)
            print("Done", flush=True)

        except Exception as e:            
            print(f"Main Error: {e}", flush=True)
        xcheck_position_stop_loss_take_profit()
        time.sleep(60)

    time.sleep(10)
