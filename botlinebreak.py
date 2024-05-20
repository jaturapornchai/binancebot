import time
import requests
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from datetime import datetime
import numpy as np
import requests
from scipy.stats import linregress
from binance.client import Client
import time
from scipy.stats import linregress
from bs4 import BeautifulSoup
import traceback
import concurrent.futures
import datetime
import random
import time
import ccxt
from binance.client import Client
from binance.enums import *
import requests
import pandas as pd
import requests
import talib
import ta
import numpy as np
import pandas_datareader as pdr
import datetime

api_key = 'FpwthNz84887fuWpz9lEIsLm1zwZB9YV8ZO2FjVQ6v2k6lmR8nv1oKZZOoJSY0il'
api_secret = 'nszlVyvoFAZPVIXdWnJyhaxgiujMTTUmFN4Ncix3rKBtLhF2kO8hhCZhnwIeu3gt'
client = Client(api_key, api_secret)
# LINE Notify token
line_token = "cbBeuaCxvJcxe1wxovmMADeRsnktbFvyLizTceJpzbh"
dollar_amount = 75  # Order amount in USD
leverage = 10
timeframe = '15m'
exchange = ccxt.binance()
future_symbols = []
spot_symbols = []
exchange_rate_thai = 0.0
ignore_symbols = ['DONUSDT','USDCUSDT','SRMUSDT']

def get_exchange_rate_thai():
    url = 'https://www.x-rates.com/calculator/?from=USD&to=THB&amount=1'
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')

    rate = soup.find('span', class_='ccOutputTrail').previous_sibling
    # return double
    return float(rate)

def send_line_notify(message):
    """headers = {
        'Authorization': f'Bearer {line_token}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    payload = {'message': message}
    requests.post("https://notify-api.line.me/api/notify", headers=headers, params=payload)"""

def fetch_future_symbols():
    info = client.futures_exchange_info()
    symbols = [item['symbol'] for item in info['symbols'] if 'USDT' in item['symbol'] and item['status'] == 'TRADING']
    symbols = [symbol for symbol in symbols if not any(char.isdigit() for char in symbol)]
    symbols = [symbol for symbol in symbols if symbol not in ignore_symbols]
    symbols.sort()
    return symbols

def fetch_data(symbol, timeframe, limit):
    bars = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df

def linear_regression_channel(data, length):
    def linear_regression_slope(series):
        x = np.arange(len(series))
        slope, _ = np.polyfit(x, series, 1)
        return slope

    data['regression_slope'] = data['close'].rolling(window=length).apply(linear_regression_slope)
    data['mean'] = data['close'].rolling(window=length).mean()
    data['stddev'] = data['close'].rolling(window=length).std()
    data['upper'] = data['mean'] + 2 * data['stddev']
    data['lower'] = data['mean'] - 2 * data['stddev']
    return data

def trading_signal(data):
    last_row = data.iloc[-1]
    if last_row['high'] > last_row['upper'] and last_row['low'] < last_row['upper']:
        return 'long'
    elif last_row['low'] < last_row['lower'] and last_row['high'] > last_row['lower']:
        return 'short'
    else:
        return 'normal'

def get_market_state(symbol):
    length = 100         
    data = fetch_data(symbol, timeframe, length)
    data = linear_regression_channel(data, length)
    signal = trading_signal(data)
    return signal
       
def adjust_to_precision(value, precision):
    format_str = "{:0.0" + str(precision) + "f}"
    return float(format_str.format(value))

def get_precision_from_step_size(step_size):
    # Count the number of decimals in the step size
    str_step_size = str(step_size).rstrip('0')
    decimal_index = str_step_size.find('.')
    return len(str_step_size) - decimal_index - 1 if decimal_index != -1 else 0

def get_symbol_info(client, symbol):
    info = client.futures_exchange_info()
    for s in info['symbols']:
        if s['symbol'] == symbol:
            filters = {f['filterType']: f for f in s['filters']}
            return {
                'quantityPrecision': get_precision_from_step_size(filters['LOT_SIZE']['stepSize']),
                'pricePrecision': get_precision_from_step_size(filters['PRICE_FILTER']['tickSize'])
            }
    raise ValueError(f"Symbol info for {symbol} not found")

def adjust_to_lot_size(quantity, lot_size_info):
    step_size = float(lot_size_info['stepSize'])
    return round(quantity - (quantity % step_size), len(str(step_size).split('.')[1].rstrip('0')))

def place_order_future(client, symbol, direction, dollar_amount):  
    print(f"Future Placing order for {symbol}...")
    # ถ้ามี position เดิม และ สถานะไม่เหมือนกัน ให้ปิด position เดิมก่อน
    positions = client.futures_position_information()
    for position in positions:
        position_amount = float(position['positionAmt'])
        if position_amount != 0 and position['symbol'] == symbol:
            current_signal =  (position_amount < 0 and 'short') or (position_amount > 0 and 'long')
            if current_signal == direction:
                return 
            else:
                message = f"{symbol}: Signal changed from {current_signal} to {direction}. Closing position."
                client.futures_create_order(
                    symbol=symbol,
                    side="SELL" if position_amount > 0 else "BUY",
                    type="MARKET",
                    quantity=abs(position_amount)
                )
                # ลบ order ที่เหลือออก
                orders = client.futures_get_open_orders(symbol=symbol)
                for order in orders:
                    print(f"ลบ {symbol} order ค้าง {order['orderId']} สำเร็จ : 1")
                    client.futures_cancel_order(
                        symbol=order['symbol'],
                        orderId=order['orderId']
                    )
          
    symbol_info = get_symbol_info(client, symbol)
    quantity_precision = symbol_info['quantityPrecision']
    price_precision = symbol_info['pricePrecision']

    # Fetch current market price
    current_price = float(client.get_symbol_ticker(symbol=symbol)['price'])
    quantity = dollar_amount / current_price
    quantity = adjust_to_precision(quantity, quantity_precision)

    try:
        client.futures_change_margin_type(symbol=symbol, marginType='CROSSED')
    except Exception as e:
        pass

    if (direction == 'long'):
        # Place order
        order = client.futures_create_order(
            symbol=symbol,
            side="BUY",
            type="MARKET",
            quantity=quantity
        )
        
        # ดึง order ที่เพิ่งสร้าง มาใช้งานต่อ
        order = client.futures_get_order(
            symbol=symbol,
            orderId=order['orderId']
        )
        # get enter price
        enter_price = float(order['avgPrice'])
        order_id = order['orderId']

        # ค้นหาราคาต่ำสุดย้อนหลัง 28 bars
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=28)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        low_price = df['low'].min()
        # กำหนด stop loss ต่ำกว่า low ที่เจอได้ 1%
        stop_loss_price = low_price - ((low_price * (1 / 100)) / leverage)
        stop_loss_price = adjust_to_precision(stop_loss_price, price_precision)
        # take profit เป็น 1.5 เท่าของ enter_price , stop loss
        take_profit_price = enter_price + ((enter_price - stop_loss_price) * 1.25)
        take_profit_price = adjust_to_precision(take_profit_price, price_precision)

        # สร้าง stop loss order
        client.futures_create_order(
            symbol=symbol,
            side="SELL",
            type="STOP_MARKET",
            quantity=quantity,
            stopPrice=stop_loss_price,
            closePosition=True,
            timeInForce='GTE_GTC',
            order_id=order_id
        )
        # สร้าง tailing stop
        client.futures_create_order(
            symbol=symbol,
            side='SELL',
            type='TRAILING_STOP_MARKET',
            quantity=quantity,
            activationPrice=take_profit_price,
            callbackRate=1.5,
        )

        """# สร้าง take profit order
        client.futures_create_order(
            symbol=symbol,
            side="SELL",
            type="TAKE_PROFIT_MARKET",
            quantity=quantity,
            stopPrice=take_profit_price,
            closePosition=True,
            timeInForce='GTE_GTC',
            order_id=order_id
        )"""
    elif (direction == 'short'):
        # Place order
        order = client.futures_create_order(
            symbol=symbol,
            side="SELL",
            type="MARKET",
            quantity=quantity
        )
        
        # ดึง order ที่เพิ่งสร้าง มาใช้งานต่อ
        order = client.futures_get_order(
            symbol=symbol,
            orderId=order['orderId']
        )
        # get enter price
        enter_price = float(order['avgPrice'])
        order_id = order['orderId']
        # ค้นหาราคาสูงสุดย้อนหลัง 28 bars
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=28)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        high_price = df['high'].max()
        # กำหนด stop loss สูงกว่า high ที่เจอได้ 1%
        stop_loss_price = high_price + ((high_price * (1 / 100)) / leverage)
        stop_loss_price = adjust_to_precision(stop_loss_price, price_precision)
        # take profit เป็น 1.5 เท่าของช่องว่างระหว่าง enter_price , stop loss
        take_profit_price = enter_price - ((stop_loss_price - enter_price) * 1.25)
        take_profit_price = adjust_to_precision(take_profit_price, price_precision)
        
        # สร้าง stop loss order
        client.futures_create_order(
            symbol=symbol,
            side="BUY",
            type="STOP_MARKET",
            quantity=quantity,
            stopPrice=stop_loss_price,
            closePosition=True,
            timeInForce='GTE_GTC',
            order_id=order_id
        )
        # สร้าง tailing stop
        client.futures_create_order(
            symbol=symbol,
            side='BUY',
            type='TRAILING_STOP_MARKET',
            quantity=quantity,
            activationPrice=take_profit_price,
            callbackRate=1.5,
        )
        """
        # สร้าง take profit order
        client.futures_create_order(
            symbol=symbol,
            side="BUY",
            type="TAKE_PROFIT_MARKET",
            quantity=quantity,
            stopPrice=take_profit_price,
            closePosition=True,
            timeInForce='GTE_GTC',
            order_id=order_id
        )"""

    return order

def process_symbol(symbol, dollar_amount):
    try:
        signal = get_market_state(symbol)
        print(f"{symbol}: {signal}")
        if signal == 'long':
            direction = 'long'
            message = f"{symbol}: Bullish signal detected! Opening long position."
            print(message)
            place_order_future(client, symbol, direction, dollar_amount)
        elif signal == 'short':                
            direction = 'short'
            message = f"{symbol}: Bearish signal detected! Opening short position."
            print(message)
            place_order_future(client, symbol, direction, dollar_amount)
    except Exception as e:
        traceback.print_exc()
        #print(f"1:Error encountered while processing {symbol}: {e}")
        if "insufficient" in str(e):
            return 'stop'
        if "Invalid symbol" in str(e) or "pass an index" in str(e):
            return 'remove', symbol
    return 'continue'

def findShortLong():
    print("Start findShortLong")
    balance = client.futures_account_balance()
    balance = [item for item in balance if item['asset'] == 'USDT']
    balance = float(balance[0]['balance'])
    dollar_amount = round((balance / 50) * leverage)
    print(f"balance: {dollar_amount}")    
    
    random.shuffle(future_symbols)
    
    for symbol in future_symbols:
        result = process_symbol(symbol, dollar_amount)
        if result == 'stop':
            break
        elif result[0] == 'remove':
            try:
                future_symbols.remove(result[1])
            except:
                pass
            print(f"Removed {result[1]} from symbols list.")

    print("End findShortLong")

def recheckPositionReverseSignal():
    positions = client.futures_position_information()
    for position in positions:
        position_amount = float(position['positionAmt'])
        if position_amount != 0:
            current_signal =  (position_amount < 0 and 'short') or (position_amount > 0 and 'long')
            symbol = position['symbol']
            signal = get_market_state(symbol)
            if signal != 'normal':
                if signal != current_signal:
                    message = f"{symbol}: Signal changed from {current_signal} to {signal}. Closing position."
                    client.futures_create_order(
                        symbol=symbol,
                        side="SELL" if position_amount > 0 else "BUY",
                        type="MARKET",
                        quantity=abs(position_amount)
                    )

def removeOrderLostPosition():
    # ค้นหา position ที่ไม่มี stop loss หรือ trailing stop
    positions = client.futures_position_information()
    for position in positions:
        position_amount = float(position['positionAmt'])
        if position_amount != 0:
            symbol = position['symbol']
            orders = client.futures_get_open_orders(symbol=symbol)
            have_stop_loss = False
            have_trailing_stop = False
            for order in orders:
                if order['type'] == 'STOP_MARKET':
                    have_stop_loss = True
                if order['type'] == 'TRAILING_STOP_MARKET':
                    have_trailing_stop = True
            if not have_stop_loss:
                print(f"ไม่มี stop loss สำหรับ {symbol} จะทำการปิด position")
                client.futures_create_order(
                    symbol=symbol,
                    side="SELL" if position_amount > 0 else "BUY",
                    type="MARKET",
                    quantity=abs(position_amount)
                )
            if not have_trailing_stop:
                print(f"ไม่มี trailing stop สำหรับ {symbol} จะทำการปิด position")
                client.futures_create_order(
                    symbol=symbol,
                    side="SELL" if position_amount > 0 else "BUY",
                    type="MARKET",
                    quantity=abs(position_amount)
                )

    positions = client.futures_position_information()
    orders = client.futures_get_open_orders()
    for order in orders:
        have_position = False
        for position in positions:
            if float(position['positionAmt']) != 0 and position['symbol'] == order['symbol']:
                have_position = True
                break
        if not have_position:
            xsymbol = order['symbol']
            print(f"ลบ order {xsymbol} ค้าง {order['orderId']} สำเร็จ : 2")
            client.futures_cancel_order(
                symbol=order['symbol'],
                orderId=order['orderId']
            )
    
    # ค้นหา position ที่ไม่มี order != 2 อัน ลบ position นั้นออก
    positions = client.futures_position_information()
    for position in positions:
        position_amount = float(position['positionAmt'])
        if position_amount != 0:
            symbol = position['symbol']
            orders = client.futures_get_open_orders(symbol=symbol)
            if len(orders) != 2:
                print(f"ลบ position ที่ไม่มี order ไม่เท่ากับ 2 อัน {symbol} สำเร็จ : 3")
                client.futures_create_order(
                    symbol=symbol,
                    side="SELL" if position_amount > 0 else "BUY",
                    type="MARKET",
                    quantity=abs(position_amount)
                )
                # ลบ order ที่เหลือออก
                orders = client.futures_get_open_orders(symbol=symbol)
                for order in orders:
                    print(f"ลบ {symbol} order ค้าง {order['orderId']} สำเร็จ : 4")
                    client.futures_cancel_order(
                        symbol=order['symbol'],
                        orderId=order['orderId']
                    )
                 
if __name__ == "__main__":
    future_symbols = [symbol for symbol in fetch_future_symbols() if '_' not in symbol and not any(char.isdigit() for char in symbol)]
    for symbol in future_symbols:
        # เปลี่ยน leverage
        try:
            client.futures_change_leverage(symbol=symbol, leverage=leverage)
        except Exception as e:
            print(f"Error encountered: {e}")
            pass

    first_run = True
    #tread_spot()
    exchange_rate_thai = get_exchange_rate_thai()
    while True:
        try:
            tm_min = time.localtime(time.time()).tm_min
            if tm_min % 15 == 0 or first_run == True:
                time.sleep(30)
                exchange = ccxt.binance()
                recheckPositionReverseSignal()
                first_run = False                
                removeOrderLostPosition()
                findShortLong()
                try:
                    futures_account_info = client.futures_account()
                    margin_balance = futures_account_info['totalMarginBalance']
                    withdrawable_amount = futures_account_info['maxWithdrawAmount']
                    # convert to double
                    margin_balance = float(margin_balance)
                    withdrawable_amount = float(withdrawable_amount)
                    if (margin_balance > 5000 and withdrawable_amount > 200):
                        transfer_result = client.futures_account_transfer(asset='USDT', amount=100, type=2)
                except Exception as e:
                    print(f"Error encountered: {e}")
                #
                #tread_spot()
                #
                time.sleep(60)
            if tm_min % 3 == 0 and time.localtime(time.time()).tm_sec == 0:
                removeOrderLostPosition()
                # ดึง asset ในตลาด future ทั้งหมด
                futures_account = client.futures_account()       
                futures_balance = float(futures_account['totalWalletBalance'])
                for asset in futures_account['assets']:
                    if float(asset['marginBalance']) > 0:
                        asset_symbol = asset['asset']
                        try:
                            # get price
                            ticker = client.get_symbol_ticker(symbol=asset_symbol + "USDT")
                            asset_price = float(ticker['price'])
                            # convert to usdt
                            asset_usdt = float(asset['marginBalance']) * asset_price
                            futures_balance += asset_usdt
                        except Exception as e:
                            pass
                futures_balance_str = f"{futures_balance:,.2f}"
                # แสดง กำไรขาดทุน format ###,###.## จำนวน position ที่เปิดอยู่
                positions = client.futures_position_information()
                profit = 0
                count_position_loss = 0
                count_position_profit = 0
                for position in positions:
                    if float(position['positionAmt']) != 0:
                        profit_or_loss = float(position['unRealizedProfit'])
                        if profit_or_loss < 0:
                            count_position_loss += 1
                        else:
                            count_position_profit += 1
                        profit += profit_or_loss
                profit_str = f"{profit:,.2f}"
                count_position = 0
                for position in positions:
                    if float(position['positionAmt']) != 0:
                        count_position += 1
                # กำไรสีเขียน ขาดทุนสีแดง
                if float(profit) > 0:
                    profit_str = f"\033[92m{profit_str}\033[0m"
                else:
                    profit_str = f"\033[91m{profit_str}\033[0m"         
                # ดึงมูลค่ารวม spot ทั้งหมด แปลงเป็น usdt
                spot_balance = 0
                try:
                    account_info = client.get_account()
                except Exception as e:
                    print(f"Failed to get account information: {e}")
                for asset in account_info['balances']:
                    spot_symbol = asset['asset'] + "USDT"
                    # ยกเว้นใน list ignore_symbols
                    if spot_symbol in ignore_symbols:
                        continue
                    if float(asset['free']) + float(asset['locked']) > 0:
                        spot_symbol_free = float(asset['free'])
                        spot_symbol_locked = float(asset['locked'])
                        try:
                            if spot_symbol == 'USDTUSDT':
                                spot_balance += spot_symbol_free
                            else:
                                ticker = client.get_symbol_ticker(symbol=spot_symbol)
                                spot_balance += (float(asset['free']) + float(asset['locked'])) * float(ticker['price'])
                        except Exception as e:
                            print(f"Error fetching price for {spot_symbol}: {e}")
                            try:
                                ignore_symbols.remove(spot_symbol)
                            except:
                                pass
                # แสดงผล
                total_asset = profit + futures_balance + spot_balance
                total_asset_str = f"{total_asset:,.2f}"
                # convert เป็นเงินบาท
                total_asset_thb = total_asset * exchange_rate_thai
                total_asset_thb_str = f"{total_asset_thb:,.2f}"
                print(f"กำไรขาดทุน: {profit_str} จำนวน position: {count_position} ขาดทุน: {count_position_loss} กำไร: {count_position_profit} มูลค่าคงเหลือ: {futures_balance_str} spot: {spot_balance:,.2f} รวม: \033[92m${total_asset_str}\033[0m  รวม : \033[92m{total_asset_thb_str}\033[0m บาท")                

                # แจ้งเตือนผ่าน line
                message = f"กำไรขาดทุน: {profit:,.2f} position: {count_position} ขาดทุน: {count_position_loss} กำไร: {count_position_profit} คงเหลือ: {futures_balance_str} spot: {spot_balance:,.2f} รวม: ${total_asset_str} รวม: {total_asset_thb_str} บาท"
                send_line_notify(message)
            time.sleep(1)
        except Exception as e:
            print(f"Error encountered: {e}")
            time.sleep(60)
            pass
        
