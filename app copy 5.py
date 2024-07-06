import os
import random
import time
import pandas as pd
import numpy as np
from datetime import datetime
import requests
from binance.client import Client
from sklearn.linear_model import LinearRegression

# ดึงค่า API key และ secret จาก environment variables
#api_key = os.getenv('BINANCE_API_KEY')
#api_secret = os.getenv('BINANCE_SECRET_KEY')
#line_token = os.getenv('LINE_NOTIFY_TOKEN')
api_key="wpq57Bbcr4Wg1jW6iZt5qJ46YEewH7E89eyz31185wqqOjQt1r9n4a3mj1yLUmdN"
api_secret="8wuq8dMQOdsHMOSgjDLQYsPQF3J8CtdMSXu7VrB6ZNhS4VJ94ZM4b5qfu20jtnLU"
line_token="aMFv92TD5VFEXQ3fU9gN1sAaWWrkyVoo6VlJe95hvE7"
line_token_group="u63d6tjQyeDimyWKB8p2a4uecdtZ7DkKuhTSFNfJoGO"

# สร้างอินสแตนซ์ของ Binance Futures
client = Client(api_key, api_secret)
future_leverage = 10
tread_time_frame = '1h'

ignore_symbols = ['DONUSDT', 'USDCUSDT', 'SRMUSDT']

# ตรวจสอบว่า API key, secret และ line_token ไม่เป็น None
if not api_key or not api_secret or not line_token:
    raise ValueError("API key, secret หรือ LINE token ไม่ถูกต้อง")

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
    
def send_line_notify_group(message):
    #send_line_notify_thread(message, line_token_group)
    print("Send line notify group", flush=True)

def fetch_future_symbols():
    exchange_info = client.futures_exchange_info()
    symbols = [s['symbol'] for s in exchange_info['symbols'] if s['symbol'].endswith('USDT') and s['status'] == 'TRADING']
    symbols = [symbol for symbol in symbols if symbol not in ignore_symbols]
    symbols.sort()
    # random
    random.shuffle(symbols)
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

def check_signal(symbol, timeframe='1h', window=144, devlen=2.0):
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
        print(f"Error checking signal for {symbol}: {e}", flush=True)
        return 'normal'

def future_find_signal(timeframe, window=100, devlen=2.0):
    global future_exchange_info 
    global future_balance

    future_exchange_info = client.futures_exchange_info()
    future_balance = future_get_balance()
    if future_balance < 10:
        print("USDT balance is not enough", flush=True)
        return None
    
    symbols = fetch_future_symbols()
    positions = future_get_position()
    for symbol in symbols:
        # ถ้า symbol มี position ให้ข้ามไป  
        if symbol in positions:
            continue
        signal = check_signal(symbol, timeframe, window, devlen)
        if signal != 'normal':
            color = '🟢' if signal == 'LONG' else '🔴'
            message = f"Binance: Signal detected for {symbol}: {color} {signal}"
            try:
                print(message, flush=True)
                if signal == 'LONG':
                    print(f"Open position {symbol} {signal}", flush=True)
                    future_open_position(symbol, 'BUY')
                if signal == 'SHORT':
                    print(f"Open position {symbol} {signal}", flush=True)
                    future_open_position(symbol, 'SELL')                
                time.sleep(1)
            except Exception as e:
                print(f"Error sending LINE message: {e}", flush=True)        

def future_compare_stop_loss_all():
    positions = future_get_position()
    for symbol in positions:
        future_compare_stop_loss(symbol)
        
    # ตรวจสอบ postion ที่ไม่มี order ให้เตือน line notify
    positions = future_get_position()
    for symbol in positions:
        orders = client.futures_get_open_orders(symbol=symbol)
        if len(orders) == 0:
            try:
                send_line_notify(f"Position {symbol} without order")
            except Exception as e:
                print(f"Error: {e}", flush=True)

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
    diff_percent_max = 5 # จะต้องห่างจากราคาปัจจุบันไม่เกินกี่ %

    if not future_get_last_trade(symbol):
        print(f"Skip symbol {symbol} because last trade near", flush=True)
        return None

    if future_change_margin_type_and_leverage(symbol) == False:
        print(f"Error changing margin type and leverage for {symbol}", flush=True)
        return None
    
    usdt_amount = future_balance / 125.0    
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
        df = pd.DataFrame(client.futures_klines(symbol=symbol, interval=tread_time_frame, limit=7), columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        df = df.iloc[:-2]
        if side == 'BUY':
            df['low'] = df['low'].astype(float)
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
                    quantity=quantity
                )
                send_line_notify(f"Open position {symbol} {side}")
        if side == 'SELL':
            df['high'] = df['high'].astype(float)
            max_price = df['high'].max()
            # ราคาปัจจุบัน ห่างจากราคาสูงสุดไม่เกิน diff_percent_max
            diff_price = max_price - current_price
            diff_percent = (diff_price * 100) / max_price
            print(f"max_price: {max_price} current_price:{current_price} diff_price: {diff_price} diff_percent: {diff_percent}", flush=True)            
            if current_price < max_price and diff_percent < diff_percent_max:
                print(f"Price > MAX : Short Open position {symbol} {quantity}", flush=True)
                client.futures_create_order(
                    symbol=symbol,
                    side='SELL',
                    type='MARKET',
                    quantity=quantity
                )
                send_line_notify(f"Open position {symbol} {side}")

    except Exception as e:
        print(f"Error: {e}", flush=True)
        return None

def future_get_balance():
    # ดึงข้อมูล account balance
    balance = client.futures_account_balance()
    balance_usdt = 0
    for item in balance:
        if item['asset'] == 'USDT':
            balance_usdt = float(item['balance'])
            break
    print(f"USDT balance: {balance_usdt}", flush=True)
    balance_usdt = balance_usdt / 1.5
    return balance_usdt

def future_get_last_trade(symbol):
    try:
        time_hour = 4
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
    tread_time_frame_stop_loss = '15m'
    limit_time_frame = 14
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
            df = pd.DataFrame(client.futures_klines(symbol=symbol, interval=tread_time_frame_stop_loss, limit=limit_time_frame), columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            df['low'] = df['low'].astype(float)
            df['high'] = df['high'].astype(float)
            if position_side == 'BUY':
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
                    time.sleep(1) 
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
        send_line_notify(f"Error: {e}")
        return None

def future_get_position():
    positions_open = []
    positions = client.futures_position_information()
    for position in positions:
        position_amount = float(position['positionAmt'])
        if position_amount != 0:
            positions_open.append(position['symbol'])
    return positions_open

def future_change_margin_type_and_leverage(symbol):
    try:
        # เปลี่ยนเป็น cross margin ถ้าเป็น isolated margin
        positions = client.futures_position_information(symbol=symbol)
        if positions[0]['marginType'] == 'cross':
            print(f"Change margin type to ISOLATED for {symbol}", flush=True)
            client.futures_change_margin_type(symbol=symbol, marginType='ISOLATED')  
    except Exception as e:
        print(f"Error changing margin type: {e}", flush=True)
        return False
    
    try:
        positions = client.futures_position_information(symbol=symbol)
        current_leverage = positions[0]['leverage']
        if int(current_leverage) != future_leverage:
            print(f"Change leverage to {future_leverage} for {symbol}", flush=True)
            client.futures_change_leverage(symbol=symbol, leverage=future_leverage)
    except Exception as e:
        print(f"Error checking or setting leverage: {e}", flush=True)
        return False
    
    return True

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

    # ตรวจสอบ position ที่มี order มากกว่า 1 order ให้ลบ order ที่เก่าที่สุดออก ให้เหลือ 1 order
    positions = future_get_position()
    for symbol in positions:
        orders = client.futures_get_open_orders(symbol=symbol)
        if len(orders) > 1:
            orders.sort(key=lambda x: x['time'])
            for order in orders[:-1]:
                try:
                    print(f"Cancel order {order['orderId']} {symbol}", flush=True)
                    client.futures_cancel_order(symbol=symbol, orderId=order['orderId'])
                except Exception as e:
                    print(f"Error: {e}", flush=True)

    print("End check order no position : " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"), flush=True)

def future_change_margin_type_and_leverage_all():
    symbols = fetch_future_symbols()
    for symbol in symbols:
        future_change_margin_type_and_leverage(symbol)        

def get_thb_usd_rate():
    url = "https://api.exchangerate-api.com/v4/latest/USD"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        if response.status_code == 200:
            thb_rate = data['rates']['THB']
            return thb_rate
        else:
            return None
    except requests.RequestException:
        return None
    
def future_profit_or_loss_notify():
    # ดึงช้อมูล จากตลาด Future คำนวณ ยอดกำไร ยอดขายทุน ยอดคงเหลือ กำไรหักขาดทุน ส่ง line notify
    balance = client.futures_account_balance()
    balance_usdt = 0
    profit_usdt = 0
    profit_position_count = 0
    loss_usdt = 0
    loss_position_count = 0
    for item in balance:
        if item['asset'] == 'USDT':
            balance_usdt = float(item['balance'])
            break
    positions = client.futures_position_information()
    for position in positions:
        position_amount = float(position['positionAmt'])
        if position_amount != 0:
            symbol = position['symbol']
            position_side = (position_amount > 0) and 'BUY' or 'SELL'
            position_price = float(position['entryPrice'])
            current_price = float(client.futures_symbol_ticker(symbol=symbol)['price'])
            position_profit = (current_price - position_price) * position_amount
            if position_profit > 0:
                profit_usdt += position_profit
                profit_position_count += 1
            if position_profit < 0:
                loss_usdt += position_profit
                loss_position_count += 1
           
    # ดึงทรัพย์ทั้งหมด ของมูลค่าตลาด spot จาก Binance ดึงราคามาด้วย คำนวเป็น USDT
    spot_account = client.get_account()
    spot_balance_usdt = 0
    for asset in spot_account['balances']:
        if float(asset['free']) > 0:
            if asset['asset'] == 'USDT':
                spot_balance_usdt += float(asset['free'])
            else:
                print(asset, flush=True)
                symbol = asset['asset'] + 'USDT'

                try:
                    ticker = client.futures_symbol_ticker(symbol=symbol)
                    spot_balance_usdt += float(asset['free']) * float(ticker['price'])
                except Exception as e:
                    print(f"Error with symbol {symbol}: {e}", flush=True)
                    continue

    # ดึงอัตราแลกเปลี่ยน thb/usd จาก internet
    exchange_rate = get_thb_usd_rate()
    if exchange_rate:
        balance_thb = balance_usdt * exchange_rate
        profit_thb = profit_usdt * exchange_rate
        loss_thb = loss_usdt * exchange_rate
        spot_balance_thb = spot_balance_usdt * exchange_rate
        net_usdt = balance_usdt + profit_usdt + loss_usdt + spot_balance_usdt
        net_thb = balance_thb + profit_thb + loss_thb + spot_balance_thb

        message = (
            "Binance:\n"
            "USDT:\n"
            f"{format_message(f'กำไร ({profit_position_count}) ไม้:', profit_usdt, 'USDT')}\n"
            f"{format_message(f'ขาดทุน ({loss_position_count}) ไม้:', loss_usdt, 'USDT')}\n"
            f"{format_message('ยอดคงเหลือ:', balance_usdt, 'USDT')}\n"
            f"{format_message('สินทรัพย์ Spot:', spot_balance_usdt, 'USDT')}\n"
            f"{format_message('สุทธิ:', net_usdt, 'USDT')}\n"
            "\nTHB:\n"
            f"{format_message(f'กำไร ({profit_position_count}) ไม้:', profit_thb, 'บาท')}\n"
            f"{format_message(f'ขาดทุน ({loss_position_count}) ไม้:', loss_thb, 'บาท')}\n"
            f"{format_message('ยอดคงเหลือ:', balance_thb, 'บาท')}\n"
            f"{format_message('สินทรัพย์ Spot:', spot_balance_thb, 'บาท')}\n"
            f"{format_message('สุทธิ:', net_thb, 'บาท')}"
        )
    else:
        net_usdt = balance_usdt + profit_usdt + loss_usdt + spot_balance_usdt
        message = (
            "Binance:\n"
            "USDT:\n"
            f"{format_message(f'กำไร ({profit_position_count}) ไม้:', profit_usdt, 'USDT')}\n"
            f"{format_message(f'ขาดทุน ({loss_position_count}) ไม้:', loss_usdt, 'USDT')}\n"
            f"{format_message('ยอดคงเหลือ:', balance_usdt, 'USDT')}\n"
            f"{format_message('สินทรัพย์ Spot:', spot_balance_usdt, 'USDT')}\n"
            f"{format_message('สุทธิ:', net_usdt, 'USDT')}\n\n"
            "ไม่สามารถคำนวณเป็นเงินบาทได้ เนื่องจากไม่สามารถดึงข้อมูลอัตราแลกเปลี่ยนได้"
        )

    send_line_notify(message)
    send_line_notify_group(message)

def format_message(label, value, unit, width=15):
    return f"{label:<{width}} {value:>{width},.2f} {unit}"

def transfer_usdt_to_future():
    # ดึง USDT ที่สามารถ transfer ได้
    data = client.futures_account_balance()
    max_withdraw_amount = 0
    for item in data:
        if item['asset'] == 'USDT':
            max_withdraw_amount += float(item['maxWithdrawAmount'])
    
    print(f"USDT balance ready for Transfer : {max_withdraw_amount}", flush=True)

    try:
        client.futures_account_transfer(asset='USDT', amount=max_withdraw_amount - 1000, type=2)

    except Exception as e:
        print(f"Error: {e}", flush=True)
        return None

# start
print("Start", flush=True)
#transfer_usdt_to_future()
#future_change_margin_type_and_leverage_all()
#future_profit_or_loss_notify()
#future_change_margin_type_and_leverage('BTCUSDT')
#future_find_order_no_position()
#future_find_signal(tread_time_frame)
#future_compare_stop_loss_all()
first_time = True
while True:
    try:
        date_time_now = datetime.now()
        print(f"Check signal {date_time_now.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
        last_minute = date_time_now.minute
        if first_time == True or last_minute % 15 == 0:
            first_time = False
            future_find_signal(tread_time_frame)
            future_find_order_no_position()
            future_compare_stop_loss_all()
            future_profit_or_loss_notify()
            transfer_usdt_to_future()
            time.sleep(120)
    except Exception as e:
        send_line_notify(f"Error: {e}")
        print(f"Error: {e}", flush=True)
    time.sleep(10)
