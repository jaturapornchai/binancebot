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
usdt_open_position = 25
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
            #time.sleep(2)
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
                        klines = client.futures_klines(symbol=symbol, interval=tread_time_frame, limit=3)
                        lows = [float(kline[3]) for kline in klines]
                        stop_loss = min(lows)
                        stop_loss = math.floor(stop_loss / get_price_step_size) * get_price_step_size
                        take_profit = ((current_price - stop_loss) * 1.25) + current_price
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
                        """is_take_profit = False
                        for order in find_order:
                            if order['type'] == 'TAKE_PROFIT_MARKET':
                                is_take_profit = True
                                break
                        if not is_take_profit:
                            client.futures_create_order(symbol=symbol, side='SELL', type='TAKE_PROFIT_MARKET', stopPrice=take_profit, quantity=abs(position_amount), timestamp=timestamp, recvWindow=myRecvWindow,closePosition=True)"""
                    else:
                        # หาราคาสูงสุด ย้อนไป 14 time frame
                        klines = client.futures_klines(symbol=symbol, interval=tread_time_frame, limit=3)
                        highs = [float(kline[2]) for kline in klines]
                        stop_loss = max(highs)
                        stop_loss = math.ceil(stop_loss / get_price_step_size) * get_price_step_size
                        take_profit = current_price - ((stop_loss - current_price) * 1.25) 
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
                        """is_take_profit = False
                        for order in find_order:
                            if order['type'] == 'TAKE_PROFIT_MARKET':
                                is_take_profit = True
                                break
                        if not is_take_profit:
                            client.futures_create_order(symbol=symbol, side='BUY', type='TAKE_PROFIT_MARKET', stopPrice=take_profit, quantity=abs(position_amount), timestamp=timestamp, recvWindow=myRecvWindow,closePosition=True)"""
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
            time.sleep(2)
    
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

    













def get_binance_data(symbol, interval, limit=100):
    klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
    df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 
                                     'close_time', 'quote_asset_volume', 'number_of_trades', 
                                     'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df.set_index('timestamp', inplace=True)
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    return df

def linear_regression_channel(df, period=100, dev_multiplier=1):
    x = np.arange(len(df))
    y = df['close'].values
    slope, intercept = np.polyfit(x[-period:], y[-period:], 1)
    
    # คำนวณเส้น Regression
    df['regression_line'] = intercept + slope * x
    
    # คำนวณ Channel
    deviations = df['close'] - df['regression_line']
    std_dev = deviations.std()
    df['upper_channel'] = df['regression_line'] + std_dev * dev_multiplier
    df['lower_channel'] = df['regression_line'] - std_dev * dev_multiplier
    
    # เพิ่มการคำนวณทิศทางเทรนด์
    df['trend'] = np.where(slope > 0, 'UP', 'DOWN')
    
    return df

def check_buy_sell_signal(df):
    X0 = df.iloc[-1]  # แท่งล่าสุด
    X1 = df.iloc[-2]  # แท่งก่อนหน้า
    current_trend = X0['trend']
    
    buy_conditions = [
        X1['high'] >= X1['upper_channel'] and X1['low'] <= X1['upper_channel'],  # X1 ทับเส้นบน
        X0['high'] >= X0['upper_channel'] and X0['low'] <= X0['upper_channel'],  # X0 ทับเส้นบน
        X0['close'] > X0['upper_channel'],  # Close อยู่ด้านบน
        current_trend == 'DOWN'  # เพิ่มเงื่อนไขเทรนด์ลง
    ]
    
    sell_conditions = [
        X1['high'] >= X1['lower_channel'] and X1['low'] <= X1['lower_channel'],  # X1 ทับเส้นล่าง
        X0['high'] >= X0['lower_channel'] and X0['low'] <= X0['lower_channel'],  # X0 ทับเส้นล่าง
        X0['close'] < X0['lower_channel'],  # Close อยู่ด้านล่าง
        current_trend == 'UP'  # เพิ่มเงื่อนไขเทรนด์ขึ้น
    ]
    
    if all(buy_conditions):
        return "BUY"
    elif all(sell_conditions):
        return "SELL"
    return "HOLD"

def check_signal(symbol, interval):
    try:
        df = get_binance_data(symbol, interval)
        df = linear_regression_channel(df)
        return check_buy_sell_signal(df)
    except:
        return "HOLD"  # Return HOLD in case of any errors







first_run = True
while True:
    now = datetime.datetime.now()
    if now.minute == 0 or first_run:
        if first_run == False:
            time.sleep(60)
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
            # ดึงข้อมูล position ที่เปิดอยู่ทั้งหมด   
            position_info_all = client.futures_position_information(timestamp=timestamp, recvWindow=myRecvWindow)

            for symbol in symbols:
                # ตรวจสอบว่ามี position อยู่หรือไม่ ถ้าไม่มีให้ทำต่อ
                is_position = False
                for position in position_info_all:
                    if position['symbol'] == symbol and float(position['positionAmt']) != 0:
                        is_position = True
                        break
                if not is_position:
                    try:
                        orders = client.futures_get_open_orders(symbol=symbol, timestamp=timestamp, recvWindow=myRecvWindow)
                        for order in orders:
                            client.futures_cancel_order(symbol=symbol, orderId=order['orderId'])


                        signal = check_signal(symbol, tread_time_frame)
                        
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

            time.sleep(2)
            print("Done", flush=True)

        except Exception as e:            
            print(f"Main Error: {e}", flush=True)
        xcheck_position_stop_loss_take_profit()
        time.sleep(60)

    time.sleep(1)
