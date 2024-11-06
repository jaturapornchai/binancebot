import random
import requests
import pandas as pd
import numpy as np
import time
from datetime import datetime
from gate_api import ApiClient, Configuration, Order, SpotApi
from gate_api.exceptions import ApiException, GateApiException

# API Credentials remain the same
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
        
        return slope_direction, upper_band[-2:], lower_band[-2:]  # Return last two values for crossover check

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
        # Rate limit checking remains the same
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
        # Balance checking remains the same
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
        # Candlesticks fetching remains the same
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

    def check_crossover_conditions(self, df, current_direction, upper_bands, lower_bands):
        """
        Check for crossover conditions based on the new rules
        """
        try:
            current_close = float(df['close'].iloc[-1])
            prev_high = float(df['high'].iloc[-2])
            prev_low = float(df['low'].iloc[-2])
            
            # Buy condition: Downtrend + Latest candle crosses above upper band + Close above upper band
            buy_signal = (
                current_direction == -1 and  # Downtrend
                prev_high <= upper_bands[0] and  # Previous candle touched or crossed upper band
                current_close > upper_bands[1]  # Current close above upper band
            )
            
            # Sell condition: Uptrend + Latest candle crosses below lower band + Close below lower band
            sell_signal = (
                current_direction == 1 and  # Uptrend
                prev_low >= lower_bands[0] and  # Previous candle touched or crossed lower band
                current_close < lower_bands[1]  # Current close below lower band
            )
            
            return buy_signal, sell_signal
            
        except Exception as e:
            print(f"Error checking crossover conditions: {str(e)}", flush=True)
            return False, False

    def scan_and_trade(self):
        print(f"\n🔍 Starting scan at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
        pairs_with_signal = 0
        
        try:
            print("\nScanning Gate.io USDT pairs for crossover signals...", flush=True)
            
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
            
            for idx, coin in enumerate(coins, 1):
                symbol = f"{coin}_USDT"
                print(f"\rProcessing {idx}/{len(coins)}: {symbol}", end='', flush=True)
                
                try:
                    portfolio_value, coin_balance = self.check_coin_balance(symbol)
                    
                    candles = self.get_candlesticks(symbol)
                    if not candles:
                        continue
                    
                    df = pd.DataFrame(candles, columns=[
                        'timestamp', 'volume', 'close', 'high', 
                        'low', 'open', 'amount', 'count'
                    ])
                    
                    # Convert prices to numeric
                    for col in ['close', 'high', 'low']:
                        df[col] = pd.to_numeric(df[col], errors='coerce')
                    df = df.dropna()
                    
                    if len(df) < 100:
                        continue
                    
                    # Get current trend and bands
                    closes = df['close'].values
                    current_direction, upper_bands, lower_bands = self.lrc.calculate(closes)
                    
                    if current_direction is None:
                        continue
                        
                    # Check for buy/sell signals
                    buy_signal, sell_signal = self.check_crossover_conditions(
                        df, current_direction, upper_bands, lower_bands
                    )
                    
                    current_price = float(df['close'].iloc[-1])
                    
                    # Handle sell signal
                    if sell_signal and portfolio_value > 0:
                        print(f"\n\n📉 Sell Signal Detected: {symbol}", flush=True)
                        print(f"💰 Current Value: ${portfolio_value:.2f} USDT", flush=True)
                        print(f"📊 Current Balance: {coin_balance} {coin}", flush=True)
                        print(f"📊 Current Price: {current_price:.8f} USDT", flush=True)
                        
                        if self.place_spot_sell_order(symbol, coin_balance):
                            print(f"✅ Successfully sold {coin_balance} {coin}", flush=True)
                        continue
                    
                    # Handle buy signal
                    if buy_signal:
                        if portfolio_value >= 5:
                            print(f"\n⚠️ {symbol} skipped: Portfolio value (${portfolio_value:.2f}) >= $5.00", flush=True)
                            continue
                            
                        if not self.check_24h_volume(df):
                            print(f"\n⚠️ {symbol} skipped: 24h volume < $10,000 USDT", flush=True)
                            continue
                            
                        pairs_with_signal += 1
                        
                        print(f"\n\n🚨 Buy Signal Found: {symbol}", flush=True)
                        print(f"📈 Current Price: {current_price:.8f} USDT", flush=True)
                        print(f"📊 Upper Band: {upper_bands[-1]:.8f}", flush=True)
                        print(f"📊 Lower Band: {lower_bands[-1]:.8f}", flush=True)
                        
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

    def place_spot_order(self, symbol):
        # Order placement remains the same
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
        # Sell order placement remains the same
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
        # Volume checking remains the same
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
