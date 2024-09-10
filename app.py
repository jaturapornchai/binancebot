import numpy as np
from binance.client import Client
import time
import datetime
import requests

# สร้าง client สำหรับการเชื่อมต่อ Binance API
api_key = 'wpq57Bbcr4Wg1jW6iZt5qJ46YEewH7E89eyz31185wqqOjQt1r9n4a3mj1yLUmdN'
api_secret = '8wuq8dMQOdsHMOSgjDLQYsPQF3J8CtdMSXu7VrB6ZNhS4VJ94ZM4b5qfu20jtnLU'
line_token = "aMFv92TD5VFEXQ3fU9gN1sAaWWrkyVoo6VlJe95hvE7"
client = Client(api_key, api_secret)
future_leverage = 5
symbols = ['NEIROETHUSDT']
tread_time_frame = '1m'
ignore_symbols = ['DONUSDT', 'USDCUSDT', 'SRMUSDT']

# Function to send LINE notification
def send_line_notify_thread(message, token):
    try:
        headers = {
            'Authorization': f'Bearer ' + token,
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        payload = {'message': message}
        response = requests.post("https://notify-api.line.me/api/notify", headers=headers, params=payload)
        if response.status_code == 200:
            print("LINE notification sent successfully", flush=True)
        else:
            print(f"Failed to send LINE notification. Status code: {response.status_code}", flush=True)
    except Exception as e:
        print(f"Error sending LINE message: {e}", flush=True)

def send_line_notify(message):
    send_line_notify_thread(message, line_token)
    print("Send line notify", flush=True)

# Function to calculate EMA
def calculate_ema(prices, period):
    ema = np.zeros(len(prices))
    multiplier = 2 / (period + 1)
    ema[0] = prices[0]
    for i in range(1, len(prices)):
        ema[i] = (prices[i] - ema[i - 1]) * multiplier + ema[i - 1]
    return ema

# Function to generate buy/sell signal based on EMA 7, 25, and 99
def get_buy_sell_signal(symbol):
    try:
        interval = tread_time_frame
        klines = client.futures_klines(symbol=symbol, interval=interval, limit=500)
    except Exception as e:
        print(f"Error fetching klines: {e}", flush=True)
        return None

    # Prepare price data
    closes = np.array([float(kline[4]) for kline in klines])

    # Calculate EMAs
    ema_7 = calculate_ema(closes, 7)
    ema_25 = calculate_ema(closes, 25)
    ema_99 = calculate_ema(closes, 99)

    # Generate buy signal: EMA 7 > EMA 25 and EMA 25 crosses above EMA 99
    buy_signal = ema_7[-1] > ema_25[-1] and ema_25[-2] < ema_99[-2] and ema_25[-1] > ema_99[-1]

    # Generate sell signal: EMA 7 < EMA 25 and EMA 25 crosses below EMA 99
    sell_signal = ema_7[-1] < ema_25[-1] and ema_25[-2] > ema_99[-2] and ema_25[-1] < ema_99[-1]

    if buy_signal:
        return "BUY"
    elif sell_signal:
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
    if balance_usdt > 100:
        balance_usdt = 100
    print(f"USDT balance: {balance_usdt}", flush=True)
    balance_usdt = balance_usdt / 1.5
    return balance_usdt

def future_close_all_position():
    positions = client.futures_position_information()
    for position in positions:
        position_amount = float(position['positionAmt'])
        if position_amount != 0:
            symbol = position['symbol']
            side = 'SELL' if position_amount > 0 else 'BUY'
            print(f"Closing position for {symbol} ({side})", flush=True)
            try:
                client.futures_create_order(symbol=symbol, side=side, type='MARKET', quantity=abs(position_amount))
            except Exception as e:
                print(f"Error closing position for {symbol}: {e}", flush=True)

def get_step_size(symbol):
    exchange_info = client.futures_exchange_info()
    for item in exchange_info['symbols']:
        if item['symbol'] == symbol:
            for filt in item['filters']:
                if filt['filterType'] == 'LOT_SIZE':
                    return float(filt['stepSize'])
    return None

def future_create_position(symbol, side):
    future_close_all_position()
    time.sleep(5)
    usdt_amount = future_get_usdt_balance()
    if usdt_amount <= 10:
        print("Not enough balance to open position", flush=True)
        return
    print(f"Opening position for {symbol} ({side})", flush=True)
    ticker = client.futures_symbol_ticker(symbol=symbol)
    current_price = float(ticker['price'])
    step_size = get_step_size(symbol)
    quantity = usdt_amount / current_price * future_leverage
    quantity = (quantity // step_size) * step_size
    if side == 'BUY':
        client.futures_create_order(symbol=symbol, side='BUY', type='MARKET', quantity=quantity)
    elif side == 'SELL':
        client.futures_create_order(symbol=symbol, side='SELL', type='MARKET', quantity=quantity)

# ตรวจสอบ position ที่ไม่มี stop loss และ take profit แล้วปิดทิ้ง เพิ่มจะสร้างใหม่
def check_position():
    positions = client.futures_position_information()
    for position in positions:
        position_amount = float(position['positionAmt'])
        if position['positionSide'] == 'BOTH' and position_amount != 0:            
            symbol = position['symbol']
            # ดึง order id
            print(f"Checking position for {symbol}", flush=True)

            # ลบ order stop loss และ take profit ทิ้ง
            try:
                client.futures_cancel_all_open_orders(symbol=symbol)
                time.sleep(1)
            except Exception as e:
                print(f"Error cancelling orders for {symbol}: {e}", flush=True)
            # ดึงราคาต่ำสุดและสูงสุด ย้อนหลังไป 28 time frame (tread_time_frame)
            try:
                klines = client.futures_klines(symbol=symbol, interval=tread_time_frame, limit=28)
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
                    client.futures_create_order(symbol=symbol, side='SELL', type='STOP_MARKET', quantity=abs(position_amount), stopPrice=low_min,closePosition=True)
                except Exception as e:
                    print(f"Error setting stop loss for {symbol}: {e}", flush=True)
            # ถ้า SELL position ให้สร้าง stop loss โดยใช้ high_max
            elif position_amount < 0:
                try:
                    client.futures_create_order(symbol=symbol, side='BUY', type='STOP_MARKET', quantity=abs(position_amount), stopPrice=high_max,closePosition=True)
                except Exception as e:
                    print(f"Error setting stop loss for {symbol}: {e}", flush=True)

def future_change_margin_type_and_leverage(symbol):
    print(f"Change margin type and leverage for {symbol}", flush=True)
    try:
        # เปลี่ยนเป็น isolated margin ถ้าเป็น cross margin
        positions = client.futures_position_information(symbol=symbol)
        if positions[0]['marginType'] == 'cross':
            print(f"Change margin type to ISOLATED for {symbol}", flush=True)
            client.futures_change_margin_type(symbol=symbol, marginType='ISOLATED')  
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

def future_change_margin_type_and_leverage_all():
    symbols = fetch_future_symbols()
    for symbol in symbols:
        future_change_margin_type_and_leverage(symbol)        

def fetch_future_symbols():
    info = client.futures_exchange_info()
    symbols = [item['symbol'] for item in info['symbols'] if 'USDT' in item['symbol'] and item['status'] == 'TRADING']
    symbols = [symbol for symbol in symbols if not any(char.isdigit() for char in symbol)]
    symbols = [symbol for symbol in symbols if symbol not in ignore_symbols]
    symbols.sort()    
    # random 
    np.random.shuffle(symbols)
    return symbols

def find_symbol_action():
    symbols = fetch_future_symbols()
    for symbol in symbols:
        signal = get_buy_sell_signal(symbol)
        if signal:
            return symbol, signal
    return None, None

#future_change_margin_type_and_leverage_all()
first_run = True
symbol_action = ""
while True:
    now = datetime.datetime.now()

    if now.second == 0 or first_run:
        print(f"Current time: {now}", flush=True)
        first_run = False 
        try:
            # หา position ที่เปิดอยู่
            positions = client.futures_position_information()
            have_position = False
            for position in positions:
                if float(position['positionAmt']) != 0:
                    have_position = True
                    break
            if not have_position:
                symbol_action,signal = find_symbol_action()
                if symbol_action and signal:
                    future_create_position(symbol_action, signal)
                    send_line_notify(f"Open Order Signal for {symbol_action} at {now}: {signal}")
            else:
                check_position()

            time.sleep(1)

        except Exception as e:
            print(f"Error: {e}", flush=True)
            send_line_notify(f"Error: {e}") 

    time.sleep(0.5)
