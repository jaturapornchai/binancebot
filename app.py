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

def send_line_notify_thread(message, token):
    try:
        """Send notifications through LINE Notify."""
        headers = {
            'Authorization': f'Bearer {token}',
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

# ฟังก์ชันสำหรับการคำนวณ True Range
def true_range(highs, lows, closes):
    tr = np.zeros(len(closes))
    for i in range(1, len(closes)):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
    return tr

# ฟังก์ชันสำหรับการคำนวณ ATR
def calculate_atr(highs, lows, closes, atr_period=10):
    tr = true_range(highs, lows, closes)
    atr = np.zeros(len(closes))
    atr[atr_period-1] = np.mean(tr[:atr_period])  # คำนวณ ATR เริ่มต้นจากค่าเฉลี่ย TR
    for i in range(atr_period, len(closes)):
        atr[i] = (atr[i-1] * (atr_period - 1) + tr[i]) / atr_period  # คำนวณ ATR ต่อเนื่อง
    return atr

# ฟังก์ชันสำหรับการดึงข้อมูลและคำนวณสัญญาณ BUY/SELL
def get_buy_sell_signal(symbol, atr_period=10, key_value=1):
    # ดึงข้อมูลแท่งเทียนจาก Binance Futures (time frame 5 นาที)
    interval = Client.KLINE_INTERVAL_5MINUTE
    klines = client.futures_klines(symbol=symbol, interval=interval, limit=500)

    # เตรียมข้อมูลราคาจากแท่งเทียน
    highs = np.array([float(kline[2]) for kline in klines])
    lows = np.array([float(kline[3]) for kline in klines])
    closes = np.array([float(kline[4]) for kline in klines])

    # คำนวณ ATR โดยไม่ใช้ TA-Lib
    atr = calculate_atr(highs, lows, closes, atr_period)

    # ค่าตัวแปร a (Key Value)
    n_loss = key_value * atr

    # คำนวณค่าของ ATR Trailing Stop
    atr_trailing_stop = np.zeros(len(closes))
    for i in range(1, len(closes)):
        if closes[i] > atr_trailing_stop[i-1] and closes[i-1] > atr_trailing_stop[i-1]:
            atr_trailing_stop[i] = max(atr_trailing_stop[i-1], closes[i] - n_loss[i])
        elif closes[i] < atr_trailing_stop[i-1] and closes[i-1] < atr_trailing_stop[i-1]:
            atr_trailing_stop[i] = min(atr_trailing_stop[i-1], closes[i] + n_loss[i])
        elif closes[i] > atr_trailing_stop[i-1]:
            atr_trailing_stop[i] = closes[i] - n_loss[i]
        else:
            atr_trailing_stop[i] = closes[i] + n_loss[i]

    # สร้างสถานะซื้อขาย
    pos = np.zeros(len(closes))
    for i in range(1, len(closes)):
        if closes[i-1] < atr_trailing_stop[i-1] and closes[i] > atr_trailing_stop[i]:
            pos[i] = 1  # Buy
        elif closes[i-1] > atr_trailing_stop[i-1] and closes[i] < atr_trailing_stop[i]:
            pos[i] = -1  # Sell
        else:
            pos[i] = pos[i-1]

    # คืนค่าสัญญาณ BUY หรือ SELL
    if pos[-1] == 1:
        return "BUY"
    elif pos[-1] == -1:
        return "SELL"
    else:
        return "HOLD"

def future_get_usdt_balance():
    # ดึงข้อมูล account balance
    balance = client.futures_account_balance()
    balance_usdt = 0
    for item in balance:
        if item['asset'] == 'USDT':
            balance_usdt = float(item['balance'])
            break
    # ถ้ามากกว่า $50 ให้เหลือ $50
    if balance_usdt > 50:
        balance_usdt = 50
    print(f"USDT balance: {balance_usdt}", flush=True)
    balance_usdt = balance_usdt / 1.5
    return balance_usdt

def future_get_position():
    positions_open = []
    positions = client.futures_position_information()
    for position in positions:
        position_amount = float(position['positionAmt'])
        if position_amount != 0:
            positions_open.append(position['symbol'])
    return positions_open

def future_close_all_position():
    # ปิดทุก position ที่เปิดอยู่
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
    quantity = round_quantity(quantity, step_size)
    if side == 'BUY':
        order = client.futures_create_order(symbol=symbol, side='BUY', type='MARKET', quantity=quantity)
    elif side == 'SELL':
        order = client.futures_create_order(symbol=symbol, side='SELL', type='MARKET', quantity=quantity)

# วนลูปทำงานทุก ๆ 5 นาที
symbol = 'NEIROETHUSDT'
last_signal = ""
future_close_all_position()
while True:
    # ตรวจสอบเวลาปัจจุบัน
    now = datetime.datetime.now()

    # ทุก 5 นาที
    if now.minute % 5 == 0 and now.second == 0:
        signal = get_buy_sell_signal(symbol)
        print(f"Check Signal for {symbol} at {now}: {signal}")
        if signal != last_signal:
            last_signal = signal
            print(f"Signal for {symbol} at {now}: {signal}")
            future_create_position(symbol, signal)
            send_line_notify(f"Signal for {symbol} at {now}: {signal}")

        # รอจนถึงวินาทีถัดไปเพื่อหลีกเลี่ยงการรันซ้ำในวินาทีแรกของนาทีเดียวกัน
        time.sleep(1)

    # หน่วงเวลาเล็กน้อยเพื่อหลีกเลี่ยงการใช้ CPU มากเกินไป
    time.sleep(0.5)
