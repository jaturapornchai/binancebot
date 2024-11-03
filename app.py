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
                print(f"Rate limit reached, sleeping for {sleep_time:.2f} seconds")
                time.sleep(sleep_time)
                self.request_count = 0
                self.last_request_time = time.time()
        else:
            self.request_count = 0
            self.last_request_time = current_time
            
        self.request_count += 1

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
            return True
            
        except GateApiException as ex:
            print(f"\n❌ Gate.io API Error for {symbol}:")
            print(f"Label: {ex.label}")
            print(f"Message: {ex.message}")
            # Check for both types of balance error messages
            if "Insufficient balance" in ex.message or "Not enough balance" in ex.message:
                print("\n💡 Insufficient balance detected. Ending current scan round.")
                print("⏰ Waiting for next hour...")
                raise InsufficientBalanceError("Not enough balance")
            return False
        except ApiException as e:
            print(f"\n❌ API Error for {symbol}: {str(e)}")
            if "Not enough balance" in str(e):
                print("\n💡 Insufficient balance detected. Ending current scan round.")
                print("⏰ Waiting for next hour...")
                raise InsufficientBalanceError("Not enough balance")
            return False
        except Exception as e:
            print(f"\n❌ Error placing order for {symbol}: {str(e)}")
            if "Not enough balance" in str(e):
                print("\n💡 Insufficient balance detected. Ending current scan round.")
                print("⏰ Waiting for next hour...")
                raise InsufficientBalanceError("Not enough balance")
            return False

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

    def scan_and_trade(self):
        """Scan for volume spikes and place orders"""
        print(f"\n🔍 Starting scan at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        pairs_with_signal = 0
        
        try:
            print("\nScanning Gate.io USDT pairs for volume spikes...")
            
            # Get all trading pairs
            endpoint = f"{self.base_url}/spot/currency_pairs"
            response = requests.get(endpoint, headers=self.headers)
            if response.status_code != 200:
                print("Failed to fetch trading pairs")
                return
                
            pairs = response.json()
            
            # Extract base coins from USDT pairs and filter out numbers
            coins = []
            for pair in pairs:
                if pair['id'].endswith('_USDT'):
                    base_coin = pair['id'].split('_')[0]
                    if not any(c.isdigit() for c in base_coin):
                        coins.append(base_coin)
            
            # Randomly shuffle the coin list
            random.shuffle(coins)
            
            print(f"\nFound {len(coins)} valid coins")
            print("Coins have been randomly shuffled for processing")
            
            # Process each coin in random order
            for idx, coin in enumerate(coins, 1):
                symbol = f"{coin}_USDT"
                print(f"\rProcessing {idx}/{len(coins)}: {symbol}", end='', flush=True)
                
                try:
                    candles = self.get_candlesticks(symbol)
                    if not candles:
                        continue
                    
                    df = pd.DataFrame(candles, columns=[
                        'timestamp', 'volume', 'close', 'high', 
                        'low', 'open', 'amount', 'count'
                    ])
                    
                    df['volume'] = pd.to_numeric(df['volume'], errors='coerce')
                    df['close'] = pd.to_numeric(df['close'], errors='coerce')
                    df = df.dropna(subset=['volume', 'close'])
                    
                    if len(df) < 144:
                        continue
                    
                    # Calculate 24h volume in USDT
                    df['volume_usdt'] = df['volume'] * df['close']
                    volume_24h_usdt = float(df['volume_usdt'].tail(24).sum())
                    
                    # Skip if 24h volume is less than $100,000
                    if volume_24h_usdt < 100000:
                        continue
                    
                    ma_144 = df['volume'].rolling(window=144).mean()
                    current_volume = float(df['volume'].iloc[-1])
                    avg_volume = float(ma_144.iloc[-1])
                    
                    if pd.isna(avg_volume) or avg_volume == 0:
                        continue
                    
                    volume_increase = ((current_volume - avg_volume) / avg_volume) * 100
                    
                    if volume_increase > 100:  
                        df['open'] = pd.to_numeric(df['open'], errors='coerce')
                        
                        try:
                            price_change = ((float(df['close'].iloc[-1]) - float(df['open'].iloc[-1])) / 
                                          float(df['open'].iloc[-1])) * 100
                        except (ValueError, ZeroDivisionError):
                            price_change = 0
                        
                        current_price = float(df['close'].iloc[-1])
                        
                        if current_volume > avg_volume:
                            pairs_with_signal += 1
                            
                            print(f"\n\n🚨 Volume Spike Found: {symbol}")
                            print(f"💹 Volume Increase: {volume_increase:.2f}%")
                            print(f"📈 Price Change: {price_change:.2f}%")
                            print(f"💰 Price: {current_price:.8f} USDT")
                            print(f"📊 24h Volume: ${volume_24h_usdt:,.2f} USDT")
                            
                            self.place_spot_order(symbol)
                            print("-" * 80)
                
                except InsufficientBalanceError:
                    print("\n⏰ Waiting for next hour due to insufficient balance...")
                    return
                except Exception as e:
                    continue
                
                time.sleep(0.1)
            
            print(f"\n\n✨ Scan completed. Found {pairs_with_signal} pairs with signals.")
            
        except Exception as e:
            print(f"\nAn error occurred during scan: {str(e)}")

def main():
    print("🤖 Gate.io Volume Scanner Bot Starting...")
    trader = GateioTrader()
    
    # Run first scan
    trader.scan_and_trade()
    
    print("\n⏰ Waiting for the first minute of next hour...")
    
    while True:
        if datetime.now().minute == 0:
            trader.scan_and_trade()
            time.sleep(55)
        time.sleep(1)

if __name__ == "__main__":
    main()