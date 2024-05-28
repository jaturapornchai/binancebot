from datetime import datetime, timedelta
from termcolor import colored
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

def get_volume_symbols(symbol, timeframe='1h', limit=24):
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    if len(ohlcv) < limit:
        return 0

    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    total_volume = df['volume'].sum()

    return total_volume

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

# Fetch OHLCV data from Gate.io
def fetch_recent_ohlcv(symbol, timeframe='1h', limit=900):
    try:
        data = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        return data
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return []

# Calculate RSI
def calculate_rsi(df, window=14):
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=window, min_periods=1).mean()
    avg_loss = loss.rolling(window=window, min_periods=1).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

# Detect RSI Divergences
def detect_divergence(df, rsi_col='rsi', price_col='close', lbL=5, lbR=5, rangeUpper=60, rangeLower=5):
    bull_divergences = []
    bear_divergences = []

    for i in range(lbR, len(df) - lbR):
        rsi_window = df[rsi_col].iloc[i - lbR:i + lbR + 1]
        price_window = df[price_col].iloc[i - lbR:i + lbR + 1]

        # Bullish Divergence: ราคาลดลง แต่ RSI เพิ่มขึ้น
        if rsi_window.iloc[-1] > rsi_window.iloc[0] and price_window.iloc[-1] < price_window.iloc[0]:
            bull_divergences.append((df.index[i], df[price_col].iloc[i]))

        # Bearish Divergence: ราคาเพิ่มขึ้น แต่ RSI ลดลง
        if rsi_window.iloc[-1] < rsi_window.iloc[0] and price_window.iloc[-1] > price_window.iloc[0]:
            bear_divergences.append((df.index[i], df[price_col].iloc[i]))

    return bull_divergences, bear_divergences

def order_buy():
    timeframe = "1h"
    lookback_hours = 6
    markets = exchange.load_markets()
    order_symbols = []
    for symbol in markets:
        if symbol.endswith('/USDT'):
            order_symbols.append(symbol)
    # ลบ 3S และ 3L , 5S และ 5L
    order_symbols = [symbol for symbol in order_symbols if '3S' not in symbol and '3L' not in symbol and '5S' not in symbol and '5L' not in symbol]
    # remove USDC
    order_symbols = [symbol for symbol in order_symbols if 'USDC' not in symbol]
    # remove if have digit
    order_symbols = [symbol for symbol in order_symbols if not any(char.isdigit() for char in symbol)]
    # random
    order_symbols = np.random.permutation(order_symbols)
    for symbol in order_symbols:
        data = fetch_recent_ohlcv(symbol, timeframe)
        if not data:
            continue

        df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        df['rsi'] = calculate_rsi(df)

        bull_divs, bear_divs = detect_divergence(df, lbL=5, lbR=5)

        # Check for Divergences in the specified lookback hours
        current_time = df.index[-1]
        lookback_period = timedelta(hours=lookback_hours)
        recent_bull_divs = [d for d in bull_divs if d[0] >= current_time - lookback_period]
        recent_bear_divs = [d for d in bear_divs if d[0] >= current_time - lookback_period]

        # Print the latest Divergence if any
        if recent_bull_divs:
            latest_bull_div = recent_bull_divs[-1]
            print(colored(f"RSI Divergences for {symbol}: Latest Bullish Divergence detected at {latest_bull_div[0]}.", 'green'))
            volume = get_volume_symbols(symbol)
            # ค้นหาราคาล่าสุด
            current_price = exchange.fetch_ticker(symbol)['last']
            volume_usd = volume * current_price
            if volume_usd > 10000 and volume_usd < 100000:            
                print(f"Order {symbol} Volume: {volume}, Volume USD: {volume_usd}")
                place_market_order_buy(symbol)

        if recent_bear_divs:
            latest_bear_div = recent_bear_divs[-1]
            print(colored(f"RSI Divergences for {symbol}: Latest Bearish Divergence detected at {latest_bear_div[0]}.", 'red'))
     
if __name__ == "__main__":
    print("\033[1;37;40m")
    order_remove_all()
    #close_all_position()
    #take_profit(True)
    order_buy()
    #order_buy_use_ema200()
    #order_buy_use_rsi()
    while True:
        try:
            if datetime.datetime.now().minute == 1:
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
