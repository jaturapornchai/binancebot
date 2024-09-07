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

# Function to send LINE notification
def send_line_notify_thread(message, token):
    try:
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        payload = {'message': message}
        response = requests.post("https://notify-api.line.me/api/notify", headers=headers, params=payload)
        if response.status_code == 200:
            print("LINE notification sent successfully")
        else:
            print(f"Failed to send LINE notification. Status code: {response.status_code}")
    except Exception as e:
        print(f"Error sending LINE message: {e}")

def send_line_notify(message):
    send_line_notify_thread(message, line_token)
    print("Send line notify")

# Function to calculate Heikin Ashi candles
def calculate_heikin_ashi(klines):
    heikin_ashi_closes = np.zeros(len(klines))
    heikin_ashi_opens = np.zeros(len(klines))
    heikin_ashi_highs = np.zeros(len(klines))
    heikin_ashi_lows = np.zeros(len(klines))

    for i in range(len(klines)):
        open_price = float(klines[i][1])
        high_price = float(klines[i][2])
        low_price = float(klines[i][3])
        close_price = float(klines[i][4])

        # Calculate Heikin Ashi Close
        heikin_ashi_closes[i] = (open_price + high_price + low_price + close_price) / 4

        if i == 0:
            heikin_ashi_opens[i] = (open_price + close_price) / 2
        else:
            heikin_ashi_opens[i] = (heikin_ashi_opens[i-1] + heikin_ashi_closes[i-1]) / 2

        heikin_ashi_highs[i] = max(high_price, heikin_ashi_opens[i], heikin_ashi_closes[i])
        heikin_ashi_lows[i] = min(low_price, heikin_ashi_opens[i], heikin_ashi_closes[i])

    return heikin_ashi_opens, heikin_ashi_highs, heikin_ashi_lows, heikin_ashi_closes

# Function to generate buy/sell signal using Heikin Ashi
def get_buy_sell_signal(symbol, atr_period=10, key_value=1):
    interval = Client.KLINE_INTERVAL_5MINUTE  # Using 5-minute interval
    klines = client.futures_klines(symbol=symbol, interval=interval, limit=500)

    # Calculate Heikin Ashi candles
    heikin_ashi_opens, heikin_ashi_highs, heikin_ashi_lows, heikin_ashi_closes = calculate_heikin_ashi(klines)

    # Generate buy/sell signals based on Heikin Ashi color
    if heikin_ashi_closes[-1] > heikin_ashi_opens[-1]:  # Green candle (bullish)
        return "BUY"
    elif heikin_ashi_closes[-1] < heikin_ashi_opens[-1]:  # Red candle (bearish)
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
    if balance_usdt > 50:
        balance_usdt = 50
    print(f"USDT balance: {balance_usdt}")
    balance_usdt = balance_usdt / 1.5
    return balance_usdt

def future_close_all_position():
    positions = client.futures_position_information()
    for position in positions:
        position_amount = float(position['positionAmt'])
        if position_amount != 0:
            symbol = position['symbol']
            side = 'SELL' if position_amount > 0 else 'BUY'
            print(f"Closing position for {symbol} ({side})")
            try:
                client.futures_create_order(symbol=symbol, side=side, type='MARKET', quantity=abs(position_amount))
            except Exception as e:
                print(f"Error closing position for {symbol}: {e}")

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
        print("Not enough balance to open position")
        return
    print(f"Opening position for {symbol} ({side})")
    ticker = client.futures_symbol_ticker(symbol=symbol)
    current_price = float(ticker['price'])
    step_size = get_step_size(symbol)
    quantity = usdt_amount / current_price * future_leverage
    quantity = (quantity // step_size) * step_size
    if side == 'BUY':
        client.futures_create_order(symbol=symbol, side='BUY', type='MARKET', quantity=quantity)
    elif side == 'SELL':
        client.futures_create_order(symbol=symbol, side='SELL', type='MARKET', quantity=quantity)

# Main loop to check signals and take actions
symbol = 'IOSTUSDT'
last_signal = ""
future_close_all_position()
signal = get_buy_sell_signal(symbol)
print(f"Initial signal for {symbol}: {signal}")
while True:
    now = datetime.datetime.now()

    if now.minute % 5 == 0 and now.second == 0:
        signal = get_buy_sell_signal(symbol)
        if signal and signal != last_signal:
            last_signal = signal
            print(f"Signal for {symbol} at {now}: {signal}")
            future_create_position(symbol, signal)
            send_line_notify(f"Signal for {symbol} at {now}: {signal}")

        time.sleep(1)

    time.sleep(0.5)
