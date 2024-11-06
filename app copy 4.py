import random
import requests
import pandas as pd
import time
import hmac
import hashlib
import json
from datetime import datetime
from gate_api import ApiClient, Configuration, Order, SpotApi
from gate_api.exceptions import ApiException, GateApiException

# API Credentials
API_KEY = "c84d3616806f44e5651912c198094a1b"
API_SECRET = "32ebfc90ac917be0911561c09da2b6dea9adafc9a4c0587c375645073be2e506"

# Custom exception for insufficient balance
class InsufficientBalanceError(Exception):
    pass

class GateioTrader:
    def __init__(self):
        self.base_url = "https://api.gateio.ws/api/v4"
        self.headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        self.request_count = 0
        self.last_request_time = time.time()
        self.rate_limit = 300  # requests per minute
        
        # Initialize gate-api client
        config = Configuration(key=API_KEY, secret=API_SECRET)
        client = ApiClient(config)
        self.spot_api = SpotApi(client)
        
    def _rate_limit_check(self):
        """Implement rate limiting"""
        current_time = time.time()
        time_passed = current_time - self.last_request_time
        
        if time_passed < 60:  # Within a minute window
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

    def check_24h_volume(self, df):
        """
        Check if the last 24 timeframes have total volume greater than $10,000 USDT
        """
        try:
            if len(df) < 24:
                return False
            
            # Get last 24 candles
            last_24_candles = df.tail(24)
            
            # Calculate volume in USDT (volume * close price)
            volume_usdt = sum(float(row['volume']) * float(row['close']) for _, row in last_24_candles.iterrows())
            
            print(f"📊 24h Volume in USDT: ${volume_usdt:,.2f}", flush=True)
            
            return volume_usdt > 10000
            
        except Exception as e:
            print(f"Error checking 24h volume: {str(e)}", flush=True)
            return False

    def check_coin_balance(self, symbol):
        """Check if already have this coin and get current value in USDT"""
        try:
            coin = symbol.split('_')[0]  # Get coin from pair (e.g., BTC from BTC_USDT)
            
            # Get balance
            balances = self.spot_api.list_spot_accounts(currency=coin)
            
            if not balances or len(balances) == 0:
                return 0
                
            # Get current price
            tickers = self.spot_api.list_tickers(currency_pair=symbol)
            if not tickers or not tickers[0].last:
                return 0
                
            current_price = float(tickers[0].last)
            balance = float(balances[0].available)
            
            # Calculate current value in USDT
            current_value = balance * current_price
            
            return current_value
            
        except Exception as e:
            print(f"Error checking {symbol} balance: {str(e)}", flush=True)
            return 0

    def get_candlesticks(self, symbol, interval='1h', limit=144):
        """Get candlestick data for a trading pair"""
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
        """Place a spot market buy order using gate-api"""
        try:                        
            # Create market buy order $20
            order = Order(
                currency_pair=symbol,
                side='buy',
                amount=20,
                type='market',
                time_in_force='ioc'  # Immediate or Cancel for market orders
            )
            
            # Place order
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
                print("\n💡 Insufficient balance detected. Ending current scan round.", flush=True)
                print("⏰ Waiting for next hour...", flush=True)
                raise InsufficientBalanceError("Not enough balance")
            return False
        except Exception as e:
            print(f"\n❌ Error placing order for {symbol}: {str(e)}", flush=True)
            if "Not enough balance" in str(e):
                print("\n💡 Insufficient balance detected. Ending current scan round.", flush=True)
                print("⏰ Waiting for next hour...", flush=True)
                raise InsufficientBalanceError("Not enough balance")
            return False

    def place_spot_sell_order(self, symbol, amount):
        """Place a spot market sell order using gate-api"""
        try:
            # Create market sell order
            order = Order(
                currency_pair=symbol,
                side='sell',
                amount=str(amount),
                type='market',
                time_in_force='ioc'
            )
            
            # Place order
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
        """Check portfolio and sell coins with value over threshold"""
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
        """Scan for volume spikes and place orders"""
        print(f"\n🔍 Starting scan at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
        pairs_with_signal = 0
        
        try:
            # First, check portfolio and sell coins over $200
            self.check_and_sell_portfolio(threshold=200)
            
            print("\nScanning Gate.io USDT pairs for volume spikes...", flush=True)
            
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
                    
                    # Convert columns to numeric
                    df['amount'] = pd.to_numeric(df['amount'], errors='coerce')
                    df['close'] = pd.to_numeric(df['close'], errors='coerce')
                    df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
                    df['open'] = pd.to_numeric(df['open'], errors='coerce')
                    df = df.dropna(subset=['amount', 'close', 'volume', 'open'])
                    
                    if len(df) < 144:
                        continue
                    
                    # Calculate buy volume moving average
                    ma_144 = df['amount'].rolling(window=144).mean()
                    current_buy_volume = float(df['amount'].iloc[-1])
                    avg_buy_volume = float(ma_144.iloc[-1])
                    
                    if pd.isna(avg_buy_volume) or avg_buy_volume == 0:
                        continue
                    
                    # Calculate buy volume increase
                    volume_increase = ((current_buy_volume - avg_buy_volume) / avg_buy_volume) * 100
                    
                    if volume_increase > 500:  # Buy volume increased by more than 500%
                        try:
                            price_change = ((float(df['close'].iloc[-1]) - float(df['open'].iloc[-1])) / 
                                          float(df['open'].iloc[-1])) * 100
                        except (ValueError, ZeroDivisionError):
                            price_change = 0
                        
                        current_price = float(df['close'].iloc[-1])
                        
                        if current_buy_volume > avg_buy_volume:
                            # Check 24h volume requirement
                            if not self.check_24h_volume(df):
                                print(f"\n⚠️ {symbol} skipped: 24h volume < $10,000 USDT", flush=True)
                                continue
                                
                            pairs_with_signal += 1
                            
                            print(f"\n\n🚨 Buy Volume Spike Found: {symbol}", flush=True)
                            print(f"💹 Buy Volume Increase: {volume_increase:.2f}%", flush=True)
                            print(f"📈 Price Change: {price_change:.2f}%", flush=True)
                            print(f"💰 Price: {current_price:.8f} USDT", flush=True)
                            print(f"💼 Portfolio Value: ${portfolio_value:.2f} USDT", flush=True)
                            print(f"🛒 Current Buy Volume: {current_buy_volume:.2f}", flush=True)
                            print(f"📈 Average Buy Volume (144h): {avg_buy_volume:.2f}", flush=True)
                            
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
    print("🤖 Gate.io Volume Scanner Bot Starting...", flush=True)
    trader = GateioTrader()
    trader.scan_and_trade() 
    
    while True:
        if datetime.now().minute == 0:
            trader.scan_and_trade()
            time.sleep(55)
        time.sleep(10)

if __name__ == "__main__":
    main()