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
        
        return upper_band[-2:], lower_band[-2:]  # Return last two values for crossover check

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

    def check_crossover_conditions(self, df, upper_bands, lower_bands):
        """
        Check for crossover conditions based on the new rules:
        BUY = Latest candle crosses lower band and price is above lower band
        SELL = Price is below the lowest price of last 144 timeframes
        """
        try:
            current_close = float(df['close'].iloc[-1])
            current_low = float(df['low'].iloc[-1])
            prev_low = float(df['low'].iloc[-2])
            
            # Get minimum price of last 144 candles
            min_price_144 = df['low'].tail(144).min()
            
            # Buy condition: Latest candle crosses below lower band but closes above it
            buy_signal = (
                prev_low >= lower_bands[0] and  # Previous low was above lower band
                current_low <= lower_bands[1] and  # Current low crossed below lower band
                current_close > lower_bands[1]  # But current close is above lower band
            )
            
            # Sell condition: Price drops below 144-period low
            sell_signal = current_close < min_price_144
            
            return buy_signal, sell_signal
            
        except Exception as e:
            print(f"Error checking crossover conditions: {str(e)}", flush=True)
            return False, False

    def scan_and_trade(self):
        print(f"\n🔍 Starting scan at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
        pairs_with_signal = 0
        
        try:
            print("\nScanning Gate.io USDT pairs for trading signals...", flush=True)
            
            # Get all trading pairs
            endpoint = f"{self.base_url}/spot/currency_pairs"
            response = requests.get(endpoint, headers=self.headers)
            if response.status_code != 200:
                print("Failed to fetch trading pairs", flush=True)
                return
                
            pairs = response.json()
            
            # Filter for USDT pairs
            coins = [
                pair['id'].split('_')[0] for pair in pairs 
                if pair['id'].endswith('_USDT') and not any(c.isdigit() for c in pair['id'].split('_')[0])
            ]
            
            random.shuffle(coins)
            
            print(f"\nFound {len(coins)} valid coins", flush=True)
            
            for idx, coin in enumerate(coins, 1):
                symbol = f"{coin}_USDT"
                print(f"\rProcessing {idx}/{len(coins)}: {symbol}", end='', flush=True)
                
                try:
                    # Get current balance
                    portfolio_value, coin_balance = self.check_coin_balance(symbol)
                    
                    # Get candlestick data (ensure we get at least 144 candles for the new sell condition)
                    candles = self.get_candlesticks(symbol, limit=200)  # Get extra for safety
                    if not candles or len(candles) < 144:  # Ensure we have enough data
                        continue
                    
                    df = pd.DataFrame(candles, columns=[
                        'timestamp', 'volume', 'close', 'high', 
                        'low', 'open', 'amount', 'count'
                    ])
                    
                    # Convert prices to numeric
                    for col in ['close', 'high', 'low']:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                    df = df.dropna()
                    
                    # Get current bands
                    closes = df['close'].values
                    upper_bands, lower_bands = self.lrc.calculate(closes)
                    
                    if upper_bands is None:
                        continue
                        
                    # Check for buy/sell signals with new conditions
                    buy_signal, sell_signal = self.check_crossover_conditions(
                        df, upper_bands, lower_bands
                    )
                    
                    current_price = float(df['close'].iloc[-1])
                    
                    # Handle sell signal
                    if sell_signal and portfolio_value > 0:
                        print(f"\n\n📉 Sell Signal Detected: {symbol}", flush=True)
                        print(f"💰 Current Value: ${portfolio_value:.2f} USDT", flush=True)
                        print(f"📊 Current Balance: {coin_balance} {coin}", flush=True)
                        print(f"📊 Current Price: {current_price:.8f} USDT", flush=True)
                        print(f"📊 144-period Low Broken", flush=True)
                        
                        if self.place_spot_sell_order(symbol, coin_balance):
                            print(f"✅ Successfully sold {coin_balance} {coin}", flush=True)
                        continue
                    
                    # Handle buy signal
                    if buy_signal:
                        if portfolio_value >= 5:
                            continue
                            
                        if not self.check_24h_volume(df):
                            continue
                            
                        pairs_with_signal += 1
                        
                        print(f"\n\n🚨 Buy Signal Found: {symbol}", flush=True)
                        print(f"📈 Current Price: {current_price:.8f} USDT", flush=True)
                        print(f"📊 Lower Band: {lower_bands[-1]:.8f}", flush=True)
                        print(f"📊 Current Low: {float(df['low'].iloc[-1]):.8f}", flush=True)
                        
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

    # [Rest of the methods remain the same as in the original code]
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
                return 0, 0
                
            tickers = self.spot_api.list_tickers(currency_pair=symbol)
            if not tickers or not tickers[0].last:
                return 0, 0
                
            current_price = float(tickers[0].last)
            balance = float(balances[0].available)
            current_value = balance * current_price
            
            return current_value, balance
            
        except Exception as e:
            print(f"Error checking {symbol} balance: {str(e)}", flush=True)
            return 0, 0

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

    def check_24h_volume(self, df):
        try:
            if len(df) < 24:
                return False
            
            last_24_candles = df.tail(24)
            volume_usdt = sum(float(row['volume']) * float(row['close']) for _, row in last_24_candles.iterrows())
            
            print(f"📊 24h Volume in USDT: ${volume_usdt:,.2f}", flush=True)
            
            return volume_usdt > 10000 and volume_usdt < 1000000
            
        except Exception as e:
            print(f"Error checking 24h volume: {str(e)}", flush=True)
            return False

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
