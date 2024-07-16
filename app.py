import matplotlib.pyplot as plt
import sys
from scipy import stats
import ccxt
import os
import random
import time
import pandas as pd
import numpy as np
import requests
from binance.client import Client
from datetime import datetime, timedelta
import io
from sklearn.linear_model import LinearRegression
from typing import List
import talib

# ดึงค่า API key และ secret จาก environment variables
#api_key = os.getenv('BINANCE_API_KEY')
#api_secret = os.getenv('BINANCE_SECRET_KEY')
#line_token = os.getenv('LINE_NOTIFY_TOKEN')

api_key="wpq57Bbcr4Wg1jW6iZt5qJ46YEewH7E89eyz31185wqqOjQt1r9n4a3mj1yLUmdN"
api_secret="8wuq8dMQOdsHMOSgjDLQYsPQF3J8CtdMSXu7VrB6ZNhS4VJ94ZM4b5qfu20jtnLU"

api_key_for_withdraw="Ujet1FjuMIwxxyPzArJUu3NDZYXsaqWEj6riAJVintMMtgOQFqfxkDYwLeieyPNb"
api_secret_withdraw="QitSQ5S5WE6qoSecFnFjBzrIBJEivJJPS8NHBhbFgGt0dE6KJrZMEJL5cSGegJhq"

line_token="aMFv92TD5VFEXQ3fU9gN1sAaWWrkyVoo6VlJe95hvE7"
line_token_group="u63d6tjQyeDimyWKB8p2a4uecdtZ7DkKuhTSFNfJoGO"
line_all_message = ""

# สร้างอินสแตนซ์ของ Binance Futures
exchange = ccxt.binance({
    'apiKey': api_key,
    'secret': api_secret,
})

client = Client(api_key, api_secret)
trade_time_frame = '1h'
tread_time_frame_stop_loss = '15m'
limit_time_frame_for_stop_loss = 12
future_leverage = 10
temp_folder = 'temp'
line_all_message = ""
ignore_symbols = ['DONUSDT', 'USDCUSDT', 'SRMUSDT']

# ตรวจสอบว่า API key, secret และ line_token ไม่เป็น None
if not api_key or not api_secret or not line_token:
    raise ValueError("API key, secret หรือ LINE token ไม่ถูกต้อง")


















def analyze_signal(symbol):

    # Get the latest 144 15-minute klines
    #klines = client.get_historical_klines(symbol, Client.KLINE_INTERVAL_15MINUTE, "36 hours ago UTC")
    klines = client.get_historical_klines(symbol, Client.KLINE_INTERVAL_1HOUR, "144 hours ago UTC")

    # Convert to DataFrame
    df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    for col in ['open', 'high', 'low', 'close']:
        df[col] = df[col].astype(float)

    length = 21
    df['o'] = df['open'].shift(length)
    df['h'] = df['high'].shift(length)
    df['l'] = df['low'].shift(length)
    df['c'] = df['close'].shift(length)

    df['d'] = abs(df['c'] - df['o'])

    # Function to calculate pivot high and low
    def pivot_high_low(data, length):
        pivot_high = np.where((data.high > data.high.shift(1)) & (data.high > data.high.shift(-1)) & 
                              (data.high.shift(1) > data.high.shift(2)) & (data.high.shift(-1) > data.high.shift(-2)), data.high, np.nan)
        pivot_low = np.where((data.low < data.low.shift(1)) & (data.low < data.low.shift(-1)) & 
                             (data.low.shift(1) < data.low.shift(2)) & (data.low.shift(-1) < data.low.shift(-2)), data.low, np.nan)
        return pd.Series(pivot_high), pd.Series(pivot_low)

    df['ph'], df['pl'] = pivot_high_low(df, length)

    # Define patterns
    df['hammer'] = (df['pl'].notna() & 
                    (np.minimum(df['o'], df['c']) - df['l'] > df['d']) & 
                    (df['h'] - np.maximum(df['c'], df['o']) < df['d']))

    df['ihammer'] = (df['pl'].notna() & 
                     (df['h'] - np.maximum(df['c'], df['o']) > df['d']) & 
                     (np.minimum(df['c'], df['o']) - df['l'] < df['d']))

    df['bulleng'] = ((df['c'] > df['o']) & 
                     (df['c'].shift(1) < df['o'].shift(1)) & 
                     (df['c'] > df['o'].shift(1)) & 
                     (df['o'] < df['c'].shift(1)))

    df['hanging'] = (df['ph'].notna() & 
                     (np.minimum(df['c'], df['o']) - df['l'] > df['d']) & 
                     (df['h'] - np.maximum(df['o'], df['c']) < df['d']))

    df['shooting'] = (df['ph'].notna() & 
                      (df['h'] - np.maximum(df['o'], df['c']) > df['d']) & 
                      (np.minimum(df['c'], df['o']) - df['l'] < df['d']))

    df['beareng'] = ((df['c'] < df['o']) & 
                     (df['c'].shift(1) > df['o'].shift(1)) & 
                     (df['c'] < df['o'].shift(1)) & 
                     (df['o'] > df['c'].shift(1)))

    # Determine signal
    df['signal'] = 'NORMAL'
    
    # Check for signals in the last 4 time frames
    for i in range(5):  # 0 to 4
        long_condition = df['bulleng'].iloc[-i-1] | df['hammer'].iloc[-i-1] | df['ihammer'].iloc[-i-1]
        short_condition = df['hanging'].iloc[-i-1] | df['shooting'].iloc[-i-1] | df['beareng'].iloc[-i-1]
        
        if long_condition:
            df.loc[df.index[-1], 'signal'] = 'LONG'
            break
        elif short_condition:
            df.loc[df.index[-1], 'signal'] = 'SHORT'
            break

    current_signal = df['signal'].iloc[-1]

    if current_signal != 'NORMAL':

        # Create graph
        plt.figure(figsize=(20, 10))
        plt.plot(df['timestamp'], df['close'], label='Close Price')

        # Plot LONG and SHORT signals
        plt.scatter(df.loc[df['signal'] == 'LONG', 'timestamp'], df.loc[df['signal'] == 'LONG', 'close'], 
                    color='green', marker='^', s=100, label='LONG')
        plt.scatter(df.loc[df['signal'] == 'SHORT', 'timestamp'], df.loc[df['signal'] == 'SHORT', 'close'], 
                    color='red', marker='v', s=100, label='SHORT')

        # Plot individual patterns
        patterns = {
            'hammer': ('Hammer', 'limegreen', '^'),
            'ihammer': ('Inverted Hammer', 'green', '^'),
            'bulleng': ('Bullish Engulfing', 'darkgreen', '^'),
            'hanging': ('Hanging Man', 'salmon', 'v'),
            'shooting': ('Shooting Star', 'red', 'v'),
            'beareng': ('Bearish Engulfing', 'darkred', 'v')
        }

        for pattern, (name, color, marker) in patterns.items():
            plt.scatter(df.loc[df[pattern], 'timestamp'], df.loc[df[pattern], 'close'], 
                        color=color, marker=marker, s=50, label=name)

        plt.title(f"{symbol} - Current Signal: {current_signal}")
        plt.xlabel('Time')
        plt.ylabel('Price')
        plt.legend()

        # Create temp folder if it doesn't exist
        if not os.path.exists('temp'):
            os.makedirs('temp')

        # Save graph
        plt.savefig(f'temp/{symbol}-{current_signal}.png')
        plt.close()

    return current_signal
















def send_line_notify(message, token):
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
    

def colorize(text, color):
    colors = {
        'green': '\033[92m',
        'red': '\033[91m',
        'reset': '\033[0m'
    }
    return f"{colors[color]}{text}{colors['reset']}"

def print_color(text, color):
    print(colorize(text, color), file=sys.stderr, flush=True)

def find_signal(symbol):
    return analyze_signal(symbol)


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

    random.shuffle(filtered_symbols)
    return filtered_symbols

def future_find_signal(timeframe):
    global future_exchange_info 
    global future_balance

    future_exchange_info = client.futures_exchange_info()
    future_balance = future_get_balance()
    print(f"USDT balance: {future_balance}", flush=True)
    if future_balance < 10:
        print("USDT balance is not enough", flush=True)
        return None
    symbols = fetch_future_symbols()
    positions = future_get_position()
    # ลบ file ใน temp folder ทั้งหมด
    for file in os.listdir(temp_folder):
        os.remove(os.path.join(temp_folder, file))

    for symbol in symbols:
        try:
            signal = find_signal(symbol)            
            open_new_position = True
            # ถ้า symbol มี position ให้ตรวจสอบว่าอยู่ข้างเดิมหรือไม่ ถ้าไม่ให้ปิด position แล้วค่อยเปิดใหม่
            if symbol in positions:
                try:
                    position_info = client.futures_position_information(symbol=symbol)
                    position_amount = float(position_info[0]['positionAmt'])
                    if position_amount != 0:
                        open_new_position = False
                        position_side = (position_amount > 0) and 'BUY' or 'SELL'
                        if signal == 'LONG' and position_side == 'SELL':
                            print(f"Close position {symbol} {position_side}", flush=True)
                            client.futures_create_order(
                                symbol=symbol,
                                side='BUY',
                                type='MARKET',
                                quantity=position_amount
                            )
                            open_new_position = True
                        if signal == 'SHORT' and position_side == 'BUY':
                            print(f"Close position {symbol} {position_side}", flush=True)
                            client.futures_create_order(
                                symbol=symbol,
                                side='SELL',
                                type='MARKET',
                                quantity=position_amount
                            )
                            open_new_position = True
                except Exception as e:
                    print(f"Error: {e}", flush=True)

            if open_new_position and (signal == 'LONG' or signal == 'SHORT'):
                color = '🟢' if signal == 'LONG' else '🔴'
                message = f"Binance: Signal detected for {symbol}: {color} {signal}"
                try:
                    print(message, flush=True)
                    if signal == 'LONG':
                        print(f"Open position {symbol} {signal}", flush=True)
                        xresult = future_open_position(symbol, 'BUY')
                        print(f"Open position result: {xresult}", flush=True)
                        if xresult == "STOP":
                            break

                    if signal == 'SHORT':
                        print(f"Open position {symbol} {signal}", flush=True)
                        xresult = future_open_position(symbol, 'SELL')                
                        print(f"Open position result: {xresult}", flush=True)
                        if xresult == "STOP":
                            break
                
                    time.sleep(1)
                except Exception as e:
                    print(f"Error: {e}", flush=True)
        except Exception as e:
            print(f"Error: {e}", flush=True)           
            

def future_compare_stop_loss_all():
    global line_all_message
    
    positions = future_get_position()
    for symbol in positions:        
        future_compare_stop_loss(symbol)
        
    # ตรวจสอบ postion ที่ไม่มี order ให้เตือน line notify
    positions = future_get_position()
    for symbol in positions:
        orders = client.futures_get_open_orders(symbol=symbol)
        if len(orders) == 0:
            try:
                line_all_message += f"Position {symbol} without order\n"
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

def future_open_position(symbol, side,bypass=False):   
    global line_all_message
    global future_balance
    
    if future_balance < 15 and bypass == False:
        print("USDT balance is not enough", flush=True)
        return "STOP"
    
    usdt_amount = future_balance / 40.0
    if bypass == True:
        usdt_amount = usdt_amount / 2    
    print(f"USDT amount for positon : {usdt_amount}", flush=True)

    diff_percent_max = 5 # จะต้องห่างจากราคาปัจจุบันไม่เกินกี่ %

    if bypass == False:
        if not future_get_last_trade(symbol):
            print(f"Skip symbol {symbol} because last trade near", flush=True)
            return "SKIP"

    if future_change_margin_type_and_leverage(symbol) == False:
        print(f"Error changing margin type and leverage for {symbol}", flush=True)
        return e
    
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
        return e
    
    try:
        time.sleep(1)
        print(f"Open position {symbol} {side} {quantity}", flush=True)
        df = pd.DataFrame(client.futures_klines(symbol=symbol, interval=trade_time_frame, limit=7), columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        df = df.iloc[:-2]
        if side == 'BUY':
            if bypass == False:
                df['low'] = df['low'].astype(float)
                min_price = df['low'].min()    
                # ราคาปัจจุบัน ห่างจากราคาต่ำสุดไม่เกิน diff_percent_max
                diff_price = (min_price - current_price) * -1
                diff_percent = (diff_price * 100) / min_price
                if current_price > min_price and diff_percent < diff_percent_max:
                    print(f"Price < MIN : Long Open position {symbol} {quantity}", flush=True)
                    client.futures_create_order(
                        symbol=symbol,
                        side='BUY',
                        type='MARKET',
                        quantity=quantity                
                    )
                    line_all_message += f"Open position {symbol} {side}\n"
            else:
                print(f"Open position {symbol} {side} {quantity}", flush=True)
                # cancel all order before open position
                orders = client.futures_get_open_orders(symbol=symbol)
                for order in orders:
                    print(f"Cancel order {order['orderId']} {symbol}", flush=True)
                    client.futures_cancel_order(symbol=symbol, orderId=order['orderId'])
                time.sleep(1)
                client.futures_create_order(
                    symbol=symbol,
                    side='BUY',
                    type='MARKET',
                    quantity=quantity                
                )
                line_all_message += f"Open position {symbol} {side}\n"
        if side == 'SELL':
            if bypass == False:
                df['high'] = df['high'].astype(float)
                max_price = df['high'].max()
                # ราคาปัจจุบัน ห่างจากราคาสูงสุดไม่เกิน diff_percent_max
                diff_price = max_price - current_price
                diff_percent = (diff_price * 100) / max_price
                if current_price < max_price  and diff_percent < diff_percent_max:
                    print(f"Price > MAX : Short Open position {symbol} {quantity}", flush=True)
                    client.futures_create_order(
                        symbol=symbol,
                        side='SELL',
                        type='MARKET',
                        quantity=quantity
                    )
                    line_all_message += f"Open position {symbol} {side}\n"
            else:
                print(f"Open position {symbol} {side} {quantity}", flush=True)
                # cancel all order before open position
                orders = client.futures_get_open_orders(symbol=symbol)
                for order in orders:
                    print(f"Cancel order {order['orderId']} {symbol}", flush=True)
                    client.futures_cancel_order(symbol=symbol, orderId=order['orderId'])
                time.sleep(1)
                client.futures_create_order(
                    symbol=symbol,
                    side='SELL',
                    type='MARKET',
                    quantity=quantity
                )
                line_all_message += f"Open position {symbol} {side}\n"

    except Exception as e:
        print(f"Error: {e}", flush=True)
        # ถ้า เกิด Margin is insufficient.
        if "Margin is insufficient" in str(e):
            print(f"Margin is insufficient for {symbol}", flush=True)
            return "STOP"

        return e
    
    return "SUCCESS"

def future_get_balance():
    # ดึงข้อมูล account balance
    balance = client.futures_account_balance()
    balance_usdt = 0
    for item in balance:
        if item['asset'] == 'USDT':
            balance_usdt = float(item['balance'])
            break
    print(f"future_get_balance : USDT balance: {balance_usdt}", flush=True)
    return balance_usdt

def future_get_last_trade(symbol):
    return True
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

def calculate_profit_percentage(position):
    entry_price = float(position['entryPrice'])
    mark_price = float(position['markPrice'])
    position_amt = float(position['positionAmt'])
    leverage = float(position['leverage'])

    if position_amt > 0:
        profit = (mark_price - entry_price) * position_amt
    else:
        profit = (entry_price - mark_price) * position_amt

    profit_percent = (profit / (entry_price * position_amt)) * 100
    return profit_percent * leverage
    

def future_find_profit_or_loss():
    positions = future_get_position()
    for symbol in positions:        
        try:
            position_info = client.futures_position_information(symbol=symbol)
            position_amount = float(position_info[0]['positionAmt'])
            if position_amount == 0:
                return None
            profit_percent = calculate_profit_percentage(position_info[0])
            print(f"Profit percent: {profit_percent}", flush=True)
            
            market_type = (position_amount > 0) and 'LONG' or 'SHORT'
            if market_type == 'LONG':
                if profit_percent > 20 or profit_percent < -10:
                    print(f"Profit percent > 20% : Close position {symbol}", flush=True)
                    client.futures_create_order(
                        symbol=symbol,
                        side='SELL',
                        type='MARKET',
                        quantity=position_amount,
                    )
            if market_type == 'SHORT':
                if profit_percent > 20 or profit_percent < -15:
                    print(f"Profit percent > 20% : Close position {symbol}", flush=True)
                    client.futures_create_order(
                        symbol=symbol,
                        side='BUY',
                        type='MARKET',
                        quantity=position_amount * -1,
                    )
        except Exception as e:
            print(f"Error: {e}", flush=True)
            return None
    

def future_compare_stop_loss(symbol):
    global line_all_message
    
    print(f"Compare stop loss {symbol}", flush=True)
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
            df = pd.DataFrame(client.futures_klines(symbol=symbol, interval=tread_time_frame_stop_loss, limit=limit_time_frame_for_stop_loss), columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
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
            limit_time_stop_loss = limit_time_frame_for_stop_loss
            # ดึงกำไรล่าสุด คำนวณเป็น % ของกำไร ถ้ากำไรมากกว่าที่กำหนด ให้ stop loss ใกล้ขึ้น
            #profit_percent = calculate_profit_percentage(position_info[0])
            #print(f"Profit percent: {profit_percent}", flush=True)
            """if profit_percent > 20:
                # ถ้ากำไรมากกว่า 20% ให้ลดเวลาในการเปรียบเทียบ stop loss เป็น step 
                limit_time_stop_loss = limit_time_frame_for_stop_loss - ((profit_percent) % 10)
                limit_time_stop_loss = round(limit_time_stop_loss)
                if limit_time_stop_loss < 4:
                    limit_time_stop_loss = 4
                print(f"Change limit time frame for stop loss to {limit_time_stop_loss}", flush=True)
            """
            """
            if profit_percent > 50:
                # ถ้ากำไรมากกว่า 50% ให้ซื้อเพิ่ม เพราะถือว่าถูกทาง
                print(f"Profit percent > 50% : Buy more {symbol}", flush=True)
                # close open order all
                client.futures_cancel_all_open_orders(symbol=symbol)
                time.sleep(2)
                future_open_position(symbol, position_side,bypass=True)
                time.sleep(5)
                position_info = client.futures_position_information(symbol=symbol)
                position_amount = float(position_info[0]['positionAmt'])
                time.sleep(2)
            """

            # ดึง order ที่เป็น stop loss มาเทียบกับราคาปัจจุบัน
            old_order_stop_price = float(order['stopPrice'])                
            top_price = 0
            bottom_price = 0
            df = pd.DataFrame(client.futures_klines(symbol=symbol, interval=tread_time_frame_stop_loss, limit=limit_time_stop_loss), columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            df['high'] = df['high'].astype(float)
            df['low'] = df['low'].astype(float)
            top_price = df['high'].max()
            bottom_price = df['low'].min()
            if position_side == 'BUY':
                if old_order_stop_price < bottom_price and future_price > bottom_price:
                    print(f"Cancel order {order['orderId']} {symbol}", flush=True)
                    # close open order all
                    client.futures_cancel_all_open_orders(symbol=symbol)
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
                    # close open order all
                    client.futures_cancel_all_open_orders(symbol=symbol)
                    time.sleep(2) 
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

def future_change_margin_type_and_leverage(symbol):
    try:
        # เปลี่ยนเป็น cross margin ถ้าเป็น isolated margin
        positions = client.futures_position_information(symbol=symbol)
        if positions[0]['marginType'] != 'cross':
            print(f"Change margin type to CROSS for {symbol}", flush=True)
            client.futures_change_margin_type(symbol=symbol, marginType='CROSSED')  
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
    global line_all_message
    
    # ดึงช้อมูล จากตลาด Future คำนวณ ยอดกำไร ยอดขายทุน ยอดคงเหลือ กำไรหักขาดทุน ส่ง line notify
    balance = client.futures_account_balance()
    balance_usdt = 0
    profit_usdt = 0
    profit_position_count = 0
    loss_usdt = 0
    loss_position_count = 0
    for item in balance:
        balance_amount = float(item['balance'])
        if balance_amount > 0:
            if item['asset'] == 'USDT' :
                balance_usdt += balance_amount
                break
            else:
                # ดึงราคาปัจจุบันของเหรียญนั้น
                symbol = item['asset'] + 'USDT'
                try:
                    ticker = client.futures_symbol_ticker(symbol=symbol)
                    balance_usdt += balance_amount * float(ticker['price'])
                except Exception as e:
                    print(f"Error with symbol {symbol}: {e}", flush=True)
                    continue            
            

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
    # sort
    spot_account['balances'].sort(key=lambda x: x['asset'])
    for asset in spot_account['balances']:
        total = float(asset['free']) + float(asset['locked'])
        if total > 0:
            if asset['asset'] == 'USDT':
                spot_balance_usdt += total
            else:
                symbol = asset['asset'] + 'USDT'

                try:
                    ticker = client.get_symbol_ticker(symbol=symbol)
                    spot_balance_usdt += total * float(ticker['price'])
                    print(f"Symbol: {symbol} Total: {total} Price: {ticker['price']} Total USDT: {total * float(ticker['price'])}", flush=True)
                except Exception as e:
                    print(f"Error with symbol {symbol}: {e}", flush=True)
                    continue
    print(f"Spot balance: {spot_balance_usdt}", flush=True)

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
            f"{format_message('กำไรสะสม:', spot_balance_usdt, 'USDT')}\n"
            f"{format_message('สุทธิ:', net_usdt, 'USDT')}\n"
            "\nTHB:\n"
            f"{format_message(f'กำไร ({profit_position_count}) ไม้:', profit_thb, 'บาท')}\n"
            f"{format_message(f'ขาดทุน ({loss_position_count}) ไม้:', loss_thb, 'บาท')}\n"
            f"{format_message('ยอดคงเหลือ:', balance_thb, 'บาท')}\n"
            f"{format_message('กำไรสะสม:', spot_balance_thb, 'บาท')}\n"
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
            f"{format_message('กำไรสะสม:', spot_balance_usdt, 'USDT')}\n"
            f"{format_message('สุทธิ:', net_usdt, 'USDT')}\n\n"
            "ไม่สามารถคำนวณเป็นเงินบาทได้ เนื่องจากไม่สามารถดึงข้อมูลอัตราแลกเปลี่ยนได้"
        )

    line_all_message = message + "\n" + line_all_message

def format_message(label, value, unit, width=15):
    return f"{label:<{width}} {value:>{width},.2f} {unit}"

def transfer_usdt_to_spot():
    # ดึงข้อมูลยอดคงเหลือใน Future account
    futures_account_balance = client.futures_account_balance()
    
    # หายอด USDT ที่สามารถโอนได้
    available_balance = 0
    for item in futures_account_balance:
        if item['asset'] == 'USDT':
            # ใช้ 'availableBalance' แทน 'withdrawAvailable'
            available_balance = float(item['availableBalance'])
            break
    
    print(f"Total USDT balance available for transfer from Future to Spot: {available_balance}", flush=True)

    try:
        # คำนวณยอดที่จะโอน (90% ของยอดที่โอนได้ทั้งหมด)
        transfer_amount = available_balance * 0.9
        transfer_amount = round(transfer_amount, 2)  # ปัดเศษทศนิยม 2 ตำแหน่ง
        
        if transfer_amount <= 1000:
            print("No USDT available for transfer", flush=True)
            return None

        result = client.futures_account_transfer(
            asset='USDT',
            amount=transfer_amount,
            type=2  # 2 means transfer from Future to Spot
        )

        print(f"Successfully transferred {transfer_amount} USDT from Future to Spot", flush=True)
        print(f"Remaining balance in Future account: {available_balance - transfer_amount} USDT", flush=True)
        return result

    except Exception as e:
        print(f"Error: {e}", flush=True)
        return None
    
# spot market

def get_spot_usdt_pairs():
    try:
        exchange_info = client.get_exchange_info()
        pairs = [symbol['symbol'] for symbol in exchange_info['symbols']
                if symbol['symbol'].endswith('USDT')
                and 'USDC' not in symbol['symbol']
                and 'BULL' not in symbol['symbol']
                and 'BEAR' not in symbol['symbol']
                and symbol['status'] == 'TRADING']
        print(f"จำนวนคู่เทรด USDT ทั้งหมด: {len(pairs)}")
        return pairs
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการดึงข้อมูล exchange info: {e}")
        return []

def analyze_price_and_buy(spot_symbol):
    try:
        klines = client.get_historical_klines(spot_symbol, Client.KLINE_INTERVAL_1DAY, f"14 days ago UTC")
        
        # ตัดวันแรกออก
        klines = klines[2:]

        if len(klines) == 0:
            print(f"ไม่พบข้อมูลสำหรับ {spot_symbol}")
            return None
        
        # หาราคาต่ำสุด
        lowest_price = min(float(kline[3]) for kline in klines)  # kline[3] คือราคาต่ำสุดของวัน
        
        # ดึงราคาปัจจุบัน
        current_price = float(client.get_symbol_ticker(symbol=spot_symbol)['price'])
        ticker_price = lowest_price * 0.8
        if current_price <= ticker_price:
            print(f"ราคาปัจจุบันของ {spot_symbol} ({current_price:.8f} USDT) ต่ำกว่าราคาต่ำสุดในอดีต")
            buy_coin(spot_symbol, 10)  # ซื้อทันที 10 USD
        else:
            print(f"ราคาปัจจุบันของ {spot_symbol}: {current_price:.8f} USDT / ราคาต่ำสุดในอดีต: {lowest_price:.8f} USDT / ราคาเป้าหมายสำหรับการซื้อ : {ticker_price:.8f} USDT")

    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการวิเคราะห์ราคาสำหรับ {spot_symbol}: {e}")

def buy_coin(symbol, amount_usd):
    try:
        # ดึงข้อมูลราคาปัจจุบัน
        ticker = client.get_symbol_ticker(symbol=symbol)
        price = float(ticker['price'])
        
        # คำนวณจำนวนเหรียญที่จะซื้อ
        quantity = amount_usd / price
        
        # ปรับจำนวนทศนิยมให้ถูกต้องตามข้อกำหนดของ Binance
        info = client.get_symbol_info(symbol)
        step_size = float([f for f in info['filters'] if f['filterType'] == 'LOT_SIZE'][0]['stepSize'])
        quantity = round(quantity - (quantity % step_size), len(str(step_size).split('.')[1]))
        
        # ส่งคำสั่งซื้อ
        order = client.create_order(
            symbol=symbol,
            side=Client.SIDE_BUY,
            type=Client.ORDER_TYPE_MARKET,
            quantity=quantity)
        
        print(f"ซื้อ {symbol} สำเร็จ: จำนวน {quantity} ในราคาประมาณ {price:.8f} USDT")
        return order
    except Exception as e:
        print(f"เกิดข้อผิดพลาดในการซื้อ {symbol}: {e}")
        return None

def spot_main():
    try:
        spot_usdt_pairs = get_spot_usdt_pairs()

        for spot_symbol in spot_usdt_pairs:
            analyze_price_and_buy(spot_symbol)
            time.sleep(0.1)  # เพื่อหลีกเลี่ยงการถูกจำกัดการเรียก API

    except Exception as e:
        print(f"เกิดข้อผิดพลาด: {e}")


# ถอนเหรียญ BNB ไปยังตลาดอื่น จาก spot

def withdraw_bnb(address: str, amount: float):
    client_withdraw = Client(api_key=api_key_for_withdraw, api_secret=api_secret_withdraw)
    try:
        # Get the BNB balance in the spot account
        bnb_balance = float(client_withdraw.get_asset_balance(asset='BNB')['free'])
        
        if bnb_balance < amount:
            print(f"Insufficient BNB balance. Current balance: {bnb_balance}")
            return
        
        # Initiate the withdrawal
        result = client_withdraw.withdraw(
            coin='BNB',
            address=address,
            amount=amount,
            network='BSC'  # Use 'BSC' for BNB Smart Chain, or 'BNB' for Binance Chain
        )
        
        print(f"Withdrawal successful. Transaction ID: {result['id']}")
        return True
        
    except Exception as e:
        print(f"Error: {e}")
    
    return False


def withdraw_bnb_to_other_market():
    target_address = [
        '0x6E7c351F048a6d57e023a9eE7d1c8A6A4F31385C',
        '0x7d4c6fe0cf2345b85f8bdecce7d234fde1c712ba'
    ]

    bnb_amount = 0.002
    for address in target_address:
        withdraw_bnb(address, bnb_amount)


# start
print("Start", flush=True)
future_exchange_info = client.futures_exchange_info()

future_balance = future_get_balance()
#transfer_usdt_to_spot()
#future_change_margin_type_and_leverage_all()
#future_change_margin_type_and_leverage('BTCUSDT')
#future_find_order_no_position()
#future_find_signal(trade_time_frame)
#future_compare_stop_loss_all()
#withdraw_bnb_to_other_market()
first_time = True
#print(get_linear_regression_channel_signal("ACHUSDT"))
while True:
    try:
        date_time_now = datetime.now()
        print(f"Check signal {date_time_now.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
        last_minute = date_time_now.minute
        if first_time == True or last_minute == 0 or last_minute % 15 == 0:
            line_all_message = ""
            if first_time == True:                
                first_time = False
            else:
                time.sleep(30)
            if last_minute == 0:
                future_find_signal(trade_time_frame)
            future_find_order_no_position()
            future_compare_stop_loss_all()
            #future_find_profit_or_loss()
            future_profit_or_loss_notify()
            #transfer_usdt_to_spot()
            if line_all_message != "":
                send_line_notify(line_all_message, line_token)
            if last_minute < 15:
                # สแกนเหรียญใหม่ 15 นาที แรกของทุกๆ ชั่วโมง DCA ราคาต่ำสุด
                print("Scan spot market", flush=True)
                #spot_main()
            else:                
                time.sleep(120)
    except Exception as e:
        print(f"Error: {e}", flush=True)
    time.sleep(10)
