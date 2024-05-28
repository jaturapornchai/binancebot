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

def fetch_ohlcv(symbol, timeframe='1h', limit=100):
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
    ตรวจสอบสถานะราคาว่าตัดกับเส้น upper channel พอดีและเป็นการตัดขึ้น
    """
    df = fetch_ohlcv(symbol)
    df = linear_regression_channel(df)
    
    current_close = df['close'].iloc[-1]
    current_upper = df['upper_channel'].iloc[-1]
    current_slope = df['slope'].iloc[-1]
    previous_close = df['close'].iloc[-2]

    # ตรวจสอบว่าราคาได้ตัดพอดีกับเส้น upper channel และเป็นการตัดขึ้น
    breakout_up = previous_close < current_upper and current_close >= current_upper
    # ตรวจสอบว่าเส้น Linear Regression Channel เป็นขาลงหรือไม่
    downtrend = current_slope < 0
    
    if breakout_up and downtrend:
        return True
    return False

def get_volume_symbols(symbol, timeframe='1h', limit=24):
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    if len(ohlcv) < limit:
        return 0

    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    total_volume = df['volume'].sum()

    return total_volume

def place_market_order_buy(trading_pair, amount_usd=20):
    trading_pair = trading_pair.replace("/", "_").upper()
    print(f"Place market order for {trading_pair} with {amount_usd} USDT")
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
            # current_price ลดลง 0.01%
            current_price = current_price * 0.9999

            # Create a market order, attempting to set time_in_force to None
            order = gate_api.Order(amount=str(quantity), currency_pair=trading_pair, side="buy", type="limit", time_in_force="gtc", price=str(current_price))
            
            spot_api.create_order(order)
        except GateApiException as ex:
            print(f"Gate API Exception, label: {ex.label} message: {ex.message}")
        except ApiException as e:
            print(f"API Exception when calling SpotApi->create_order: {e}")    
    else:
        print(f"Skip order for {trading_pair}")


def order_buy():
    print("Order buy")
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
    print("Order buy low")
    for symbol in order_symbols:
        try:
            result = check_price_breakout(symbol)
            if result:
                volume = get_volume_symbols(symbol)
                # ค้นหาราคาล่าสุด
                current_price = exchange.fetch_ticker(symbol)['last']
                volume_usd = volume * current_price
                if volume_usd > 10000:            
                    print(symbol, result)
                    place_market_order_buy(symbol)

        except Exception as e:
            print(e)
    print("Order buy end")

def order_remove_all():
    print("Order remove all")
    try:
        # Get all open orders
        open_orders = spot_api.list_all_open_orders()
        print(f"Found {len(open_orders)} open orders.")

        # Cancel each open order
        for pair_order in open_orders:
            for order in pair_order.orders:
                try:
                    spot_api.cancel_order (order.id, order.currency_pair)
                except ApiException as e:
                    print("Error cancelling order:", e)
    except ApiException as e:
        print("Error fetching open orders:", e)        

if __name__ == "__main__":
    print("\033[1;37;40m")
    #order_remove_all()
    #close_all_position()
    #take_profit(True)
    #order_buy()
    #order_buy_use_ema200()
    #order_buy_use_rsi()
    while True:
        try:
            now = datetime.now()
            if now.minute == 1:
                time.sleep(10)
                order_remove_all()
                #take_profit(True)
                order_buy()
                #order_buy_use_ema200()
                #order_buy_use_rsi()
                print("*******************************************")
                time.sleep(60)
        except Exception as e:
            print(f"Exception: {e}")
        time.sleep(10)
