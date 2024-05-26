import ccxt
import requests
import datetime
import time
import gate_api
from gate_api.exceptions import ApiException, GateApiException
from typing import List
import pandas as pd
import os
import numpy as np

# Configure API key authorization: (Replace 'your_api_key' and 'your_api_secret' with your actual Gate.io API key and secret)
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
        'Authorization': f'Bearer {line_token}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    payload = {'message': message}
    response = requests.post("https://notify-api.line.me/api/notify", headers=headers, params=payload)
    return response.status_code

def place_market_order_buy(trading_pair, amount_usd=20):
    trading_pair = trading_pair.replace("/", "_")
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
            # current_price ลดลง 0.1%
            current_price = current_price * 0.999

            # Create a market order, attempting to set time_in_force to None
            order = gate_api.Order(amount=str(quantity), currency_pair=trading_pair, side="buy", type="limit", time_in_force="gtc", price=str(current_price))
            
            spot_api.create_order(order)
            return True
        except GateApiException as ex:
            print(f"Gate API Exception, label: {ex.label} message: {ex.message}")
        except ApiException as e:
            print(f"API Exception when calling SpotApi->create_order: {e}")    
    else:
        print(f"Skip order for {trading_pair}")
    
    return False

def get_usdt_markets_with_info():
    try:
        tickers = spot_api.list_tickers()
        usdt_tickers_info = [
            {
                'pair': ticker.currency_pair,
                'last_price': ticker.last,
                'percentage_change': ticker.change_percentage,
                'volume': ticker.quote_volume  # Make sure this is the correct attribute for volume
            } 
            for ticker in tickers if 'USDT' in ticker.currency_pair
        ]
        return usdt_tickers_info
    except GateApiException as ex:
        print(f"Gate API Exception, label: {ex.label} message: {ex.message}")
        return []
    except ApiException as e:
        print(f"API Exception when calling SpotApi->list_tickers: {e}")
        return []

def order_buy_use_volume(exchange, timeframe='1h', limit=44):
    print("Order buy")
    markets = exchange.load_markets()
    usdt_symbols = [symbol for symbol in markets if symbol.endswith('/USDT')]
    # remove 3S and 3L , 5S and 5L
    usdt_symbols = [symbol for symbol in usdt_symbols if '3S' not in symbol and '3L' not in symbol and '5S' not in symbol and '5L' not in symbol]

    for symbol in usdt_symbols:        
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            print(ohlcv)
            if len(ohlcv) < limit:
                print(f"Skip {symbol} due to insufficient data")
                continue

            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            current_volume = df['volume'].iloc[-1]
            avg_volume = df['volume'].iloc[:-1].tail(144).mean()

            if current_volume > avg_volume * 5:
                print(f"Symbol: {symbol}, Current Volume: {current_volume}, Average Volume: {avg_volume}")
                symbol_remove_usdt = symbol.replace('/', '_')
                place_market_order_buy(symbol_remove_usdt)
        except Exception as e:
            print(f"Error fetching data for {symbol}: {e}")

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
                    spot_api.cancel_order(order.id, order.currency_pair)
                except ApiException as e:
                    print("Error cancelling order:", e)
    except ApiException as e:
        print("Error fetching open orders:", e)

def take_profit(isorder=False):
    print("Take profit")
    positions = spot_api.list_spot_accounts()
    total_lost = 0
    total_profit = 0
    sum_usdt = 0
    for position in positions:
        try:
            if position.currency == 'USDT' or position.currency == 'GT':
                if position.currency == 'USDT':
                    print(f"{position.currency}: {position.available}")
                    sum_usdt += float(position.available)
                else:
                    currency_pair = f"{position.currency}_USDT"
                    current_price = float(spot_api.list_tickers(currency_pair=currency_pair)[0].last)
                    print(f"{position.currency}: {position.available}, Current Price: {current_price} {float(position.available) * current_price} USDT")
                    sum_usdt += float(position.available) * current_price
            else:
                if position.currency == 'POINT':
                    continue 
                position_available = float(position.available)
                if position_available > 0.01:
                    currency_pair = f"{position.currency}_USDT"
                    #currency_pair = 'WOO3S_USDT'
                    current_price = float(spot_api.list_tickers(currency_pair=currency_pair)[0].last)
                    sum_usdt += position_available * current_price
                    if  position_available * current_price > 3:
                        trades = spot_api.list_my_trades(currency_pair=currency_pair, limit=1000)
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
                        if total_quantity != 0:
                            average_cost = total_amount / total_quantity

                        if average_cost == 0:
                            send_line_notify(f"Error: {position.currency} average cost is 0")
                        else:
                            if position_available * current_price > 3:
                                profit_loss = (current_price - average_cost) * position_available
                                profit_loss_percent = (current_price - average_cost) / average_cost * 100
                                profit_loss_percent_str = float("{:.2f}".format(profit_loss_percent))
                                profit_loss_str = float("{:.2f}".format(profit_loss))
                                color = "red" if profit_loss_percent < 0 else "green"
                                print(f"\033[1;{31 if color == 'red' else 32};40m{profit_loss_percent_str}% : {profit_loss_str}$  : {position.currency}: {position_available}, Average Cost: {average_cost}, Current Price: {current_price} {position_available * current_price} USDT")
                                total_lost += profit_loss if profit_loss < 0 else 0
                                total_profit += profit_loss if profit_loss > 0 else 0
                                if profit_loss_percent > 10:
                                    current_price = current_price * 1.005
                                    print(f"{position.currency}: {position_available}, Average Cost: {average_cost}, Current Price: {current_price}, Profit: {profit_loss}, Profit %: {profit_loss_percent}")
                                    order = gate_api.Order(amount=str(position_available), currency_pair=f"{position.currency}_USDT", side="sell", type="limit", time_in_force="gtc", price=str(current_price))
                                    spot_api.create_order(order)
                                if profit_loss_percent < -50 and isorder == True:
                                    print(f"\033[1;33;40m{position.currency}: {position_available}, Average Cost: {average_cost}, Current Price: {current_price}, Profit: {profit_loss}, Profit %: {profit_loss_percent}")
                                    place_market_order_buy(f"{position.currency}_USDT")
        except Exception as e:
            print(f"{position.currency} Exception: {e}")
    print("\033[1;34;40m")
    print(f"Total Profit: {total_profit}, Total Lost: {total_lost} profit balance {total_profit + total_lost} USDT: {sum_usdt}")
    print("\033[1;30;40m")
    send_line_notify(f"Total Profit: {total_profit:.2f}, Total Lost: {total_lost:.2f} profit balance {total_profit + total_lost:.2f} USDT: {sum_usdt:.2f}")

def order_buy_use_rsi():
    print("Order buy")
    usdt_markets_info = get_usdt_markets_with_info()
    usdt_markets_info = sorted(usdt_markets_info, key=lambda x: x['percentage_change'], reverse=True)
    order_symbols = []
    for market_info in usdt_markets_info:
        if market_info['pair'].endswith('3S_USDT') or market_info['pair'].endswith('3L_USDT'):
            order_symbols.append(market_info)
    # sort by symbol
    order_symbols = sorted(order_symbols, key=lambda x: x['pair'])
    last_symbol_rsi = ""
    last_rsi = 0
    for market_info in order_symbols:
        try:
            symbol = market_info['pair']
            if symbol.endswith('USD_USDT'):
                continue
            try:
                symbol_rsi = symbol.replace("_USDT", "")
                symbol_rsi = symbol_rsi.replace("3S", "")
                symbol_rsi = symbol_rsi.replace("5S", "")
                symbol_rsi = symbol_rsi.replace("3L", "")
                symbol_rsi = symbol_rsi.replace("5L", "")
                rsi = 0
                if last_symbol_rsi != symbol_rsi:
                    last_symbol_rsi = symbol_rsi
                    rsi = get_rsi_from_gateio(symbol_rsi)
                    last_rsi = rsi
                else:
                    rsi = last_rsi
                if rsi > 75 and "3S" in symbol:
                    if place_market_order_buy(symbol):
                        print(f"\033[1;31;40mOrder Short {symbol}, RSI: {rsi}\033[1;30;40m")
                
                if rsi < 25 and "3L" in symbol:
                    if place_market_order_buy(symbol):
                        print(f"\033[1;32;40mOrder Long {symbol}, RSI: {rsi}\033[1;30;40m")
            except Exception as e:
                print(f"order_buy 1 : Exception: {e} {symbol}")
        except Exception as e:
            print(f"order_buy 2 : Exception: {e} {symbol}")

    print("Order buy end")

def get_rsi_from_gateio(symbol):
    try:
        max_candlesticks = 144  # Retrieve data for 144 hours

        candlesticks = spot_api.list_candlesticks(currency_pair=f'{symbol}_USDT', interval='1h', limit=max_candlesticks)

        closes = [float(candle[2]) for candle in candlesticks]  # Confirm index 2 is the close price

        gains = []
        losses = []

        for i in range(1, min(15, len(closes))):
            change = closes[i] - closes[i - 1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))

        if len(closes) < 15:
            return None

        average_gain = sum(gains) / 14
        average_loss = sum(losses) / 14

        for i in range(15, len(closes)):
            change = closes[i] - closes[i - 1]
            if change > 0:
                gain = change
                loss = 0
            else:
                gain = 0
                loss = abs(change)
            average_gain = (average_gain * 13 + gain) / 14
            average_loss = (average_loss * 13 + loss) / 14

        if average_loss == 0:
            rsi = 100
        else:
            rs = average_gain / average_loss
            rsi = 100 - (100 / (1 + rs))
        return rsi

    except Exception as e:
        return None
    
def get_spot_symbol():
    exchange = ccxt.binance()  # ตัวอย่างการใช้ Binance exchange
    markets = exchange.load_markets()
    usdt_symbols = [symbol for symbol in markets if symbol.endswith('/USDT')]
    # ลบ 3S และ 3L , 5S และ 5L
    usdt_symbols = [symbol for symbol in usdt_symbols if '3S' not in symbol and '3L' not in symbol and '5S' not in symbol and '5L' not in symbol and 'UP' not in symbol and 'DOWN' not in symbol and 'USDC' not in symbol]
    
    valid_symbols = []
    count = 0
    for symbol in usdt_symbols:
        try:
            # ดึงข้อมูลราคาล่าสุด
            ticker = exchange.fetch_ticker(symbol)
            last_price = ticker['last']
            
            # ดึงข้อมูลปริมาณการซื้อขายย้อนหลัง 1 วัน
            since = exchange.parse8601(exchange.iso8601(datetime.datetime.utcnow() - datetime.timedelta(days=1)))
            ohlcv = exchange.fetch_ohlcv(symbol, '1d', since)
            
            if ohlcv and len(ohlcv) > 0:
                volume = ohlcv[-1][5]  # ปริมาณการซื้อขายของวันที่ผ่านมา
                volume_usd = volume * last_price
                
                if volume_usd >= 100000:
                    valid_symbols.append(symbol)
                    count += 1
                    print(f"{count} : Symbol: {symbol}, Last Price: {last_price}, Volume (USD): {volume_usd}")
        
        except Exception as e:
            print(f"Error fetching data for {symbol}: {e}")
    # ลบไฟล์เดิม (ถ้ามี)
    try:
        os.remove(file_name_symbol)
    except FileNotFoundError:
        pass
    # บันทึกลงไฟล์
    with open(file_name_symbol, "w") as f:
        for symbol in valid_symbols:
            f.write(f"{symbol}\n")
    print(f"Found {len(valid_symbols)} valid symbols.")

def check_ema_cross(symbol):
    try:
        # ดึงข้อมูลในกรอบเวลา 1 ชั่วโมง
        timeframe = '1h'
        limit = 500

        # ดึงข้อมูลแท่งเทียน (ohlcv)
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)

        # สร้าง DataFrame จากข้อมูลแท่งเทียน
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

        # แปลง timestamp เป็นวันที่และเวลาในเวลาโลก (UTC)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

        # คำนวณ EMA 200
        df['EMA200'] = df['close'].ewm(span=200, adjust=False).mean()

        # หาจุดตัดของราคาและ EMA 200
        cross_up = df[(df['close'].shift(1) < df['EMA200'].shift(1)) & (df['close'] > df['EMA200'])]
        cross_down = df[(df['close'].shift(1) > df['EMA200'].shift(1)) & (df['close'] < df['EMA200'])]

        # ตรวจหาจุดตัดล่าสุด
        if not cross_up.empty and cross_up['timestamp'].iloc[-1] == df['timestamp'].iloc[-1]:
            return "Up"
        elif not cross_down.empty and cross_down['timestamp'].iloc[-1] == df['timestamp'].iloc[-1]:
            return "Down"
        else:
            return None
    except Exception as e:
        return f"Error: {e}"

def order_buy_use_ema200_shot_long():
    print("Order buy")
    usdt_markets_info = get_usdt_markets_with_info()
    usdt_markets_info = sorted(usdt_markets_info, key=lambda x: x['percentage_change'], reverse=True)
    order_symbols = []
    for market_info in usdt_markets_info:
        if market_info['pair'].endswith('3S_USDT') or market_info['pair'].endswith('3L_USDT'):
            order_symbols.append(market_info)
    # sort by symbol
    order_symbols = sorted(order_symbols, key=lambda x: x['pair'])
    last_symbol_ema = ""
    last_ema = 0
    for market_info in order_symbols:
        try:
            symbol = market_info['pair']
            if symbol.endswith('USD_USDT'):
                continue
            try:
                symbol_rsi = symbol.replace("_USDT", "")
                symbol_rsi = symbol_rsi.replace("3S", "")
                symbol_rsi = symbol_rsi.replace("5S", "")
                symbol_rsi = symbol_rsi.replace("3L", "")
                symbol_rsi = symbol_rsi.replace("5L", "")
                symbol_ema = symbol_rsi + "/USDT"
                ema = 0
                if last_symbol_ema != symbol_ema:
                    last_symbol_ema = symbol_ema
                    ema = check_ema_cross(symbol_ema)
                    last_ema = ema
                else:
                    ema = last_ema
                if ema is not None:
                    if ema == "Up" and "3L" in symbol:
                        if place_market_order_buy(symbol):
                            print(f"\033[1;31;40mOrder Long {symbol}, EMA: {ema}\033[1;30;40m")
                    
                    if ema == "Down" and "3S" in symbol:
                        if place_market_order_buy(symbol):
                            print(f"\033[1;32;40mOrder Short {symbol}, EMA: {ema}\033[1;30;40m")
            except Exception as e:
                print(f"order_buy 1 : Exception: {e} {symbol}")
        except Exception as e:
            print(f"order_buy 2 : Exception: {e} {symbol}")

    print("Order buy end")

def order_buy_use_ema200():
    print("Order buy")
    # read from file
    with open(file_name_symbol, "r") as f:
        order_symbols = f.read().splitlines()
    for market_info in order_symbols:
        try:
            symbol = market_info            
            ema = check_ema_cross(symbol)
            if ema is not None:
                print(f"Symbol: {symbol}, EMA: {ema}")
                if ema == "Up":
                    if place_market_order_buy(symbol):
                        print(f"\033[1;31;40mOrder Long {symbol}, EMA: {ema}\033[1;30;40m")
        except Exception as e:
            print(f"order_buy 2 : Exception: {e} {symbol}")

    print("Order buy end")

def is_price_near_lowest(symbol):
    # ดึงข้อมูล OHLCV จาก Gate.io
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=44)
    
    # สร้าง DataFrame จากข้อมูล OHLCV
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    
    # คำนวณราคาต่ำสุดย้อนหลัง 44 time frame
    min_low_price = df['low'].min()
    
    # ราคาปัจจุบัน (ราคาปิดล่าสุด)
    current_price = df['close'].iloc[-1]
    
    # ตรวจสอบว่าราคาปัจจุบันใกล้ราคาต่ำสุดภายใน 1% หรือไม่
    if current_price <= min_low_price * 1.01:
        # หาตำแหน่งของราคาต่ำสุด
        min_low_index = df['low'].idxmin()
        
        # ตรวจสอบว่าตำแหน่งของราคาต่ำสุดห่างจากตำแหน่งปัจจุบัน 44 time frame หรือไม่
        if len(df) - min_low_index > 14:
            print(f"Symbol: {symbol}, Current Price: {current_price}, Min Low Price: {min_low_price}")
            return True
    
    return False

def get_volume_symbols(symbol, timeframe='1h', limit=24):
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    if len(ohlcv) < limit:
        return 0

    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    total_volume = df['volume'].sum()

    return total_volume


def order_buy_low():
    markets = exchange.load_markets()
    order_symbols = []
    for symbol in markets:
        if symbol.endswith('/USDT'):
            order_symbols.append(symbol)
    # ลบ 3S และ 3L , 5S และ 5L
    order_symbols = [symbol for symbol in order_symbols if '3S' not in symbol and '3L' not in symbol and '5S' not in symbol and '5L' not in symbol]
    # remove USDC
    order_symbols = [symbol for symbol in order_symbols if 'USDC' not in symbol]
    print("Order buy low")
    for symbol in order_symbols:
        try:
            volume = get_volume_symbols(symbol)
            # ค้นหาราคาล่าสุด
            current_price = exchange.fetch_ticker(symbol)['last']
            volume_usd = volume * current_price
            if volume_usd > 10000 and volume_usd < 100000:            
                if is_price_near_lowest(symbol):
                    print(f"{symbol} : {volume_usd}")                    
                    if place_market_order_buy(symbol):
                        print(f"\033[1;31;40mOrder Long {symbol}\033[1;30;40m")
        except Exception as e:
            print(f"order_buy low : Exception: {e} {symbol}")

    print("Order buy low end")

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
            print(f"{position.currency} Exception: {e}")



if __name__ == "__main__":
    print("\033[1;37;40m")
    order_remove_all()
    #close_all_position()
    #take_profit(True)
    order_buy_low()
    #order_buy_use_ema200()
    #order_buy_use_rsi()
    while True:
        try:
            if datetime.datetime.now().minute == 1:
                time.sleep(10)
                order_remove_all()
                #take_profit(True)
                order_buy_low()
                #order_buy_use_ema200()
                #order_buy_use_rsi()
                print("*******************************************")
                time.sleep(60)
        except Exception as e:
            print(f"Exception: {e}")
        time.sleep(10)
