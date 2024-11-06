import random
import requests
import pandas as pd
import numpy as np
import time
from datetime import datetime
from gate_api import ApiClient, Configuration, Order, SpotApi
from gate_api.exceptions import ApiException, GateApiException

# API Credentials
API_KEY = "c84d3616806f44e5651912c198094a1b"
API_SECRET = "32ebfc90ac917be0911561c09da2b6dea9adafc9a4c0587c375645073be2e506"

class InsufficientBalanceError(Exception):
    pass

class LinearRegressionChannel:
    def __init__(self, length=100, deviation=2.0):
        self.length = length
        self.deviation = deviation

    def calculate(self, data):
        """Calculate Linear Regression Channel"""
        if len(data) < self.length:
            return None, None, None

        # Get the last n periods
        closes = data[-self.length:]
        x = np.arange(len(closes))
        
        # Calculate linear regression
        slope, intercept = np.polyfit(x, closes, 1)
        
        # Calculate regression line
        reg_line = slope * x + intercept
        
        # Calculate standard deviation
        deviation = np.std(closes - reg_line)
        
        # Calculate upper and lower bands
        upper_band = reg_line + (deviation * self.deviation)
        lower_band = reg_line - (deviation * self.deviation)
        
        # Get current slope direction
        slope_direction = 1 if slope > 0 else -1 if slope < 0 else 0
        
        return slope_direction, upper_band[-1], lower_band[-1]

class GateioTrader:
    def __init__(self):
        self.base_url = "https://api.gateio.ws/api/v4"
        self.headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        self.request_count = 0
        self.last_request_time = time.time()
        self.rate_limit = 300
        
        # Initialize gate-api client
        config = Configuration(key=API_KEY, secret=API_SECRET)
        client = ApiClient(config)
        self.spot_api = SpotApi(client)
        
        # Initialize Linear Regression Channel
        self.lrc = LinearRegressionChannel(length=100, deviation=2.0)
        
    def _rate_limit_check(self):
        current_time = time.time()
        time_passed = current_time - self.last_request_time
        
        if time_passed < 60:
            if self.request_count >= self.rate_limit:
                sleep_time = 60 - time_passed
                print(f"Rate limit reached, sleeping for {sleep_time:.2f} seconds", flush=True)
                time.sleep(sleep_time)
                self.request_count = 0
                self.last_request_time = time.time()
        else:
            self.request_count = 0
            self.last_request_time = current_time
            
        self.request_count += 1

    def check_coin_balance(self, symbol):
        try:
            coin = symbol.split('_')[0]
            balances = self.spot_api.list_spot_accounts(currency=coin)
            
            if not balances or len(balances) == 0:
                return 0
                
            tickers = self.spot_api.list_tickers(currency_pair=symbol)
            if not tickers or not tickers[0].last:
                return 0
                
            current_price = float(tickers[0].last)
            balance = float(balances[0].available)
            current_value = balance * current_price
            
            return current_value
            
        except Exception as e:
            print(f"Error checking {symbol} balance: {str(e)}", flush=True)
            return 0

    def get_candlesticks(self, symbol, interval='1h', limit=144):
        endpoint = f"{self.base_url}/spot/candlesticks"
        params = {
            'currency_pair': symbol,
            'interval': interval,
            'limit': limit
        }
        response = requests.get(endpoint, headers=self.headers, params=params)
        if response.status_code == 200:
            return response.json()
        return None

    def place_spot_order(self, symbol):
        try:
            order = Order(
                currency_pair=symbol,
                side='buy',
                amount='20',
                type='market',
                time_in_force='ioc'
            )
            
            result = self.spot_api.create_order(order)
            print(f"\n✅ Market Buy Order Placed for {symbol}", flush=True)
            print(f"Order ID: {result.id}", flush=True)
            print(f"Status: {result.status}", flush=True)
            print(f"Amount: $20.00 USDT", flush=True)
            return True
            
        except GateApiException as ex:
            print(f"\n❌ Gate.io API Error for {symbol}:", flush=True)
            print(f"Label: {ex.label}", flush=True)
            print(f"Message: {ex.message}", flush=True)
            if "Insufficient balance" in ex.message or "Not enough balance" in ex.message:
                raise InsufficientBalanceError("Not enough balance")
            return False
        except Exception as e:
            print(f"\n❌ Error placing order for {symbol}: {str(e)}", flush=True)
            if "Not enough balance" in str(e):
                raise InsufficientBalanceError("Not enough balance")
            return False

    def place_spot_sell_order(self, symbol, amount):
        try:
            order = Order(
                currency_pair=symbol,
                side='sell',
                amount=str(amount),
                type='market',
                time_in_force='ioc'
            )
            
            result = self.spot_api.create_order(order)
            print(f"\n✅ Market Sell Order Placed for {symbol}", flush=True)
            print(f"Order ID: {result.id}", flush=True)
            print(f"Status: {result.status}", flush=True)
            print(f"Amount: {amount} {symbol.split('_')[0]}", flush=True)
            return True
            
        except GateApiException as ex:
            print(f"\n❌ Gate.io API Error for {symbol}:", flush=True)
            print(f"Label: {ex.label}", flush=True)
            print(f"Message: {ex.message}", flush=True)
            return False
        except Exception as e:
            print(f"\n❌ Error placing sell order for {symbol}: {str(e)}", flush=True)
            return False

    def check_and_sell_portfolio(self, threshold=200):
        print(f"\n📊 Checking portfolio for coins over ${threshold} USDT...", flush=True)
        
        try:
            balances = self.spot_api.list_spot_accounts()
            
            for balance in balances:
                if float(balance.available) > 0:
                    symbol = f"{balance.currency}_USDT"
                    
                    try:
                        current_value = self.check_coin_balance(symbol)
                        
                        if current_value > threshold:
                            print(f"\n💰 Found {symbol} worth ${current_value:.2f} USDT", flush=True)
                            self.place_spot_sell_order(symbol, float(balance.available))
                            print(f"🔄 Attempted to sell {balance.available} {balance.currency}", flush=True)
                            
                    except Exception as e:
                        print(f"Error processing {symbol}: {str(e)}", flush=True)
                        continue
            
            print("\n✅ Portfolio check completed", flush=True)
            
        except Exception as e:
            print(f"\n❌ Error checking portfolio: {str(e)}", flush=True)

    def scan_and_trade(self):
        print(f"\n🔍 Starting scan at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
        pairs_with_signal = 0
        
        try:
            # First, check portfolio and sell coins over $200
            #self.check_and_sell_portfolio(threshold=200)
            
            print("\nScanning Gate.io USDT pairs for trend changes...", flush=True)
            
            # Get all trading pairs
            endpoint = f"{self.base_url}/spot/currency_pairs"
            response = requests.get(endpoint, headers=self.headers)
            if response.status_code != 200:
                print("Failed to fetch trading pairs", flush=True)
                return
                
            pairs = response.json()
            
            coins = []
            for pair in pairs:
                if pair['id'].endswith('_USDT'):
                    base_coin = pair['id'].split('_')[0]
                    if not any(c.isdigit() for c in base_coin):
                        coins.append(base_coin)
            
            random.shuffle(coins)
            
            print(f"\nFound {len(coins)} valid coins", flush=True)
            print("Coins have been randomly shuffled for processing", flush=True)
            
            for idx, coin in enumerate(coins, 1):
                symbol = f"{coin}_USDT"
                print(f"\rProcessing {idx}/{len(coins)}: {symbol}", end='', flush=True)
                
                try:
                    portfolio_value = self.check_coin_balance(symbol)
                    
                    if portfolio_value > 5:
                        continue
                        
                    candles = self.get_candlesticks(symbol)
                    if not candles:
                        continue
                    
                    df = pd.DataFrame(candles, columns=[
                        'timestamp', 'volume', 'close', 'high', 
                        'low', 'open', 'amount', 'count'
                    ])
                    
                    # Convert close prices to numeric and get recent data
                    df['close'] = pd.to_numeric(df['close'], errors='coerce')
                    df = df.dropna(subset=['close'])
                    
                    if len(df) < 100:  # Need at least length periods
                        continue
                    
                    # Get current and previous trend directions
                    closes = df['close'].values
                    current_direction, upper, lower = self.lrc.calculate(closes)
                    prev_direction, _, _ = self.lrc.calculate(closes[:-1])
                    
                    # Check for trend change from down to up
                    if prev_direction == -1 and current_direction == 1 or current_direction == 1:
                        pairs_with_signal += 1
                        
                        current_price = float(df['close'].iloc[-1])
                        
                        print(f"\n\n🚨 Trend Change Signal Found: {symbol}", flush=True)
                        print(f"📈 Previous Trend: Downward", flush=True)
                        print(f"📈 Current Trend: Upward", flush=True)
                        print(f"💰 Current Price: {current_price:.8f} USDT", flush=True)
                        print(f"📊 Upper Band: {upper:.8f}", flush=True)
                        print(f"📊 Lower Band: {lower:.8f}", flush=True)
                        print(f"💼 Portfolio Value: ${portfolio_value:.2f} USDT", flush=True)
                        
                        self.place_spot_order(symbol)
                        print("-" * 80, flush=True)
                
                except InsufficientBalanceError:
                    print("\n⏰ Waiting for next hour due to insufficient balance...", flush=True)
                    return
                except Exception as e:
                    continue
                
                time.sleep(0.1)
            
            print(f"\n\n✨ Scan completed. Found {pairs_with_signal} pairs with signals.", flush=True)
            
        except Exception as e:
            print(f"\nAn error occurred during scan: {str(e)}", flush=True)

def main():
    print("🤖 Gate.io Linear Regression Channel Bot Starting...", flush=True)
    trader = GateioTrader()
    trader.scan_and_trade() 
    
    while True:
        if datetime.now().minute == 0:
            trader.scan_and_trade()
            time.sleep(55)
        time.sleep(10)

if __name__ == "__main__":
    main()