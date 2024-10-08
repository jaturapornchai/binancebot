from typing import List
import numpy as np
from binance.client import Client
import time
import datetime
import requests

# สร้าง client สำหรับการเชื่อมต่อ Binance API
api_key = 'wpq57Bbcr4Wg1jW6iZt5qJ46YEewH7E89eyz31185wqqOjQt1r9n4a3mj1yLUmdN'
api_secret = '8wuq8dMQOdsHMOSgjDLQYsPQF3J8CtdMSXu7VrB6ZNhS4VJ94ZM4b5qfu20jtnLU'
client = Client(api_key, api_secret)
future_leverage = 5
symbols = []
tread_time_frame = '15m'
ignore_symbols = ['USDCUSDT']
usdt_open_position = 15

def price_step_size(symbol):
    exchange_info = client.futures_exchange_info()
    for item in exchange_info['symbols']:
        if item['symbol'] == symbol:
            for filt in item['filters']:
                if filt['filterType'] == 'PRICE_FILTER':
                    return float(filt['tickSize'])
    return None

def calculate_sma(prices, period):
    return np.convolve(prices, np.ones(period), 'valid') / period

def get_buy_sell_signal(symbol):
    try:
        interval = tread_time_frame
        klines = client.futures_klines(symbol=symbol, interval=interval, limit=500)
    except Exception as e:
        print(f"Error fetching klines: {e}", flush=True)
        return None

    # Prepare price data
    closes = np.array([float(kline[4]) for kline in klines])

    # Calculate SMAs
    sma_7 = calculate_sma(closes, 7)
    sma_25 = calculate_sma(closes, 25)

    # ตรวจสอบเงื่อนไขใหม่
    if sma_7[-2] <= sma_25[-2] and sma_7[-1] > sma_25[-1]:
        return "BUY"
    elif sma_7[-2] >= sma_25[-2] and sma_7[-1] < sma_25[-1]:
        return "SELL"
    else:
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
    print(f"Opening position for {symbol} ({side})", flush=True)
    ticker = client.futures_symbol_ticker(symbol=symbol)
    current_price = float(ticker['price'])
    step_size = get_step_size(symbol)
    quantity = usdt_open_position / current_price * future_leverage
    quantity = (quantity // step_size) * step_size
    if side == 'BUY':
        client.futures_create_order(symbol=symbol, side='BUY', type='MARKET', quantity=quantity)
    elif side == 'SELL':
        client.futures_create_order(symbol=symbol, side='SELL', type='MARKET', quantity=quantity)
    time.sleep(1)
    check_position(symbol,current_price)


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
    print(f"Change margin type and leverage for {symbol}", flush=True)
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
        if symbol in prices and symbol in volumes:
            volume_usdt = prices[symbol] * volumes[symbol]
            if volume_usdt > 10000000:
                filtered_symbols.append(symbol)

    # ลบที่มีตัวเลข
    filtered_symbols = [x for x in filtered_symbols if not any(c.isdigit() for c in x)]

    np.random.shuffle(filtered_symbols)
    print(f"Filtered symbols: {filtered_symbols}", flush=True)
    return filtered_symbols


def remove_order_no_position():
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

first_run = True
while True:
    now = datetime.datetime.now()
    if now.minute % 15 == 0 or first_run:
        print(f"Current time: {now}", flush=True)
        first_run = False 
        try:
            symbols = fetch_future_symbols()
            remove_order_no_position()
            # หา position ที่เปิดอยู่
            for symbol in symbols:
                try:
                    signal = get_buy_sell_signal(symbol)
                    if signal:
                        positions = client.futures_position_information()          
                        have_position = False
                        for position in positions:
                            if position['symbol'] == symbol and float(position['positionAmt']) != 0:
                                have_position = True
                                break
                        if not have_position:
                            future_change_margin_type_and_leverage(symbol)
                            future_create_position(symbol, signal)
                except Exception as e:
                    print(f"Error: {e}", flush=True)

            time.sleep(2)

        except Exception as e:
            print(f"Error: {e}", flush=True)
        
        time.sleep(30)

    time.sleep(1)
