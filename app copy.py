import requests
import requests
import datetime
import time
import requests
import gate_api 
from gate_api.exceptions import ApiException, GateApiException
import requests
from typing import List

# Configure API key authorization: (Replace 'your_api_key' and 'your_api_secret' with your actual Gate.io API key and secret)
api_key = "c64a07643c277d2dbd07892bd9804425"
api_secret = "4ef7ba483b69ffcb9735e1e28ec41799ef85950e5b48783ccc47f2e21336f9a5"
configuration = gate_api.Configuration(
    key=api_key,
    secret=api_secret
)
api_client = gate_api.ApiClient(configuration)
spot_api = gate_api.SpotApi(api_client)
line_token = "cbBeuaCxvJcxe1wxovmMADeRsnktbFvyLizTceJpzbh"

def send_line_notify(message):
    """Send notifications through LINE Notify."""
    headers = {
        'Authorization': f'Bearer {line_token}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    payload = {'message': message}
    response = requests.post("https://notify-api.line.me/api/notify", headers=headers, params=payload)
    return response.status_code

class CryptoData:
    def __init__(self, symbol: str, volume_24h: float, market_cap: float):
        self.symbol = symbol
        self.volume_24h = volume_24h
        self.market_cap = market_cap

def fetch_crypto_data(api_key: str, symbols: str) -> List[CryptoData]:
    url = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest"
    parameters = {'symbol': symbols, 'convert': 'USD'}
    headers = {'Accepts': 'application/json', 'X-CMC_PRO_API_KEY': api_key}
    response = requests.get(url, headers=headers, params=parameters)
    response_json = response.json()

    # สร้างรายการข้อมูลสกุลเงินดิจิทัล
    crypto_list = []
    for symbol in symbols.split(','):
        # ตรวจสอบว่าข้อมูลที่ได้มีข้อมูลสำหรับสัญลักษณ์นี้หรือไม่
        if symbol in response_json['data']:
            crypto_data = response_json['data'][symbol]
            quote_data = crypto_data['quote']['USD']
            crypto = CryptoData(
                symbol=crypto_data['symbol'],
                volume_24h=quote_data['volume_24h'],
                market_cap=quote_data['market_cap']
            )
            crypto_list.append(crypto)
    return crypto_list

def get_usdt_markets_with_info():
    api_client = gate_api.ApiClient(configuration)
    spot_api = gate_api.SpotApi(api_client)
    try:
        tickers = spot_api.list_tickers()
        usdt_tickers_info = [
            {
                'pair': ticker.currency_pair,
                'last_price': ticker.last,
                'percentage_change': ticker.change_percentage,
                'volume': ticker.quote_volume    # Make sure this is the correct attribute for volume
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

def place_market_order_buy(trading_pair, amount_usd=20):
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
            # current_price ลดลง 0.25%
            current_price = current_price * 0.9975

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

def take_profit(isorder=False):
    print("Take profit")
    # get position and show profit and loss
    positions =  spot_api.list_spot_accounts()
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
                                #print(f"Average cost is 0 {position.currency}")
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
                                    print(f"\033[1;{31 if color == 'red' else 32};40m{profit_loss_percent_str}% : {profit_loss_str}$  : {position.currency}: {position_available}, Average Cost: {average_cost}, Current Price: {current_price} {position_available * current_price} USDT")
                                    total_lost += profit_loss if profit_loss < 0 else 0
                                    total_profit += profit_loss if profit_loss > 0 else 0
                                    if profit_loss_percent > 10:
                                        # เพิ่มขึ้น 0.5%
                                        current_price = current_price * 1.005
                                        print(f"{position.currency}: {position_available}, Average Cost: {average_cost}, Current Price: {current_price}, Profit: {profit_loss}, Profit %: {profit_loss_percent}")
                                        order = gate_api.Order(amount=str(position_available), currency_pair=f"{position.currency}_USDT", side="sell", type="limit", time_in_force="gtc", price=str(current_price))
                                        spot_api.create_order(order)
                                    if profit_loss_percent < -50 and isorder == True:
                                        # loss 50% ซื้อเพิ่ม
                                        # พิมพ์สีเหลือง
                                        print(f"\033[1;33;40m{position.currency}: {position_available}, Average Cost: {average_cost}, Current Price: {current_price}, Profit: {profit_loss}, Profit %: {profit_loss_percent}")
                                        place_market_order_buy(f"{position.currency}_USDT")

            except Exception as e:
                print(f"{position.currency} Exception: {e}")
    # print blue color
    print("\033[1;34;40m")
    print(f"Total Profit: {total_profit}, Total Lost: {total_lost} profit balance {total_profit + total_lost} USDT: {sum_usdt}")
    # print black color
    print("\033[1;30;40m")
    send_line_notify(f"Total Profit: {total_profit:.2f}, Total Lost: {total_lost:.2f} profit balance {total_profit + total_lost:.2f} USDT: {sum_usdt:.2f}")

def order_buy_use_rsi():
    print("Order buy")
    usdt_markets_info = get_usdt_markets_with_info()
    usdt_markets_info = sorted(usdt_markets_info, key=lambda x: x['percentage_change'], reverse=True)
    order_symbols = []
    for market_info in usdt_markets_info:
        # พิมพ์ที่มี 5S
        if market_info['pair'].endswith('3S_USDT') or market_info['pair'].endswith('3L_USDT'):
            # print(f"Pair: {market_info['pair']}, Last Price: {market_info['last_price']}, Percentage Change: {market_info['percentage_change']}, Volume: {market_info['volume']}")
            order_symbols.append(market_info)
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
                rsi = get_rsi_from_gateio(symbol_rsi)
                
                if rsi > 75 and "3S" in symbol:
                    if place_market_order_buy(symbol):
                        # พิมพ์สีแดง ปิดด้วยสีดำ
                        print(f"\033[1;31;40mOrder Short {symbol}, RSI: {rsi}\033[1;30;40m")
                
                if rsi < 25 and "3L" in symbol:
                    if place_market_order_buy(symbol):
                        # พิมพ์สีเขียว ปิดด้วยสีดำ
                        print(f"\033[1;32;40mOrder Long {symbol}, RSI: {rsi}\033[1;30;40m")
            except Exception as e:
                print(f"order_buy 1 : Exception: {e} {symbol}")
        except Exception as e:
            print(f"order_buy 2 : Exception: {e} {symbol}")

    print("Order buy end")

def order_buy_use_volume():
    markets = configuration.load_markets()
    usdt_symbols = [symbol for symbol in markets if symbol.endswith('/USDT')]

    for symbol in usdt_symbols:
        try:
            ohlcv = configuration.fetch_ohlcv(symbol, timeframe='1h', limit=145)
            if len(ohlcv) < 45:
                continue

            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            current_volume = df['volume'].iloc[-1]
            avg_volume = df['volume'].iloc[:-1].tail(144).mean()

            if current_volume > avg_volume * 10:                
                print(f"Symbol: {symbol}, Current Volume: {current_volume}, Average Volume: {avg_volume}")
                place_market_order_buy(symbol)
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
                    spot_api.cancel_order (order.id, order.currency_pair)
                except ApiException as e:
                    print("Error cancelling order:", e)
    except ApiException as e:
        print("Error fetching open orders:", e)        

def get_rsi_from_gateio(symbol):
    try:
        # Define the number of candlesticks to retrieve
        max_candlesticks = 144  # Retrieve data for 36 hours (144 candlesticks of 15 minutes each)

        # Retrieve candlestick data from API
        candlesticks = spot_api.list_candlesticks(currency_pair=f'{symbol}_USDT', interval='1h', limit=max_candlesticks)

        # Extract closing prices
        closes = [float(candle[2]) for candle in candlesticks]  # Confirm index 2 is the close price

        # Initialize lists for gains and losses
        gains = []
        losses = []

        # Calculate initial gains and losses
        for i in range(1, min(15, len(closes))):  # At least 14 periods are required to start calculating RSI
            change = closes[i] - closes[i - 1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))

        # Check if enough data is available to calculate RSI
        if len(closes) < 15:
            return None  # Not enough data

        # Initialize average gain and loss
        average_gain = sum(gains) / 14
        average_loss = sum(losses) / 14

        # Update average gain and loss for all data using exponential moving average
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

        # Calculate RSI
        if average_loss == 0:
            rsi = 100  # Avoid division by zero
        else:
            rs = average_gain / average_loss
            rsi = 100 - (100 / (1 + rs))
        return rsi

    except Exception as e:
        return None  # Returning None in case of error

if __name__ == "__main__":
    # print color white
    print("\033[1;37;40m")
    order_remove_all()
    take_profit(True)
    order_buy_use_volume()
    #order_buy_use_rsi()
    while True:
        try:
            if datetime.datetime.now().minute == 1:
                time.sleep(10)
                order_remove_all()
                take_profit(True)
                order_buy_use_rsi()
                print("*******************************************")
                time.sleep(60)
        except Exception as e:
            print(f"Exception: {e}")
        time.sleep(10)
        
