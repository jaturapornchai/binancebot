import datetime
import ccxt
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from datetime import datetime, timedelta
from termcolor import colored
import requests
import time
import gate_api
from gate_api.exceptions import ApiException, GateApiException

# Configure API key authorization
api_key = "c64a07643c277d2dbd07892bd9804425"
api_secret = "4ef7ba483b69ffcb9735e1e28ec41799ef85950e5b48783ccc47f2e21336f9a5"
configuration = gate_api.Configuration(
    key=api_key,
    secret=api_secret,
)
api_client = gate_api.ApiClient(configuration)
spot_api = gate_api.SpotApi(api_client)
line_token = "cbBeuaCxvJcxe1wxovmMADeRsnktbFvyLizTceJpzbh"

# สร้าง client ของ Gate.io
exchange = ccxt.gateio({
    'apiKey': api_key,
    'secret': api_secret,
})
file_name_symbol = "symbol.txt"

def send_line_notify(message):
    """Send notifications through LINE Notify."""
    headers = {
        'Authorization': f'Bearer ' + line_token,
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    payload = {'message': message}
    response = requests.post("https://notify-api.line.me/api/notify", headers=headers, params=payload)
    return response.status_code

def fetch_ohlcv(symbol, timeframe='15m', limit=100):
    """
    ดึงข้อมูล OHLCV จาก Gate.io
    """
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def linear_regression_channel(df):
    """
    สร้าง Linear Regression Channel จากข้อมูลราคา
    """
    X = np.arange(len(df)).reshape(-1, 1)
    y = df['close'].values

    model = LinearRegression().fit(X, y)
    trend = model.predict(X)

    residuals = y - trend
    std_dev = np.std(residuals)

    upper_channel = trend + 2 * std_dev
    lower_channel = trend - 2 * std_dev

    df['upper_channel'] = upper_channel
    df['lower_channel'] = lower_channel
    df['trend'] = trend
    df['slope'] = np.gradient(trend)
    
    return df

def check_price_breakout(symbol):
    """
    ตรวจสอบสถานะว่าราคาได้ตัดขึ้นกับเส้นบนของ channel ขาลงพอดี
    """
    df = fetch_ohlcv(symbol)
    df = linear_regression_channel(df)
    
    current_close = df['close'].iloc[-1]
    current_upper = df['upper_channel'].iloc[-1]
    previous_close = df['close'].iloc[-2]
    current_slope = df['slope'].iloc[-1]

    # ตรวจสอบว่า channel เป็นขาลง (slope เป็นลบ)
    is_downtrend = current_slope < 0

    # ตรวจสอบว่าราคาได้ตัดขึ้นกับเส้นบนของ channel
    breakout_up = previous_close < current_upper and current_close >= current_upper

    if is_downtrend and breakout_up:
        return True
    return False

def check_price_breakout_down(symbol):
    """
    ตรวจสอบสถานะว่าราคาได้ตัดลงกับเส้นล่างของ channel ขาขึ้นพอดี
    """
    df = fetch_ohlcv(symbol)
    df = linear_regression_channel(df)
    
    current_close = df['close'].iloc[-1]
    current_lower = df['lower_channel'].iloc[-1]
    previous_close = df['close'].iloc[-2]
    current_slope = df['slope'].iloc[-1]

    # ตรวจสอบว่า channel เป็นขาขึ้น (slope เป็นบวก)
    is_uptrend = current_slope > 0

    # ตรวจสอบว่าราคาได้ตัดลงกับเส้นล่างของ channel
    breakout_down = previous_close > current_lower and current_close <= current_lower

    if is_uptrend and breakout_down:
        return True
    return False

def get_volume_symbols(symbol, timeframe='15m', limit=24):
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    if len(ohlcv) < limit:
        return 0

    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    total_volume = df['volume'].sum()

    return total_volume

def place_market_order_buy(trading_pair, amount_usd=20):
    trading_pair = trading_pair.replace("/", "_").upper()
    print(f"Place market order for {trading_pair} with {amount_usd} USDT",flush=True)
    order_now = True
    trades = spot_api.list_my_trades(currency_pair=trading_pair)
    for trade in trades:
        create_time = float(trade.create_time)
        if (time.time() - create_time) < 12 * 60 * 60:
            order_now = False
            break
    if order_now:
        try:
            # Fetch the latest ticker for the trading pair
            ticker = spot_api.list_tickers(currency_pair=trading_pair)[0]
            current_price = float(ticker.last)  # Get the latest price
            quantity = amount_usd / current_price  # Calculate the quantity to buy
            # current_price เพิ่มขึ้น 0.5%
            current_price = current_price * 1.005

            # Create a market order, attempting to set time_in_force to None
            order = gate_api.Order(amount=str(quantity), currency_pair=trading_pair, side="buy", type="limit", time_in_force="gtc", price=str(current_price))
            
            spot_api.create_order(order)
        except GateApiException as ex:
            print(f"Gate API Exception, label: {ex.label} message: {ex.message}",flush=True)
        except ApiException as e:
            print(f"API Exception when calling SpotApi->create_order: {e}",flush=True)    
    else:
        print(f"Skip order for {trading_pair}",flush=True)

def order_buy():
    print("Order buy start",flush=True)
    markets = exchange.load_markets()
    order_symbols = []
    for symbol in markets:
        if symbol.endswith('/USDT'):
            order_symbols.append(symbol)
    # ลบ 3S และ 3L , 5S และ 5L
    order_symbols = [symbol for symbol in order_symbols if '3S' not in symbol and '3L' not in symbol and '5S' not in symbol and '5L' not in symbol]
    # remove USDC
    order_symbols = [symbol for symbol in order_symbols if 'USDC' not in symbol]
    # random
    np.random.shuffle(order_symbols)
    for symbol in order_symbols:
        try:
            result = check_price_breakout(symbol)
            if result:
                volume = get_volume_symbols(symbol)
                # ค้นหาราคาล่าสุด
                current_price = exchange.fetch_ticker(symbol)['last']
                volume_usd = volume * current_price
                if volume_usd > 50000:            
                    print(symbol, result,flush=True)
                    place_market_order_buy(symbol)

        except Exception as e:
            print(e,flush=True)
    print("Order buy end",flush=True)

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

def check_buy_div_signal(symbol):
    timeframe = '15m'
    limit = 1000  # จำนวนแท่งข้อมูลที่ดึงต่อครั้ง
    since = exchange.milliseconds() - 1000 * 60 * 60 * 24 * 30  # ดึงข้อมูลย้อนหลัง 30 วัน

    # ดึงข้อมูลในช่วงเวลาที่กำหนด
    bars = []
    while True:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since, limit)
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

    if divergences['bullish']:
        latest_divergence = divergences['bullish'][-1][0]
        time_since_divergence = (data.index[-1] - latest_divergence) // pd.Timedelta(minutes=60)
        if time_since_divergence <= 6:
            print(f"Symbol: {symbol} - Latest bullish divergence detected at {latest_divergence}, {time_since_divergence} time frames ago.",flush=True)
            return True
    return False

def order_by_divergence():
    markets = exchange.load_markets()
    order_symbols = []
    for symbol in markets:
        if symbol.endswith('/USDT'):
            order_symbols.append(symbol)
    # ลบ 3S และ 3L , 5S และ 5L
    order_symbols = [symbol for symbol in order_symbols if '3S' not in symbol and '3L' not in symbol and '5S' not in symbol and '5L' not in symbol]
    # remove USDC
    order_symbols = [symbol for symbol in order_symbols if 'USDC' not in symbol]
    # random
    np.random.shuffle(order_symbols)
    for symbol in order_symbols:
        buy_signal = check_buy_div_signal(symbol)
        if buy_signal:
            volume = get_volume_symbols(symbol)
            # ค้นหาราคาล่าสุด
            current_price = exchange.fetch_ticker(symbol)['last']
            volume_usd = volume * current_price
            if volume_usd > 50000:            
                print(f"Symbol: {symbol} - Buy signal detected.",flush=True)
                place_market_order_buy(symbol)

def order_stop():
    print("Order stop start",flush=True)
    positions =  spot_api.list_spot_accounts()
    for position in positions:
        symbol = f"{position.currency}_USDT"        
        try:
            if check_price_breakout_down(symbol):
                order = gate_api.Order(amount=str(position.available), currency_pair=f"{position.currency}_USDT", side="sell", type="market", time_in_force="ioc")
                spot_api.create_order(order)
        except Exception as e:
            print(f"{position.currency} Exception: {e}",flush=True)
    print("Order stop end",flush=True)


def order_remove_all():
    print("Order remove all",flush=True)
    try:
        # Get all open orders
        open_orders = spot_api.list_all_open_orders()
        print(f"Found {len(open_orders)} open orders.",flush=True)

        # Cancel each open order
        for pair_order in open_orders:
            for order in pair_order.orders:
                try:
                    spot_api.cancel_order (order.id, order.currency_pair)
                except ApiException as e:
                    print("Error cancelling order:", e,flush=True)
    except ApiException as e:
        print("Error fetching open orders:", e,flush=True)        

def close_all_position():
    # ขายทิ้ง
    positions =  spot_api.list_spot_accounts()
    total_lost = 0
    total_profit = 0
    sum_usdt = 0
    for position in positions:
        try:
            position_available = float(position.available)
            if position_available > 0.01:
                order = gate_api.Order(amount=str(position_available), currency_pair=f"{position.currency}_USDT", side="sell", type="market", time_in_force="ioc")
                spot_api.create_order(order)
        except Exception as e:
            print(f"{position.currency} Exception: {e}",flush=True)

def take_profit():
    print("Take profit",flush=True)
    # get position and show profit and loss
    positions =  spot_api.list_spot_accounts()
    total_lost = 0
    total_profit = 0
    sum_usdt = 0
    for position in positions:
            try:
                if position.currency == 'USDT' or position.currency == 'GT':
                    if position.currency == 'USDT':
                        print(f"{position.currency}: {position.available}",flush=True)
                        sum_usdt += float(position.available)
                    else:
                        currency_pair = f"{position.currency}_USDT"
                        current_price = float(spot_api.list_tickers(currency_pair=currency_pair)[0].last)
                        print(f"{position.currency}: {position.available}, Current Price: {current_price} {float(position.available) * current_price} USDT",flush=True)
                        sum_usdt += float(position.available) * current_price
                else:
                    if position.currency == 'POINT':
                        continue 
                    """if position.currency != 'BNB':
                        continue """
                    position_available = float(position.available)
                    if position_available > 0.01:
                        currency_pair = f"{position.currency}_USDT"
                        current_price = float(spot_api.list_tickers(currency_pair=currency_pair)[0].last)
                        sum_usdt += position_available * current_price
                        if  position_available * current_price > 3:
                            # get ราคาต้นทุนเฉลี่ย
                            trades = spot_api.list_my_trades(currency_pair=currency_pair,limit=1000)
                            # sort trades by timestamp
                            #trades = sorted(trades, key=lambda x: float(x.create_time), reverse=False)
                            total_amount = 0
                            total_quantity = 0
                            for i in range(len(trades) - 1, -1, -1):
                                trade = trades[i]
                                if trade.side == "buy":
                                    total_amount += float(trade.price) * float(trade.amount)
                                    total_quantity += float(trade.amount) - float(trade.fee)
                                else:
                                    total_amount = 0
                                    total_quantity = 0
                            average_cost = 0
                            if total_quantity != 0:
                                average_cost = total_amount / total_quantity
                            
                            """
                            # ขายทิ้ง
                            order = gate_api.Order(amount=str(position_available), currency_pair=f"{position.currency}_USDT", side="sell", type="market", time_in_force="ioc")
                            spot_api.create_order(order)
                            """

                            if average_cost == 0:
                                # ไม่มีข้อมูล ยอมแพ้ ขายทิ้ง
                                #print(f"Average cost is 0 {position.currency}",flush=True)
                                #order = gate_api.Order(amount=str(position_available), currency_pair=f"{position.currency}_USDT", side="sell", type="limit", time_in_force="gtc", price=str(current_price))
                                #spot_api.create_order(order)
                                send_line_notify(f"Average cost is 0 {position.currency}")
                            else:
                                if position_available * current_price > 3:
                                    # คำนวณกำไรขาดทุน=
                                    profit_loss = (current_price - average_cost) * position_available
                                    profit_loss_percent = (current_price - average_cost) / average_cost * 100
                                    # profit_loss_percent format ###.##
                                    profit_loss_percent_str = float("{:.2f}".format(profit_loss_percent))
                                    profit_loss_str = float("{:.2f}".format(profit_loss))
                                    color = "red" if profit_loss_percent < 0 else "green"
                                    print(f"\033[1;{31 if color == 'red' else 32};40m{profit_loss_percent_str}% : {profit_loss_str}$  : {position.currency}: {position_available}, Average Cost: {average_cost}, Current Price: {current_price} {position_available * current_price} USDT",flush=True)
                                    total_lost += profit_loss if profit_loss < 0 else 0
                                    total_profit += profit_loss if profit_loss > 0 else 0
                                    if profit_loss_percent > 5:
                                        # ลดลง 0.5%
                                        current_price = current_price * 0.995
                                        print(f"{position.currency}: {position_available}, Average Cost: {average_cost}, Current Price: {current_price}, Profit: {profit_loss}, Profit %: {profit_loss_percent}",flush=True)
                                        order = gate_api.Order(amount=str(position_available), currency_pair=f"{position.currency}_USDT", side="sell", type="limit", time_in_force="gtc", price=str(current_price))
                                        spot_api.create_order(order)
                                        send_line_notify(f"{position.currency}: take profit {profit_loss_str}$")
                                    if profit_loss_percent < -50:
                                        # loss 50% ซื้อเพิ่ม
                                        # พิมพ์สีเหลือง
                                        print(f"\033[1;33;40m{position.currency}: {position_available}, Average Cost: {average_cost}, Current Price: {current_price}, Profit: {profit_loss}, Profit %: {profit_loss_percent}",flush=True)
                                        place_market_order_buy(f"{position.currency}_USDT")

            except Exception as e:
                print(f"{position.currency} Exception: {e}",flush=True)
    # print blue color
    print("\033[1;34;40m",flush=True)
    print(f"Total Profit: {total_profit}, Total Lost: {total_lost} profit balance {total_profit + total_lost} USDT: {sum_usdt}",flush=True)
    # print black color
    print("\033[1;30;40m",flush=True)

if __name__ == "__main__":
    print("\033[1;37;40m",flush=True)
    order_remove_all()
    #close_all_position()
    take_profit()
    order_buy()
    #order_by_divergence()
    #order_buy_use_ema200()
    #order_buy_use_rsi()
    while True:
        try:
            now = datetime.now()
            if now.minute % 15 == 0:
                time.sleep(10)
                order_remove_all()
                #take_profit()
                #order_buy()
                order_by_divergence()
                #order_buy_use_ema200()
                #order_buy_use_rsi()
                print("*******************************************",flush=True)
                time.sleep(60)
            else:
                if now.minute % 10 == 0:
                    take_profit()
                    time.sleep(60)
        except Exception as e:
            print(f"Exception: {e}",flush=True)
        time.sleep(10)
