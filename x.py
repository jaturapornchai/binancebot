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
tread_time_frame = '15m'
exchange = ccxt.binance()
ignore_symbols = ['DONUSDT', 'USDCUSDT', 'SRMUSDT']
line_token = "cbBeuaCxvJcxe1wxovmMADeRsnktbFvyLizTceJpzbh"

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

def get_usdt_volume_symbols(symbol, limit=24):
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=tread_time_frame, limit=limit)
    if len(ohlcv) < limit:
        return 0

    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    total_volume = df['volume'].sum()

    # ดึงราคาล่าสุด จาก Binance API และคำนวณหามูลค่า Volume เป็น USDT
    ticker = exchange.fetch_ticker(symbol)
    last_price = ticker['last']
    total_volume = total_volume * last_price    

    return total_volume

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

def check_div_signal(symbol):
    # จำนวนแท่งข้อมูลที่ดึงต่อครั้ง
    limit = 1000  
    # ดึงข้อมูลย้อนหลัง 10 วัน
    since = exchange.milliseconds() - 1000 * 60 * 60 * 24 * 10  

    # ดึงข้อมูลในช่วงเวลาที่กำหนด
    bars = []
    while True:
        ohlcv = exchange.fetch_ohlcv(symbol, tread_time_frame, since, limit)
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
        if time_since_bullish < 6:
            latest_divergence = 'long'

    if divergences['bearish']:
        latest_bearish_divergence = divergences['bearish'][-1][0]
        time_since_bearish = (data.index[-1] - latest_bearish_divergence) // pd.Timedelta(minutes=60)
        if time_since_bearish < 6:
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
    # ดึงข้อมูล Last trade จาก symbol ถ้าไม่มีการเทรดล่าสุด ภายใน 4 ชั่วโมง ให้ return true
    trades = client.futures_account_trades(symbol=symbol)
    if len(trades) == 0:
        return True
    last_trade = trades[-1]
    trade_time = datetime.fromtimestamp(last_trade['time'] / 1000)
    time_diff = datetime.now() - trade_time
    if time_diff.total_seconds() < 60 * 60 * 4:
        return False
    return True


def set_leverage(symbol, leverage):
    try:
        response = client.futures_change_leverage(symbol=symbol, leverage=leverage)
        return response
    except Exception as e:
        print(f"Error: {e}", flush=True)
        return None

def get_step_size(symbol):
    info = client.futures_exchange_info()
    for item in info['symbols']:
        if item['symbol'] == symbol:
            for filt in item['filters']:
                if filt['filterType'] == 'LOT_SIZE':
                    return float(filt['stepSize'])
    return None

def get_tick_size(symbol):
    info = client.futures_exchange_info()
    for item in info['symbols']:
        if item['symbol'] == symbol:
            for filt in item['filters']:
                if filt['filterType'] == 'PRICE_FILTER':
                    return float(filt['tickSize'])
    return None

def round_quantity(quantity, step_size):
    return (quantity // step_size) * step_size

def round_price(price, tick_size):
    return round(price / tick_size) * tick_size

def future_open_position(symbol, side, usdt_amount, leverage=5):
    # ตรวจสอบและเปลี่ยน leverage เป็น 5x ถ้าเป็นอย่างอื่น
    try:
        positions = client.futures_position_information(symbol=symbol)
        current_leverage = positions[0]['leverage']
        if int(current_leverage) != leverage:
            set_leverage(symbol, leverage)
            time.sleep(1)  # รอให้ leverage เปลี่ยนแปลงเสร็จสิ้น
    except Exception as e:
        print(f"Error checking or setting leverage: {e}", flush=True)
        return None
    
    # หาราคาสูงสุดย้อนหลัง 14 time frame จาก Binance API เปรียบเทียบราคาปัจจุบัน ถ้ามากกว่า 5% ให้ return None
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, tread_time_frame, limit=14)
        if len(ohlcv) < 14:
            return None
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        current_price = float(client.futures_symbol_ticker(symbol=symbol)['price'])
        highest_price = df['high'].max()
        if current_price < highest_price * 0.95:
            print(f"Current price is not within 5% of the highest price, skipping: {current_price} {highest_price}", flush=True)
            return None
    except Exception as e:
        print(f"Error checking highest price: {e}", flush=True)
        return None
    
    # คำนวณจำนวน contracts จากจำนวนเงิน USDT
    try:
        current_price = float(client.futures_symbol_ticker(symbol=symbol)['price'])
        step_size = get_step_size(symbol)
        tick_size = get_tick_size(symbol)
        quantity = usdt_amount / current_price * leverage
        quantity = round_quantity(quantity, step_size)
    except Exception as e:
        print(f"Error calculating quantity: {e}", flush=True)
        return None
    
    # ฟังก์ชันเปิด Position ใน Binance Futures
    try:
        # เปิด Position
        order = client.futures_create_order(
            symbol=symbol,
            side=side,
            type='MARKET',
            quantity=quantity,
            reduceOnly=False,
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
            position_enter_amount = float(position_info[0]['positionAmt']) * -1
            position_enter_price = float(position_info[0]['markPrice'])
            position_enter_total_amount = position_enter_amount * position_enter_price
            position_profit_or_loss_persent = ((position_profit_or_loss * 100) / position_enter_total_amount) * position_leverage
            print(f"Symbol: {position}, Profit/Loss: {position_profit_or_loss} {position_enter_amount} {position_enter_price} {position_profit_or_loss_persent}", flush=True)            
            if position_profit_or_loss_persent > 15:
                # ปิด Position ที่มีกำไรมากกว่า 15%
                quantity = float(position_info[0]['positionAmt']) * -1
                order = client.futures_create_order(
                    symbol=position,
                    side='BUY',
                    type='MARKET',
                    quantity=quantity,
                    reduceOnly=True,
                    recvWindow=5000
                )            
                
        except Exception as e:
            print(f"Error: {e}", flush=True)
            continue


def future_find_short_signal():
    symbols = fetch_future_symbols()
    for symbol in symbols:
        try:
            signal = check_div_signal(symbol)
            if signal == 'short':
                if not future_get_last_trade(symbol):
                    print(f"Skip symbol {symbol} because last trade within 4 hours", flush=True)
                    continue
                message = f"Symbol: {symbol}, Signal: {signal}"
                print(message, flush=True)
                send_line_notify(message)
                future_open_position(symbol, "SELL", 10)
        except Exception as e:
            print(f"Error: {e}", flush=True)    
            continue    
    print("End check signal : " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"), flush=True)

future_check_profit_or_loss()
future_find_short_signal()
while True:    
    date_time_now = datetime.now()
    """if date_time_now.minute == 1:
        future_check_profit_or_loss()
        future_find_short_signal()
        time.sleep(120)"""
    if date_time_now.minute % 15 == 0:
        future_check_profit_or_loss()
        future_find_short_signal()
        time.sleep(120)
    time.sleep(10)
