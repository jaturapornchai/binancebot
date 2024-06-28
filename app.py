import datetime
import ccxt
import pandas as pd
from datetime import datetime
import requests
from binance.client import Client
import time

# Configure API key authorization
api_key = 'wpq57Bbcr4Wg1jW6iZt5qJ46YEewH7E89eyz31185wqqOjQt1r9n4a3mj1yLUmdN'
api_secret = '8wuq8dMQOdsHMOSgjDLQYsPQF3J8CtdMSXu7VrB6ZNhS4VJ94ZM4b5qfu20jtnLU'
client = Client(api_key, api_secret)
exchange = ccxt.binance()
ignore_symbols = ['DONUSDT', 'USDCUSDT', 'SRMUSDT']
line_token = "cbBeuaCxvJcxe1wxovmMADeRsnktbFvyLizTceJpzbh"
future_balance = 0
future_exchange_info = []
future_leverage = 10
tread_time_frame = '1h'
symbol_file_name = 'symbol.txt'

def send_line_notify(message):
    """Send notifications through LINE Notify."""
    headers = {
        'Authorization': f'Bearer ' + line_token,
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    payload = {'message': message}
    response = requests.post("https://notify-api.line.me/api/notify", headers=headers, params=payload)
    return response.status_code

def fetch_future_symbols():
    info = client.futures_exchange_info()
    symbols = [item['symbol'] for item in info['symbols'] if 'USDT' in item['symbol'] and item['status'] == 'TRADING']
    symbols = [symbol for symbol in symbols if not any(char.isdigit() for char in symbol)]
    symbols = [symbol for symbol in symbols if symbol not in ignore_symbols]
    symbols.sort()    
    return symbols

def rsi(df, periods=14, ema=True):
    close_delta = df['close'].diff()
    
    if ema:
        up = close_delta.clip(lower=0)
        down = -1 * close_delta.clip(upper=0)
        ma_up = up.ewm(com=periods-1, adjust=True, min_periods=periods).mean()
        ma_down = down.ewm(com=periods-1, adjust=True, min_periods=periods).mean()
    else:
        up = close_delta[close_delta > 0].reindex_like(df)
        down = -1 * close_delta[close_delta < 0].reindex_like(df)
        ma_up = up.rolling(window=periods, min_periods=0).mean()
        ma_down = down.rolling(window=periods, min_periods=0).mean()
    
    rs = ma_up / ma_down
    return 100 - (100 / (1 + rs))

def find_swing_points(data, rsi_col='rsi', lb=5):
    swing_highs = []
    swing_lows = []
    
    for i in range(lb, len(data) - lb):
        if data[rsi_col].iloc[i] == max(data[rsi_col].iloc[i - lb:i + lb + 1]):
            swing_highs.append((data.index[i], data[rsi_col].iloc[i]))
        if data[rsi_col].iloc[i] == min(data[rsi_col].iloc[i - lb:i + lb + 1]):
            swing_lows.append((data.index[i], data[rsi_col].iloc[i]))
    
    return swing_highs, swing_lows

def find_divergence(data, swing_highs, swing_lows):
    divergences = {'bullish': [], 'bearish': []}
    
    for i in range(1, len(swing_lows)):
        if swing_lows[i][1] > swing_lows[i - 1][1] and data['close'][swing_lows[i][0]] < data['close'][swing_lows[i - 1][0]]:
            divergences['bullish'].append(swing_lows[i])
    
    for i in range(1, len(swing_highs)):
        if swing_highs[i][1] < swing_highs[i - 1][1] and data['close'][swing_highs[i][0]] > data['close'][swing_highs[i - 1][0]]:
            divergences['bearish'].append(swing_highs[i])
    
    return divergences

def check_div_signal(symbol,time_frame):
    # สร้างเงื่อนไขการเทรด จากการหา divergence ของ RSI
    time_since = 6
    # จำนวนแท่งข้อมูลที่ดึงต่อครั้ง
    limit = 1000  
    # ดึงข้อมูลย้อนหลัง 10 วัน
    since = exchange.milliseconds() - 1000 * 60 * 60 * 24 * 10  

    # ดึงข้อมูลในช่วงเวลาที่กำหนด
    bars = []
    while True:
        ohlcv = exchange.fetch_ohlcv(symbol, time_frame, since, limit)
        if not ohlcv:
            break
        since = ohlcv[-1][0] + 1
        bars.extend(ohlcv)
        if len(ohlcv) < limit:
            break

    data = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    data['timestamp'] = pd.to_datetime(data['timestamp'], unit='ms')
    data.set_index('timestamp', inplace=True)

    data['rsi'] = rsi(data, periods=14)
    swing_highs, swing_lows = find_swing_points(data)
    divergences = find_divergence(data, swing_highs, swing_lows)

    latest_divergence = None

    if divergences['bullish']:
        latest_bullish_divergence = divergences['bullish'][-1][0]
        time_since_bullish = (data.index[-1] - latest_bullish_divergence) // pd.Timedelta(minutes=60)
        if time_since_bullish < time_since:
            latest_divergence = 'long'

    if divergences['bearish']:
        latest_bearish_divergence = divergences['bearish'][-1][0]
        time_since_bearish = (data.index[-1] - latest_bearish_divergence) // pd.Timedelta(minutes=60)
        if time_since_bearish < time_since:
            latest_divergence = 'short'

    if not latest_divergence:
        latest_divergence = 'normal'

    return latest_divergence

def future_get_position():
    # ดึงข้อมูล Position ที่เปิดอยู่ return symbols ใช้ binance api
    positions_open = []
    positions = client.futures_position_information()
    for position in positions:
        position_amount = float(position['positionAmt'])
        if position_amount != 0:
            positions_open.append(position['symbol'])
    return positions_open

def future_get_last_trade(symbol):
    # ดึงข้อมูล Last trade จาก symbol ถ้าไม่มีการเทรดล่าสุด ภายใน ชั่วโมงที่กำหนด ให้ return true
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

def future_open_position(symbol, side):
    # future_change_margin_type_and_leverage(symbol)
    # ตรวจสอบและเปลี่ยน leverage เป็น 5x ถ้าเป็นอย่างอื่น
    #usdt_amount = future_balance / 200.0    
    usdt_amount = future_balance / 10.0    
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
            # ราคาปัจจุบัน ห่างจากราคาสูงสุดไม่เกิน diff_percent_max
            diff_price = max_price - current_price
            diff_percent = (diff_price * 100) / max_price
            print(f"diff_price: {diff_price} diff_percent: {diff_percent}", flush=True)
            if current_price < max_price and diff_percent < diff_percent_max:
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


def future_check_profit_or_loss():
    positions = future_get_position()    
    for position in positions:
        try:
            position_info = client.futures_position_information(symbol=position)
            position_profit_or_loss = float(position_info[0]['unRealizedProfit'])
            position_leverage = float(position_info[0]['leverage'])
            position_amount = float(position_info[0]['positionAmt']) 
            position_enter_amount = position_amount
            if position_enter_amount < 0:
                position_enter_amount = position_enter_amount * -1
            position_enter_price = float(position_info[0]['markPrice'])
            position_enter_total_amount = position_enter_amount * position_enter_price
            position_profit_or_loss_persent = ((position_profit_or_loss * 100) / position_enter_total_amount) * position_leverage
            print(f"Symbol: {position}, Profit/Loss: {position_profit_or_loss} {position_enter_amount} {position_enter_price} {position_profit_or_loss_persent}", flush=True)     
            if position_profit_or_loss_persent < -10:
                # ปิด Position ที่มีขาดทุนมากกว่า 10%
                # ถ้าเป็นฝั่ง short
                if position_amount < 0:
                    print(f"Short Close position {position} {position_amount}", flush=True)
                    
                    # Fetch 29 time frames historical data (24 + 5)
                    bars = exchange.fetch_ohlcv(position, timeframe=tread_time_frame, limit=29)
                    df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    df.set_index('timestamp', inplace=True)
                    
                    # Exclude the most recent 5 time frames
                    df = df.iloc[:-5]
                    
                    # Find the highest price in the remaining 24 time frames
                    max_price = df['high'].max()
                    current_price = float(client.futures_symbol_ticker(symbol=position)['price'])
                    
                    # Close the position if the current price is higher than the max price
                    if current_price > max_price:
                        quantity = position_amount * -1
                        print(f"Price > MAX : Short Close position {position} {quantity}", flush=True)
                        order = client.futures_create_order(
                            symbol=position,
                            side='BUY',
                            type='MARKET',
                            quantity=quantity,
                            recvWindow=5000
                        )                
                # ถ้าเป็นฝั่ง long
                if position_amount > 0:
                    print(f"Long Close position {position} {position_amount}", flush=True)
                    
                    # Fetch 29 time frames historical data (24 + 5)
                    bars = exchange.fetch_ohlcv(position, timeframe=tread_time_frame, limit=29)
                    df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                    df.set_index('timestamp', inplace=True)
                    
                    # Exclude the most recent 5 time frames
                    df = df.iloc[:-5]
                    
                    # Find the lowest price in the remaining 24 time frames
                    min_price = df['low'].min()
                    current_price = float(client.futures_symbol_ticker(symbol=position)['price'])
                    
                    # Close the position if the current price is lower than the min price
                    if current_price < min_price:
                        quantity = position_amount
                        print(f"Price < MIN : Long Close position {position} {quantity}", flush=True)
                        order = client.futures_create_order(
                            symbol=position,
                            side='SELL',
                            type='MARKET',
                            quantity=quantity,
                            recvWindow=5000
                        )
                
            if position_profit_or_loss_persent > 15:
                # ปิด Position ที่มีกำไรมากกว่า 10%
                # ถ้าเป็นฝั่ง short
                if position_amount < 0:
                    quantity = position_amount * -1
                    print(f"Short Close position {position} {quantity}", flush=True)
                    order = client.futures_create_order(
                        symbol=position,
                        side='BUY',
                        type='MARKET',
                        quantity=quantity,
                        recvWindow=5000
                    )
                # ถ้าเป็นฝั่ง long
                if position_amount > 0:
                    quantity = position_amount
                    print(f"Long Close position {position} {quantity}", flush=True)
                    order = client.futures_create_order(
                        symbol=position,
                        side='SELL',
                        type='MARKET',
                        quantity=quantity,
                        recvWindow=5000
                    )
                
        except Exception as e:
            print(f"Error: {e}", flush=True)
            continue

def future_find_signal(open_position=True):
    print("Start check signal : " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"), flush=True)
    symbols = fetch_future_symbols()
    # delet old symbol file
    with open(symbol_file_name, 'w') as f:
        f.write('')
    # write new symbol file
    with open(symbol_file_name, 'a') as f:
        for symbol in symbols:
            try:
                signal = check_div_signal(symbol, tread_time_frame)
                if open_position:
                    close_positioned = False
                    if signal == 'short':
                        is_close = False
                        is_order = True
                        positions = client.futures_position_information(symbol=symbol)
                        for position in positions:
                            position_amount = float(position['positionAmt'])
                            if position_amount != 0:
                                if position_amount > 0.0:
                                    is_close = True
                                    break
                                else:
                                    is_order = False
                                    break
                        if is_close:
                            # ปิด Position BUY ที่เปิดอยู่
                            print(f"Close position {symbol}", flush=True)
                            quantity = float(position['positionAmt']) 
                            client.futures_create_order(
                                symbol=symbol,
                                side='SELL',
                                type='MARKET',
                                quantity=quantity,
                                recvWindow=5000
                            )  
                            # รอให้ Position ปิดเสร็จสิ้น
                            time.sleep(1)
                            close_positioned = True
                        else:
                            # ดึง position ที่เปิดอยู่
                            if not future_get_last_trade(symbol):
                                print(f"Skip symbol {symbol} because last trade near", flush=True)
                                is_order = False
                        if is_order and close_positioned == False:
                            message = f"{signal} Symbol: {symbol}, Signal: {signal}"
                            print(message, flush=True)
                            future_open_position(symbol, "SELL")

                    if signal == 'long':
                        is_close = False
                        is_order = True
                        quantity = 0
                        positions = client.futures_position_information(symbol=symbol)
                        for position in positions:
                            position_amount = float(position['positionAmt'])
                            if position_amount != 0:
                                if position_amount < 0.0: 
                                    is_close = True
                                    break
                                else:
                                    is_order = False
                                    break
                        if is_close:
                            # ปิด Position ที่เปิดอยู่
                            quantity = float(position['positionAmt']) * -1
                            client.futures_create_order(
                                symbol=symbol,
                                side='BUY',
                                type='MARKET',
                                quantity=quantity,
                                recvWindow=5000
                            )
                            # รอให้ Position ปิดเสร็จสิ้น
                            time.sleep(1)
                            close_positioned = True
                        else:
                            if not future_get_last_trade(symbol):
                                print(f"Skip symbol {symbol} because last trade near", flush=True)
                                is_order = False
                        if is_order and close_positioned == False:
                            message = f"Symbol: {symbol}, Signal: {signal}"
                            print(message, flush=True)
                            future_open_position(symbol, "BUY")
                else:
                    if signal != 'normal':
                        message = f"Symbol: {symbol}, Signal: {signal} : {tread_time_frame}"
                        print(message, flush=True)
                        send_line_notify(message)
            except Exception as e:
                print(f"Error: {e}", flush=True)    
                continue    
    # close file
    f.close()
    print("End check signal : " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"), flush=True)

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
    tread_time_frame_stop_loss = '15m'
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
                print(f"Old order stop price: {symbol} {old_order_stop_price} bottom price: {bottom_price} future price: {future_price}", flush=True)
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
    
def future_find_position_no_stop_loss():
    # สร้าง stop loss ให้กับ position ที่ไม่มี stop loss
    print("Start check position no stop loss : " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"), flush=True)
    positions = future_get_position()
    for position in positions:
        future_compare_stop_loss(position)
    # position ที่ไม่มี stop loss ให้ปิด position ทิ้ง
    positions = future_get_position()
    for position in positions:
        try:
            position_info = client.futures_position_information(symbol=position)
            position_amount = float(position_info[0]['positionAmt'])
            if position_amount != 0:
                # ค้นหา stop loss ของ position จาก order ที่เปิดอยู่
                orders = client.futures_get_all_orders(symbol=position)
                is_stop_loss = False
                for order in orders:
                    if order['type'] == 'STOP_MARKET':
                        is_stop_loss = True
                        break
                if not is_stop_loss:
                    # ปิด position ที่ไม่มี stop loss
                    print(f"Close position {position} because no stop loss", flush=True)
                    quantity = float(position_info[0]['positionAmt'])
                    if quantity > 0:
                        client.futures_create_order(
                            symbol=position,
                            side='SELL',
                            type='MARKET',
                            quantity=quantity,
                            recvWindow=5000
                        )
                    if quantity < 0:
                        client.futures_create_order(
                            symbol=position,
                            side='BUY',
                            type='MARKET',
                            quantity=quantity * -1,
                            recvWindow=5000
                        )                
                    
        except Exception as e:
            print(f"Error: {e}", flush=True)
            continue
    print("End check position no stop loss : " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"), flush=True)

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
    print("End check order no position : " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"), flush=True)

def future_find_stop_position():
    print("Start check stop position : " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"), flush=True)
    # หา position ที่ถึง stop loss แล้วให้ปิด position
    positions = future_get_position()
    for position in positions:
        try:
            position_info = client.futures_position_information(symbol=position)
            position_amount = float(position_info[0]['positionAmt'])
            signal =  check_div_signal(position,"15m")
            if signal == 'short' and position_amount > 0:
                # ปิด Position BUY เมื่อมีสัญญาณ short
                print(f"Close position {position} because stop loss", flush=True)
                client.futures_create_order(
                    symbol=position,
                    side='SELL',
                    type='MARKET',
                    quantity=position_amount,
                    recvWindow=5000
                )
            if signal == 'long' and position_amount < 0:
                # ปิด Position SELL เมื่อมีสัญญณ long
                print(f"Close position {position} because stop loss", flush=True)
                client.futures_create_order(
                    symbol=position,
                    side='BUY',
                    type='MARKET',
                    quantity=position_amount * -1,
                    recvWindow=5000
                )
            
        except Exception as e:
            print(f"Error: {e}", flush=True)
            continue
    print("End check stop position : " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"), flush=True)

# start
# clear screen terminal
print("\033[H\033[J")
#future_change_margin_type_and_leverage_all()
future_balance = future_get_balance()
future_exchange_info = client.futures_exchange_info()
#future_open_position('BATUSDT', 'BUY')
#exit()
#future_check_profit_or_loss()
future_find_signal(False)
#future_find_position_no_stop_loss()
#future_find_order_no_position()
#future_find_stop_position()
while True:    
    try:
        date_time_now = datetime.now()
        if date_time_now.minute % 15 == 0:
            time.sleep(10)
            future_exchange_info = client.futures_exchange_info()
            future_balance = future_get_balance()
            #future_check_profit_or_loss()
            #future_find_order_no_position()
            future_find_signal(False)
            time.sleep(10)
            future_find_position_no_stop_loss()
            #future_find_stop_position()
            time.sleep(10)
            future_find_order_no_position()
            time.sleep(120)
    except Exception as e:
        send_line_notify(f"Error: {e}")
        print(f"Error: {e}", flush=True)
    time.sleep(10)
